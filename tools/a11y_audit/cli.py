"""Capture an accessibility session per screen and run deterministic rules over it.

  a11y-audit capture <screen> [--out audits] [--serial SERIAL]
      Clears logcat, dumps the node tree and takes a screenshot (screen-start.png), shows
      focus and speech live while you walk the screen with TalkBack, dumps and screenshots
      again when you press Enter (screen-end.png), runs the Accessibility Test Framework checks on
      that last dump, then saves session.txt and runs `rules`. A line typed before Enter is saved
      as notes.md, for the tester's own observations.

  a11y-audit keyboard <screen> [--steps 60] [--out audits] [--serial SERIAL]
      Walks the screen with TAB, as a keyboard user without TalkBack: dumps the tree and takes a
      screenshot (keyboard/step-NN.png) after each key, stops when focus cycles or stops moving,
      then saves session.txt and runs `rules`.

  a11y-audit capture <screen> --auto [--steps 60] [--out audits] [--serial SERIAL]
      Walks the screen with TalkBack on its own, from its first element until focus comes back to it,
      without activating anything. Same output as `capture`, without notes.md.

  a11y-audit start <screen> [--out audits] [--serial SERIAL]
  a11y-audit press next|prev|first|activate [--times N] [--dir DIR]
  a11y-audit look [--dir DIR]
  a11y-audit stop [--dir DIR]
      The same capture, one step per call, for an agent that drives TalkBack itself. `start` connects
      a virtual keyboard (the system's `hid` tool) whose keys TalkBack takes as its shortcuts and dumps
      the tree; `press` sends a shortcut and prints what it produced; `look` saves a screenshot;
      `stop` dumps again, disconnects the keyboard, saves session.txt and runs `rules`. Without
      --dir they act on the session `start` opened.

  a11y-audit talkback on|off [--serial SERIAL]
      Turns TalkBack on or off, keeping the other accessibility services.

  a11y-audit setup [--serial SERIAL]
  a11y-audit release [--serial SERIAL]
      `setup` gets the device ready to capture: makes the logger the default text-to-speech engine,
      turns A11y Focus Logger on and restarts TalkBack, if it is on, so it picks up the engine.
      `release` gives the device back when the audit is over: turns A11y Focus Logger off and
      restores the default text-to-speech engine. Both keep the other accessibility services.

  a11y-audit rules <dir>
      Parses <dir>/session.txt and writes <dir>/findings.json.

Only needs Python 3 and adb. The log format is described in the README.
"""

import argparse
import sys
import time

from .device import (
    adb,
    device_setup_problems,
    put_services,
    read_session,
    snapshot,
    talkback_component,
    version_code,
    warn_if_not_ready,
)
from .findings import rules
from .keyboard import input_focus_sequence, keyboard_ending
from .records import dumps, label, parse_record
from .talkback import FOCUS_LOGGER, PACKAGE, TALKBACK_KEYS, with_logger, with_service, without_logger
from .walk import follow, open_session, output_dir, press_keys, start_session, stop_session

# The APK this script talks to; bump it with versionCode in app/build.gradle.kts.
APK_VERSION_CODE = 2
RELEASES = "https://github.com/asanre/a11y-speech-logger/releases"


def talkback(args):
    services = adb(args.serial, "shell", "settings", "get", "secure", "enabled_accessibility_services")
    value = with_service(services, talkback_component(args.serial), args.state == "on")
    put_services(args.serial, value)
    time.sleep(2)  # TalkBack takes a moment to start or stop
    print(f"TalkBack {args.state}: {value or '(no services)'}")


def setup(args):
    install = (f"install the APK of the matching release from {RELEASES} (`adb install -r <apk>`), "
               "or run `./gradlew :app:installDebug` from a clone")
    if PACKAGE not in adb(args.serial, "shell", "pm", "list", "packages", PACKAGE):
        sys.exit(f"error: A11y Speech Logger is not installed; {install}")
    installed = version_code(adb(args.serial, "shell", "dumpsys", "package", PACKAGE))
    if installed != APK_VERSION_CODE:
        sys.exit(f"error: A11y Speech Logger {installed} is installed, a11y-audit needs {APK_VERSION_CODE}; {install}")
    adb(args.serial, "shell", "settings", "put", "secure", "tts_default_synth", PACKAGE)
    services = adb(args.serial, "shell", "settings", "get", "secure", "enabled_accessibility_services")
    value = with_logger(services)
    if "talkback" in services.casefold():  # TalkBack picks up the new engine only when it starts
        put_services(args.serial, with_service(value, talkback_component(args.serial), False))
        time.sleep(2)
    put_services(args.serial, value)
    time.sleep(2)  # the services take a moment to start
    if problems := device_setup_problems(args.serial):
        sys.exit("error: the setup didn't stay: " + "; ".join(problems) + ". Run `a11y-audit setup` again")
    print(f"Logger set up: default TTS engine and A11y Focus Logger. Services: {value}")


def release(args):
    services = adb(args.serial, "shell", "settings", "get", "secure", "enabled_accessibility_services")
    value = without_logger(services)
    put_services(args.serial, value)
    if adb(args.serial, "shell", "settings", "get", "secure", "tts_default_synth").strip() == PACKAGE:
        adb(args.serial, "shell", "settings", "delete", "secure", "tts_default_synth")
    print(f"A11y Focus Logger off, default TTS engine restored. Services: {value or '(none)'}")


def start(args):
    folder, _ = start_session(args.serial, args.out, args.screen)
    print(folder)


def press(args):
    folder, meta = open_session(args.dir)
    press_keys(folder, meta, args.action, args.times)


def look(args):
    folder, meta = open_session(args.dir)
    path = folder / f"look-{len(list(folder.glob('look-*.png'))) + 1:02}.png"
    path.write_bytes(adb(meta["serial"], "exec-out", "screencap", "-p", binary=True))
    print(path)


def stop(args):
    stop_session(*open_session(args.dir))


def capture(args):
    if args.auto:
        folder, meta = start_session(args.serial, args.out, args.screen)
        try:
            press_keys(folder, meta, "first", 1)
            press_keys(folder, meta, "next", args.steps)
        finally:
            stop_session(folder, meta)
        return
    warn_if_not_ready(args.serial)
    folder = output_dir(args.out, args.screen)
    adb(args.serial, "logcat", "-c")
    viewer = follow(args.serial)
    snapshot(args.serial, folder / "screen-start.png")
    print(f"Walk '{args.screen}' with TalkBack, then press Enter to save. Type a note first to keep it in notes.md.\n")
    note = input().strip()
    viewer.terminate()
    # Dumped again because the screen can change after the capture starts (a sheet opened, a scroll).
    snapshot(args.serial, folder / "screen-end.png", atf=True)
    session = read_session(args.serial, dumps=2, atf=True)
    (folder / "session.txt").write_text(session, encoding="utf-8")
    if note:
        (folder / "notes.md").write_text(note + "\n", encoding="utf-8")
    print(f"saved {folder}")
    rules(argparse.Namespace(dir=folder))


def keyboard(args):
    services = adb(args.serial, "shell", "settings", "get", "secure", "enabled_accessibility_services")
    if "talkback" in services.casefold():
        print("warning: TalkBack is on; keyboard users browse without it and TAB behaves differently", file=sys.stderr)
    if FOCUS_LOGGER not in services and f"{PACKAGE}/{PACKAGE}.FocusLoggerService" not in services:
        print("warning: A11y Focus Logger is not enabled, so nothing will be captured", file=sys.stderr)
    folder = output_dir(args.out, args.screen)
    steps = folder / "keyboard"
    steps.mkdir()
    adb(args.serial, "logcat", "-c")
    for step in range(args.steps + 1):
        if step:
            adb(args.serial, "shell", "input", "keyevent", "KEYCODE_TAB")
            time.sleep(0.5)
        snapshot(args.serial, steps / f"step-{step:02}.png")
        session = read_session(args.serial, dumps=step + 1)
        sequence = input_focus_sequence(dumps([r for r in map(parse_record, session.splitlines()) if r]))
        current = sequence[-1] if sequence else None
        name = (label(current) or current.get("id")) if current else "(no input focus)"
        print(f"{step:02} {name}", flush=True)
        if keyboard_ending(sequence):
            break
    (folder / "session.txt").write_text(session, encoding="utf-8")
    print(f"saved {folder}")
    rules(argparse.Namespace(dir=folder))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(required=True)
    cap = sub.add_parser("capture", help="capture a screen and run the rules")
    cap.add_argument("screen", help="name for the screen, used as folder name")
    cap.add_argument("--out", default="audits", help="base folder (default: audits)")
    cap.add_argument("--serial", help="adb device serial, when more than one is connected")
    cap.add_argument("--auto", action="store_true", help="walk the screen with TalkBack on its own")
    cap.add_argument("--steps", type=int, default=60, help="with --auto, maximum number of moves (default: 60)")
    cap.set_defaults(func=capture)
    sta = sub.add_parser("start", help="open a capture driven step by step (for an agent)")
    sta.add_argument("screen", help="name for the screen, used as folder name")
    sta.add_argument("--out", default="audits", help="base folder (default: audits)")
    sta.add_argument("--serial", help="adb device serial, when more than one is connected")
    sta.set_defaults(func=start)
    pre = sub.add_parser("press", help="send a TalkBack shortcut and print what it produced")
    pre.add_argument("action", choices=[*TALKBACK_KEYS, "activate"])
    pre.add_argument("--times", type=int, default=1, help="presses; going next, stops when the walk ends")
    pre.add_argument("--dir", help="session folder (default: the open one)")
    pre.set_defaults(func=press)
    loo = sub.add_parser("look", help="save a screenshot in the session folder and print its path")
    loo.add_argument("--dir", help="session folder (default: the open one)")
    loo.set_defaults(func=look)
    sto = sub.add_parser("stop", help="dump again, disconnect the keyboard, save and run the rules")
    sto.add_argument("--dir", help="session folder (default: the open one)")
    sto.set_defaults(func=stop)
    tal = sub.add_parser("talkback", help="turn TalkBack on or off, keeping the other services")
    tal.add_argument("state", choices=["on", "off"])
    tal.add_argument("--serial", help="adb device serial, when more than one is connected")
    tal.set_defaults(func=talkback)
    set_ = sub.add_parser("setup", help="make the logger the TTS engine and turn A11y Focus Logger on")
    set_.add_argument("--serial", help="adb device serial, when more than one is connected")
    set_.set_defaults(func=setup)
    rel = sub.add_parser("release", help="turn A11y Focus Logger off and restore the default TTS engine")
    rel.add_argument("--serial", help="adb device serial, when more than one is connected")
    rel.set_defaults(func=release)
    key = sub.add_parser("keyboard", help="walk a screen with TAB and check keyboard access")
    key.add_argument("screen", help="name for the screen, used as folder name")
    key.add_argument("--steps", type=int, default=60, help="maximum number of TABs (default: 60)")
    key.add_argument("--out", default="audits", help="base folder (default: audits)")
    key.add_argument("--serial", help="adb device serial, when more than one is connected")
    key.set_defaults(func=keyboard)
    rul = sub.add_parser("rules", help="run the rules over a captured folder")
    rul.add_argument("dir", help="folder with session.txt")
    rul.set_defaults(func=rules)
    args = parser.parse_args()
    args.func(args)
