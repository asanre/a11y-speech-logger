"""A Compose preview's component tree as the tree dump the rules read, to audit a screen without a device."""

# The package the dump is given: it tells the report's draft that nothing was verified on a device.
PREVIEW_PKG = "preview"
# Compose roles as the class TalkBack's role comes from.
ROLE_CLASSES = {"Checkbox": "CheckBox", "Image": "ImageView", "DropdownList": "Spinner"}


def quote(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def semantic_nodes(component, depth=1):
    """(depth, composable) for each composable with semantics; depth counts only those."""
    own = component.get("semantics")
    if own:
        yield depth, component
    for child in component.get("children") or []:
        yield from semantic_nodes(child, depth + 1 if own else depth)


def has_name(component):
    semantics = component.get("semantics") or {}
    return bool(semantics.get("text") or semantics.get("contentDescription")) or any(
        has_name(child) for child in component.get("children") or [])


def node_fields(component, density):
    """The composable as the fields of a `[tree]` node. Sizes are layout sizes: Compose widens the touch
    target of a small clickable on the device, so no target is judged from a preview."""
    semantics = component["semantics"]
    actions = [action.strip() for action in semantics.get("actions", "").split(",")]
    clickable = "OnClick" in actions
    role = semantics.get("role")
    kind = "EditText" if "SetText" in actions else ROLE_CLASSES.get(role, role) or ("TextView" if semantics.get("text") else "View")
    bounds, source = component["bounds"], component.get("sourceLocation") or {}
    width, height = (round((bounds[b] - bounds[a]) * 160 / density) for a, b in (("left", "right"), ("top", "bottom")))
    return " ".join(field for field in (
        "id=-",
        f"class={kind}",
        f"text={quote(semantics['text'])}" if semantics.get("text") else "",
        f"desc={quote(semantics['contentDescription'])}" if semantics.get("contentDescription") else "",
        f"state={quote(semantics['stateDescription'])}" if semantics.get("stateDescription") else "",
        f"checked={'true' if semantics['toggleableState'] == 'On' else 'false'}" if "toggleableState" in semantics else "",
        "clickable" if clickable else "",
        "heading" if semantics.get("heading") == "true" else "",
        "selected" if semantics.get("selected") == "true" else "",
        f"bounds=[{bounds['left']},{bounds['top']}][{bounds['right']},{bounds['bottom']}]",
        f"size={width}x{height}dp",
        f"src={source['fileName']}:{source['lineNumber']}" if source.get("fileName") else "",
        "issues=NO_LABEL" if clickable and not has_name(component) else "",
    ) if field)


def preview_lines(tree):
    """The component tree `android preview render --component-tree` writes, as the lines of a session
    with one dump. It has no window title, so the screen's title is not judged."""
    density = tree.get("densityDpi") or 160
    nodes = [node for component in tree.get("components") or [] for node in semantic_nodes(component)]
    return (
        [f"[tree] t=1 begin pkg={PREVIEW_PKG}"]
        + [f"[tree] t=1 {'  ' * depth}{node_fields(component, density)}" for depth, component in nodes]
        + [f"[tree] t=1 end nodes={len(nodes)}"]
    )
