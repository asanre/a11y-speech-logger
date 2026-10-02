---
name: compose-a11y
description: Use when writing or fixing Jetpack Compose UI for accessibility, when an accessibility audit finding needs a Compose fix, or when asked how to make a component accessible. Gives the principles, the per-component patterns (expected TalkBack speech, code, anti-patterns, test assertion, WCAG 2.2 criteria) and how to verify the fix.
---

# Accessible Jetpack Compose

## When to use it

- Writing a new composable that users can see or act on.
- Fixing an accessibility audit finding (TalkBack speech, focus order, target size, contrast) in Compose code.
- Answering "how do I make this component accessible?".

## Principles

1. **TalkBack reads the semantics tree, not the pixels.** Every fix is a change to semantics: what a node is (role), what it is called (text or contentDescription), what state it is in, and how nodes are grouped. Inspect it with `composeTestRule.onRoot(useUnmergedTree = true).printToLog("TAG")` or the Layout Inspector.
2. **One focus stop per meaningful element.** A row with an icon, a title and a price is one stop. `clickable`, `toggleable` and `selectable` merge their descendants; for a non-interactive group use `Modifier.semantics(mergeDescendants = true) {}`. A child with its own `clickable` defies the merge and becomes a separate stop.
3. **Name and role on the same node, the actionable one.** When a node with a role also has accessibility children, Compose puts the role on a separate fake child that TalkBack reads as content, so you hear something like "Button, Stop response" instead of one control named "Stop response". Put the role and the name on the node that receives the action: give it `mergeDescendants`, or replace its children's semantics with `clearAndSetSemantics { contentDescription = ...; role = ... }`. `clearAndSetSemantics` clears everything after it in the modifier chain and hides it from every service, so use it sparingly.
4. **State goes in state properties, never in the label.** Use `selected`, `toggleableState`, `stateDescription` (or `toggleable`/`selectable`, which set them). A label like "Notifications on" goes stale and is never announced as a state change.
5. **Don't repeat the role in the label.** TalkBack adds the role. `contentDescription = "Close button"` is read "Close button, Button".
6. **On one modifier chain, the first value of a semantics key wins.** Put `Modifier.semantics { ... }` before `clickable`/`toggleable` when you override what they set.
7. **Traversal follows layout** (left to right, top to bottom). When that splits a logical group, set `isTraversalGroup = true` on the group's container; use `traversalIndex` on focusable children only when grouping is not enough. Scroll containers and Material surfaces are traversal groups by default.
8. **Prefer Material and Foundation components.** They ship roles, states, merging and a 48dp minimum target. Custom components should copy the semantics of the closest Material component.
9. **No `announceForAccessibility`.** It is deprecated in Android 16 (API 36). Use `liveRegion` for status changes and `paneTitle` (or `Activity.setTitle`) for window or pane changes.

## How to verify a fix

1. **Write down the expected speech first**, as "name, role, state" (for example "Wi-Fi, Switch, On"; TalkBack's order varies with its version and settings), then check it on a device.
2. **Capture with the repo tool, when available.** With TalkBack on and this repo's logger set up, run `python3 tools/audit.py capture <screen>`, walk the screen, press Enter, then `python3 tools/audit.py rules audits/<date>/<screen>` to re-run the rules. Compare the spoken lines in `findings.json` (`timeline`) with the expected speech.
3. **Guard against regressions in Compose UI tests** with `enableAccessibilityChecks()` (Compose 1.8.0+, dependency `androidx.compose.ui:ui-test-junit4-accessibility`). It runs the Accessibility Test Framework, the same checks the capture tool runs on its last tree dump: missing labels, contrast, small touch targets, traversal order. Any action, or `tryPerformAccessibilityChecks()`, runs them.

```kotlin
@get:Rule val composeTestRule = createAndroidComposeRule<ComponentActivity>()

@Test
fun favoriteToggle_isAccessible() {
    composeTestRule.setContent { FavoriteToggle() }
    composeTestRule.enableAccessibilityChecks()
    composeTestRule.onRoot().tryPerformAccessibilityChecks()
    composeTestRule
        .onNode(SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.Switch))
        .performClick()
        .assertIsOff()
}
```

ATF checks catch structural problems, not wrong words. Assert names, roles and states with semantics matchers too; see each pattern's **Test assertion**.

## Per-component patterns

Read [`references/patterns.md`](references/patterns.md) for the component you are touching: button, link, tab, checkbox/radio/switch, chip, card with actions, list, dropdown, text field, dialog and bottom sheet, screen title, status and loading, heading, images, carousel/pager, focus after an action, touch target size and contrast. Each has the expected speech, Compose code, anti-patterns, a test assertion and the WCAG 2.2 criteria.
