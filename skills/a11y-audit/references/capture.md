# Capture mode: from a capture folder to the report

A capture folder holds:

| File | What it is |
|---|---|
| `report-draft.md` | The report already laid out from the findings. Start here |
| `screen-start.png`, `screen-end.png` | The screen when the capture began and ended. Always look at them |
| `findings.json` | The findings, the `timeline` (each focus with what TalkBack said) and the `tree` (the last node dump) |
| `session.txt` | The raw log. Read it only when the rest is not enough |
| `notes.md` | What a person who walked the screen tried and couldn't do. Quote it as a *tester note* |
| `look-NN.png` | Screenshots taken on the way in a walk driven from `adb` |

If `report-draft.md` is missing, run `a11y-audit rules <folder>`: it writes it.

A keyboard pass is a sibling folder, `<screen>-keyboard`. Run `a11y-audit rules` on it first and then
on the screen's folder: the draft takes its findings and marks the keyboard criteria.

## Steps

1. **Read `report-draft.md` and look at both screenshots.** If `screen-start.png` shows another
   screen, the walk began elsewhere: say so at the top of the report.
2. **Check what the capture can tell**, from the draft's first lines:
   - *Speech: not captured*: audit semantics only, and say so at the top.
   - *ATF: not run*, or an error: the tool's own rules still apply.
   - *Keyboard pass: no*: 2.1.1, 2.1.2, 2.4.7 and 2.4.11 stay *Not tested*.
3. **Confirm or dismiss each problem.** Each one has a `Check:` line: do what it says with the
   elements and the speech listed above it and the screenshot. Keep the dismissed ones, with the
   reason. A problem with "also `ATF:…`" is one problem: cite both names.
4. **Read the Activations section.** For each line:
   - the screen changed (a filter looks selected, a section opened) and TalkBack said nothing: report
     it, 4.1.2;
   - focus moved, bounced or was lost: it already is a problem above;
   - text is listed under *Text that appeared and TalkBack didn't say*: report it, 4.1.3.
5. **Go through *To judge on this screen*.** Each line is a check no rule makes. Look at the
   screenshot and the speech, and report what you find as a problem with **Evidence**: judgement.
6. **Fill every `?` of the conformance table.** **Fail** or **Advisory** when a problem you confirmed
   touches the criterion; **Pass** only when you looked at the evidence the row names and found
   nothing, and say what you looked at; otherwise **Not tested**, with the reason. When you dismissed
   every finding of a row, change its result. The meaning of each criterion on a native screen is in
   [wcag-mobile.md](wcag-mobile.md).
7. **Locate the code**, only when a repo path was given.
   - A node `id` other than `-` is the Compose `testTag` (`testTagsAsResourceId`) or the View id.
     Search for it, or for a constant holding it.
   - Otherwise search for the visible text in the string resources, then for its usages.
   - Report `path:line` when found and "not located" when not. Never guess a file.
8. **Write `report.md` in the capture folder**, in the format below.

Hints that name the keyboard's selection key ("Press select to activate") come from the virtual
keyboard of a walk driven from `adb`: never report them.

## Report format

Write it in the language the user asked in. It is for developers who aren't accessibility experts: plain
words, one problem per section, and what to hear once it's fixed.

1. **Summary.** Screen, app package, mode, and what the capture covered: speech, ATF, keyboard pass.
   Then 2–3 sentences on the most serious problems.
2. **Conformance by criterion.** The draft's table, with every `?` filled.
3. **Problems**, most severe first, grouped by what the user experiences. If five product cards have the
   same nested button, that is one problem with five instances. Each problem has:
   - **What happens**: what a TalkBack or keyboard user lives, with the speech quoted exactly;
   - **Why it matters**: one sentence, and the criteria with level and conformance, with the links
     the draft gives;
   - **Where**: the elements (label, bounds, screenshot) and `path:line` when located;
   - **Fix**: the change, from the `compose-a11y` skill. For a View-based screen, use the View
     equivalent (`contentDescription`, `android:accessibilityHeading`, `ViewCompat.setStateDescription`,
     `AccessibilityDelegateCompat`, `android:accessibilityPaneTitle`, `android:accessibilityLiveRegion`);
   - **Expected speech after the fix**, e.g. "Sort, Button, collapsed";
   - **Evidence**: rule names, "judgement" with what you looked at, or *observed while walking* with
     the line the command printed.
4. **Dismissed findings**, each with the reason.
5. **Not tested**: what the capture couldn't show, and the capture that would (a state not visited, a
   keyboard pass, a larger font size).

## Severity

- **high**: a user can't identify, reach or operate something (no name, silent focus, unreachable by
  keyboard, no visible focus).
- **medium**: it works but misleads or slows down (missing role or state, focus moved by the app,
  wrong order, missing title, unannounced status, low contrast).
- **low**: polish (repeated role word, verbosity, a 24–47dp target).
