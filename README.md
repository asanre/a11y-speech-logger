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
  - window changes (`[window]`) and announcements (`[announce]`);
  - the screen's node tree on request (`[tree]`).

On top of the APK:

- **`tools/audit.py`**: captures a session per screen and runs deterministic rules.
- **`.claude/skills/a11y-audit`**: a [Claude Code](https://claude.com/claude-code) skill that turns a
  capture into a report, with WCAG references and Compose fixes.

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
python3 tools/audit.py capture checkout   # dumps the tree, screenshots, waits while you walk the screen
python3 tools/audit.py rules audits/2026-10-01/checkout   # re-run the rules on an existing capture
```

`capture` warns you if the engine or the service isn't active. It writes
`audits/<date>/<screen>/` with `session.txt`, `screen.png` and `findings.json`. `audits/` is
gitignored because it contains screenshots of the audited app.

Or by hand:

```bash
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
- writes `report.md` with severity, the exact speech, the WCAG criterion and the Compose fix.

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
| `[tree]` | `DUMP` broadcast | `begin pkg=…`, one indented node per line (`FOCUSED` marks the current focus), `end nodes=N` |

Node fields, present only when they apply:
- **Identity**: `id` (`-` if none), `class`, `text`, `desc`, `role`.
- **State**: `state`, `hint`, `error`, `checked`, `heading`, `selected`, `disabled`.
- **Actions**: `clickable`, `longclickable`, `actions` (action labels, e.g. `onClickLabel` or custom
  actions).
- **Geometry**: `bounds` (px), `size` (dp).
- **Issues**: `issues` (below).

### Rules

All of them are heuristics to verify, not verdicts.

| Rule | Where | Severity | Meaning |
|---|---|---|---|
| `NO_LABEL` | APK | high | Actionable, with no text, description or children to read from |
| `LABEL_IN_CHILD` | APK | medium | Actionable without its own label; the only label is the content description of a non-actionable child (an icon button with the description on the icon) |
| `EDIT_NO_HINT` | APK | medium | Empty `EditText` without a hint, e.g. a placeholder drawn as a separate text |
| `SMALL_TARGET` | APK | medium | Actionable and smaller than 48dp on one side |
| `SILENT_FOCUS` | `audit.py` | high | An element got focus and TalkBack said nothing for 1.5 s |
| `NO_HEADING` | `audit.py` | medium | No node on the screen is a heading |
| `DUPLICATE_LABEL` | `audit.py` | medium | Several actionable elements share the same label |
| `REPEATED_ROLE` | `audit.py` | low | The role TalkBack appends ("…, Button", in any language) already appears in the label ("Add button, Button") |
| `ORDER_JUMP` | `audit.py` | low | Focus moved up more than 48dp; could also be a backwards swipe or a scroll |

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

## License

[MIT](LICENSE)
