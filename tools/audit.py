#!/usr/bin/env python3
"""Capture an accessibility session per screen and run deterministic rules over it.

  audit.py capture <screen> [--out audits] [--serial SERIAL]
      Clears logcat, dumps the node tree, takes a screenshot, waits while you walk the
      screen with TalkBack, then saves session.txt + screen.png and runs `rules`.

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
from collections import defaultdict
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
SYSTEM_PACKAGES = {"com.android.systemui", "android"}

SEVERITY = {
    "NO_LABEL": "high",
    "SILENT_FOCUS": "high",
    "LABEL_IN_CHILD": "medium",
    "EDIT_NO_HINT": "medium",
    "SMALL_TARGET": "medium",
    "NO_HEADING": "medium",
    "DUPLICATE_LABEL": "medium",
    "REPEATED_ROLE": "low",
    "ORDER_JUMP": "low",
}

RECORD = re.compile(r"^\[(\w+)\] t=(\d+) ?(.*)$")
TOKEN = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)|(\S+)')
BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


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


def parse_session(path):
    records = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = RECORD.match(line)
        if not m:
            continue
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
        records.append(record)
    return records


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


def finding(rule, source, node=None, detail=None, t=None):
    return {
        "rule": rule,
        "severity": SEVERITY[rule],
        "source": source,
        "t": t,
        "node": {k: node[k] for k in ("id", "class", "text", "desc", "bounds", "size") if k in node} if node else None,
        "detail": detail,
    }


def repeats_role(utterance):
    """TalkBack appends the role as the last segment ("…, Button") in the device's language.
    If that single word already appears earlier ("Add button, Button"), the label repeats the role."""
    *rest, last = [part.strip() for part in utterance.split(",")]
    if not rest or not re.fullmatch(r"\w+", last):
        return False
    return re.search(rf"\b{re.escape(last)}\b", ", ".join(rest), re.IGNORECASE) is not None


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


def run_rules(records):
    tree = [r for r in records if r["kind"] == "tree" and "marker" not in r]
    tree_pkg = next((r["marker"].split("pkg=", 1)[1] for r in records
                     if r["kind"] == "tree" and r.get("marker", "").startswith("begin pkg=")), None)
    all_focuses = [r for r in records if r["kind"] == "focus"]
    focuses = [r for r in all_focuses if r.get("pkg") not in SYSTEM_PACKAGES]
    speeches = [r for r in records if r["kind"] == "speech"]
    findings, seen = [], set()

    # Node-level issues the APK already flagged, deduplicated between tree and focus records.
    for source, nodes in (("tree", tree), ("focus", focuses)):
        for node in nodes:
            for issue in node["issues"]:
                key = (issue, node.get("id"), str(node.get("bounds")))
                if issue in SEVERITY and key not in seen:
                    seen.add(key)
                    findings.append(finding(issue, source, node, t=node["t"]))

    # System UI focuses stay in the timeline: they delimit what the app's last focus said.
    timeline = build_timeline(all_focuses, speeches)
    for i, entry in enumerate(timeline):
        focus = entry["focus"]
        if focus is None or focus.get("pkg") in SYSTEM_PACKAGES:
            continue
        next_t = timeline[i + 1]["t"] if i + 1 < len(timeline) else None
        lingered = next_t is None or next_t - focus["t"] >= SILENT_FOCUS_MS
        if lingered and not any(s.strip() for s in entry["speech"]):
            findings.append(finding("SILENT_FOCUS", "speech", focus, "focus with no speech", focus["t"]))
    for speech in speeches:
        if repeats_role(speech["text"]):
            findings.append(finding("REPEATED_ROLE", "speech", detail=speech["text"], t=speech["t"]))

    px_per_dp = density(tree + focuses)
    if px_per_dp:
        for prev, cur in zip(focuses, focuses[1:]):
            same_pkg = prev.get("pkg") == cur.get("pkg")
            if same_pkg and isinstance(prev.get("bounds"), list) and isinstance(cur.get("bounds"), list):
                jump_dp = (prev["bounds"][1] - cur["bounds"][1]) / px_per_dp
                if jump_dp > ORDER_JUMP_DP:
                    findings.append(finding(
                        "ORDER_JUMP", "focus", cur,
                        f"focus moved up {round(jump_dp)}dp after {label(prev) or prev.get('id')!r}; "
                        "check it was not a backwards swipe or a scroll",
                        cur["t"],
                    ))

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

    findings.sort(key=lambda f: ("high", "medium", "low").index(f["severity"]))
    summary = defaultdict(int)
    for f in findings:
        summary[f["rule"]] += 1
    return {
        "package": tree_pkg,
        "summary": dict(summary),
        "findings": findings,
        "timeline": timeline,
        "tree": tree,
    }


# --- commands ------------------------------------------------------------------------------

def adb(serial, *args, binary=False):
    cmd = ["adb"] + (["-s", serial] if serial else []) + list(args)
    result = subprocess.run(cmd, capture_output=True, check=True)
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


def capture(args):
    warn_if_not_ready(args.serial)
    folder = output_dir(args.out, args.screen)
    adb(args.serial, "logcat", "-c")
    adb(args.serial, "shell", "am", "broadcast", "-a", DUMP_ACTION)
    (folder / "screen.png").write_bytes(adb(args.serial, "exec-out", "screencap", "-p", binary=True))
    input(f"Walk '{args.screen}' with TalkBack, then press Enter to save… ")
    session = adb(args.serial, "logcat", "-d", "-s", f"{LOG_TAG}:I", "-v", "raw")
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
