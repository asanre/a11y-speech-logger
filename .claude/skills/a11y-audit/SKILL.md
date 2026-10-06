---
name: a11y-audit
description: Audits the accessibility of an Android screen against WCAG 2.2 A/AA and writes a report a developer can act on. Three modes - driving TalkBack on a connected device to capture the screen itself, from an a11y-speech-logger capture folder (session.txt, findings.json, screenshots), or from the screen's source code when there is no device. Use when asked to audit a screen or app on a device, to analyze or report on a capture under audits/, after running `tools/audit.py capture` or `keyboard`, or to review a screen's code for accessibility. Optional argument - the path to the audited app's source repo, to locate each problem in the code.
---

# Accessibility audit of a screen

Pick the mode from what you have:

- **Device mode**: a device connected over `adb` and no capture yet. You walk the screen with TalkBack
  yourself, following [references/device.md](references/device.md), then continue in Capture mode on
  the folder it produces.
- **Capture mode**: a capture folder (`audits/<date>/<screen>/`) or a date folder with several. It shows
  what TalkBack really said and is the reliable mode.
- **Code mode**: no capture, only the screen's source. Use it when no device is available. Every finding
  is marked *from code, not verified on device*, and the report says which capture would confirm it.

The criteria, what each one asks of a native screen and what evidence answers it are in
[references/wcag-mobile.md](references/wcag-mobile.md). For each fix, use the `compose-a11y` skill.

## Capture mode

### Input

- **`findings.json`**, the output of `tools/audit.py rules`:
  - `package`: the audited app;
  - `findings`: each one with `rule`, `severity`, `wcag`, `conformance` (`failure` or `advisory`),
    `source` (`tree`, `focus`, `speech`, `screenshot`, `keyboard` or `atf`), the `node`, a `detail`, and
    `overlaps` when an ATF check reported the same element;
  - `summary` and `summary_by_wcag`: counts per rule and per criterion;
  - `timeline`: each focused element with what TalkBack said for it;
  - `tree`: the last node dump, which matches `screen-end.png`;
  - `titles`: the titles TalkBack can announce for the screen;
  - `appeared`: text that showed up during the walk and was never spoken or focused;
  - `atf`: the Accessibility Test Framework run on the last dump. `results` without `skipped` means
    every check ran, contrast included; `skipped: contrast` with a `reason` means there was no
    screenshot; `error` means no results. `null` in captures taken before ATF was added. Text that only
    appeared in earlier dumps wasn't checked;
  - `keyboard` (keyboard pass only): the input-focus `sequence` and its `ending` (`cycle` or `stuck`).
    A `null` in `sequence` is a TAB that stopped on something the tree doesn't expose.
- **`session.txt`**: the raw log. Read it only when `findings.json` is not enough. The format is in the
  repo's README ("Log format").
- **`screen-start.png`, `screen-end.png`**: always look at them. If the start shows another screen, the
  walk began elsewhere. Older captures have a single `screen.png`.
- **`keyboard/step-NN.png`** (keyboard pass only): the screen after each TAB.
- **Hints** that name the keyboard's selection key instead of a double tap mean the walk was driven
  from `adb` (Device mode or `capture --auto`). They come from the virtual keyboard: never report them.
- **`notes.md`**, if present: what the tester tried and couldn't do. Quote it as a *tester note*. It
  points at a problem; the capture or the code must still show where it is.

A keyboard pass is a folder of its own, with a `keyboard/` subfolder. Its `findings.json` only has
`keyboard`, `findings` and `tree`: no timeline, titles or ATF. Audit it together with the TalkBack
capture of the same screen (a sibling folder; ask if it isn't clear which) and write one `report.md`
in the TalkBack capture's folder. The keyboard pass answers 2.1.1, 2.1.2, 2.4.7 and 2.4.11.

### Steps

1. **Check what the capture can tell.**
   - No `[speech]`: the logger wasn't the TTS engine. Audit semantics only and say so at the top.
   - No `[focus]` or `[tree]`: the focus logger was off. Stop and say so.
   - `atf` is `null` or has `error`: ATF results are missing; the own rules still apply.
   - `atf.skipped` is `contrast`: contrast comes only from `TEXT_CONTRAST` on the screenshot.
   - No keyboard pass: 2.1.1, 2.1.2 and 2.4.7 are *Not tested*.
2. **Verify every finding.** All of them are evidence to check, not verdicts. Confirm or dismiss each one
   with the timeline, the tree or the screenshot, and keep the dismissed ones with the reason.
   - `SILENT_FOCUS`: confirm in the timeline that nothing was spoken on any of the element's focuses.
   - `UNREACHABLE_ACTIONS`: confirm in the timeline that the clickable node it names gets focus and
     carries no `actions`. Find the visible control those actions stand for in the screenshot.
   - `NO_ROLE` *failure*: no role anywhere, so TalkBack gives no hint that it can be activated.
     *Advisory*: the role is on a descendant (`detail` says which), which Compose does when the
     actionable node has children of its own. TalkBack reads it as content ("Button, Stop").
   - `ROLE_BEFORE_LABEL`: advisory. Report the cause, a name missing on the actionable node, not the order.
     See "Advisory, not failure" in the reference.
   - `NESTED_ACTIONABLE`: confirm in the timeline that the inner control is a separate focus stop.
   - `ORDER_JUMP`: dismiss it if the previous step was a backwards swipe, the list scrolled, or a walk
     from `adb` wrapped around from the last element to the top.
   - `FOCUS_MOVED_AFTER_ACTION`: find where focus landed in the screenshot. At the top of the screen,
     or on an unrelated element, it is a 2.4.3 failure. On the result of the action, it is fine.
   - `DUPLICATE_LABEL`: dismiss it if the speech tells the elements apart.
   - `LIST_SEMANTICS`: check in the screenshot that it is a visual list.
   - `SCREEN_TITLE` and `titles`: across several captures, the same title on different screens is also
     a failure.
   - `TEXT_CONTRAST`, `ATF:TextContrastCheck`: dismiss them on text over images or gradients, which the
     screenshot shows. TalkBack's focus outline (green, blue on some builds) can skew the focused element.
   - `KEYBOARD_UNREACHABLE`, `FOCUS_NOT_VISIBLE`: check the step screenshots. Elements reached with
     arrows (carousels) are *Not verified*, not failures.
   - `ATF:*`: ATF's messages are terse. Restate them as the user's problem.
   - A finding with `overlaps` and the ATF finding it names are one problem. Report it once and cite both.
3. **Add the checks that need judgement.** Go through the reference table. These are the usual ones:
   - text that looks like a heading but isn't marked (1.3.1);
   - a selected tab, filter or option that is visible but not spoken (1.3.1, 4.1.2);
   - colour as the only cue (1.4.1);
   - decorative images that are read aloud, or informative ones that aren't (1.1.1);
   - links that act as buttons, or buttons that act as links; radios that act as buttons (4.1.2);
   - a placeholder as the only label, and required fields not exposed (3.3.2);
   - text in the screenshot that is missing from the tree and the speech;
   - text in `appeared` that should have been announced (4.1.3);
   - vague labels out of context ("More", "Image"), verbosity, mixed languages;
   - reading order against the visual order.
4. **Locate the code**, only when a repo path was given.
   - A node `id` other than `-` is the Compose `testTag` (`testTagsAsResourceId`) or the View id. Search
     for it, or for a constant holding it.
   - Otherwise search for the visible text in the string resources, then for its usages.
   - Report `path:line` when found and "not located" when not. Never guess a file.
5. **Write `report.md` in the capture folder** (format below).

## Code mode

1. Find the screen's composables (or layouts) from the name the user gives, and follow the components they use.
2. Go through the reference table and the judgement list above, reading semantics in the code:
   - labels (`contentDescription`, `semantics`);
   - roles (`Role`, `clickable(role = …)`);
   - state (`selected`, `toggleable`, `stateDescription`);
   - merging (`mergeDescendants`, `clearAndSetSemantics`), headings and `paneTitle`;
   - `liveRegion`, traversal and target sizes.
3. Mark each finding *from code, not verified on device*, with `path:line`. Name the capture that would
   confirm it, for example: `python3 tools/audit.py capture <screen>`, then swipe to the sort button.
4. In the conformance table, contrast, focus visibility and anything that depends on runtime state are
   *Not tested*, unless the code makes them certain (a hard-coded colour pair).

## Report format

Write it in the language the user asked in. It is for developers who aren't accessibility experts: plain
words, one problem per section, and what to hear once it's fixed.

1. **Summary.** Screen, app package, mode, and what the capture covered: speech, ATF, keyboard pass.
   Then 2–3 sentences on the most serious problems.
2. **Conformance by criterion.** One row per criterion of the reference. Result is **Fail**, **Advisory**
   (only advisory findings), **Pass** (evidence and no problems) or **Not tested**, with the reason in a
   few words. Never mark Pass without evidence.
3. **Problems**, most severe first, grouped by what the user experiences. If five product cards have the
   same nested button, that is one problem with five instances. Each problem has:
   - **What happens**: what a TalkBack or keyboard user lives, with the speech quoted exactly from the
     timeline;
   - **Why it matters**: one sentence, and the criteria with level and conformance, linked to
     `https://www.w3.org/WAI/WCAG22/Understanding/<slug>`;
   - **Where**: the elements (label, bounds, screenshot) and `path:line` when located;
   - **Fix**: the change, from the `compose-a11y` skill. For a View-based screen, use the View
     equivalent (`contentDescription`, `android:accessibilityHeading`, `ViewCompat.setStateDescription`,
     `AccessibilityDelegateCompat`, `android:accessibilityPaneTitle`, `android:accessibilityLiveRegion`);
   - **Expected speech after the fix**, e.g. "Sort, Button, collapsed";
   - **Evidence**: rule names, or "judgement" with what you looked at.
4. **Dismissed findings**, each with the reason.
5. **Not tested**: what the capture couldn't show, and the capture that would (a state not visited, a
   keyboard pass, a larger font size).

## Severity

- **high**: a user can't identify, reach or operate something (no name, silent focus, unreachable by
  keyboard, no visible focus).
- **medium**: it works but misleads or slows down (missing role or state, wrong order, missing title,
  unannounced status, low contrast).
- **low**: polish (repeated role word, verbosity, a 24–47dp target).

## Rules for the report

- Quote speech exactly as captured. Never paraphrase what TalkBack said.
- Don't report a problem you can't point to in the capture or the code.
- Failure only when the criterion is broken as written. Guidelines and good practice are advisory.
