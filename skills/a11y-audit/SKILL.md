---
name: a11y-audit
description: Audits the accessibility of an Android screen against WCAG 2.2 A/AA and writes a report a developer can act on. Three modes - driving TalkBack on a connected device to capture the screen itself, from an a11y-speech-logger capture folder (session.txt, findings.json, screenshots), or from the screen's source code when there is no device. Use when asked to audit a screen or app on a device, to analyze or report on a capture under audits/, after running `a11y-audit capture` or `keyboard`, or to review a screen's code for accessibility. Optional argument - the path to the audited app's source repo, to locate each problem in the code.
---

# Accessibility audit of a screen

Pick one path from what you have, open its file and follow it step by step:

| You have | Path | File |
|---|---|---|
| One question about one element ("is this a heading?", "what does TalkBack say here?") | One question | below |
| A device or emulator in `adb devices`, and no capture yet | Device, then Capture | [references/device.md](references/device.md) |
| A capture folder (`audits/<date>/<screen>/`), or a date folder with several | Capture | [references/capture.md](references/capture.md) |
| No device, only the screen's source | Code | [references/code.md](references/code.md) |
| An issue to check after a fix | The `a11y-retest` skill | |

A capture shows what TalkBack really said: prefer it. The Code path finds less, and everything it
finds is *from code, not verified on device*.

## Rules for every path

- Run only `a11y-audit` and the commands the files give. Don't read the tool's source and don't swap a
  step for `uiautomator` or another tool: when a command fails, its error names the next command.
- Quote speech exactly as captured. Never paraphrase what TalkBack said.
- Don't report a problem you can't point to in the capture or the code.
- Never mark Pass without evidence.
- Failure only when the criterion is broken as written. Guidelines and good practice are advisory.
- For each fix, use the `compose-a11y` skill.

## One question

Answer it with the smallest capture, and no report.

- **About the element itself** (heading, role, name, state, size, contrast), with a device:
  ```bash
  a11y-audit setup
  a11y-audit capture <name> --now      # the screen as it is, about two seconds
  a11y-audit release
  ```
  Find the element under `tree` in `findings.json` and answer with its fields: `heading`, `class`,
  `text`, `desc`, `selected`, `size`. A field that is missing is a no.
- **About what TalkBack says or does**: `a11y-audit audit <name> --app <package>`, with
  `--activate "<element>"` when the question is what happens after a tap. Quote the lines it printed.
- **Without a device**: the Code path, on that element only. Say it is not verified on a device.
