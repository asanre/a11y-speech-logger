# A11y Speech Logger

Android tool that writes to logcat **exactly what TalkBack says** and **which element it is talking
about**, so a person or an LLM can audit an app's accessibility from text instead of by ear.

TalkBack's spoken output has no public API, and production builds don't log it. This app gets it
anyway by being the text-to-speech engine TalkBack talks to, so it works with any TalkBack build
that uses the system's default engine.

## How it works

One APK, two components, both logging to the `A11ySpeech` tag:

- **`SpeechLoggerService`**: a silent text-to-speech engine. Set it as the default engine and every
  TalkBack utterance is logged as `[speech]`. It plays no audio, so TalkBack is silent on the whole
  device while it is the default.
- **`FocusLoggerService`**: an accessibility service that runs next to TalkBack. It logs:
  - the focused element (`[focus]`), with its semantics and heuristic issues;
  - the element with input focus (`[input]`) and each activation (`[click]`);
  - window changes (`[window]`) and announcements (`[announce]`);
  - the screen's node tree on request (`[tree]`);
  - on the last request, the results of the
    [Accessibility Test Framework](https://github.com/google/Accessibility-Test-Framework-for-Android)
    (`[atf]`), the checks behind Accessibility Scanner and Compose's `enableAccessibilityChecks()`.

On top of the APK:

- **`tools/audit.py`**: captures a session per screen, walks it with a keyboard, and runs rules tagged
  with their WCAG 2.2 criteria.
- [Claude Code](https://claude.com/claude-code) skills in `.claude/skills/`:
  - **`a11y-audit`**: turns a capture, or the screen's code when there is no device, into a report by
    WCAG criterion;
  - **`a11y-retest`**: checks whether a reported issue is fixed;
  - **`compose-a11y`**: accessible Compose patterns, with the expected speech and a test for each.

## Setup

1. Build and install: `./gradlew :app:installDebug`.
2. Open **A11y Speech Logger** from the launcher. Its FAQ has every step below:
   - buttons that open the right Settings screens on any device;
   - copyable `adb` commands built at runtime for that device. They use the TalkBack that is
     installed (Google's or a vendor build) and keep the accessibility services you already have
     enabled.
3. Make it the preferred engine in the text-to-speech settings. Where they live varies by device,
   so use the app's button or run:
   ```bash
   adb shell settings put secure tts_default_synth io.github.asanre.a11ylogger
   ```
4. Enable **A11y Focus Logger** in the accessibility settings, usually under installed apps or
   services. Leave its shortcut off: on some devices enabling the shortcut turns TalkBack off.
5. Turn TalkBack off and on again so it picks up the new engine.

To restore everything, run the command below, turn the service off and pick your previous engine.

```bash
adb shell settings delete secure tts_default_synth
```

## Capture

Per screen, with `tools/audit.py` (Python 3 and `adb` only):

```bash
python3 tools/audit.py capture checkout   # dumps the tree, screenshots, shows the walk live, dumps again on Enter
python3 tools/audit.py keyboard checkout  # walks the screen with TAB, TalkBack off
python3 tools/audit.py rules audits/2026-10-01/checkout   # re-run the rules on an existing capture
```

`capture` warns you if the engine or the service isn't active. While you walk the screen it prints
each focus and what TalkBack says, one short line each, since TalkBack itself is silent. It writes
`audits/<date>/<screen>/` with `session.txt`, `screen-start.png`, `screen-end.png` and
`findings.json`, plus `notes.md` if you type a line before pressing Enter: what you tried and couldn't
do, which the log doesn't show. The tree is dumped at the start and again when you press Enter, because the screen
can change in between (a sheet opens, a list scrolls). The rules use the last dump, and only the
focus of the app in that dump: the keyboard and the system UI are left out. On the last dump the
service also runs ATF; its contrast checks need a screenshot, which an accessibility service can only
take from Android 11 (API 30). `audits/` is gitignored because it contains screenshots of the audited
app.

`keyboard` is for people who use a hardware keyboard (motor disabilities, tablets with a keyboard, Chromebooks, desktop modes), so turn TalkBack off first. Switch Access doesn't use keyboard focus: it walks the accessibility tree, like TalkBack. It presses TAB, dumps the tree
and takes a screenshot after each key (`keyboard/step-NN.png`), and stops when focus cycles back or
stops moving. Arrow-key navigation (carousels, grids) isn't walked.

Or by hand:

```bash
adb logcat -s A11ySpeech:I -v raw                           # follow what TalkBack says, live
adb logcat -c                                               # start a clean session
adb shell am broadcast -a io.github.asanre.a11ylogger.DUMP  # snapshot the current screen's tree
adb logcat -d -s A11ySpeech:I -v raw > session.txt          # save and exit
```

## Report

With Claude Code, open this repo and ask for the audit, optionally pointing to the app's source so
each finding is located by its test tag:

```
/a11y-audit audits/2026-10-01/checkout ~/code/my-app
```

The skill:
- verifies every heuristic against the timeline and the screenshot;
- adds the checks that need judgement: vague labels, verbosity, visual vs reading order, mixed
  languages;
- writes `report.md` with a conformance table by WCAG criterion (including what was *not tested*),
  and one section per problem the user lives: the exact speech, why it matters, the fix and the speech
  expected after it.

Without a device, `/a11y-audit` also reviews a screen from its code; each finding is then marked as
not verified on device. To check a fix, give `/a11y-retest` the issue's text and a new capture, or the
code.

## Log format

One record per line: `[kind] t=<ms> <fields>`.

- `t` is `elapsedRealtime` and is shared by every record, so speech can be matched to focus by time.
- Text values are quoted, with `\n` and `\"` escaped.

| Kind | Source | Fields |
|---|---|---|
| `[speech]` | TTS engine | the exact utterance |
| `[focus]` | accessibility focus | `pkg` plus node fields |
| `[window]` | window or pane change | `pkg`, `class`, `text` |
| `[announce]` | `announceForAccessibility` | `pkg`, `text` |
| `[input]` | input focus (keyboard) | `pkg` plus node fields |
| `[click]` | activation | `pkg` plus node fields |
| `[tree]` | `DUMP` broadcast | `begin pkg=… window="…"` (the window title, empty if none), one indented node per line (`FOCUSED` marks accessibility focus, `INPUT_FOCUSED` input focus), `end nodes=N` |
| `[atf]` | `DUMP` with `--ez atf true` | `check`, `type` (`ERROR` or `WARNING`), `id`, `class`, `bounds`, `msg`; then `end results=N`, with `skipped=contrast reason="…"` or `error="…"` when it applies. Without `skipped`, every check ran, contrast included |

Node fields, present only when they apply:
- **Identity**: `id` (`-` if none), `class`, `text`, `desc`, `role`.
- **State**: `state`, `hint`, `error`, `checked`, `expanded`, `required`, `heading`, `selected`,
  `disabled`. `expanded` and `required` need Android 16 (API 36).
- **Structure**: `pane` (pane title), `live` (`polite` or `assertive`), `collection` (rows x columns),
  `item` (row, column), `scrollable`.
- **Actions**: `clickable`, `longclickable`, `actions` (action labels, e.g. `onClickLabel` or custom
  actions).
- **Geometry**: `bounds` (px), `size` (dp).
- **Issues**: `issues` (below).

### Rules

Each finding names its WCAG 2.2 criteria and its conformance:
- **failure**: it breaks the criterion as written;
- **advisory**: an Android guideline, good practice, or a hint that needs a check.

All of them are evidence to verify, not verdicts. The `a11y-audit` skill confirms or dismisses each one.

| Rule | Where | WCAG | Conformance | Meaning |
|---|---|---|---|---|
| `NO_LABEL` | APK | 4.1.2, 1.1.1 | failure | Actionable, with no text or description of its own or in any non-actionable descendant, so TalkBack has nothing to read |
| `EDIT_NO_HINT` | APK | 3.3.2, 4.1.2 | failure | Empty `EditText` without a hint, e.g. a placeholder drawn as a separate text |
| `SMALL_TARGET` | APK | 2.5.8 | failure below 24dp, advisory up to 48dp | Actionable and smaller than 48dp on one side. WCAG asks for 24dp; 48dp is Android's guideline |
| `LABEL_IN_CHILD` | APK | 4.1.2 | advisory | Actionable without its own label; the only label is the content description of a non-actionable descendant (an icon button with the description on the icon). TalkBack often reads it fine; other services may not |
| `SILENT_FOCUS` | `audit.py` | 4.1.2 | failure | TalkBack said nothing on any focus of an element, and it was focused twice or for 1.5 s: a single quick swipe past can beat the speech |
| `UNREACHABLE_ACTIONS` | `audit.py` | 4.1.2 | failure | Actions (custom actions, e.g. "Add to bag") on a node that isn't actionable, inside a clickable one. TalkBack focuses the clickable node and only offers that node's actions |
| `NO_ROLE` | `audit.py` | 4.1.2 | failure, or advisory if the role is on a descendant | Clickable or checkable with a generic class (`View`, `*Layout`…) and no role, so nothing says what it is or that it can be activated |
| `CONFLICTING_STATE` | `audit.py` | 4.1.2 | failure | The same node is checkable and selected, and TalkBack reads both states |
| `RAW_TEXT_SPOKEN` | `audit.py` | 1.1.1, 4.1.2 | failure | Markup (`<br>`, `&nbsp;`) or a resource key (`screen.title.label`) in the text or the speech |
| `SCREEN_TITLE` | `audit.py` | 2.4.2 | failure | No window title, pane title or window-change text for the screen |
| `TEXT_CONTRAST` | `audit.py` | 1.4.3 | failure below 3:1, advisory up to 4.5:1 | Text and background colours measured on `screen-end.png`. Skipped where ATF measured the same element |
| `FOCUS_NOT_VISIBLE` | `keyboard` | 2.4.7 | failure | Nothing changes on screen around the element that gets keyboard focus, or TAB stops on something the accessibility tree doesn't expose and nothing changes at all |
| `STALE_FOCUS_INDICATOR` | `keyboard` | 2.4.7 | failure | The focus indicator stays drawn on an element after focus moved on, so two elements look focused |
| `KEYBOARD_UNREACHABLE` | `keyboard` | 2.1.1 (2.1.2 if stuck) | failure | An actionable element that TAB never reaches, or that gets focus and loses it right away (focus reset) |
| `NESTED_ACTIONABLE` | `audit.py` | 4.1.2, 2.4.3 | advisory | An actionable element inside another one, e.g. a favourite button inside a clickable card. Inside means deeper in the dump and within its bounds |
| `LIST_SEMANTICS` | `audit.py` | 1.3.1 | advisory | A list whose declared item count doesn't match its items (not checked on lazy lists), a list of a single item, or clickable children without item info |
| `FOCUS_MOVED_AFTER_ACTION` | `audit.py` | 2.4.3 | advisory | Within 1 s of an activation, focus jumped to another element; the detail says where |
| `NO_HEADING` | `audit.py` | 1.3.1, 2.4.6 | advisory | No node on the screen is a heading. WCAG doesn't require headings; it requires visual headings to be marked |
| `DUPLICATE_LABEL` | `audit.py` | 2.4.6, 2.4.4 | advisory | Several actionable elements share the same label |
| `ROLE_BEFORE_LABEL` | `audit.py` | 4.1.2, 2.5.3 | advisory | The utterance starts with a role word ("Button, Stop"), one the session shows trailing elsewhere ("Menu, Button") |
| `ORDER_JUMP` | `audit.py` | 1.3.2, 2.4.3 | advisory | Focus moved up more than 48dp; could also be a backwards swipe or a scroll |
| `REPEATED_ROLE` | `audit.py` | — | advisory | The role TalkBack appends ("…, Button", in any language) already appears in the label ("Add button, Button") |
| `LONG_SPEECH` | `audit.py` | — | advisory | One utterance over 300 characters, which the user can only stop by interrupting TalkBack |

### Advisory vs failure: `ROLE_BEFORE_LABEL`

Hearing "Button, Send" instead of "Send, Button" is not a WCAG failure:
- 4.1.2 asks for the name and role to be *programmatically determinable*, not for an order;
- TalkBack lets each user choose the order (*Element description order*).

It is still worth fixing, so the rule stays as advisory:
- with the default order, the name first is easier to follow, above all when swiping fast;
- it points at a real cause: the actionable node has no name of its own. In Compose, when a clickable
  node has accessibility children, the role is not set on its class but on an extra child that carries
  only the role. TalkBack then reads that role as content, before the name it takes from another child.
- That same cause can break 4.1.2 for other accessibility services, and 2.5.3 for voice control:
  "tap Send" doesn't match.

The fix is a name on the actionable node, by merging its children or setting its description. The fix
is not a change in the order.

### Rules from ATF vs our own

ATF results become findings named `ATF:<check>`:
- an `ERROR` takes the conformance in the table below;
- a `WARNING`, which ATF gives when it can't be sure (an unknown text size, a borderline value), is
  always advisory.

| Check | WCAG | `ERROR` |
|---|---|---|
| `SpeakableTextPresentCheck` | 4.1.2, 1.1.1 | failure |
| `TextContrastCheck` | 1.4.3 | failure |
| `ClickableSpanCheck` | 4.1.2, 2.1.1 | failure |
| `TraversalOrderCheck` | 1.3.2, 2.4.3 | failure |
| `TouchTargetSizeCheck` | 2.5.8 | failure below 24dp, advisory above |
| `ImageContrastCheck` | 1.4.11 | advisory |
| `DuplicateSpeakableTextCheck` | 2.4.6 | advisory |
| `DuplicateClickableBoundsCheck`, `EditableContentDescCheck`, `ClassNameCheck` | 4.1.2 | advisory |
| `TextSizeCheck` | 1.4.4 | advisory |
| `LinkPurposeUnclearCheck` | 2.4.4 | advisory |
| `RedundantDescriptionCheck` | — | advisory |

ATF only sees the node tree and a screenshot. Our rules also use what TalkBack said, the walk's
sequence, the keyboard pass and the log's structure fields. Where both look at the same thing, both are
kept until they have been compared on real captures; ours is marked with `overlaps`:

| Ours | ATF |
|---|---|
| `NO_LABEL` | `SpeakableTextPresentCheck` |
| `SMALL_TARGET` | `TouchTargetSizeCheck` |
| `DUPLICATE_LABEL` | `DuplicateSpeakableTextCheck` |
| `REPEATED_ROLE` | `RedundantDescriptionCheck` |

Our `TEXT_CONTRAST` only runs where ATF didn't measure contrast: below Android 11, when the screenshot
failed, and on older captures.

### Not covered

- Orientation (1.3.4), reflow and text scaling (1.4.4, 1.4.10): they need captures at other settings.
- Arrow-key navigation in the keyboard pass.
- Media, timing, motion and gestures (1.2.x, 2.2.x, 2.5.1, 2.5.4).
- Flows across screens (3.3.4, 3.3.7, 3.3.8), except by comparing captures.
- iOS. For a WebView, the tool sees only the node tree that WebView exposes.

## Caveats

- **Ids in Compose.** `id` is the `testTag`, and only when
  `Modifier.semantics { testTagsAsResourceId = true }` is set on an ancestor. Dialogs, popups and
  `ModalBottomSheet` are separate windows and need their own.
- **Tree order.** `[tree]` follows tree order, not TalkBack's traversal order. It excludes nodes that
  are not important for accessibility, just as TalkBack does.
- **Speech-to-focus matching is approximate.** Each focus owns what is spoken until the next one.
  Swiping very fast can shift utterances between neighbours.
- **Tested** so far on one device, with a vendor build of TalkBack (13.1). Google's TalkBack relies
  on the same mechanism, the default TTS engine, but hasn't been tested yet. Reports from other
  devices are welcome.
- **Not yet tested on a device**: the ATF results, the keyboard pass and the structure fields (`pane`,
  `collection`, `item`, `live`, `expanded`, `required`, `window`, `[click]`, `[input]`). Rules over them
  are covered by `python3 -m unittest tools/test_audit.py`.

## License

[MIT](LICENSE)
