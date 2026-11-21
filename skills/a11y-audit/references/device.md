# Device mode: capture the screen yourself

One command walks the screen with TalkBack, as a TalkBack user would. You then audit the folder it
produced with the Capture mode. Captures go to `audits/` in the current folder: run the commands from
the audited app's repo, or pass `--out`. How the walk works is in the README's
[Driving TalkBack](https://github.com/asanre/a11y-speech-logger#driving-talkback).

Use only `a11y-audit` and the `adb` commands written here. Don't read the tool's source and don't
replace a step with `uiautomator` or other commands: when something fails, the error says what to run.

## 1. Reach the screen

Ask the user which screen and state to audit, unless they said. If it is not open:
- with a deep link the user gives you: `adb shell am start -a android.intent.action.VIEW -d "<link>"`;
- or with taps: `adb shell input tap <x> <y>`. Take a screenshot first
  (`adb exec-out screencap -p > <scratch>.png`) to find the coordinates.

Never sign in, type credentials or fill personal data: ask the user to do it.

## 2. Walk it

```bash
a11y-audit audit <screen> --app <the app's package>
```

It sets the device up, turns TalkBack on, walks the screen from the first element, saves the capture,
runs the rules and gives the device back. Read its output:

| You see | It means | Do |
|---|---|---|
| `error: …` and exit status 2 | The device isn't ready | Run the command the error names, then `audit` again. `a11y-audit doctor` lists everything that isn't ready |
| `error: the window on top belongs to …` | A dialog or another app covers the screen | Close it (`adb shell input keyevent KEYCODE_BACK`) or open the app, then `audit` again |
| `error: the logger's APK couldn't be downloaded` | No access to GitHub | Stop and give the user the line it prints |
| `→ <class> "<name>" [bounds] actions="…" [issues]`, then quoted lines | An element TalkBack focused, and what TalkBack said | Nothing: this is the evidence |
| `(nothing spoken)` | TalkBack was silent on that element | Nothing: the rules report it |
| `walk ended: cycle` or `stopped` | The walk reached the end of the screen | Nothing |
| `walk ended: left app` | Focus went to the keyboard or the system bars | Nothing, unless elements of the app were left out: compare with `screen-end.png` |
| `saved <folder>` and `findings: …` | The capture is in `<folder>` | Go to step 3 or 4 |

Hints that name the keyboard's selection key ("Press select to activate") come from the virtual
keyboard: never report them.

## 3. Try what changes the state

List the elements whose state matters: chips, tabs, filters, dropdowns, expandable sections, the
options of a chat, a dialog's buttons. Then run `audit` again on the same screen, in its starting
state, naming each one:

```bash
a11y-audit audit <screen>-states --app <package> --activate "<name>" --activate "<other name>"
```

After the walk it goes to each element by its name, activates it and says what focus did:

| You see | It means |
|---|---|
| `(focus stayed on '<name>')` | Fine, if TalkBack also said the new state. Check the lines above it |
| `!! focus moved on its own to …, N ms after the activation` | The app moved focus. It is a problem unless it landed on the result of the action |
| `!! focus moved N times on its own` | A problem: the user is thrown around the screen |
| `!! focus lost: … left the screen and nothing took TalkBack's focus` | A problem: the user is nowhere |
| `(a new window opened)` | A dialog or another screen. Audit it in a run of its own if the user wants it |
| `(nothing was activated: the element has no click action)` | The element can't be activated by TalkBack. Report it if it looks like a control |
| `!! not reached, so not activated` | No element has that name. Check the name against the walk's output |

An activation that changes the screen stays for the ones after it: when two elements exclude each
other (two chat options), use one run for each.

- **Ask the user before activating** anything that buys, pays, sends a message or a form, deletes,
  resets, signs out or changes the account or settings. Labels like "Buy", "Send", "Delete",
  "Reset", "Restart" or "Sign out", in any language, are a stop. So are elements that send without
  saying it (a suggestion chip in a chat sends its question; a mic may send what it hears) and
  elements whose `actions` close or leave the screen.
- If you can't activate (the user said no, or your environment refused it), don't work around it with
  taps: list the element under *Not tested*.
- Links inside a text (TalkBack: "links available") can't be opened this way. List them under
  *Not tested*, with the link names TalkBack read.

What an activation did goes in the problem's **Evidence** as *observed while walking*, with the line
the command printed.

## 4. The keyboard pass, optional

With the screen in its starting state: `a11y-audit setup`, `a11y-audit keyboard <screen>-keyboard`,
`a11y-audit release`.

Then follow the Capture mode on the folder (and the keyboard folder).

## Step by step, when one command isn't enough

For a state you can only reach by walking (a field to fill between two activations):

```bash
a11y-audit setup
a11y-audit talkback on
a11y-audit start <screen>          # prints the folder and the window on top
a11y-audit goto "<name>"           # moves to that element; never count presses
a11y-audit press activate          # prints what focus did
a11y-audit press next --times 10
a11y-audit look                    # a screenshot, when the output isn't what you expected
a11y-audit stop                    # always, even after an error: it disconnects the keyboard
a11y-audit talkback off            # if it was off before
a11y-audit release                 # always: a service left on skews performance measurements
```

Close a dialog, menu or keyboard with `adb shell input keyevent KEYCODE_BACK`. Type into a field with
`adb shell input text "<text>"` (spaces as `%s`). Get to an element with `goto`, `press next` or
`press prev`; never by tapping, which bypasses TalkBack.

## What is different from a walk by hand

- An `ORDER_JUMP` on the move from the last element back to the top comes from the walk. Dismiss it.
- `look-NN.png` are the screenshots you took to find your way; the rules don't use them, but you can
  cite them.
- There is no `notes.md`.

## If it can't run

- `audit` says the device has no `hid` tool: ask the user to walk the screen by hand with
  `a11y-audit capture <screen>` ([README, Quick start](https://github.com/asanre/a11y-speech-logger#quick-start),
  step 2), then continue with the Capture mode.
- No device: use the Code mode.
