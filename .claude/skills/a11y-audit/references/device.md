# Device mode: drive the capture yourself

You walk the screen with TalkBack from `adb`, as a TalkBack user would, then audit the folder you
produced with the Capture mode. Run every command from the repo root. How the walk works and why is in
the README's "Driving TalkBack".

## 1. Check the device

- `adb devices` lists one device (pass `--serial` to `start` and `talkback` when there are several).
- `adb shell settings get secure tts_default_synth` is `io.github.asanre.a11ylogger`, and
  `adb shell settings get secure enabled_accessibility_services` contains `FocusLoggerService`.
  If not, stop and send the user to the README's Quick start, step 1: it is done once, on the device.
- Note whether TalkBack is on (`talkback` in that list), to leave it as you found it.

## 2. Reach the screen

Ask the user which screen and state to audit, unless they said. If they say it is already open, check
it with a `look` after `start`. If it is not open:
- with a deep link the user gives you: `adb shell am start -a android.intent.action.VIEW -d "<link>"`;
- or with taps: `adb shell input tap <x> <y>` reaches the app as a plain tap, also with TalkBack on.
  Take a screenshot first (`adb exec-out screencap -p > <scratch>.png`) to find the coordinates.

Never sign in, type credentials or fill personal data: ask the user to do it.

## 3. Walk it

```bash
python3 tools/audit.py talkback on        # if it was off
python3 tools/audit.py start <screen>     # --out <folder> to write elsewhere than audits/
python3 tools/audit.py look               # check that the screen is the right one
python3 tools/audit.py press first
python3 tools/audit.py press next --times 40
```

- `start` prints the capture folder: `<out>/<date>/<screen>/`. Before the session begins it puts
  TalkBack's focus on the window's last node (often a tiny or invisible one), so a `FOCUSED` in the first
  dump is the tool's doing, not the app's.
- Each press prints `→ <class> "<label>" [bounds] actions="…" [issues]`, then what TalkBack said,
  quoted. `(nothing spoken)` means TalkBack was silent on that element; `(focus didn't move)` means
  the press changed nothing. `actions` are the labels of what the element does (a click label, custom
  actions): read them before activating.
- `walk ended: cycle` (back on the first element), `stopped` (focus stopped moving) or `left app`
  (the system bars). `stopped` on the last element at the bottom of the screen is the normal end;
  with elements left below it in a `look`, it is a trap. The next `press next` starts a new walk.
- If the screen scrolls, TalkBack scrolls it as it moves. Take a `look` when the output doesn't match
  what you expected.

## 4. Try what changes the state

Go to each element whose state matters for the audit, `press activate`, read what happened, and walk
the new state with `press next` until the walk ends. Typical ones: chips, tabs, filters, dropdowns,
expandable sections, a field (it should open the keyboard), a dialog's buttons.

- Get to an element with `press next` or `press prev`; never by tapping, which bypasses TalkBack.
- After `activate`, check where focus went: on the result of the action, or lost to the top.
- Close a dialog, menu or keyboard with `adb shell input keyevent KEYCODE_BACK`. Type into a field
  with `adb shell input text "<text>"` (spaces as `%s`).
- **Ask the user before activating** anything that buys, pays, sends a message or a form, deletes,
  resets, signs out or changes the account or settings. Labels like "Buy", "Send", "Delete",
  "Reset", "Restart" or "Sign out", in any language, are a stop. So are elements that send without
  saying it (a suggestion chip in a chat sends its question; a mic may send what it hears) and
  elements whose `actions` close or leave the screen (a sheet's drag handle that "closes the sheet").
- If you can't activate (the user said no, or your environment refused it), don't work around it with
  taps: list the element under *Not tested*.
- Links inside a text (TalkBack: "links available") can't be opened with `press activate`, which
  clicks the whole text. List them under *Not tested*, with the link names TalkBack read.
- Stay on this screen. If an activation opens another screen, go back and note it; audit that screen
  in a session of its own if the user wants it.

Write down, as you go, what you tried and what happened: what the log can't show (you couldn't find
an action, the keyboard didn't open). In the report it goes in the problem's **Evidence** as *observed
while walking*, never as a tester note.

## 5. Close

```bash
python3 tools/audit.py stop
python3 tools/audit.py talkback off      # if it was off before
```

`stop` prints the folder and the findings. If anything failed before `stop`, run `stop` anyway: it
disconnects the keyboard.

Optionally run the keyboard pass on the same screen, with TalkBack off:
`python3 tools/audit.py keyboard <screen>-keyboard`.

Then follow the Capture mode on the folder (and the keyboard folder).

## What is different from a walk by hand

- TalkBack's hints name the keyboard's selection key ("press the selection key to activate"), not a
  double tap. That comes from the virtual keyboard: don't report it.
- An `ORDER_JUMP` on the move from the last element back to the top, by the wrap or by a
  `press first`, comes from the walk. Dismiss it.
- `look-NN.png` are the screenshots you took to find your way; the rules don't use them, but you can
  cite them.
- There is no `notes.md`.

## If it can't run

- `start` says the device has no `hid` tool: ask the user to walk the screen by hand with
  `python3 tools/audit.py capture <screen>` (README, Quick start, step 2), then continue with the
  Capture mode.
- No device: use the Code mode.
