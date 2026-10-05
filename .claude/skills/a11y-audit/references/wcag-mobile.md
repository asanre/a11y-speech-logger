# WCAG 2.2 A/AA for native Android screens

Every Level A and AA success criterion of [WCAG 2.2](https://www.w3.org/TR/WCAG22/), read for a native
app the way W3C does in [WCAG2ICT](https://www.w3.org/TR/wcag2ict-22/) and in its notes on mobile.
"Page" means a screen, "keyboard" means a hardware keyboard or a D-pad (Switch Access walks the accessibility tree instead, so it is covered by the TalkBack walk and the node rules, not by the keyboard pass), and "set of pages" means the
screens of one app. 4.1.1 Parsing is obsolete in 2.2 and left out.

**Evidence** says what answers the criterion in a capture:
- a rule name (`NO_LABEL`, `ATF:TextContrastCheck`…) is in `findings.json`;
- *timeline*, *tree*, *screenshot* and *keyboard steps* are for you to judge.

**Capture** says how far a capture can go:
- **Yes**: a rule decides it, which you still confirm;
- **Partly**: a rule finds some cases and judgement covers the rest;
- **Judgement**: no rule, but the capture holds the evidence;
- **No**: the capture can't show it. Report it as *Not tested* and say what would test it.

| SC | Level | What it asks of a screen | Evidence | Capture |
|---|---|---|---|---|
| 1.1.1 Non-text Content | A | Images, icons and controls without text have a text alternative; decorative ones are hidden | `NO_LABEL`, `ATF:SpeakableTextPresentCheck`, `RAW_TEXT_SPOKEN`; icons in the screenshot that are read as nothing or as a file name | Partly |
| 1.2.1–1.2.5 Media | A/AA | Captions, transcripts and audio description for audio and video | Only applies if the screen plays media | No |
| 1.3.1 Info and Relationships | A | What the layout shows (headings, lists, groups, labels of fields, selected tab) is in the semantics | `LIST_SEMANTICS`, `NO_HEADING`; text that looks like a heading in the screenshot but has no `heading` in the tree; a selected state that is visible but not spoken | Partly |
| 1.3.2 Meaningful Sequence | A | The reading order keeps the meaning | `ORDER_JUMP`, `ATF:TraversalOrderCheck`; the timeline against the screenshot | Partly |
| 1.3.3 Sensory Characteristics | A | Instructions don't rely only on shape, position or colour ("tap the green button") | Spoken and visible text | Judgement |
| 1.3.4 Orientation | AA | Works in portrait and landscape unless one is essential | Needs a capture in both orientations | No |
| 1.3.5 Identify Input Purpose | AA | Fields for the user's own data declare their purpose (autofill hints) | Not in the log | No |
| 1.4.1 Use of Color | A | Colour isn't the only way to tell state or meaning (an error, a selected item, a link in text) | Screenshot plus the spoken state | Judgement |
| 1.4.2 Audio Control | A | Audio that plays on its own can be paused or stopped | Not in the log | No |
| 1.4.3 Contrast (Minimum) | AA | Text has 4.5:1, or 3:1 when large (18sp, or 14sp bold) | `ATF:TextContrastCheck`, `TEXT_CONTRAST` | Yes |
| 1.4.4 Resize Text | AA | Text scales to 200% without losing content | `ATF:TextSizeCheck` hints only; needs a capture at the largest font size | Partly |
| 1.4.5 Images of Text | AA | Text is real text, not an image | Screenshot text that has no node with that text | Judgement |
| 1.4.10 Reflow | AA | Content fits a narrow width without scrolling in two directions | Needs a capture with large font or display size | No |
| 1.4.11 Non-text Contrast | AA | Control boundaries, icons and focus indicators have 3:1 | `ATF:ImageContrastCheck`; screenshot | Partly |
| 1.4.12 Text Spacing | AA | No loss of content when spacing increases | Rarely applicable to native apps | No |
| 1.4.13 Content on Hover or Focus | AA | Tooltips and popups shown on focus can be dismissed and don't vanish | Keyboard steps, if any appear | Judgement |
| 2.1.1 Keyboard | A | Everything works with a keyboard | `KEYBOARD_UNREACHABLE` (keyboard pass), `ATF:ClickableSpanCheck` | Yes, with a keyboard pass |
| 2.1.2 No Keyboard Trap | A | Keyboard focus can always leave a component | `KEYBOARD_UNREACHABLE` with a "stuck" ending | Yes, with a keyboard pass |
| 2.1.4 Character Key Shortcuts | A | Single-key shortcuts can be turned off or remapped | Rare in apps | No |
| 2.2.1 Timing Adjustable | A | Time limits can be extended (sessions, auto-advancing content) | Not in the log | No |
| 2.2.2 Pause, Stop, Hide | A | Moving or auto-updating content (carousels) can be paused | Screenshots and the timeline only hint at it | Judgement |
| 2.3.1 Three Flashes | A | Nothing flashes more than three times a second | Not in the log | No |
| 2.4.1 Bypass Blocks | A | Repeated blocks can be skipped: headings or panes to jump past them | `NO_HEADING`; the timeline length before the main content | Judgement |
| 2.4.2 Page Titled | A | Each screen, dialog and sheet has a title TalkBack announces | `SCREEN_TITLE`, `titles` (same title on different screens is a failure too) | Yes |
| 2.4.3 Focus Order | A | Focus moves in an order that keeps the meaning, and lands somewhere sensible after an action | `ORDER_JUMP`, `FOCUS_MOVED_AFTER_ACTION`, `NESTED_ACTIONABLE`, `ATF:TraversalOrderCheck`; keyboard sequence | Partly |
| 2.4.4 Link Purpose (In Context) | A | A link's purpose is clear from its text or its context | `DUPLICATE_LABEL`, `ATF:LinkPurposeUnclearCheck`; "More", "Here" in the timeline | Partly |
| 2.4.5 Multiple Ways | AA | More than one way to reach a screen | Applies across the app, not one screen | No |
| 2.4.6 Headings and Labels | AA | Headings and labels describe their topic or purpose | `DUPLICATE_LABEL`, `ATF:DuplicateSpeakableTextCheck`; vague labels in the timeline | Partly |
| 2.4.7 Focus Visible | AA | The keyboard focus is visible | `FOCUS_NOT_VISIBLE` (keyboard pass) | Yes, with a keyboard pass |
| 2.4.11 Focus Not Obscured (Minimum) | AA | The focused element isn't fully hidden by sticky bars or sheets | Keyboard steps | Judgement |
| 2.5.1 Pointer Gestures | A | Multi-point or path gestures have a single-tap alternative | `actions` on the node; gestures in the code | Judgement |
| 2.5.2 Pointer Cancellation | A | Actions fire on release, not on press | Not in the log | No |
| 2.5.3 Label in Name | A | The accessible name contains the visible text, so voice control works | `ROLE_BEFORE_LABEL`, `LABEL_IN_CHILD`, `NO_ROLE` (role on a child); visible text vs `desc` | Partly |
| 2.5.4 Motion Actuation | A | Shake or tilt actions have an on-screen alternative | Code only | No |
| 2.5.7 Dragging Movements | AA | Dragging has a single-pointer alternative (reorder, sliders, sheets) | `actions` on the node (custom actions, expand/collapse) | Judgement |
| 2.5.8 Target Size (Minimum) | AA | Targets are at least 24×24dp, or spaced as if they were | `SMALL_TARGET`, `ATF:TouchTargetSizeCheck` (failure below 24dp; 24–47dp only misses Android's 48dp guideline) | Yes |
| 3.1.1 Language of Page | A | The app's language is set, so TalkBack reads it with the right voice | Pronunciation can't be heard in text; mixed scripts in one utterance hint at it | Judgement |
| 3.1.2 Language of Parts | AA | Passages in another language are marked | Timeline | Judgement |
| 3.2.1 On Focus | A | Focusing something doesn't change the context | Timeline: `[window]` right after a `[focus]` with no `[click]` | Judgement |
| 3.2.2 On Input | A | Changing a setting doesn't change the context unless the user was told | Timeline: `[window]` right after a value change | Judgement |
| 3.2.3 Consistent Navigation | AA | Navigation repeated across screens keeps its order | Compare captures of several screens | Judgement |
| 3.2.4 Consistent Identification | AA | The same function has the same name across screens | Compare captures of several screens | Judgement |
| 3.2.6 Consistent Help | A | Help is in the same place across screens | Compare captures of several screens | Judgement |
| 3.3.1 Error Identification | A | Errors are described in text and announced | `error` field on the node; `appeared` and `[announce]`; needs a capture with the error shown | Partly |
| 3.3.2 Labels or Instructions | A | Fields have a label that stays visible; required fields are marked | `EDIT_NO_HINT`, `ATF:EditableContentDescCheck`, `required`; a placeholder used as the only label in the screenshot | Partly |
| 3.3.3 Error Suggestion | AA | Errors suggest how to fix them | Error text, when captured | Judgement |
| 3.3.4 Error Prevention | AA | Legal, financial and data submissions can be reviewed, corrected or undone | Flow, not a screen | No |
| 3.3.7 Redundant Entry | A | Information already entered isn't asked for again in the same flow | Flow, not a screen | No |
| 3.3.8 Accessible Authentication (Minimum) | AA | Login doesn't require a cognitive test; paste and password managers work | Code and flow | No |
| 4.1.2 Name, Role, Value | A | Every control exposes its name, its role and its state | `NO_LABEL`, `SILENT_FOCUS`, `NO_ROLE`, `CONFLICTING_STATE`, `NESTED_ACTIONABLE`, `UNREACHABLE_ACTIONS`, `ATF:SpeakableTextPresentCheck`, `ATF:ClassNameCheck`; the spoken state against the screenshot | Yes |
| 4.1.3 Status Messages | AA | Status changes (results count, errors, "added to cart", loading) are announced without moving focus | `appeared` (text that showed up and was never spoken), `[announce]`, `live` | Partly |

## Advisory, not failure

Some rules are **advisory**: Android guidelines, good practice, or hints that need a check. Report them,
but never as a failure of the criterion. The clearest example is `ROLE_BEFORE_LABEL`:

- WCAG 4.1.2 asks for the name and role to be *programmatically determinable*, not for an order of reading,
  and TalkBack lets each user choose the order (*Element description order*).
- The rule still points at a real cause: the actionable node has no name of its own, so TalkBack takes it
  from a descendant and reads it as secondary content. That cause risks 4.1.2 for other services and
  breaks 2.5.3 for voice control ("tap Send" doesn't match).
- With the default order, "Send, Button" is also easier to follow than "Button, Send", above all when
  swiping fast.

Report the cause and its fix, not the symptom.
