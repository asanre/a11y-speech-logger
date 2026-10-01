---
name: a11y-audit
description: Turns an a11y-speech-logger capture (session.txt, findings.json, screen.png) into an accessibility report for that screen. Use when asked to audit, analyze or report on a capture folder under audits/, or after running `tools/audit.py capture`. Optional argument - the path to the audited app's source repo, to locate each problem in the code by its testTag or text.
---

# Accessibility audit of a captured screen

Input: one capture folder (`audits/<date>/<screen>/`) or a date folder with several. Each holds:

- `findings.json` — output of `tools/audit.py rules`: `summary`, `findings` (deterministic heuristics), `timeline` (each focused element with the utterances TalkBack spoke for it) and `tree` (node dump of the screen).
- `session.txt` — the raw log. Read it only when `findings.json` is not enough.
- `screen.png` — screenshot taken when the capture started. Always look at it.

The log format and every field are described in the repo's README ("Log format").

## Steps

1. **Check the capture is usable.**
   - If there are no `[speech]` records, the speech logger was not the default TTS engine. The report then covers semantics only; say so at the top.
   - If there are no `[focus]` or `[tree]` records, the A11y Focus Logger was not enabled. Stop and say so.
2. **Verify every deterministic finding.** They are heuristics. Confirm or dismiss each one with evidence from the timeline, the tree or the screenshot, and keep the dismissed ones in the report with the reason.
   - `ORDER_JUMP`: dismiss it if the previous step was a backwards swipe or the list scrolled.
   - `DUPLICATE_LABEL`: dismiss it if TalkBack's speech disambiguates the elements (for example, it reads the product name too).
   - `SILENT_FOCUS`: confirm with the timeline that nothing was spoken.
3. **Add the checks that need judgement.**
   - Labels that don't make sense out of context ("More", "Click here", "Image").
   - Excessive verbosity: a container read whole in one go, or decorative content read aloud.
   - Missing state, such as selected, expanded or checked, when the screenshot shows it.
   - Reading order against the visual order in the screenshot.
   - Mixed languages in one utterance.
   - Text in the screenshot that never appears in the tree or the speech.
   - Interactive elements without a role ("Button", "Switch"…) or without an action hint.
4. **Locate the code** (only when a repo path was given).
   - For nodes with `id` other than `-`, search the repo for that id as a test tag (`testTag("<id>")` or a constant holding it).
   - Otherwise search for the visible text in string resources and then its usages.
   - Report `path:line` when found, and "not located" when not. Never guess a file.
5. **Write `report.md` in the capture folder** with this structure:
   - **Summary**:
     - the screen, the app package, whether speech was captured;
     - a table of confirmed findings by severity.
   - **Findings**, most severe first. One section each with:
     - what TalkBack says, quoted from the timeline;
     - the evidence (node fields, screenshot);
     - why it matters, with the WCAG criterion;
     - the fix in Compose;
     - the location in code.
   - **Dismissed heuristics**, each with the reason.
   - **Not verified**: anything the capture could not show, such as states not visited or screens not walked.

## Severity

- **high**: a TalkBack user can't identify or operate the element. Examples: no label, silent focus, unreachable content.
- **medium**: it works but is confusing or slow. Examples: label in a child, missing hint, small target, no headings, duplicate labels.
- **low**: polish. Examples: repeated role word, suspect order, verbosity.

## WCAG references

| Problem | WCAG 2.2 |
|---|---|
| No label, label in child, missing role or state | 4.1.2 Name, Role, Value; 1.1.1 Non-text Content |
| Field without hint or label | 3.3.2 Labels or Instructions |
| Small touch target | 2.5.8 Target Size (Minimum). Android's own guideline is 48dp. |
| Reading order | 1.3.2 Meaningful Sequence; 2.4.3 Focus Order |
| No headings | 1.3.1 Info and Relationships; 2.4.6 Headings and Labels |
| Duplicate or vague labels | 2.4.6 Headings and Labels; 2.4.4 Link Purpose |
| Mixed languages | 3.1.2 Language of Parts |

## Compose fixes

| Problem | Fix |
|---|---|
| Icon-only control without a label | `Icon(contentDescription = "…")` inside an `IconButton`, or `Modifier.semantics { contentDescription = "…" }` on the clickable |
| Label on a child, not on the clickable | Move the description to the clickable, or merge with `Modifier.semantics(mergeDescendants = true) {}`. Check that the child doesn't open its own semantics boundary. |
| Field without hint | `TextField(label = { Text("…") })` instead of a separate `Text` placeholder |
| Small target | `Modifier.minimumInteractiveComponentSize()` or `Modifier.sizeIn(minWidth = 48.dp, minHeight = 48.dp)` |
| Role word repeated ("Add button, Button") | Drop "button" from the description; set the role with `Modifier.clickable(role = Role.Button)` or `semantics { role = Role.Button }` |
| Vague action hint | `Modifier.clickable(onClickLabel = "open details")` |
| No headings | `Modifier.semantics { heading() }` on section titles |
| Wrong order | `Modifier.semantics { isTraversalGroup = true }` on the group, `traversalIndex` on its children |
| Whole list read at once | Remove `mergeDescendants` or `clearAndSetSemantics` from the container. Expose items separately, with `collectionInfo` on the list if needed. |
| `[announce]` records | Replace `announceForAccessibility` with `Modifier.semantics { liveRegion = LiveRegionMode.Polite }` on the changing content |
| Decorative content read aloud | `Icon(contentDescription = null)` or `Modifier.clearAndSetSemantics {}` |

## Rules for the report

- Quote speech exactly as captured. Don't paraphrase what TalkBack said.
- Don't report a problem you can't point to in the capture.
- Write the report in the language the user asked in.
