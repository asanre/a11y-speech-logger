#!/usr/bin/env python3
"""Capture an accessibility session per screen and run deterministic rules over it.

  audit.py capture <screen> [--out audits] [--serial SERIAL]
      Clears logcat, dumps the node tree and takes a screenshot (screen-start.png), shows
      focus and speech live while you walk the screen with TalkBack, dumps and screenshots
      again when you press Enter (screen-end.png), then saves session.txt and runs `rules`.

  audit.py rules <dir>
      Parses <dir>/session.txt and writes <dir>/findings.json.

Only needs Python 3 and adb. The log format is described in the README.
"""

import argparse
import datetime
import json
import re
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path

PACKAGE = "io.github.asanre.a11ylogger"
DUMP_ACTION = f"{PACKAGE}.DUMP"
FOCUS_LOGGER = f"{PACKAGE}/.FocusLoggerService"
LOG_TAG = "A11ySpeech"

# Focus followed by no speech for this long means TalkBack said nothing for it, not that the
# user swiped on before it could speak.
SILENT_FOCUS_MS = 1500
# An upward jump bigger than this between consecutive focuses suggests a reading-order problem.
ORDER_JUMP_DP = 48
# Longer than this, an utterance is a block the user can only stop by interrupting TalkBack.
LONG_SPEECH_CHARS = 300

# The WCAG 2.2 success criteria the rules refer to: number -> (name, level).
WCAG = {
    "1.1.1": ("Non-text Content", "A"),
    "1.3.1": ("Info and Relationships", "A"),
    "1.3.2": ("Meaningful Sequence", "A"),
    "2.4.2": ("Page Titled", "A"),
    "2.4.3": ("Focus Order", "A"),
    "2.4.4": ("Link Purpose (In Context)", "A"),
    "2.4.6": ("Headings and Labels", "AA"),
    "2.5.3": ("Label in Name", "A"),
    "2.5.8": ("Target Size (Minimum)", "AA"),
    "3.3.2": ("Labels or Instructions", "A"),
    "4.1.2": ("Name, Role, Value", "A"),
}

# conformance: "failure" breaks the criterion as written; "advisory" is a platform guideline, a best
# practice or a hint that needs checking. Criteria are empty when the rule is best practice only.
RULES = {
    "NO_LABEL": {"severity": "high", "wcag": ["4.1.2", "1.1.1"], "conformance": "failure"},
    "SILENT_FOCUS": {"severity": "high", "wcag": ["4.1.2"], "conformance": "failure"},
    "EDIT_NO_HINT": {"severity": "medium", "wcag": ["3.3.2", "4.1.2"], "conformance": "failure"},
    # Advisory between 24dp and 48dp (Android's guideline), a failure below 24dp: see target_conformance.
    "SMALL_TARGET": {"severity": "medium", "wcag": ["2.5.8"], "conformance": "advisory"},
    "NO_HEADING": {"severity": "medium", "wcag": ["1.3.1", "2.4.6"], "conformance": "advisory"},
    "DUPLICATE_LABEL": {"severity": "medium", "wcag": ["2.4.6", "2.4.4"], "conformance": "advisory"},
    "ROLE_BEFORE_LABEL": {"severity": "medium", "wcag": ["4.1.2", "2.5.3"], "conformance": "advisory"},
    "LABEL_IN_CHILD": {"severity": "low", "wcag": ["4.1.2"], "conformance": "advisory"},
    "REPEATED_ROLE": {"severity": "low", "wcag": [], "conformance": "advisory"},
    "LONG_SPEECH": {"severity": "low", "wcag": [], "conformance": "advisory"},
    "ORDER_JUMP": {"severity": "low", "wcag": ["1.3.2", "2.4.3"], "conformance": "advisory"},
    "NO_ROLE": {"severity": "medium", "wcag": ["4.1.2"], "conformance": "failure"},
    "CONFLICTING_STATE": {"severity": "medium", "wcag": ["4.1.2"], "conformance": "failure"},
    "RAW_TEXT_SPOKEN": {"severity": "high", "wcag": ["1.1.1", "4.1.2"], "conformance": "failure"},
    "NESTED_ACTIONABLE": {"severity": "medium", "wcag": ["4.1.2", "2.4.3"], "conformance": "advisory"},
    "LIST_SEMANTICS": {"severity": "medium", "wcag": ["1.3.1"], "conformance": "advisory"},
    "SCREEN_TITLE": {"severity": "medium", "wcag": ["2.4.2"], "conformance": "failure"},
    "FOCUS_MOVED_AFTER_ACTION": {"severity": "medium", "wcag": ["2.4.3"], "conformance": "advisory"},
}

# Classes a clickable node gets when nothing sets its role: Compose's default, plain Views and layouts.
GENERIC_CLASSES = {"View", "ViewGroup", "TextView", "ImageView"}
# Markup or a resource key read out instead of text: `<br>`, `&nbsp;`, `accessibility.loading.text`.
RAW_MARKUP = re.compile(r"</?[A-Za-z][^>]*>|&(?:nbsp|amp|lt|gt|quot|apos|#\d+);")
RESOURCE_KEY = re.compile(r"\b[a-z][a-z0-9_]*(?:\.[a-z0-9_]+){2,}\b")
TOP_LEVEL_DOMAINS = {"com", "org", "net", "io", "dev", "app", "edu", "gov", "co", "uk", "es", "de", "fr", "it"}

# Focus that moves this soon after an activation was moved by the app, not by a swipe.
FOCUS_AFTER_ACTION_MS = 1000

# WCAG 2.5.8 asks for 24x24 CSS px; Android's guideline is 48dp. One dp is one CSS px.
WCAG_TARGET_DP = 24

RECORD = re.compile(r"^\[(\w+)\] t=(\d+) ?(.*)$")
TOKEN = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)|(\S+)')
BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
TREE_DONE = re.compile(r"^\[tree\] t=\d+ (end nodes=|no active window)", re.MULTILINE)


# --- parsing -------------------------------------------------------------------------------

def unquote(value):
    if not (value.startswith('"') and value.endswith('"')):
        return value
    out, chars = [], iter(value[1:-1])
    for c in chars:
        if c == "\\":
            nxt = next(chars, "")
            out.append("\n" if nxt == "n" else nxt)
        else:
            out.append(c)
    return "".join(out)


def parse_fields(text):
    """`key=value` pairs plus bare flags (`heading`, `clickable`, `FOCUSED`…)."""
    fields, flags = {}, []
    for key, value, flag in TOKEN.findall(text):
        if key:
            fields[key] = unquote(value)
        else:
            flags.append(flag)
    fields["flags"] = flags
    fields["issues"] = fields["issues"].split(",") if "issues" in fields else []
    if m := BOUNDS.fullmatch(fields.get("bounds", "")):
        fields["bounds"] = [int(v) for v in m.groups()]
    return fields


def parse_record(line):
    m = RECORD.match(line)
    if not m:
        return None
    kind, t, rest = m.group(1), int(m.group(2)), m.group(3)
    record = {"kind": kind, "t": t}
    if kind == "speech":
        record["text"] = unquote(rest.strip())
    elif kind == "tree":
        stripped = rest.lstrip(" ")
        if stripped.startswith(("begin", "end", "no active window")):
            record["marker"] = stripped
        else:
            record["depth"] = (len(rest) - len(stripped)) // 2
            record.update(parse_fields(stripped))
    else:
        record.update(parse_fields(rest))
    return record


def parse_session(path):
    records = (parse_record(line) for line in Path(path).read_text(encoding="utf-8").splitlines())
    return [r for r in records if r]


# --- rules ---------------------------------------------------------------------------------

def label(node):
    return (node.get("text") or node.get("desc") or "").strip()


def actionable(node):
    return "clickable" in node["flags"] or "longclickable" in node["flags"]


def density(nodes):
    for node in nodes:
        size, bounds = node.get("size", ""), node.get("bounds")
        if m := re.fullmatch(r"(\d+)x(\d+)dp", size):
            if isinstance(bounds, list) and int(m.group(1)) > 0:
                return (bounds[2] - bounds[0]) / int(m.group(1))
    return None


def finding(rule, source, node=None, detail=None, t=None, conformance=None):
    return {
        "rule": rule,
        "severity": RULES[rule]["severity"],
        "wcag": RULES[rule]["wcag"],
        "conformance": conformance or RULES[rule]["conformance"],
        "source": source,
        "t": t,
        "node": {k: node[k] for k in ("id", "class", "text", "desc", "bounds", "size") if k in node} if node else None,
        "detail": detail,
    }


def target_conformance(node):
    """Below 24dp on one side fails WCAG 2.5.8; between 24dp and 48dp only misses Android's guideline."""
    m = re.fullmatch(r"(\d+)x(\d+)dp", node.get("size", ""))
    return "failure" if m and min(int(m.group(1)), int(m.group(2))) < WCAG_TARGET_DP else "advisory"


def element_key(node):
    """The same element across dumps and focuses: its id, or its bounds when it has none."""
    return node.get("id") if node.get("id") not in (None, "-") else str(node.get("bounds"))


def trailing_role(utterance):
    """TalkBack appends the role as the last segment ("…, Button") in the device's language.
    Returns that single word, or None when the utterance doesn't end like that."""
    *rest, last = [part.strip() for part in utterance.split(",")]
    return last if rest and re.fullmatch(r"[^\W\d_]+", last) else None


def repeats_role(utterance):
    """The role word already appears in the label ("Add button, Button")."""
    role = trailing_role(utterance)
    rest = utterance.rsplit(",", 1)[0]
    return role is not None and re.search(rf"\b{re.escape(role)}\b", rest, re.IGNORECASE) is not None


def leading_role(utterance, roles):
    """The utterance starts with a role word that the session shows trailing elsewhere ("Button, Stop"):
    TalkBack found no name on the node and read a descendant's description as secondary content."""
    first, *rest = [part.strip() for part in utterance.split(",")]
    return any(rest) and first.casefold() in roles


def lacks_role(node):
    cls = node.get("class") or ""
    return "clickable" in node["flags"] and "role" not in node and (cls in GENERIC_CLASSES or cls.endswith("Layout"))


def has_conflicting_state(node):
    """Checkable and selected at once: TalkBack reads both, e.g. a tab built on a toggle ("checked, selected")."""
    return "checked" in node and "selected" in node["flags"]


def raw_text(text):
    """The markup or resource key found in the text, or None."""
    if m := RAW_MARKUP.search(text):
        return m.group(0)
    for m in RESOURCE_KEY.finditer(text):
        if m.group(0).rsplit(".", 1)[1] not in TOP_LEVEL_DOMAINS:
            return m.group(0)
    return None


def normalized(text):
    return " ".join(text.split()).casefold()


def was_spoken(text, spoken):
    """Whether TalkBack said the text, allowing for a different prefix or line breaks: some fragment
    (a line or what follows a "Sender:" prefix) of at least 12 characters starts in the speech."""
    fragments = [normalized(f) for f in re.split(r"[\n:]", text)]
    long_ones = [f for f in fragments if len(f) >= 12]
    return any(f[:40] in spoken for f in long_ones) if long_ones else normalized(text) in spoken


def descendants(tree, i):
    """The nodes dumped inside tree[i], in tree order."""
    for other in tree[i + 1:]:
        if other["depth"] <= tree[i]["depth"]:
            break
        yield other


def nested_actionables(tree):
    """Each clickable node with the clickable nodes inside it: the inner ones are controls of their own."""
    for i, node in enumerate(tree):
        if "clickable" in node["flags"]:
            inner = [other for other in descendants(tree, i) if "clickable" in other["flags"]]
            if inner:
                yield node, inner


def role_in_descendant(tree, node, speech, roles):
    """Where the role of a clickable node without one lives, or None if nowhere.

    A Compose node that has children of its own keeps the role out of its class and puts it on a child
    node that only carries the role; TalkBack reads that child as content ("Button, Stop")."""
    if node in tree:
        i = tree.index(node)
        for other in descendants(tree, i):
            if "clickable" not in other["flags"] and (other.get("role") or other.get("class") not in GENERIC_CLASSES):
                return other.get("role") or other.get("class")
    for text in reversed(speech):
        for part in text.split(","):
            if part.strip().casefold() in roles:
                return part.strip()
    return None


def build_timeline(focuses, speeches):
    """Each focus owns the utterances spoken before the next focus. Approximate when swiping fast."""
    timeline = []
    for i, focus in enumerate(focuses):
        until = focuses[i + 1]["t"] if i + 1 < len(focuses) else float("inf")
        spoken = [s for s in speeches if focus["t"] <= s["t"] < until]
        timeline.append({"t": focus["t"], "focus": focus, "speech": [s["text"] for s in spoken]})
    first = focuses[0]["t"] if focuses else float("inf")
    orphans = [s["text"] for s in speeches if s["t"] < first]
    if orphans:
        timeline.insert(0, {"t": None, "focus": None, "speech": orphans})
    return timeline


def dumps(records):
    """Each `[tree]` dump as (fields of its begin marker, nodes), in log order."""
    result, current = [], None
    for r in records:
        if r["kind"] != "tree":
            continue
        marker = r.get("marker", "")
        if marker.startswith("begin"):
            current = (parse_fields(marker[len("begin"):]), [])
            result.append(current)
        elif marker:
            current = None
        elif current is not None:
            current[1].append(r)
    return result


def list_problems(tree):
    """Collections whose items don't match what they declare. Scrollable ones are skipped: a lazy list
    declares every item but only the visible ones are in the tree."""
    for i, node in enumerate(tree):
        m = re.fullmatch(r"(-?\d+)x(-?\d+)", node.get("collection", ""))
        if not m or "scrollable" in node["flags"]:
            continue
        rows, cols = int(m.group(1)), int(m.group(2))
        inside = list(descendants(tree, i))
        items = [n for n in inside if "item" in n]
        loose = [n for n in inside if "clickable" in n["flags"] and "item" not in n]
        problems = []
        if min(rows, cols) == 1 and rows * cols != len(items):
            problems.append(f"declares {rows * cols} items, {len(items)} carry item info")
        if loose and items:
            problems.append(f"{len(loose)} clickable inside without item info: " + ", ".join(repr(label(n) or n.get("id")) for n in loose))
        elif loose:
            problems.append(f"no child carries item info ({len(loose)} clickable inside)")
        if problems:
            yield node, "; ".join(problems)


def focus_moves_after_action(records, app_pkg):
    """Each activation in the app followed within FOCUS_AFTER_ACTION_MS by focus on another element,
    with no window change in between (a new screen or dialog takes focus legitimately)."""
    for i, r in enumerate(records):
        if r["kind"] != "click" or r.get("pkg") != app_pkg:
            continue
        for later in records[i + 1:]:
            if later["t"] - r["t"] > FOCUS_AFTER_ACTION_MS or later["kind"] in ("window", "click"):
                break
            if later["kind"] == "focus":
                if element_key(later) != element_key(r):
                    yield r, later
                break


def run_rules(records):
    all_dumps = dumps(records)
    first_dump, last_dump = (all_dumps[0], all_dumps[-1]) if all_dumps else (({}, []), ({}, []))
    tree, tree_pkg = last_dump[1], last_dump[0].get("pkg")
    all_focuses = [r for r in records if r["kind"] == "focus"]
    # The audited app is the dumped one; without a dump, the most focused package. Everything else
    # (keyboard, system UI) only delimits the timeline.
    focused_pkgs = Counter(r.get("pkg") for r in all_focuses if r.get("pkg") not in (None, "null"))
    app_pkg = tree_pkg or next(iter(focused_pkgs.most_common(1)), (None,))[0]
    focuses = [r for r in all_focuses if r.get("pkg") == app_pkg]
    speeches = [r for r in records if r["kind"] == "speech"]
    findings, seen = [], set()

    # Node-level issues the APK already flagged, deduplicated between tree and focus records.
    for source, nodes in (("tree", tree), ("focus", focuses)):
        for node in nodes:
            for issue in node["issues"]:
                key = (issue, node.get("id"), str(node.get("bounds")))
                if issue in RULES and key not in seen:
                    seen.add(key)
                    conformance = target_conformance(node) if issue == "SMALL_TARGET" else None
                    findings.append(finding(issue, source, node, t=node["t"], conformance=conformance))

    # Node rules over the fields already logged, so they also run on older captures.
    for source, nodes in (("tree", tree), ("focus", focuses)):
        for node in nodes:
            key = ("CONFLICTING_STATE", node.get("id"), str(node.get("bounds")))
            if has_conflicting_state(node) and key not in seen:
                seen.add(key)
                findings.append(finding("CONFLICTING_STATE", source, node, t=node["t"]))
    for node in tree:
        for value in (node.get("text"), node.get("desc")):
            if value and (raw := raw_text(value)) and ("RAW_TEXT_SPOKEN", value) not in seen:
                seen.add(("RAW_TEXT_SPOKEN", value))
                findings.append(finding("RAW_TEXT_SPOKEN", "tree", node, f"{raw!r} in {value[:80]!r}", node["t"]))
    for node, inner in nested_actionables(tree):
        names = ", ".join(repr(label(n) or n.get("id")) for n in inner)
        findings.append(finding("NESTED_ACTIONABLE", "tree", node, f"{len(inner)} clickable inside: {names}", node["t"]))

    # Other packages' focuses stay in the timeline: they delimit what the app's last focus said.
    timeline = build_timeline(all_focuses, speeches)
    roles = {role.casefold() for s in speeches if (role := trailing_role(s["text"]))}
    for i, entry in enumerate(timeline):
        focus = entry["focus"]
        if focus is not None and focus.get("pkg") != app_pkg:
            continue
        t = entry["t"]
        for text in entry["speech"]:
            if repeats_role(text):
                findings.append(finding("REPEATED_ROLE", "speech", focus, text, t))
            if leading_role(text, roles):
                findings.append(finding("ROLE_BEFORE_LABEL", "speech", focus, text, t))
            if (raw := raw_text(text)) and ("RAW_TEXT_SPOKEN", text) not in seen:
                seen.add(("RAW_TEXT_SPOKEN", text))
                findings.append(finding("RAW_TEXT_SPOKEN", "speech", focus, f"{raw!r} in {text[:80]!r}", t))
            if len(text) > LONG_SPEECH_CHARS:
                findings.append(finding("LONG_SPEECH", "speech", focus, f"{len(text)} chars: {text[:80]}…", t))
        if focus is None:
            continue
        next_t = timeline[i + 1]["t"] if i + 1 < len(timeline) else None
        lingered = next_t is None or next_t - focus["t"] >= SILENT_FOCUS_MS
        if lingered and not any(s.strip() for s in entry["speech"]):
            findings.append(finding("SILENT_FOCUS", "speech", focus, "focus with no speech", focus["t"]))

    # A focus owns what TalkBack said for it; a tree node owns the speech of a focus on the same element.
    speech_by_element = defaultdict(list)
    for entry in timeline:
        if entry["focus"] is not None:
            speech_by_element[element_key(entry["focus"])] += entry["speech"]
    # Any trailing segment of a few words can be a role ("Button", "Drop-down list") when it is read as content.
    role_phrases = roles | {
        last.strip().casefold() for s in speeches if "," in s["text"]
        for last in [s["text"].rsplit(",", 1)[1]] if re.fullmatch(r"[^\W\d_]+(?:[ -][^\W\d_]+){0,2}", last.strip())
    }
    for source, nodes in (("tree", tree), ("focus", focuses)):
        for node in nodes:
            element = element_key(node)
            if not lacks_role(node) or ("NO_ROLE", element) in seen:
                continue
            seen.add(("NO_ROLE", element))
            where = role_in_descendant(tree, node, speech_by_element[element], role_phrases)
            if where:
                detail = f"the role ({where!r}) is on a descendant, read as content, not on the actionable node"
                findings.append(finding("NO_ROLE", source, node, detail, node["t"], conformance="advisory"))
            else:
                findings.append(finding("NO_ROLE", source, node, "no role on the node or its descendants", node["t"]))

    px_per_dp = density(tree + focuses)
    if px_per_dp:
        # Consecutive in the whole sequence: a jump across the keyboard is not a reading-order jump.
        for prev, cur in zip(all_focuses, all_focuses[1:]):
            same_app = prev.get("pkg") == cur.get("pkg") == app_pkg
            if same_app and isinstance(prev.get("bounds"), list) and isinstance(cur.get("bounds"), list):
                jump_dp = (prev["bounds"][1] - cur["bounds"][1]) / px_per_dp
                if jump_dp > ORDER_JUMP_DP:
                    findings.append(finding(
                        "ORDER_JUMP", "focus", cur,
                        f"focus moved up {round(jump_dp)}dp after {label(prev) or prev.get('id')!r}; "
                        "check it was not a backwards swipe or a scroll",
                        cur["t"],
                    ))

    for node, detail in list_problems(tree):
        findings.append(finding("LIST_SEMANTICS", "tree", node, detail, node["t"]))

    for click, focus in focus_moves_after_action(records, app_pkg):
        jump = ""
        if isinstance(click.get("bounds"), list) and isinstance(focus.get("bounds"), list) and px_per_dp:
            jump = f", {round((click['bounds'][1] - focus['bounds'][1]) / px_per_dp)}dp above"
        findings.append(finding(
            "FOCUS_MOVED_AFTER_ACTION", "focus", focus,
            f"after activating {label(click) or click.get('id')!r}, focus moved to {label(focus) or focus.get('id')!r}{jump}",
            focus["t"],
        ))

    # Titles TalkBack can announce for the screen: the window's, the panes' and window-change texts.
    app_dumps = [(fields, nodes) for fields, nodes in all_dumps if fields.get("pkg") == app_pkg]
    titles = sorted(
        {fields["window"] for fields, _ in app_dumps if fields.get("window")}
        | {n["pane"] for _, nodes in app_dumps for n in nodes if n.get("pane")}
        | {r["text"] for r in records if r["kind"] == "window" and r.get("pkg") == app_pkg and r.get("text")}
    )
    if any("window" in fields for fields, _ in app_dumps) and not titles:
        findings.append(finding("SCREEN_TITLE", "tree", detail="no window title, pane title or window-change text"))

    # New text on screen that was never spoken or focused: a status message TalkBack may have missed.
    spoken = normalized(" ".join(r["text"] for r in records if r["kind"] in ("speech", "announce") and r.get("text")))
    focused = {label(f) for f in focuses}
    before = {label(n) for n in first_dump[1]} if first_dump is not last_dump else set()
    appeared = sorted({
        label(n) for n in tree
        if label(n) and label(n) not in before and label(n) not in focused and not was_spoken(label(n), spoken)
    }) if first_dump is not last_dump else []

    nodes = tree or focuses
    if nodes and not any("heading" in n["flags"] for n in nodes):
        findings.append(finding("NO_HEADING", "tree" if tree else "focus", detail="no node marked as heading"))

    by_label = defaultdict(list)
    for node in tree:
        if actionable(node) and label(node):
            by_label[label(node).casefold()].append(node)
    for nodes_with_label in by_label.values():
        if len(nodes_with_label) > 1:
            findings.append(finding(
                "DUPLICATE_LABEL", "tree", nodes_with_label[0],
                f"{len(nodes_with_label)} actionable elements share this label",
            ))

    findings.sort(key=lambda f: (("high", "medium", "low").index(f["severity"]), f["conformance"] != "failure"))
    summary = defaultdict(int)
    by_wcag = defaultdict(lambda: {"failure": 0, "advisory": 0})
    for f in findings:
        summary[f["rule"]] += 1
        for criterion in f["wcag"]:
            by_wcag[criterion][f["conformance"]] += 1
    return {
        "package": app_pkg,
        "summary": dict(summary),
        "summary_by_wcag": {
            c: {"name": WCAG[c][0], "level": WCAG[c][1], **counts} for c, counts in sorted(by_wcag.items())
        },
        "findings": findings,
        "titles": titles,
        "appeared": appeared,
        "timeline": timeline,
        "tree": tree,
    }


# --- commands ------------------------------------------------------------------------------

def adb_cmd(serial, *args):
    return ["adb"] + (["-s", serial] if serial else []) + list(args)


def adb(serial, *args, binary=False):
    result = subprocess.run(adb_cmd(serial, *args), capture_output=True, check=True)
    return result.stdout if binary else result.stdout.decode("utf-8", "replace")


def warn_if_not_ready(serial):
    engine = adb(serial, "shell", "settings", "get", "secure", "tts_default_synth").strip()
    services = adb(serial, "shell", "settings", "get", "secure", "enabled_accessibility_services")
    if engine != PACKAGE:
        print(f"warning: the default TTS engine is {engine!r}, so [speech] won't be captured", file=sys.stderr)
    if FOCUS_LOGGER not in services and f"{PACKAGE}/{PACKAGE}.FocusLoggerService" not in services:
        print("warning: A11y Focus Logger is not enabled, so [focus] and [tree] won't be captured", file=sys.stderr)


def output_dir(base, screen):
    folder = Path(base) / datetime.date.today().isoformat() / screen
    candidate, n = folder, 2
    while candidate.exists():
        candidate, n = folder.with_name(f"{screen}-{n}"), n + 1
    candidate.mkdir(parents=True)
    return candidate


def snapshot(serial, path):
    adb(serial, "shell", "am", "broadcast", "-a", DUMP_ACTION)
    path.write_bytes(adb(serial, "exec-out", "screencap", "-p", binary=True))


def live_line(record):
    """A short line per record to follow the walk; session.txt keeps the full records."""
    def quoted(text, limit=160):
        text = text if len(text) <= limit else text[:limit] + "…"
        return json.dumps(text, ensure_ascii=False)

    kind = record["kind"]
    if kind == "speech":
        return f"    {quoted(record['text'])}"
    if kind == "focus":
        name = quoted(label(record)) if label(record) else "(no label)"
        issues = f" [{','.join(record['issues'])}]" if record["issues"] else ""
        return f"→ {record.get('class')} {name}{issues}"
    if kind == "tree":
        marker = record.get("marker", "")
        return f"[tree] {marker.removeprefix('end ')}" if marker.startswith(("end", "no active")) else None
    return f"[{kind}] {quoted(record.get('text') or record.get('class') or '')}"


def follow(serial):
    """Prints the log as it is written, until the returned process is terminated."""
    proc = subprocess.Popen(adb_cmd(serial, "logcat", "-s", f"{LOG_TAG}:I", "-v", "raw"),
                            stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")

    def pump():
        for line in proc.stdout:
            record = parse_record(line.rstrip("\n"))
            if record and (shown := live_line(record)):
                print(shown, flush=True)

    threading.Thread(target=pump, daemon=True).start()
    return proc


def read_session(serial, dumps):
    """The dump is logged asynchronously by the service: wait until all of them are in the log."""
    for _ in range(20):
        session = adb(serial, "logcat", "-d", "-s", f"{LOG_TAG}:I", "-v", "raw")
        if len(TREE_DONE.findall(session)) >= dumps:
            break
        time.sleep(0.25)
    return session


def capture(args):
    warn_if_not_ready(args.serial)
    folder = output_dir(args.out, args.screen)
    adb(args.serial, "logcat", "-c")
    viewer = follow(args.serial)
    snapshot(args.serial, folder / "screen-start.png")
    print(f"Walk '{args.screen}' with TalkBack, then press Enter to save.\n")
    input()
    viewer.terminate()
    # Dumped again because the screen can change after the capture starts (a sheet opened, a scroll).
    snapshot(args.serial, folder / "screen-end.png")
    session = read_session(args.serial, dumps=2)
    (folder / "session.txt").write_text(session, encoding="utf-8")
    print(f"saved {folder}")
    rules(argparse.Namespace(dir=folder))


def rules(args):
    folder = Path(args.dir)
    result = run_rules(parse_session(folder / "session.txt"))
    (folder / "findings.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = ", ".join(f"{rule}={n}" for rule, n in result["summary"].items()) or "none"
    print(f"findings: {counts} -> {folder / 'findings.json'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(required=True)
    cap = sub.add_parser("capture", help="capture a screen and run the rules")
    cap.add_argument("screen", help="name for the screen, used as folder name")
    cap.add_argument("--out", default="audits", help="base folder (default: audits)")
    cap.add_argument("--serial", help="adb device serial, when more than one is connected")
    cap.set_defaults(func=capture)
    rul = sub.add_parser("rules", help="run the rules over a captured folder")
    rul.add_argument("dir", help="folder with session.txt")
    rul.set_defaults(func=rules)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
