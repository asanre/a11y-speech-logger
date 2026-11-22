# A11y Speech Logger

Android tool that writes to logcat **exactly what TalkBack says** and **which element it is talking
about**, so a person or an LLM can audit an app's accessibility from text instead of by ear.

TalkBack's spoken output has no public API, and production builds don't log it. This app gets it
anyway by being the text-to-speech engine TalkBack talks to, so it works with any TalkBack build
that uses the system's default engine.

## Install

1. **The skills**, for your agent. The `a11y-audit` command comes inside them (in the `a11y-audit`
   skill, `scripts/audit.py`: Python 3.9 or later, standard library only), and the agent runs it from
   there, so the command and the skills are always the same version:
   - Claude Code: `claude plugin marketplace add asanre/a11y-speech-logger`, then
     `claude plugin install a11y-speech-logger@a11y-speech-logger`. Skills are namespaced:
     `/a11y-speech-logger:a11y-audit`.
   - GitHub Copilot CLI: `copilot plugin marketplace add asanre/a11y-speech-logger`, then
     `copilot plugin install a11y-speech-logger@a11y-speech-logger`.
   - VS Code: add `"chat.plugins.marketplaces": ["asanre/a11y-speech-logger"]` (experimental) and
     install it from the Extensions view (`@agentPlugins`).
   - Any agent that reads [Agent Skills](https://agentskills.io):
     `npx skills add asanre/a11y-speech-logger`, or clone the repo and link each folder of `skills/`
     into `~/.agents/skills/` (OpenCode: `~/.config/opencode/skills/`). OpenCode, Copilot and VS Code
     also read `~/.agents/skills/`, so don't combine it with the plugin in those, or the skills load
     twice.
2. **The APK**: nothing to do. `a11y-audit setup` (and `a11y-audit audit`) installs the one of its own
   release on the device. Where the computer can't reach GitHub, download it from the
   [release](https://github.com/asanre/a11y-speech-logger/releases) once and pass it:
   `a11y-audit setup --apk a11y-speech-logger-<version>.apk`. If the install fails because the
   signature doesn't match, `adb uninstall io.github.asanre.a11ylogger` first. From a clone,
   `./gradlew :app:installDebug`.
3. **The command in your own terminal**, only if you want to capture by hand:
   ```bash
   uv tool install git+https://github.com/asanre/a11y-speech-logger
   ```
   `pipx install` takes the same URL. From a clone, `python3 skills/a11y-audit/scripts/audit.py` is
   the same command. Upgrade it when you update the skills: `a11y-audit doctor` says when the APK on
   the device belongs to another version.

   The examples below use the skills' short names, such as `/a11y-audit`. If your agent doesn't take
   it, use the plugin's prefix: `/a11y-speech-logger:a11y-audit`.

For a team, commit this in the app's `.claude/settings.json` (Claude Code and VS Code read it), and
add `audits/` to the app's `.gitignore`, since captures hold screenshots of the app:

```json
{
  "extraKnownMarketplaces": {
    "a11y-speech-logger": { "source": { "source": "github", "repo": "asanre/a11y-speech-logger" } }
  },
  "enabledPlugins": { "a11y-speech-logger@a11y-speech-logger": true }
}
```

For a whole organization, a claude.ai Owner can sync this repo in the organization's plugin catalog.

## Which capture to use

From the cheapest to the most complete. Each one writes `findings.json` and `report-draft.md`.

| You have | Run | It shows |
|---|---|---|
| No device, a `@Preview` of the screen | `android preview render <module> --component-tree --output <folder> --fqn <preview>`, then `a11y-audit preview <folder>` | Names, roles, states, headings and contrast, each with file and line. Nothing about speech, focus or touch targets |
| A device, two seconds | `a11y-audit capture <screen> --now` | The tree, the ATF checks, contrast and target sizes of the screen as it is |
| A device, a minute | `a11y-audit audit <screen> --app <package> --activate "<name>"` | What TalkBack says on each element, the order, and what focus does after each activation |
| A person with the device | `a11y-audit capture <screen>` | The states an automatic walk can't reach: gestures, links inside a text, a flow |
| Keyboard users to check | `a11y-audit keyboard <screen>-keyboard` | What TAB reaches and whether focus can be seen |

## Quick start

You need:
- an Android device or emulator with TalkBack, Android 8 or later (Android 11 or later for contrast
  checks), connected with USB debugging on: `adb devices` must list it. For the walks driven from
  `adb` (by the agent, `audit` or `--auto`), its shell also needs the `hid` tool; `doctor` checks it.
  Tested on Android 12 and on an API 37 emulator so far;
- what [Install](#install) sets up, and `adb` on the `PATH`. To build the APK yourself, JDK 17 or later
  and the Android SDK (`ANDROID_HOME` or `sdk.dir` in `local.properties`);
- an LLM agent that can run commands, with the skills installed: Claude Code, GitHub Copilot (CLI or
  VS Code), OpenCode, or any agent that reads Agent Skills.

1. **Set up the device**, once:
   ```bash
   a11y-audit setup
   ```
   It makes the logger the preferred text-to-speech engine, enables **A11y Focus Logger** and turns
   TalkBack off and on again so it picks up the engine. The app's FAQ has the same steps by hand.

   From then on TalkBack is silent: what it says is printed in your terminal. [Setup](#setup) has the
   details. `setup` installs the APK of its own release when it is missing or another version
   (`--apk <file>` when the device's computer can't reach GitHub). `a11y-audit doctor` lists what
   isn't ready, each line with the command that fixes it.

   **Or let the agent do steps 2 to 4.** Open the screen on the device and ask, with the agent started
   in the app's repo:
   - with slash commands (Claude Code, Copilot):
     `/a11y-audit audit the screen open on my device ~/code/my-app`;
   - otherwise: *"Use the a11y-audit skill in Device mode on the screen open on my device. The app's
     source is in `~/code/my-app`."*

   The source path is optional. The agent walks the screen with TalkBack, activates what changes the
   screen's state, and writes `audits/<date>/<screen>/report.md` next to the capture. It asks before
   activating anything that buys, sends, deletes or changes the account. It runs many `adb` and
   `a11y-audit` commands: allow them, or be ready to approve each one, or it stops at the
   first it can't run (then what it couldn't activate is listed as not tested). See
   [Driving TalkBack](#driving-talkback).
2. **Capture a screen with TalkBack on.**
   1. In the app you audit, open the screen in the state you want to check: a sheet open, results
      loaded.
   2. Run `a11y-audit capture checkout`. The name only names the folder.
   3. Swipe right through every element, top to bottom, following along in the terminal. Double-tap
      what you want to test (a chip, a dropdown), and keep swiping in the state it leads to. Stay on
      this screen.
   4. If something didn't work as you expected (you couldn't find an action, the keyboard opened by
      itself), type it in one line before pressing Enter.

   You get `audits/<date>/checkout/`, with the log, two screenshots and `findings.json`.

   To skip the swiping, run `a11y-audit audit checkout` instead: it sets the device up, turns
   TalkBack on, walks every element in TalkBack's order, saves the capture and gives the device
   back. Add `--activate "<name>"` for each element to tap after the walk: it says what happened to
   focus. `a11y-audit capture checkout --now` captures the screen as it is, without a walk: the
   tree, the ATF checks and the contrast, in two seconds, with or without TalkBack.
3. **Walk it with a keyboard** (optional, same screen). Turn TalkBack off and leave the screen as it
   was, then run `a11y-audit keyboard checkout-keyboard`. You don't need a physical
   keyboard: TAB is sent over `adb`. It stops on its own.
4. **Ask for the report**, with the agent started in the app's repo:
   - with slash commands:
     ```
     /a11y-audit audits/<date>/checkout audits/<date>/checkout-keyboard ~/code/my-app
     ```
   - otherwise: *"Use the a11y-audit skill on `audits/<date>/checkout` and
     `audits/<date>/checkout-keyboard`. The app's source is in `~/code/my-app`."*

   The source path is optional: with it, each problem points to a file and line. In Compose, that
   needs `testTagsAsResourceId` (see [Caveats](#caveats)). The agent writes `report.md` in the
   capture folder.
5. **Fix and check.**
   - `compose-a11y` gives the fix for each component.
   - `/a11y-retest` checks one issue: paste its text and point it to a new capture, or to the code.
   - Without a device, `/a11y-audit` reviews a screen from its code:
     `/a11y-audit "checkout screen" ~/code/my-app`.
6. **Give the device back** when you're done:
   ```bash
   a11y-audit release
   ```
   It turns off A11y Focus Logger, keeping your other accessibility services, and restores the
   default text-to-speech engine. An accessibility service left on makes Compose apps keep tracking
   semantics changes, which skews performance measurements on the device. The agent runs it at the
   end of a Device mode audit; run `setup` again before the next one.

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
  - also on request, for the walks driven from `adb`: it moves focus into the app's window, and
    clicks the element TalkBack is on, as a double tap does;
  - on the last request, the results of the
    [Accessibility Test Framework](https://github.com/google/Accessibility-Test-Framework-for-Android)
    (`[atf]`), the checks behind Accessibility Scanner and Compose's `enableAccessibilityChecks()`.

On top of the APK:

- **`a11y-audit`** (`skills/a11y-audit/scripts/`): captures a session per screen (walked by you, on its own, or
  by an agent step by step), walks it with a keyboard, and runs rules tagged with their WCAG 2.2
  criteria.
- Agent skills in `skills/`, also published as a plugin for Claude Code, Copilot CLI and VS Code:
  - **`a11y-audit`**: walks a screen on the device with TalkBack itself, or takes a capture you made,
    or the screen's code when there is no device, and turns it into a report by WCAG criterion;
  - **`a11y-retest`**: checks whether a reported issue is fixed;
  - **`compose-a11y`**: accessible Compose patterns, with the expected speech and a test for each.

## Setup

1. Install the APK ([Install](#install), step 2).
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

`a11y-audit setup` does steps 3 to 5 over `adb`. To restore everything, run
`a11y-audit release`: it turns the service off and restores the default engine (pick your
previous one if it wasn't the default).

## Capture

Per screen, with `a11y-audit`:

```bash
a11y-audit capture checkout   # dumps the tree, screenshots, shows the walk live, dumps again on Enter
a11y-audit capture checkout --auto   # the same, walking with TalkBack on its own
a11y-audit capture checkout --now    # the screen as it is: tree, ATF and contrast, no walk
a11y-audit audit checkout --app com.example.shop --activate "Sort"   # set up, walk, activate, save, release
a11y-audit doctor             # what isn't ready on the device, and the command that fixes it
a11y-audit preview build/previews   # no device: the rules over a Compose preview's component tree
a11y-audit keyboard checkout  # walks the screen with TAB, TalkBack off
a11y-audit rules audits/2026-10-01/checkout   # re-run the rules on an existing capture
```

Every capture also gets `report-draft.md`: the report laid out from the findings, with the conformance
table filled where a rule decides, each problem with its elements and what TalkBack said on them, and
what is left to judge marked `?`. The agent starts from it instead of from `findings.json`.

`preview` needs no device: render a `@Preview` with `android preview render <module> --component-tree
--output <folder> --fqn <preview>` and pass the folder. The rules read the semantics Compose builds and
the contrast of the image, and each finding names its file and line. It has no speech, no focus and no
touch targets.

`capture` warns you if the engine or the service isn't active. While you walk the screen it prints
each focus and what TalkBack says, one short line each, since TalkBack itself is silent. It writes
`audits/<date>/<screen>/` with `session.txt`, `screen-start.png`, `screen-end.png` and
`findings.json`, plus `notes.md` if you type a line before pressing Enter: what you tried and couldn't
do, which the log doesn't show. The tree is dumped at the start and again when you press Enter, because the screen
can change in between (a sheet opens, a list scrolls). The rules use the last dump, and only the
focus of the app in that dump: the keyboard and the system UI are left out. On the last dump the
service also runs ATF; its contrast checks need a screenshot, which an accessibility service can only
take from Android 11 (API 30). `audits/` holds screenshots of the audited app: keep it out of git, as
this repo does.

`keyboard` is for people who use a hardware keyboard (motor disabilities, tablets with a keyboard, Chromebooks, desktop modes), so turn TalkBack off first. Switch Access doesn't use keyboard focus: it walks the accessibility tree, like TalkBack. It presses TAB, dumps the tree
and takes a screenshot after each key (`keyboard/step-NN.png`), and stops when focus cycles back or
stops moving. Arrow-key navigation (carousels, grids) isn't walked.

### Driving TalkBack

`adb shell input` can't move TalkBack: it injects keys and touches after the accessibility input
filter, where TalkBack reads its gestures and keyboard shortcuts, so they reach the app as plain
input. A keyboard does go through that filter. `a11y-audit` makes one with the `hid` tool of the
device's shell (no root; `start` checks that it is there), and sends TalkBack's shortcuts with it:

```bash
a11y-audit talkback on              # keeps the other accessibility services
a11y-audit start checkout           # connects the keyboard, dumps the tree, prints <out>/<date>/checkout
a11y-audit press first              # TalkBack's first element in the window
a11y-audit press next --times 30    # stops early with "walk ended: cycle|stopped|left app"
a11y-audit goto "Sort"              # moves to the element whose name contains the text
a11y-audit press activate           # what a double tap does, then what focus did
a11y-audit look                     # screenshot, prints its path
a11y-audit stop                     # dumps again, disconnects, saves and runs the rules
a11y-audit talkback off
```

Each `press` prints what it produced: the focus (with its `actions`), what TalkBack said or
`(nothing spoken)`, clicks and window changes, or `(focus didn't move)`. `start` takes `--out` like
`capture`. `capture --auto` runs `start`, `first`, `next` until the walk ends, and `stop`.
`press`, `look` and `stop` act on the session `start` opened, or on `--dir`. To go back or type, use
`adb` directly: `adb shell input keyevent KEYCODE_BACK`, `adb shell input text …`. An injected
`adb shell input tap` reaches the app as a plain tap, also with TalkBack on.

What to know:
- The keyboard has no letter keys, so Android doesn't count it as a keyboard in the configuration
  and connecting it doesn't recreate the screen. Without letters TalkBack has no shortcut to
  activate, so the focus logger clicks the element TalkBack is on instead (`ACTION_CLICK`, what
  TalkBack's double tap sends).
- TalkBack's hints name the keyboard's selection key instead of a double tap. That comes from the
  keyboard, not from the app.
- `start` moves focus into the app's window before the session begins, because TalkBack's "first
  element" works within the window that has focus, which can be the navigation bar.
- After the last element, TalkBack goes back to the top of the window or stops moving; the walk ends
  there. An `ORDER_JUMP` on that last move comes from the walk, not from the app.
- TalkBack's shortcuts use Alt on some builds and Search on others (Google's TalkBack 17). The first
  key of a session tries both and keeps the one that moves focus.
- Each key is logged as `[key]`, so the rules know which focus moves were the walk's. After
  `press activate` the app is watched for at least 3 s and the tree is dumped again; then a line
  says whether focus stayed, moved on its own (`!!`) or was lost, and whether the element left the
  screen.
- A walk that passes a text field ends on the on-screen keyboard's keys (`walk ended: left app`).
  `goto` closes the keyboard before it starts from the top.
- Google's TalkBack asks to send notifications each time it starts until someone answers.
  `talkback on` closes that prompt with Back, unanswered, because it covers the app.
- The session's records are copied from `adb logcat` to a file while it is open: the device's log is
  not cleared, and a long session doesn't depend on what the device's buffer still holds.
- `activate` clicks the whole element TalkBack is on, so links inside a text can't be opened this way.

Or by hand:

```bash
adb logcat -s A11ySpeech:I -v raw                           # follow what TalkBack says, live
adb logcat -c                                               # start a clean session
adb shell am broadcast -a io.github.asanre.a11ylogger.DUMP  # snapshot the current screen's tree
adb logcat -d -s A11ySpeech:I -v raw > session.txt          # save and exit
```

## Report

With the agent started in the app's repo, ask for the audit, optionally pointing to the app's source
so each finding is located by its test tag:

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
| `[key]` | a walk driven from `adb` | `action` (`next`, `prev` or `first`): the key `a11y-audit` pressed |
| `[more]` | any record over 1000 characters | the rest of the record before it, in as many entries as it takes |
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
| `FOCUS_MOVED_AFTER_ACTION` | `audit.py` | 2.4.3 | advisory | After an activation focus went to another element with no key in between (within 1 s in a capture by hand, where keys aren't logged); the detail says where, how long after, and whether the activated element left the screen |
| `FOCUS_BOUNCED` | `audit.py` | 2.4.3 | failure | After an activation focus moved two or more times on its own |
| `FOCUS_LOST` | `audit.py` | 2.4.3 | failure | The activated element left the screen and nothing took TalkBack's focus |
| `NO_HEADING` | `audit.py` | 1.3.1, 2.4.6 | advisory | No node on the screen is a heading. WCAG doesn't require headings; it requires visual headings to be marked |
| `DUPLICATE_LABEL` | `audit.py` | 2.4.6, 2.4.4 | advisory | Several actionable elements share the same label |
| `ROLE_BEFORE_LABEL` | `audit.py` | 4.1.2, 2.5.3 | advisory | The utterance starts with a role word ("Button, Stop"), one the session shows trailing elsewhere ("Menu, Button") |
| `ORDER_JUMP` | `audit.py` | 1.3.2, 2.4.3 | advisory | Focus moved up more than 48dp; could also be a backwards swipe or a scroll. In a walk driven from `adb`, only after a forward key |
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
- In the walks driven from `adb`: links inside a text (`activate` clicks the whole text), TalkBack's
  menus (actions, links), and long-press. Long lists that scroll as TalkBack moves, and Google's
  TalkBack, haven't been tested yet.

## Caveats

- **Ids in Compose.** `id` is the `testTag`, and only when
  `Modifier.semantics { testTagsAsResourceId = true }` is set on an ancestor. Dialogs, popups and
  `ModalBottomSheet` are separate windows and need their own.
- **Tree order.** `[tree]` follows tree order, not TalkBack's traversal order. It excludes nodes that
  are not important for accessibility, just as TalkBack does.
- **Speech-to-focus matching is approximate.** Each focus owns what is spoken until the next one.
  Swiping very fast can shift utterances between neighbours.
- **Tested** on these two. Reports from other devices are welcome.

  | Device | Android | TalkBack | Tried with |
  |---|---|---|---|
  | A phone | 12 | 13.1, a vendor build (Alt shortcuts) | 0.2.0: captures by hand, the keyboard pass, the ATF results and the walks driven from `adb`. Not tried again with 0.3.0 |
  | An emulator, `Medium_Phone` | API 37 | 17.0, Google's (Search shortcuts) | 0.3.0: `audit`, `goto`, activations, `capture --now`, the keyboard pass and the ATF results |

- **Not yet tested on a device**: `expanded` and `required`, which need Android 16. Rules over them
  are covered by `python3 -m unittest tools/test_audit.py`.

## Releasing

The APK, the command and the skills ship together, and the command and the skills install from
`main`, so a version bump on `main` and its release go out in one step:

1. Bump `versionCode` and `versionName` in `app/build.gradle.kts`, `VERSION` and `APK_VERSION_CODE`
   in `skills/a11y-audit/scripts/a11y_audit/cli.py`, and `version` in `pyproject.toml` and
   `.claude-plugin/plugin.json`.
   `python3 -m unittest tools/test_audit.py` fails if they disagree.
2. Commit, then build, push `main` with the tag, and publish the APK:
   ```bash
   ./gradlew :app:assembleDebug
   ```
   ```bash
   cp app/build/outputs/apk/debug/app-debug.apk a11y-speech-logger-<version>.apk
   ```
   ```bash
   git tag v<version> && git push origin main v<version>
   ```
   ```bash
   gh release create v<version> a11y-speech-logger-<version>.apk
   ```

A plugin keeps its users on the `version` of `plugin.json` until that string changes, so a change to the
skills or the command only reaches them with a version bump.

The APK is signed with the debug key of the machine that builds it; build every release on the same
one, or installs over the previous release fail.

## License

[MIT](LICENSE)
