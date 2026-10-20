# Compose accessibility patterns

How to read this file:

- **Expected speech** is written as "name, role, state". TalkBack's actual order and wording depend on its version and verbosity settings (the official docs quote a Switch as "On; Switch; double tap to toggle"), so compare the parts, not the order. Hints such as "Double tap to activate" are left out unless they matter.
- **Test assertion** uses APIs from the official docs: finders (`onNodeWithText`, `onNodeWithContentDescription`, `onNode`, `onAllNodes`), matchers (`hasText`, `hasClickAction`, `SemanticsMatcher.expectValue`), `assertIsOff`, `assertCountEquals`, `assertIsDisplayed`. Names not spelled out in the guides (`SemanticsProperties` keys, `Role` values, `assertIsSelected`, `keyIsDefined`, the exposed dropdown APIs) were checked against Compose UI 1.9, ui-test 1.12 and Material 3 1.4.
- Add `composeTestRule.enableAccessibilityChecks()` to the same tests to catch missing labels, small targets and low contrast.

---

## Button and icon button

**Expected speech:** "Share, Button". With `onClickLabel = "Share article"` the hint becomes "Double tap to share article".

**Compose code**
```kotlin
IconButton(onClick = onShare) {
    Icon(Icons.Filled.Share, contentDescription = stringResource(R.string.share))
}
Button(onClick = onLike) {
    Icon(Icons.Filled.Favorite, contentDescription = null) // text already names it
    Spacer(Modifier.size(ButtonDefaults.IconSpacing))
    Text("Like")
}
// Custom clickable: role and click label on the clickable node itself
Row(Modifier.clickable(onClickLabel = "Open article", role = Role.Button) { open() }) { /* ... */ }
```

**Anti-patterns**
- `Icon(contentDescription = null)` inside `IconButton`: "Button" with no name.
- `contentDescription = "Share button"`: "Share button, Button".
- `Box(Modifier.clickable { })` without `role`: "Share", no role, so users don't know it acts.
- Clickable on an inner `Icon` and the label in a sibling `Text`: two stops, the actionable one unnamed.

**Test assertion**
```kotlin
composeTestRule.onNodeWithText("Like")
    .assert(SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.Button))
composeTestRule.onNodeWithContentDescription("Share").assert(hasClickAction())
```

**WCAG 2.2:** 4.1.2, 1.1.1, 2.5.3, 2.5.8.

---

## Link (inline link in text)

**Expected speech:** the paragraph is read as one piece of text, and TalkBack exposes each link so the user can open it. How TalkBack announces and lists links is not in the official docs; check it with the capture tool. Each link's text must make sense on its own ("privacy policy", not "here").

**Compose code**
```kotlin
Text(
    buildAnnotatedString {
        append("Read our ")
        withLink(
            LinkAnnotation.Url(
                privacyUrl,
                TextLinkStyles(style = SpanStyle(color = MaterialTheme.colorScheme.primary)),
            )
        ) { append("privacy policy") }
        append(".")
    }
)
```
Pass a listener lambda to `LinkAnnotation.Url(...) { }` to run custom code on click. For a link with no URL, one that opens something in the app, use `LinkAnnotation.Clickable`:
```kotlin
withLink(
    LinkAnnotation.Clickable(
        tag = "ai_info",
        styles = TextLinkStyles(style = SpanStyle(textDecoration = TextDecoration.Underline)),
        linkInteractionListener = { onOpenInfo() },
    )
) { append("how the assistant works") }
```

**Anti-patterns**
- `Text(modifier = Modifier.clickable { open(url) })` for a sentence with one link: the whole sentence is one control, and the link target is unclear.
- `ClickableText` (deprecated): it handles taps on offsets with no link semantics, so TalkBack and the keyboard can't reach the link.
- Link text "Click here" or "More": meaningless when read out of context.
- Link marked only by color: invisible to users who can't tell the colors apart. Add a non-color cue too, such as an underline.

**Test assertion**
```kotlin
composeTestRule.onNodeWithText("Read our privacy policy.").assertIsDisplayed()
```
The fetched docs show no link-specific matcher. Check that links can be reached with TalkBack on a device.

**WCAG 2.2:** 2.4.4, 4.1.2, 1.4.1.

---

## Tab

**Expected speech:** "Songs, Tab, Selected". A tab is *selected*, never *checked*.

**Compose code**
```kotlin
PrimaryTabRow(selectedTabIndex = selected) {
    tabs.forEachIndexed { index, tab ->
        Tab(selected = index == selected, onClick = { selected = index }, text = { Text(tab.label) })
    }
}
// Custom tabs: group them, and make each one selectable with a tab role
Row(Modifier.selectableGroup()) {
    tabs.forEachIndexed { index, tab ->
        Box(Modifier.selectable(selected = index == selected, onClick = { selected = index }, role = Role.Tab)) {
            Text(tab.label)
        }
    }
}
```

**Anti-patterns**
- `toggleable` or a `Checkbox`-like state on a tab: "Checked" / "Not checked".
- "Songs, selected" written into the label: no real state, and it goes stale.
- Plain `clickable` tabs: "Songs" with no role and no state.

**Test assertion**
```kotlin
composeTestRule.onNodeWithText("Songs")
    .assert(SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.Tab))
    .assert(SemanticsMatcher.expectValue(SemanticsProperties.Selected, true)) // or assertIsSelected()
```

**WCAG 2.2:** 4.1.2, 1.3.1.

---

## Checkbox, radio button and switch

**Expected speech:** "Remember me, Checkbox, Checked"; "Calls, Radio button, Selected" (TalkBack may say "Checked" for a radio button; the docs don't say which, so confirm with the capture); "Wi-Fi, Switch, On". The whole row is one target and one focus stop.

**Compose code**
```kotlin
Row(
    Modifier
        .toggleable(value = checked, role = Role.Checkbox, onValueChange = { checked = it })
        .padding(16.dp)
        .fillMaxWidth()
) {
    Text("Remember me", Modifier.weight(1f))
    Checkbox(checked = checked, onCheckedChange = null) // the row handles the click
}
// Switch: same shape with role = Role.Switch and Switch(checked, onCheckedChange = null)

Column(Modifier.selectableGroup()) {
    options.forEach { option ->
        Row(Modifier.fillMaxWidth().height(56.dp)
            .selectable(selected = option == current, onClick = { current = option }, role = Role.RadioButton)) {
            RadioButton(selected = option == current, onClick = null)
            Text(option)
        }
    }
}
```
To customize the state words (for example "Subscribed"), set `semantics { stateDescription = ... }` before `toggleable`.

**Anti-patterns**
- `Checkbox(onCheckedChange = { })` next to a separate `Text`: two stops, the first one "Checkbox, Not checked" with no name, and a small target.
- A row with `clickable` instead of `toggleable`/`selectable`: no state, "Double tap to activate" instead of "Double tap to toggle".
- Radio buttons without `selectableGroup()`: they are not announced as one group.

**Test assertion**
```kotlin
composeTestRule.onNode(SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.Switch))
    .performClick()
    .assertIsOff()
```

**WCAG 2.2:** 4.1.2, 1.3.1, 2.5.8.

---

## Chip

**Expected speech:** filter chip "Vegetarian", with the role Material gives it and its state ("Selected" or "Checked", depending on that role); assist chip "Set alarm, Button". Check the role in `printToLog` and the words with the capture.

**Compose code**
```kotlin
FilterChip(
    selected = selected,
    onClick = { selected = !selected },
    label = { Text("Vegetarian") },
    leadingIcon = if (selected) {
        { Icon(Icons.Filled.Done, contentDescription = null) } // the state already says it
    } else null,
)
```

**Anti-patterns**
- A check icon with `contentDescription = "Done icon"`: "Done icon, Vegetarian…", which repeats the state as a fake name.
- A chip built from `Surface` and `clickable` without `selected`: no state.
- A dismissible input chip whose close icon has no name: "Button".

**Test assertion**
```kotlin
composeTestRule.onNodeWithText("Vegetarian").performClick()
    .assert(SemanticsMatcher.expectValue(SemanticsProperties.Selected, true))
```

**WCAG 2.2:** 4.1.2, 1.1.1.

---

## Card with actions

**Expected speech:** one stop that reads the card's content once ("Running shoes, 59.99"), with TalkBack's hint that more actions are available; "Add to favorites" is in the TalkBack actions menu.

**Compose code**
```kotlin
Card(
    onClick = onOpen,
    modifier = Modifier.semantics {
        customActions = listOf(
            CustomAccessibilityAction(label = "Add to favorites") { onFavorite(); true }
        )
    },
) {
    Text(product.name)
    Text(product.price)
    // Still tappable by touch; its action moved to customActions for accessibility
    IconButton(onClick = onFavorite, modifier = Modifier.clearAndSetSemantics { }) {
        Icon(Icons.Filled.Favorite, contentDescription = null)
    }
}
```

**Anti-patterns**
- A `clickable` card with a nested `IconButton`: the button defies the merge and becomes an extra stop, often unnamed.
- A clickable on the image, another on the title and another on the price: three stops that open the same thing.
- `clearAndSetSemantics { }` on the whole card: nothing is read.
- `customActions` on a layout inside the card (a `Column`) instead of the clickable node: TalkBack focuses the clickable node and only offers its actions, so the action can't be reached at all.

**Test assertion**
```kotlin
composeTestRule.onAllNodes(hasClickAction()).assertCountEquals(1) // one actionable node per card
composeTestRule.onNode(hasClickAction() and SemanticsMatcher.keyIsDefined(SemanticsActions.CustomActions)).assertExists()
```

**WCAG 2.2:** 4.1.2, 1.3.1, 2.1.1.

---

## List

**Expected speech:** each item is one stop, read once ("Earth, third planet"). With collection info, TalkBack can also say where the user is in the list (for example "in list, 8 items").

**Compose code**
```kotlin
Column(Modifier.semantics { collectionInfo = CollectionInfo(rowCount = planets.size, columnCount = 1) }) {
    planets.forEachIndexed { index, planet ->
        Row(Modifier.semantics(mergeDescendants = true) {
            collectionItemInfo = CollectionItemInfo(index, 0, 0, 0)
        }) {
            Text(planet.name)
            Text(planet.subtitle)
        }
    }
}
```
The docs show `collectionInfo` on custom lists and tell you to set `collectionItemInfo` on each item of a `LazyColumn`/`LazyRow`. They don't say whether Lazy layouts set either one by default: check `printToLog` before adding them.

**Anti-patterns**
- Item made of separate stops (image, title, subtitle, price): many swipes per item.
- Every item has a "More" button with the same label: users can't tell which item it belongs to. Labels in a collection must be unique ("More options for Earth").
- A `Column` of `Text` styled to look like a list, with no collection info: no count, no position.

**Test assertion**
```kotlin
composeTestRule.onNode(SemanticsMatcher.keyIsDefined(SemanticsProperties.CollectionInfo)).assertExists()
```

**WCAG 2.2:** 1.3.1, 4.1.2.

---

## Dropdown / exposed menu

**Expected speech:** "Size, M", with the role and the collapsed/expanded state that Material sets. The fetched docs don't document a public semantics property for expanded/collapsed, so use the Material component rather than rebuilding it.

**Compose code**
```kotlin
ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
    OutlinedTextField(
        value = size,
        onValueChange = {},
        readOnly = true,
        label = { Text("Size") },
        modifier = Modifier.menuAnchor(ExposedDropdownMenuAnchorType.PrimaryNotEditable),
    )
    ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
        sizes.forEach { option ->
            DropdownMenuItem(text = { Text(option) }, onClick = { size = option; expanded = false })
        }
    }
}
```

**Anti-patterns**
- `Row(Modifier.clickable { })` with a value `Text` and an arrow `Icon`: "M", with no label, no role and no expanded state.
- Label shown only as a placeholder: once a value is chosen, nothing says what it is for.
- An arrow icon with its own description ("Arrow down"): an extra, meaningless stop.

**Test assertion**
```kotlin
composeTestRule.onNodeWithText("Size").performClick()
composeTestRule.onNodeWithText("L").assertIsDisplayed()
```

**WCAG 2.2:** 4.1.2, 1.3.1, 3.3.2.

---

## Text field

**Expected speech:** "Email, Edit box", then the value; in error, the error text too ("Error, Enter an email like name@example.com").

**Compose code**
```kotlin
OutlinedTextField(
    value = email,
    onValueChange = onEmailChange,
    label = { Text("Email (required)") }, // persistent label; "required" visible in text
    isError = hasError,
    supportingText = { if (hasError) Text(errorText) },
    modifier = Modifier.semantics { if (hasError) error(errorText) },
)
```
A semantics property for "required" is not in the official docs: say it in the visible label, and explain any "*" convention on screen.

**Anti-patterns**
- `placeholder` only, no `label`: the hint disappears as soon as the user types, and TalkBack may read only the value.
- Error shown only by a red border: no text, nothing announced.
- Error in a separate `Text` far from the field: read only if the user happens to reach it.

**Test assertion**
```kotlin
composeTestRule.onNode(SemanticsMatcher.expectValue(SemanticsProperties.Error, errorText)).assertExists()
```

**WCAG 2.2:** 1.3.1, 3.3.1, 3.3.2, 4.1.2.

---

## Dialog and bottom sheet

**Expected speech:** when it opens, its title ("Delete draft?" or the sheet's pane title), then focus inside it; the content behind it is not reachable.

**Compose code**
```kotlin
AlertDialog(
    onDismissRequest = onDismiss,
    title = { Text("Delete draft?") },
    text = { Text("This can't be undone.") },
    confirmButton = { TextButton(onClick = onDelete) { Text("Delete") } },
    dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
)
ModalBottomSheet(onDismissRequest = onDismiss) { /* Material sets its own paneTitle */ }
// Custom window-like component:
ShareSheet(Modifier.semantics { paneTitle = "Share photo" })
```
Pane titles must be unique across the app: TalkBack uses them as identifiers.

**Anti-patterns**
- An overlay `Box` drawn over the screen instead of `Dialog`/`ModalBottomSheet`: nothing is announced and focus can wander behind it.
- Generic pane titles ("Dialog", "Sheet") reused on different screens.
- Buttons labeled "OK" / "Yes": unclear without reading the title. Name the action ("Delete").

**Test assertion**
```kotlin
composeTestRule.onNode(SemanticsMatcher.expectValue(SemanticsProperties.PaneTitle, "Share photo")).assertExists()
composeTestRule.onNodeWithText("Delete draft?").assertIsDisplayed()
```

**WCAG 2.2:** 4.1.2, 2.4.3, 1.3.1.

---

## Screen title

**Expected speech:** on entering the screen, its name ("Checkout"); the visible title reads "Checkout, Heading".

**Compose code**
```kotlin
// When the destination changes, give the window a title:
activity.setTitle(screenTitle)
// And mark the visible title as a heading:
Text(screenTitle, style = MaterialTheme.typography.headlineSmall, modifier = Modifier.semantics { heading() })
```
For a pane that changes inside the same window, use `Modifier.semantics { paneTitle = ... }`. Both are the official replacements for `announceForAccessibility` on window changes.

**Anti-patterns**
- Every screen keeps the app name as the window title: users can't tell where they are.
- Announcing the new screen with `announceForAccessibility` (deprecated in API 36).
- A title that is just big text, with no heading.

**Test assertion**
```kotlin
composeTestRule.onNodeWithText("Checkout")
    .assert(SemanticsMatcher.keyIsDefined(SemanticsProperties.Heading))
```

**WCAG 2.2:** 2.4.2, 1.3.1.

---

## Status and loading

**Expected speech:** "Loading results", then "12 results", spoken when the text changes, without moving focus.

**Compose code**
```kotlin
Text(
    text = if (loading) "Loading results" else "${results.size} results",
    modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
)
```
Keep the live-region node in composition and change its content: accessibility services are notified of changes to the node or its children. Use `LiveRegionMode.Assertive` only for time-critical content.

**Anti-patterns**
- `view.announceForAccessibility(...)`: deprecated in Android 16 (API 36) and inconsistent across assistive technologies.
- A live region on content that updates constantly (a countdown, a progress percentage): floods the user.
- A spinner with no text and no description: nothing tells the user something is loading.

**Test assertion**
```kotlin
composeTestRule.onNode(SemanticsMatcher.expectValue(SemanticsProperties.LiveRegion, LiveRegionMode.Polite))
    .assertTextEquals("12 results")
```

**WCAG 2.2:** 4.1.3.

---

## Heading

**Expected speech:** "Shipping address, Heading". Users can jump between headings.

**Compose code**
```kotlin
Text("Shipping address", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.semantics { heading() })
```

**Anti-patterns**
- Section titles styled big and bold with no `heading()`: navigation by headings skips them.
- `heading()` on a merged row that also holds body text: the whole row becomes the heading.
- Every line marked as a heading: navigation by headings is useless.

**Test assertion**
```kotlin
composeTestRule.onNodeWithText("Shipping address")
    .assert(SemanticsMatcher.keyIsDefined(SemanticsProperties.Heading))
```

**WCAG 2.2:** 1.3.1, 2.4.6.

---

## Images

**Expected speech:** informative image: its description ("Red running shoe, side view"); decorative image: nothing, not even a focus stop.

**Compose code**
```kotlin
Image(painterResource(R.drawable.shoe_side), contentDescription = stringResource(R.string.shoe_side)) // informative
Image(painterResource(R.drawable.divider_wave), contentDescription = null)                         // decorative
Text("•", Modifier.semantics { hideFromAccessibility() }) // decorative text, still visible to tests
```
`null` and `""` are not the same: `null` adds no accessibility information, `""` creates an empty label.

**Anti-patterns**
- `contentDescription = ""`: an empty label; on a clickable node the Accessibility Test Framework reports it as missing a label.
- Descriptions like "image", "photo" or a file name: no information.
- Describing an image that repeats the adjacent text: everything is read twice.

**Test assertion**
```kotlin
composeTestRule.onNodeWithContentDescription("Red running shoe, side view").assertIsDisplayed()
```

**WCAG 2.2:** 1.1.1.

---

## Carousel and pager

**Expected speech:** each slide's content is reachable and read once; "Next slide, Button" and "Previous slide, Button" are available without swiping.

**Compose code**
```kotlin
val pagerState = rememberPagerState(pageCount = { slides.size })
val scope = rememberCoroutineScope()
HorizontalPager(state = pagerState) { page -> SlideCard(slides[page]) }
Row {
    IconButton(onClick = { scope.launch { pagerState.animateScrollToPage(pagerState.currentPage - 1) } }) {
        Icon(previousIcon, contentDescription = "Previous slide")
    }
    IconButton(onClick = { scope.launch { pagerState.animateScrollToPage(pagerState.currentPage + 1) } }) {
        Icon(nextIcon, contentDescription = "Next slide")
    }
}
```
Visible buttons work for keyboard, Switch Access, Voice Access and TalkBack. If there is no room for them, add `customActions` ("Next slide", "Previous slide") to each slide's focusable node. Material's `HorizontalMultiBrowseCarousel` items still need a `contentDescription` on each image. Auto-advance must stop while the user interacts, and there must be a way to pause it.

**Anti-patterns**
- Swipe as the only way to change slides: unreachable by keyboard and hard with switch or voice access.
- Auto-advancing slides that change under TalkBack focus.
- Page-indicator dots as tiny unlabeled clickables: many small, nameless targets.

**Test assertion**
```kotlin
composeTestRule.onNodeWithContentDescription("Next slide").performClick()
composeTestRule.onNodeWithText(slides[1].title).assertIsDisplayed()
```

**WCAG 2.2:** 2.1.1, 2.5.1, 2.2.2, 4.1.2.

---

## Focus after an action

**Expected speech:** after closing a dialog, focus returns to the control that opened it ("Filters, Button"); after deleting an item, it goes to the next item or the list heading; after a failed submit, it goes to the first invalid field.

**Compose code**
```kotlin
val filtersButton = remember { FocusRequester() }
var showFilters by remember { mutableStateOf(false) }
var restoreFocus by remember { mutableStateOf(false) }
Button(onClick = { showFilters = true }, modifier = Modifier.focusRequester(filtersButton)) { Text("Filters") }
if (showFilters) FiltersDialog(onDismiss = { showFilters = false; restoreFocus = true })
LaunchedEffect(restoreFocus) {
    if (restoreFocus) { filtersButton.requestFocus(); restoreFocus = false }
}
```
`FocusRequester.requestFocus()` moves keyboard (input) focus; call it outside composition, as above. The docs don't say that TalkBack's accessibility focus follows it, so check it on a device with the capture tool. `focusRestorer` is not in the fetched docs.

**Anti-patterns**
- Removing the focused element (closing a dialog, deleting a row) without moving focus: focus jumps to the top of the screen or gets lost.
- Calling `requestFocus()` directly in the composable body: it runs on every recomposition.
- Moving focus on every content update: users lose their place.

**Test assertion**
```kotlin
composeTestRule.onNodeWithText("Cancel").performClick()
composeTestRule.onNodeWithText("Filters").assert(SemanticsMatcher.expectValue(SemanticsProperties.Focused, true))
```

**WCAG 2.2:** 2.4.3.

---

## Touch target size

**Expected speech:** not a speech issue; the Accessibility Test Framework and the capture tool flag small targets.

**Compose code**
```kotlin
Icon(
    Icons.Filled.Share,
    contentDescription = "Share",
    modifier = Modifier
        .minimumInteractiveComponentSize() // reserves at least 48.dp
        .clickable(role = Role.Button, onClick = onShare),
)
Box(Modifier.clickable { }.sizeIn(minWidth = 48.dp, minHeight = 48.dp))
```
Material `Checkbox`, `RadioButton`, `Switch`, `Slider` and `Surface` add the 48dp minimum themselves, but only when they are interactive (a non-null click callback). Compose also extends a small clickable's touch area beyond its bounds, but neighbouring targets can then overlap, so give the composable a real minimum size. Android and Material recommend 48x48dp; WCAG 2.5.8 (AA) requires at least 24x24 CSS px, or enough spacing around smaller targets. 48dp meets both.

**Anti-patterns**
- `Modifier.size(24.dp).clickable { }` on an icon: passes 2.5.8 at best, fails the Android guideline, and is hard to hit.
- `Checkbox(onCheckedChange = null)` used on its own (not inside a `toggleable` row): no padding, tiny target.
- Text links packed together in a row with no spacing.

**Test assertion**
```kotlin
composeTestRule.enableAccessibilityChecks()
composeTestRule.onRoot().tryPerformAccessibilityChecks() // fails on small touch targets
```

**WCAG 2.2:** 2.5.8.

---

## Contrast

**Expected speech:** not a speech issue; the Accessibility Test Framework and the capture tool measure it.

**Rules:** text smaller than 18sp (or bold smaller than 14sp) needs at least 4.5:1 against its background; larger text needs at least 3:1. Non-text elements users need (icons, field borders, focus indicators, chart lines) need 3:1 against their surroundings. Placeholder and hint text count as text.

**Compose code**
```kotlin
Text("Free shipping", color = MaterialTheme.colorScheme.onSurface) // pair "on" colors with their surface
```
Take colors from `MaterialTheme.colorScheme` in matching pairs (`onSurface` on `surface`, `onPrimary` on `primary`) and check the theme once, in light and dark, instead of checking hard-coded colors one by one.

**Anti-patterns**
- Light gray text on white (hard-coded `Color(0xFFB0B1B2)` on near-white): below 4.5:1.
- Text over a photo with no scrim: contrast changes with every image.
- State shown only by a subtle color change (selected tab, error border) below 3:1.

**Test assertion**
```kotlin
composeTestRule.enableAccessibilityChecks(
    AccessibilityValidator().setThrowExceptionFor(AccessibilityCheckResult.AccessibilityCheckResultType.WARNING)
)
composeTestRule.onRoot().tryPerformAccessibilityChecks() // contrast is one of the checks
```

**WCAG 2.2:** 1.4.3, 1.4.11.

---

## Sources

All fetched with `android docs fetch` (the Android Knowledge Base); each `kb://android/<path>` is `https://developer.android.com/<path>`.

- https://developer.android.com/develop/ui/compose/accessibility/semantics
- https://developer.android.com/develop/ui/compose/accessibility/merging-clearing
- https://developer.android.com/develop/ui/compose/accessibility/traversal
- https://developer.android.com/develop/ui/compose/accessibility/testing
- https://developer.android.com/develop/ui/compose/accessibility/api-defaults
- https://developer.android.com/develop/ui/compose/accessibility/inspect-debug
- https://developer.android.com/guide/topics/ui/accessibility/principles
- https://developer.android.com/guide/topics/ui/accessibility/apps
- https://developer.android.com/design/ui/mobile/guides/foundations/accessibility
- https://developer.android.com/about/versions/16/behavior-changes-all
- https://developer.android.com/develop/ui/compose/testing/apis
- https://developer.android.com/develop/ui/compose/testing/common-patterns
- https://developer.android.com/jetpack/compose/compose-component-api-guidelines
- https://developer.android.com/develop/ui/compose/modifiers-list
- https://developer.android.com/develop/ui/compose/designsystems/material2-material3
- https://developer.android.com/develop/ui/compose/text/user-interactions
- https://developer.android.com/develop/ui/compose/quick-guides/content/validate-input
- https://developer.android.com/develop/ui/compose/touch-input/focus/change-focus-behavior
- https://developer.android.com/develop/ui/compose/layouts/pager
- https://developer.android.com/develop/ui/compose/components/tabs
- https://developer.android.com/develop/ui/compose/components/radio-button
- https://developer.android.com/develop/ui/compose/components/chip
- https://developer.android.com/develop/ui/compose/components/card
- https://developer.android.com/develop/ui/compose/components/menu
- https://developer.android.com/develop/ui/compose/components/dialog
- https://developer.android.com/develop/ui/compose/components/bottom-sheets
- https://developer.android.com/develop/ui/compose/components/carousel
