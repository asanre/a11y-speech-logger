"""The rules over a TalkBack capture: findings by WCAG criterion, the timeline and the last tree."""

import re
from collections import Counter
from collections import defaultdict

from .contrast import read_png, text_contrast
from .records import dumps, label

# Focus followed by no speech for this long means TalkBack said nothing for it, not that the
# user swiped on before it could speak: speech starts within 1 s of the focus on real captures.
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
    "1.4.3": ("Contrast (Minimum)", "AA"),
    "1.4.4": ("Resize Text", "AA"),
    "1.4.11": ("Non-text Contrast", "AA"),
    "2.1.1": ("Keyboard", "A"),
    "2.1.2": ("No Keyboard Trap", "A"),
    "2.4.2": ("Page Titled", "A"),
    "2.4.3": ("Focus Order", "A"),
    "2.4.4": ("Link Purpose (In Context)", "A"),
    "2.4.6": ("Headings and Labels", "AA"),
    "2.4.7": ("Focus Visible", "AA"),
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
    # A failure below 3:1, which no text size passes; advisory up to 4.5:1, which large text passes.
    "TEXT_CONTRAST": {"severity": "medium", "wcag": ["1.4.3"], "conformance": "failure"},
    "FOCUS_NOT_VISIBLE": {"severity": "high", "wcag": ["2.4.7"], "conformance": "failure"},
    "KEYBOARD_UNREACHABLE": {"severity": "high", "wcag": ["2.1.1"], "conformance": "failure"},
    "STALE_FOCUS_INDICATOR": {"severity": "medium", "wcag": ["2.4.7"], "conformance": "failure"},
    "UNREACHABLE_ACTIONS": {"severity": "high", "wcag": ["4.1.2"], "conformance": "failure"},
    # Accessibility Test Framework checks, as `ATF:<check>`. The conformance is that of an ERROR; a WARNING,
    # which ATF gives when it can't be sure (unknown text size, a borderline value), is always advisory.
    "ATF:SpeakableTextPresentCheck": {"severity": "high", "wcag": ["4.1.2", "1.1.1"], "conformance": "failure"},
    "ATF:TextContrastCheck": {"severity": "medium", "wcag": ["1.4.3"], "conformance": "failure"},
    "ATF:ClickableSpanCheck": {"severity": "medium", "wcag": ["4.1.2", "2.1.1"], "conformance": "failure"},
    "ATF:TraversalOrderCheck": {"severity": "medium", "wcag": ["1.3.2", "2.4.3"], "conformance": "failure"},
    # Same split as SMALL_TARGET: see target_conformance.
    "ATF:TouchTargetSizeCheck": {"severity": "medium", "wcag": ["2.5.8"], "conformance": "advisory"},
    "ATF:ImageContrastCheck": {"severity": "medium", "wcag": ["1.4.11"], "conformance": "advisory"},
    "ATF:DuplicateSpeakableTextCheck": {"severity": "medium", "wcag": ["2.4.6"], "conformance": "advisory"},
    "ATF:DuplicateClickableBoundsCheck": {"severity": "medium", "wcag": ["4.1.2"], "conformance": "advisory"},
    "ATF:EditableContentDescCheck": {"severity": "medium", "wcag": ["4.1.2"], "conformance": "advisory"},
    "ATF:ClassNameCheck": {"severity": "low", "wcag": ["4.1.2"], "conformance": "advisory"},
    "ATF:TextSizeCheck": {"severity": "low", "wcag": ["1.4.4"], "conformance": "advisory"},
    "ATF:LinkPurposeUnclearCheck": {"severity": "low", "wcag": ["2.4.4"], "conformance": "advisory"},
    "ATF:RedundantDescriptionCheck": {"severity": "low", "wcag": [], "conformance": "advisory"},
}
# Our rules that look for what an ATF check does. Both are kept, the ours marked, until compared on real captures.
OVERLAPS = {
    "NO_LABEL": "ATF:SpeakableTextPresentCheck",
    "SMALL_TARGET": "ATF:TouchTargetSizeCheck",
    "DUPLICATE_LABEL": "ATF:DuplicateSpeakableTextCheck",
    "REPEATED_ROLE": "ATF:RedundantDescriptionCheck",
}
# Classes a clickable node gets when nothing sets its role: Compose's default, plain Views and layouts.
GENERIC_CLASSES = {"View", "ViewGroup", "TextView", "ImageView"}
# Markup or a resource key read out instead of text: `<br>`, `&nbsp;`, `accessibility.loading.text`.
RAW_MARKUP = re.compile(r"</?[A-Za-z][^>]*>|&(?:nbsp|amp|lt|gt|quot|apos|#\d+);")
RESOURCE_KEY = re.compile(r"\b[a-z][a-z0-9_]*(?:\.[a-z0-9_]+){2,}\b")
TOP_LEVEL_DOMAINS = {"com", "org", "net", "io", "dev", "app", "edu", "gov", "co", "uk", "es", "de", "fr", "it"}
# Focus that moves this soon after an activation was moved by the app, not by a swipe.
FOCUS_AFTER_ACTION_MS = 1000
# WCAG 1.4.3: 4.5:1 for text, 3:1 for large text (18pt, or 14pt bold).
CONTRAST_TEXT, CONTRAST_LARGE_TEXT = 4.5, 3.0
# WCAG 2.5.8 asks for 24x24 CSS px; Android's guideline is 48dp. One dp is one CSS px.
WCAG_TARGET_DP = 24


def name_or_place(node):
    """How to point at an element in a detail: its label, its id, or its class and bounds."""
    if label(node) or node.get("id") not in (None, "-"):
        return repr(label(node) or node["id"])
    bounds = node.get("bounds")
    where = f"[{bounds[0]},{bounds[1]}][{bounds[2]},{bounds[3]}]" if isinstance(bounds, list) else "?"
    return f"the {node.get('class')} at {where}"


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
    operable = "clickable" in node["flags"] or "checked" in node
    return operable and "role" not in node and (cls in GENERIC_CLASSES or cls.endswith("Layout"))


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


def within(inner, outer):
    """Whether inner's bounds lie within outer's; true when either has none."""
    a, b = inner.get("bounds"), outer.get("bounds")
    if not (isinstance(a, list) and isinstance(b, list)):
        return True
    return b[0] <= a[0] and b[1] <= a[1] and a[2] <= b[2] and a[3] <= b[3]


def descendants(tree, i):
    """The nodes dumped inside tree[i], in tree order. Only nodes worth logging are dumped, so a deeper node
    may be the child of an undumped sibling: it must also lie within tree[i]'s bounds."""
    for other in tree[i + 1:]:
        if other["depth"] <= tree[i]["depth"]:
            break
        if within(other, tree[i]):
            yield other


def nested_actionables(tree):
    """Each clickable node with the clickable nodes inside it: the inner ones are controls of their own."""
    for i, node in enumerate(tree):
        if "clickable" in node["flags"]:
            inner = [other for other in descendants(tree, i) if "clickable" in other["flags"]]
            if inner:
                yield node, inner


def unreachable_actions(tree):
    """Each node with actions that isn't actionable itself, with the nearest clickable node it lies in:
    TalkBack focuses that one and only offers that one's actions."""
    holders = {}
    for i, node in enumerate(tree):
        if "clickable" in node["flags"]:
            for other in descendants(tree, i):
                if other.get("actions") and not actionable(other):
                    # Inner clickable nodes come later in the dump: the nearest one wins.
                    holders[id(other)] = (other, node)
    return list(holders.values())


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
            # The node's own name trails its utterance too ("Selected, Search in Women"), but it isn't a role.
            if part.strip().casefold() in roles and part.strip().casefold() != label(node).casefold():
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


def list_problems(tree):
    """Collections whose items don't match what they declare. The count isn't checked on scrolled ones, by
    themselves or by a pager inside: a lazy list declares every item but only the visible ones are in the tree."""
    for i, node in enumerate(tree):
        m = re.fullmatch(r"(-?\d+)x(-?\d+)", node.get("collection", ""))
        if not m:
            continue
        inside = list(descendants(tree, i))
        scrolled = any("scrollable" in n["flags"] for n in [node] + inside)
        rows, cols = int(m.group(1)), int(m.group(2))
        items = [n for n in inside if "item" in n]
        # Clickable elements that aren't items, nor inside one: an item's own buttons belong to it.
        loose, item_depth = [], None
        for n in inside:
            if item_depth is not None and n["depth"] > item_depth:
                continue
            item_depth = n["depth"] if "item" in n else None
            if "clickable" in n["flags"] and "item" not in n:
                loose.append(n)
        problems = []
        if scrolled:
            pass
        elif rows * cols == 1:
            problems.append("a list of a single item: TalkBack announces a list with nothing to move through")
        elif min(rows, cols) == 1 and rows * cols != len(items):
            problems.append(f"declares {rows * cols} items, {len(items)} carry item info")
        if loose and items:
            problems.append(f"{len(loose)} clickable inside without item info: " + ", ".join(name_or_place(n) for n in loose))
        elif loose:
            problems.append(f"no child carries item info ({len(loose)} clickable inside)")
        if problems:
            yield node, "; ".join(problems)


def focus_moves_after_action(records, app_pkg):
    """Each activation in the app followed within FOCUS_AFTER_ACTION_MS by focus on another element,
    with no window change of the app in between (a new screen or dialog takes focus legitimately; the
    keyboard opening doesn't)."""
    for i, r in enumerate(records):
        if r["kind"] != "click" or r.get("pkg") != app_pkg:
            continue
        for later in records[i + 1:]:
            if later["t"] - r["t"] > FOCUS_AFTER_ACTION_MS or later["kind"] == "click":
                break
            if later["kind"] == "window" and later.get("pkg") == app_pkg:
                break
            if later["kind"] == "focus":
                if element_key(later) != element_key(r):
                    yield r, later
                break


def atf_findings(records, tree):
    """ATF results, with the tree node they point at when there is one, for its label and size."""
    by_key = {element_key(n): n for n in tree}
    for r in records:
        if r["kind"] != "atf" or "check" not in r:
            continue
        node = by_key.get(element_key(r), r) if "bounds" in r else None
        if r.get("type") == "WARNING":
            conformance = "advisory"
        elif r["check"] == "TouchTargetSizeCheck" and node:
            conformance = target_conformance(node)
        else:
            conformance = None
        yield finding(f"ATF:{r['check']}", "atf", node, r.get("msg"), r["t"], conformance)


def run_rules(records, screenshot=None):
    """`screenshot` is a PNG taken when the last dump was, for contrast."""
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
    for node, holder in unreachable_actions(tree):
        actions = ", ".join(repr(a) for a in node["actions"].split("|"))
        detail = f"actions {actions} sit inside {name_or_place(holder)}, which is what TalkBack focuses: they are not offered"
        findings.append(finding("UNREACHABLE_ACTIONS", "tree", node, detail, node["t"]))

    # Other packages' focuses stay in the timeline: they delimit what the app's last focus said.
    timeline = build_timeline(all_focuses, speeches)
    roles = {role.casefold() for s in speeches if (role := trailing_role(s["text"]))}
    stops_by_element = defaultdict(list)
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
        if focus is not None:
            next_t = timeline[i + 1]["t"] if i + 1 < len(timeline) else None
            spoke = any(s.strip() for s in entry["speech"])
            stops_by_element[element_key(focus)].append((focus, next_t - focus["t"] if next_t else None, spoke))
    # Silent on every focus, and the user either stayed (a quick swipe on can beat the speech) or came back.
    for stops in stops_by_element.values():
        durations = [d for _, d, _ in stops]
        if any(spoke for _, _, spoke in stops):
            continue
        if len(stops) > 1 or any(d is None or d >= SILENT_FOCUS_MS for d in durations):
            longest = "until the end of the walk" if None in durations else f"{max(durations)} ms"
            if len(stops) > 1:
                detail = f"no speech on any of its {len(stops)} focuses (longest {longest})"
            else:
                detail = "no speech, focused until the end of the walk" if None in durations else f"no speech, focused for {longest}"
            findings.append(finding("SILENT_FOCUS", "speech", stops[0][0], detail, stops[0][0]["t"]))

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
            dp = round((click["bounds"][1] - focus["bounds"][1]) / px_per_dp)
            jump = f", {abs(dp)}dp {'above' if dp >= 0 else 'below'}"
        findings.append(finding(
            "FOCUS_MOVED_AFTER_ACTION", "focus", focus,
            f"after activating {name_or_place(click)}, focus moved to {name_or_place(focus)}{jump}",
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

    atf = list(atf_findings(records, tree))
    atf_keys = {(f["rule"], element_key(f["node"])) for f in atf if f["node"]}
    atf_run = next((r for r in reversed(records) if r["kind"] == "atf" and "end" in r["flags"]), None)

    if screenshot:
        # ATF measures contrast too: ours stays for what it didn't measure (below API 30, older captures).
        findings.extend(
            f for f in contrast_findings(tree, screenshot)
            if ("ATF:TextContrastCheck", element_key(f["node"])) not in atf_keys
        )

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

    for f in findings:
        if f["node"] and (OVERLAPS.get(f["rule"]), element_key(f["node"])) in atf_keys:
            f["overlaps"] = OVERLAPS[f["rule"]]
    findings.extend(atf)

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
        "atf": {k: v for k, v in atf_run.items() if k in ("results", "skipped", "reason", "error")} if atf_run else None,
        "timeline": timeline,
        "tree": tree,
    }


def contrast_findings(tree, screenshot):
    _, _, pixels = read_png(screenshot)
    for node in tree:
        if not node.get("text", "").strip() or not isinstance(node.get("bounds"), list):
            continue
        measured = text_contrast(pixels, node["bounds"])
        if measured and measured[2] < CONTRAST_TEXT:
            background, foreground, ratio = measured
            conformance = "failure" if ratio < CONTRAST_LARGE_TEXT else "advisory"
            detail = f"{ratio:.1f}:1, text #{bytes(foreground).hex()} on #{bytes(background).hex()}"
            if conformance == "advisory":
                detail += "; passes only if the text is large (18sp, or 14sp bold)"
            yield finding("TEXT_CONTRAST", "screenshot", node, detail, node["t"], conformance=conformance)
