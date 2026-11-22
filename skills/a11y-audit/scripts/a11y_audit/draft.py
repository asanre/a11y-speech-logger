"""The report's draft: findings.json laid out as the report, with what is left to judge marked."""

import re

from .preview import PREVIEW_PKG
from .rules import RULES, name_or_place

# Every WCAG 2.2 A/AA criterion of the skill's reference, in its order. `capture` says how far a
# capture goes: "rules" (a rule decides it), "partly", "judgement" (the evidence is there, no rule),
# "keyboard" (needs the keyboard pass) or "no". `look` is what answers it, or what would test it.
CRITERIA = [
    {"sc": sc, "name": name, "level": level, "capture": capture, "look": look}
    for sc, name, level, capture, look in (
        ("1.1.1", "Non-text Content", "A", "partly", "icons in the screenshot that are read as nothing or as a file name"),
        ("1.2.1–1.2.5", "Media", "A/AA", "no", "only applies if the screen plays audio or video; play it to check captions"),
        ("1.3.1", "Info and Relationships", "A", "partly", "text that looks like a heading, a list, or a selected item that is not said as one"),
        ("1.3.2", "Meaningful Sequence", "A", "partly", "the timeline's order against the screenshot"),
        ("1.3.3", "Sensory Characteristics", "A", "judgement", "instructions that rely on shape, position or colour"),
        ("1.3.4", "Orientation", "AA", "no", "a capture in each orientation"),
        ("1.3.5", "Identify Input Purpose", "AA", "no", "autofill hints are not in the log; read the code of the fields"),
        ("1.4.1", "Use of Color", "A", "judgement", "state or meaning shown only by colour in the screenshot, against what is spoken"),
        ("1.4.2", "Audio Control", "A", "no", "audio is not in the log"),
        ("1.4.3", "Contrast (Minimum)", "AA", "rules", "the screenshot, when ATF's contrast checks ran"),
        ("1.4.4", "Resize Text", "AA", "no", "a capture at the largest font size"),
        ("1.4.5", "Images of Text", "AA", "judgement", "text in the screenshot that no node of the tree holds"),
        ("1.4.10", "Reflow", "AA", "no", "a capture with a large font or display size"),
        ("1.4.11", "Non-text Contrast", "AA", "partly", "control boundaries and icons in the screenshot"),
        ("1.4.12", "Text Spacing", "AA", "no", "rarely applies to native apps"),
        ("1.4.13", "Content on Hover or Focus", "AA", "judgement", "tooltips or popups that show on focus"),
        ("2.1.1", "Keyboard", "A", "keyboard", "the keyboard pass"),
        ("2.1.2", "No Keyboard Trap", "A", "keyboard", "the keyboard pass"),
        ("2.1.4", "Character Key Shortcuts", "A", "no", "single-key shortcuts, rare in apps"),
        ("2.2.1", "Timing Adjustable", "A", "no", "time limits are not in the log"),
        ("2.2.2", "Pause, Stop, Hide", "A", "judgement", "content that moves or updates on its own, such as a carousel"),
        ("2.3.1", "Three Flashes", "A", "no", "flashing is not in the log"),
        ("2.4.1", "Bypass Blocks", "A", "judgement", "how many stops come before the main content, and whether headings let the user skip them"),
        ("2.4.2", "Page Titled", "A", "rules", "the titles listed above"),
        ("2.4.3", "Focus Order", "A", "partly", "where focus went after each activation, and the timeline's order"),
        ("2.4.4", "Link Purpose (In Context)", "A", "partly", "links named \"More\" or \"Here\" in the timeline"),
        ("2.4.5", "Multiple Ways", "AA", "no", "applies across the app, not to one screen"),
        ("2.4.6", "Headings and Labels", "AA", "partly", "vague names in the timeline"),
        ("2.4.7", "Focus Visible", "AA", "keyboard", "the keyboard pass"),
        ("2.4.11", "Focus Not Obscured (Minimum)", "AA", "keyboard", "the keyboard pass's screenshots"),
        ("2.5.1", "Pointer Gestures", "A", "judgement", "controls that need a path or several fingers, and their `actions`"),
        ("2.5.2", "Pointer Cancellation", "A", "no", "whether actions fire on press is not in the log"),
        ("2.5.3", "Label in Name", "A", "partly", "the visible text of each control against its spoken name"),
        ("2.5.4", "Motion Actuation", "A", "no", "shake or tilt actions; read the code"),
        ("2.5.7", "Dragging Movements", "AA", "judgement", "sliders, reorder handles and sheets, and their `actions`"),
        ("2.5.8", "Target Size (Minimum)", "AA", "rules", "the sizes in the tree"),
        ("3.1.1", "Language of Page", "A", "judgement", "utterances in another language than the screen's"),
        ("3.1.2", "Language of Parts", "AA", "judgement", "passages in another language in the timeline"),
        ("3.2.1", "On Focus", "A", "judgement", "a window change right after a focus, with no activation"),
        ("3.2.2", "On Input", "A", "judgement", "a window change right after a value changed"),
        ("3.2.3", "Consistent Navigation", "AA", "no", "captures of several screens"),
        ("3.2.4", "Consistent Identification", "AA", "no", "captures of several screens"),
        ("3.2.6", "Consistent Help", "A", "no", "captures of several screens"),
        ("3.3.1", "Error Identification", "A", "partly", "a capture with the error on screen"),
        ("3.3.2", "Labels or Instructions", "A", "partly", "fields whose only label is a placeholder in the screenshot"),
        ("3.3.3", "Error Suggestion", "AA", "judgement", "the error text, when one was captured"),
        ("3.3.4", "Error Prevention", "AA", "no", "a flow, not a screen"),
        ("3.3.7", "Redundant Entry", "A", "no", "a flow, not a screen"),
        ("3.3.8", "Accessible Authentication (Minimum)", "AA", "no", "the login flow and its code"),
        ("4.1.2", "Name, Role, Value", "A", "rules", "the name, role and state spoken for each control against the screenshot"),
        ("4.1.3", "Status Messages", "AA", "partly", "text that appeared and was not said, listed below"),
    )
]

# How to confirm or dismiss each finding. Rules left out are confirmed in the timeline, the tree or the screenshot.
CHECKS = {
    "NO_LABEL": "confirm in the screenshot that it is a control, and that nothing useful is spoken for it.",
    "SILENT_FOCUS": "confirm in the timeline that nothing was spoken on any of the element's focuses.",
    "UNREACHABLE_ACTIONS": "confirm that the clickable node it names gets focus and carries no `actions`; find in the screenshot the control those actions stand for.",
    "NO_ROLE": "a failure when no role is spoken anywhere. Advisory when the detail says the role is on a descendant.",
    "ROLE_BEFORE_LABEL": "advisory. Report the cause, a name missing on the actionable node, not the order.",
    "NESTED_ACTIONABLE": "confirm in the timeline that the inner control is a separate focus stop.",
    "ORDER_JUMP": "dismiss it if the list scrolled, the keyboard opened, a swipe went backwards or the walk wrapped from the last element to the top.",
    "FOCUS_MOVED_AFTER_ACTION": "fine if focus landed on the result of the action. A 2.4.3 failure if it landed anywhere else: the top of the screen, a text field, an unrelated element.",
    "FOCUS_BOUNCED": "a failure. Report what the user hears, from the timeline.",
    "FOCUS_LOST": "a failure. Report what the user hears, from the timeline.",
    "DUPLICATE_LABEL": "dismiss it if the speech tells the elements apart.",
    "LIST_SEMANTICS": "check in the screenshot that it is a visual list.",
    "SCREEN_TITLE": "across several captures, the same title on different screens is a failure too.",
    "NO_HEADING": "advisory. Find in the screenshot the text that works as a heading.",
    "TEXT_CONTRAST": "dismiss it on text over an image or a gradient. TalkBack's focus outline can skew the focused element.",
    "ATF:TextContrastCheck": "dismiss it on text over an image or a gradient. A ratio far below 3:1 on a plain background is a failure.",
    "SMALL_TARGET": "a failure below 24dp. From 24 to 47dp it only misses Android's 48dp guideline.",
    "EDIT_NO_HINT": "check in the screenshot whether a label stays visible while typing.",
    "KEYBOARD_UNREACHABLE": "check the step screenshots. Elements reached with arrows are not verified, not failures.",
    "FOCUS_NOT_VISIBLE": "check the step screenshots.",
}
SEVERITY_ORDER = ("high", "medium", "low")
# What a preview can't answer: it has no speech, no focus, no window and no touch target.
NEEDS_DEVICE = {"1.3.2", "1.4.13", "2.2.2", "2.4.1", "2.4.2", "2.4.3", "2.5.8", "3.1.1", "3.1.2", "3.2.1", "3.2.2", "4.1.3"}


def node_key(finding):
    node = finding.get("node") or {}
    return node.get("id"), str(node.get("bounds"))


def without_repeats(findings):
    """The findings without the ATF ones another finding already covers (`overlaps`): one problem, cited once."""
    covered = {(f["overlaps"], node_key(f)) for f in findings if f.get("overlaps")}
    return [f for f in findings if (f["rule"], node_key(f)) not in covered]


def rule_names(findings):
    return list(dict.fromkeys(f["rule"] for f in findings))


def criterion_result(criterion, findings, keyboard_pass):
    """(result, evidence or reason) for a criterion, from its findings. A criterion with no finding is
    "?" for whoever writes the report to judge: never Pass on its own."""
    if findings:
        result = "Fail" if any(f["conformance"] == "failure" for f in findings) else "Advisory"
        return result, ", ".join(rule_names(findings))
    if criterion["capture"] == "no":
        return "Not tested", criterion["look"]
    if criterion["capture"] == "keyboard" and not keyboard_pass:
        return "Not tested", "no keyboard pass: run `a11y-audit keyboard <screen>-keyboard`"
    quiet = [rule for rule, spec in RULES.items() if criterion["sc"] in spec["wcag"]]
    return "?", (f"no finding from {', '.join(quiet)}; " if quiet else "") + f"look at {criterion['look']}"


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def said_on(node, timeline):
    """What TalkBack said on the focuses of the element, in order, without repeats."""
    key = (node.get("id"), str(node.get("bounds")))
    said = [text for entry in timeline if entry["focus"] and (entry["focus"].get("id"), str(entry["focus"].get("bounds"))) == key
            for text in entry["speech"] if text]
    return list(dict.fromkeys(said))


def problem(rule, findings, timeline, names):
    first = findings[0]
    criteria = ", ".join(f"[{sc} {names[sc][0]}](https://www.w3.org/WAI/WCAG22/Understanding/{slug(names[sc][0])}) ({names[sc][1]})"
                         for sc in first["wcag"] if sc in names) or "best practice"
    conformance = "failure" if any(f["conformance"] == "failure" for f in findings) else "advisory"
    also = sorted({f["overlaps"] for f in findings if f.get("overlaps")})
    lines = [f"### {rule}", "",
             f"{criteria} · {conformance} · severity {first['severity']}" + "".join(f" · also `{a}`" for a in also), ""]
    located = [f for f in findings if f.get("node")]
    if located:
        lines.append(f"Where ({len(located)} element{'s' if len(located) != 1 else ''}):")
    for f in located:
        said = ", ".join(f'"{text}"' for text in said_on(f["node"], timeline))
        lines.append(f"- {name_or_place(f['node'])}" + (f" · {f['node']['src']}" if f["node"].get("src") else "")
                     + (f" · {f['detail']}" if f.get("detail") else "")
                     + (f" · TalkBack said: {said}" if said else ""))
    lines += [f"- {f['detail']}" for f in findings if not f.get("node") and f.get("detail")]
    lines += ["", f"Check: {CHECKS.get(rule, 'confirm it in the timeline, the tree or the screenshot.')}", ""]
    return lines


def judgement_checks(tree, appeared):
    classes = {node.get("class") for node in tree}
    checks = [
        "text that looks like a heading in the screenshot and has no `heading` in the tree (1.3.1)",
        "state or meaning shown only by colour: a selected item, an error, who wrote a message (1.4.1)",
        "the timeline's order against the visual order (1.3.2)",
        "names that are vague out of context: \"More\", \"Image\" (2.4.6)",
        "text in the screenshot that is missing from the tree and the speech (1.1.1, 1.4.5)",
    ]
    if any(node.get("clickable") or "clickable" in node.get("flags", []) for node in tree):
        checks.append("a selected tab, filter or option that is visible and not spoken (4.1.2)")
    if "EditText" in classes:
        checks.append("a field whose only label is its placeholder, and required fields that don't say so (3.3.2)")
    if "ImageView" in classes or any(node.get("desc") for node in tree):
        checks.append("decorative images that are read aloud, and informative ones that aren't (1.1.1)")
    if appeared:
        checks.append("the text listed above that should have been announced (4.1.3)")
    return checks


def report_draft(result, screen, keyboard=None):
    """The draft of the report for a TalkBack capture: `result` is what `run_rules` returned, `keyboard`
    what `run_keyboard_rules` returned for the same screen, when there is a keyboard pass."""
    findings = without_repeats(result["findings"]) + (keyboard["findings"] if keyboard else [])
    names = {c["sc"]: (c["name"], c["level"]) for c in CRITERIA}
    timeline = result["timeline"]
    from_preview = result.get("package") == PREVIEW_PKG
    spoke = any(text for entry in timeline for text in entry["speech"])
    atf = result.get("atf")
    atf_state = "not run" if not atf else atf.get("error") or ("ran, contrast skipped" if atf.get("skipped") else "ran")
    lines = [
        f"# Report draft: {screen}", "",
        "Written by `a11y-audit rules` from findings.json. It is evidence to check, not the report: confirm or",
        "dismiss each problem, fill each `?`, and write report.md as the skill's Capture mode says.", "",
        *(["- Source: a Compose preview. Every finding is *from code, not verified on device*: there is no speech,",
           "  no focus order and no touch target, and state that changes at runtime isn't in it."] if from_preview
          else [f"- App: `{result.get('package')}`"]),
        f"- Titles TalkBack can announce: {', '.join(repr(t) for t in result['titles']) or 'none'}",
        f"- Elements focused in the walk: {sum(1 for entry in timeline if entry['focus'])}",
        f"- Speech: {'captured' if spoke else 'not captured, audit semantics only'} · ATF: {atf_state} · "
        f"Keyboard pass: {'yes' if keyboard else 'no'}", "",
        "## Conformance by criterion", "",
        "`?` is yours to judge from the evidence named. Never write Pass without evidence.", "",
        "| SC | Level | Result | Evidence or reason |", "|---|---|---|---|",
    ]
    for criterion in CRITERIA:
        mine = [f for f in findings if criterion["sc"] in f["wcag"]]
        outcome, reason = criterion_result(criterion, mine, bool(keyboard))
        if from_preview and not mine and criterion["sc"] in NEEDS_DEVICE:
            outcome, reason = "Not tested", "a capture on a device: `a11y-audit audit <screen>`"
        shown = ", ".join(f"`{rule}`" for rule in rule_names(mine)) if mine else reason
        if criterion["sc"] == "4.1.3" and not mine and result["appeared"]:
            count = len(result["appeared"])
            shown = f"{count} text{'s' if count != 1 else ''} appeared and TalkBack didn't say it, listed below"
        lines.append(f"| {criterion['sc']} {criterion['name']} | {criterion['level']} | "
                     f"{f'**{outcome}**' if outcome != '?' else '?'} | {shown} |")
    lines += ["", "## Problems to confirm", ""]
    by_rule = {rule: [f for f in findings if f["rule"] == rule] for rule in rule_names(findings)}
    ordered = sorted(by_rule, key=lambda rule: SEVERITY_ORDER.index(by_rule[rule][0]["severity"]))
    for rule in ordered:
        lines += problem(rule, by_rule[rule], timeline, names)
    if not ordered:
        lines += ["No rule found a problem.", ""]
    if result.get("activations"):
        lines += ["## Activations", "", "A state that changed on screen and wasn't said is a 4.1.2 problem.", ""]
        for activation in result["activations"]:
            said = ("TalkBack said: " + ", ".join(f'"{text}"' for text in activation["said"])) if activation["said"] else "TalkBack said nothing"
            lines.append(f"- {activation['element']} · {activation['focus']} · {said}")
        lines.append("")
    if result["appeared"]:
        lines += ["## Text that appeared and TalkBack didn't say", ""]
        lines += [f'- "{text}"' for text in result["appeared"]] + [""]
    lines += ["## To judge on this screen", ""]
    lines += [f"- {check}" for check in judgement_checks(result["tree"], result["appeared"])]
    return "\n".join(lines) + "\n"
