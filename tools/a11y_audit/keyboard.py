"""The rules over a keyboard pass: what TAB reaches and whether focus can be seen."""

from collections import defaultdict

from .contrast import read_png
from .records import dumps, label
from .rules import element_key, finding

# The keyboard pass stops when input focus stays on the same element for this many keys.
KEYBOARD_STUCK_STEPS = 3
# Focus indicators are often drawn just outside the element: pixels this far out are compared too.
FOCUS_RING_PX = 6


def input_focus_sequence(all_dumps):
    """The input-focused node of each dump (None when nothing has input focus), in step order."""
    return [next((n for n in nodes if "INPUT_FOCUSED" in n["flags"]), None) for _, nodes in all_dumps]


def keyboard_ending(sequence):
    """Why the pass ended: "cycle" when focus came back to the first element, "stuck" when it stopped
    moving, None when it ran out of steps."""
    keys = [element_key(n) if n else None for n in sequence]
    first = next((k for k in keys if k), None)
    seen_first = [i for i, k in enumerate(keys) if k == first]
    if first and len(seen_first) > 1 and any(k not in (first, None) for k in keys[seen_first[0]:seen_first[-1]]):
        return "cycle"
    tail = keys[-KEYBOARD_STUCK_STEPS:]
    if len(keys) > KEYBOARD_STUCK_STEPS and tail[0] and len(set(tail)) == 1:
        return "stuck"
    return None


def expanded(bounds, height, width):
    left, top, right, bottom = bounds
    return (max(left - FOCUS_RING_PX, 0), max(top - FOCUS_RING_PX, 0),
            min(right + FOCUS_RING_PX, width), min(bottom + FOCUS_RING_PX, height))


def region_changed(before, after, bounds, previous_bounds=None):
    """Whether any pixel around the element changed, leaving out the previous element's area: its
    indicator going away is not this element's indicator appearing."""
    height, width = len(after), len(after[0])
    left, top, right, bottom = expanded(bounds, height, width)
    skip = expanded(previous_bounds, height, width) if previous_bounds else None
    for y in range(top, bottom):
        for x in range(left, right):
            if skip and skip[0] <= x < skip[2] and skip[1] <= y < skip[3]:
                continue
            if before[y][x] != after[y][x]:
                return True
    return False


def run_keyboard_rules(records, steps_dir):
    """Rules over a keyboard pass: dump N and keyboard/step-NN.png were taken after the Nth TAB."""
    all_dumps = dumps(records)
    app_pkg = all_dumps[0][0].get("pkg") if all_dumps else None
    sequence = input_focus_sequence(all_dumps)
    ending = keyboard_ending(sequence)
    findings, flagged = [], set()

    images = {}

    def step(n):
        if n not in images:
            images[n] = read_png(steps_dir / f"step-{n:02}.png")[2]
        return images[n]

    previous, hidden, indicated, stale = None, [], None, set()
    for i, node in enumerate(sequence):
        # The indicator of the element focus just left should be gone: two elements must not look focused.
        if indicated and (node is None or element_key(node) != element_key(indicated[0])):
            left_node, gained = indicated
            if (steps_dir / f"step-{i:02}.png").exists() and element_key(left_node) not in stale:
                # The new element's own indicator may touch this one's area: it is left out.
                arrived = node["bounds"] if node and isinstance(node.get("bounds"), list) else None
                if not region_changed(step(gained), step(i), left_node["bounds"], arrived):
                    stale.add(element_key(left_node))
                    findings.append(finding(
                        "STALE_FOCUS_INDICATOR", "keyboard", left_node,
                        f"its focus indicator (step {gained}) is still drawn after focus moved on (step {i})", left_node["t"],
                    ))
            indicated = None
        # Focus on something the accessibility tree doesn't expose: only the screen can show where it is.
        boxes = [n["bounds"] for n in all_dumps[i][1] if isinstance(n.get("bounds"), list)]
        if node is None and previous is not None and boxes and (steps_dir / f"step-{i:02}.png").exists():
            screen = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
            previous_bounds = previous.get("bounds") if isinstance(previous.get("bounds"), list) else None
            if not region_changed(step(i - 1), step(i), screen, previous_bounds):
                hidden.append(i)
        changed = node is not None and (previous is None or element_key(node) != element_key(previous))
        before, after = steps_dir / f"step-{i - 1:02}.png", steps_dir / f"step-{i:02}.png"
        if changed and i > 0 and isinstance(node.get("bounds"), list) and before.exists() and after.exists():
            key = element_key(node)
            previous_bounds = previous.get("bounds") if previous and isinstance(previous.get("bounds"), list) else None
            if region_changed(step(i - 1), step(i), node["bounds"], previous_bounds):
                indicated = (node, i)
            elif key not in flagged:
                flagged.add(key)
                findings.append(finding("FOCUS_NOT_VISIBLE", "keyboard", node, f"nothing changed on screen when it got focus (step {i})", node["t"]))
        previous = node or previous
    if hidden:
        findings.append(finding(
            "FOCUS_NOT_VISIBLE", "keyboard",
            detail=f"steps {', '.join(map(str, hidden))}: TAB stopped on something the accessibility tree doesn't "
                   "expose and nothing changed on screen, so neither the user nor a screen reader can tell where focus is",
        ))

    reached = {element_key(n) for n in sequence if n}
    if ending == "stuck":
        why = f"focus stopped moving at {label(sequence[-1]) or sequence[-1].get('id')!r}: check for a keyboard trap (2.1.2)"
    elif ending == "cycle":
        why = "never got focus in a full TAB cycle"
    else:
        why = f"not reached in {len(sequence) - 1} TABs"
    # Input focus that moved on before the step's dump: the element was reached, then focus jumped away.
    lost = {element_key(r) for r in records if r["kind"] == "input"}
    for node in (all_dumps[0][1] if all_dumps else []):
        if "clickable" in node["flags"] and "disabled" not in node["flags"] and element_key(node) not in reached:
            detail = why
            if element_key(node) in lost:
                detail = "got input focus and lost it before the next TAB: check whether focus is reset (2.4.3)"
            findings.append(finding("KEYBOARD_UNREACHABLE", "keyboard", node, detail, node["t"]))

    summary = defaultdict(int)
    for f in findings:
        summary[f["rule"]] += 1
    return {
        "package": app_pkg,
        "summary": dict(summary),
        "keyboard": {
            "ending": ending or "max steps",
            "sequence": [label(n) or n.get("id") if n else None for n in sequence],
        },
        "findings": findings,
        "tree": all_dumps[0][1] if all_dumps else [],
    }
