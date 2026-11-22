"""Capture an accessibility session per screen and run deterministic rules over it.

  a11y-audit doctor [--serial SERIAL]
      Says whether the device is ready, one line per check, with the command that fixes each problem.

  a11y-audit audit <screen> [--app PACKAGE] [--activate LABEL]... [--steps 60] [--out audits] [--serial SERIAL]
      The whole audit of the screen that is open, in one command: sets the device up, turns TalkBack
      on, walks the screen with it, activates each element named with --activate and says what
      happened to focus, saves the capture, runs `rules` and gives the device back. --app stops it
      when the window on top belongs to another package (a system dialog, another app).

  a11y-audit capture <screen> [--now] [--out audits] [--serial SERIAL]
      Dumps the node tree and takes a screenshot (screen-start.png), shows focus and speech live
      while you walk the screen with TalkBack, dumps and screenshots again when you press Enter
      (screen-end.png), runs the Accessibility Test Framework checks on that last dump, then saves
      session.txt and runs `rules`. A line typed before Enter is saved as notes.md, for the tester's
      own observations. --now doesn't wait for a walk: the tree, the ATF checks and the contrast of
      the screen as it is, with or without TalkBack.

  a11y-audit keyboard <screen> [--steps 60] [--out audits] [--serial SERIAL]
      Walks the screen with TAB, as a keyboard user without TalkBack: dumps the tree and takes a
      screenshot (keyboard/step-NN.png) after each key, stops when focus cycles or stops moving,
      then saves session.txt and runs `rules`.

  a11y-audit capture <screen> --auto [--steps 60] [--out audits] [--serial SERIAL]
      Walks the screen with TalkBack on its own, from its first element until focus comes back to it,
      without activating anything. Same output as `capture`, without notes.md.

  a11y-audit start <screen> [--out audits] [--serial SERIAL]
  a11y-audit press next|prev|first|activate [--times N] [--dir DIR]
  a11y-audit goto <label> [--dir DIR]
  a11y-audit look [--dir DIR]
  a11y-audit stop [--dir DIR]
      The same capture, one step per call, for an agent that drives TalkBack itself. `start` connects
      a virtual keyboard (the system's `hid` tool) whose keys TalkBack takes as its shortcuts and dumps
      the tree; `press` sends a shortcut and prints what it produced (after `activate`, also what
      happened to focus); `goto` moves to the element with that name; `look` saves a screenshot;
      `stop` dumps again, disconnects the keyboard, saves session.txt and runs `rules`. Without
      --dir they act on the session `start` opened.

  a11y-audit talkback on|off [--serial SERIAL]
      Turns TalkBack on or off, keeping the other accessibility services.

  a11y-audit setup [--apk FILE] [--serial SERIAL]
  a11y-audit release [--serial SERIAL]
      `setup` gets the device ready to capture: installs the logger's APK when it is missing or
      another version (from --apk, or from the release), makes it the default text-to-speech engine,
      turns A11y Focus Logger on and restarts TalkBack, if it is on, so it picks up the engine.
      `release` gives the device back when the audit is over: turns A11y Focus Logger off and
      restores the default text-to-speech engine. Both keep the other accessibility services.

  a11y-audit rules <dir>
      Parses <dir>/session.txt and writes <dir>/findings.json.

Exit status: 0 when the command ran, with or without findings; 2 when the device or the session
isn't ready, with the command that fixes it.

Only needs Python 3 and adb. The log format is described in the README.
"""

import argparse
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from .device import (
    LOG_FILE,
    SERVICE_TIMEOUT_S,
    NotReady,
    adb,
    device_setup_problems,
    focused_window,
    put_services,
    read_session,
    snapshot,
    stop_process,
    stream_log,
    talkback_component,
    talkback_running,
    version_code,
    wait_until,
    warn_if_not_ready,
)
from .findings import rules
from .keyboard import input_focus_sequence, keyboard_ending
from .records import dumps, label, parse_lines
from .talkback import FOCUS_LOGGER, PACKAGE, TALKBACK_KEYS, setup_problems, with_logger, with_service, without_logger
from .walk import discard_session, follow, goto, open_session, output_dir, press_keys, start_session, stop_session

# The release this command belongs to, and the APK it talks to; bump them with versionName and
# versionCode in app/build.gradle.kts.
VERSION = "0.3.0"
APK_VERSION_CODE = 3
RELEASES = "https://github.com/asanre/a11y-speech-logger/releases"
# How long TalkBack's permission prompt is waited for after TalkBack turns on.
PERMISSION_PROMPT_S = 2


def required_talkback(serial):
    component = talkback_component(serial)
    if not component:
        raise NotReady("TalkBack is not installed on this device")
    return component


def close_permission_prompt(serial):
    """Google's TalkBack asks to send notifications each time it starts until it is answered. The
    prompt covers the app and the logger can't read it, so it is closed with Back, unanswered."""
    _, asked = wait_until(lambda: focused_window(serial), lambda window: "permissioncontroller" in window,
                          PERMISSION_PROMPT_S, poll=0.3)
    if asked:
        adb(serial, "shell", "input", "keyevent", "KEYCODE_BACK")
        wait_until(lambda: focused_window(serial), lambda window: "permissioncontroller" not in window, 3, poll=0.3)
        print("note: closed TalkBack's prompt to send notifications, without answering it")


def talkback(args):
    on = args.state == "on"
    services = adb(args.serial, "shell", "settings", "get", "secure", "enabled_accessibility_services")
    value = with_service(services, required_talkback(args.serial), on)
    put_services(args.serial, value)
    _, done = wait_until(lambda: talkback_running(args.serial), lambda running: running == on, SERVICE_TIMEOUT_S, poll=0.3)
    if not done:
        raise NotReady(f"TalkBack didn't turn {args.state} in {SERVICE_TIMEOUT_S} s; run `a11y-audit talkback {args.state}` again")
    print(f"TalkBack {args.state}: {value or '(no services)'}")
    if on:
        close_permission_prompt(args.serial)


def installed_apk(serial):
    """The version code of the logger's APK on the device, or None when it isn't installed."""
    if PACKAGE not in adb(serial, "shell", "pm", "list", "packages", PACKAGE):
        return None
    return version_code(adb(serial, "shell", "dumpsys", "package", PACKAGE))


def apk_url(version):
    return f"{RELEASES}/download/v{version}/a11y-speech-logger-{version}.apk"


def install_apk(serial, apk):
    """Installs the logger's APK: the file given, or the one of this command's release."""
    by_hand = (f"download the APK of release {VERSION} from {RELEASES} and pass it with `a11y-audit setup --apk <file>`, "
               "or run `./gradlew :app:installDebug` from a clone")
    if apk:
        if not Path(apk).is_file():
            raise NotReady(f"{apk} is not a file; {by_hand}")
        adb(serial, "install", "-r", str(apk))
        return
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "a11y-speech-logger.apk"
        try:
            urllib.request.urlretrieve(apk_url(VERSION), target)
        except (urllib.error.URLError, OSError) as error:
            raise NotReady(f"the logger's APK couldn't be downloaded ({error}); {by_hand}") from None
        adb(serial, "install", "-r", str(target))


def setup(args):
    installed = installed_apk(args.serial)
    if installed != APK_VERSION_CODE:
        install_apk(args.serial, getattr(args, "apk", None))
        print(f"A11y Speech Logger {VERSION} installed" + (f" over version code {installed}" if installed else ""))
    adb(args.serial, "shell", "settings", "put", "secure", "tts_default_synth", PACKAGE)
    services = adb(args.serial, "shell", "settings", "get", "secure", "enabled_accessibility_services")
    value = with_logger(services)
    if "talkback" in services.casefold():  # TalkBack picks up the new engine only when it starts
        put_services(args.serial, with_service(value, required_talkback(args.serial), False))
        wait_until(lambda: talkback_running(args.serial), lambda running: not running, SERVICE_TIMEOUT_S, poll=0.3)
    put_services(args.serial, value)
    problems, _ = wait_until(lambda: device_setup_problems(args.serial), lambda found: not found, SERVICE_TIMEOUT_S, poll=0.3)
    if problems:
        raise NotReady("the setup didn't stay: " + "; ".join(problems) + ". Run `a11y-audit setup` again")
    print(f"Logger set up: default TTS engine and A11y Focus Logger. Services: {value}")


def release(args):
    services = adb(args.serial, "shell", "settings", "get", "secure", "enabled_accessibility_services")
    value = without_logger(services)
    put_services(args.serial, value)
    if adb(args.serial, "shell", "settings", "get", "secure", "tts_default_synth").strip() == PACKAGE:
        adb(args.serial, "shell", "settings", "delete", "secure", "tts_default_synth")
    print(f"A11y Focus Logger off, default TTS engine restored. Services: {value or '(none)'}")


def doctor_report(facts):
    """One (ok, line) per check of the device, each problem with the command that fixes it."""
    apk, services = facts["apk"], facts["services"]
    if apk is None:
        apk_line = (False, "A11y Speech Logger is not installed: run `a11y-audit setup`")
    elif apk != APK_VERSION_CODE:
        apk_line = (False, f"A11y Speech Logger is version code {apk}, a11y-audit needs {APK_VERSION_CODE}: run `a11y-audit setup`")
    else:
        apk_line = (True, f"A11y Speech Logger {VERSION} is installed")
    problems = setup_problems(facts["engine"], services)
    if not facts["talkback"]:
        talkback_line = (False, "TalkBack is not installed on this device")
    elif "talkback" not in services.casefold():
        talkback_line = (False, "TalkBack is off: run `a11y-audit talkback on` (`a11y-audit audit` does it itself)")
    else:
        talkback_line = (True, f"TalkBack is on ({facts['talkback']})")
    return [
        (True, f"device {facts['device']}"),
        apk_line,
        *([(False, f"{problem}: run `a11y-audit setup`") for problem in problems]
          or [(True, "the logger is the default TTS engine and A11y Focus Logger is on")]),
        talkback_line,
        (True, "the `hid` tool is there, so TalkBack can be driven") if facts["hid"]
        else (False, "no `hid` tool, so TalkBack can't be driven: walk the screen by hand with `a11y-audit capture`"),
    ]


def doctor(args):
    serial = args.serial
    report = doctor_report({
        "device": adb(serial, "get-serialno").strip(),
        "apk": installed_apk(serial),
        "engine": adb(serial, "shell", "settings", "get", "secure", "tts_default_synth"),
        "services": adb(serial, "shell", "settings", "get", "secure", "enabled_accessibility_services"),
        "talkback": talkback_component(serial),
        "hid": bool(adb(serial, "shell", "command -v hid || true").strip()),
    })
    for ok, line in report:
        print(f"{'ok ' if ok else 'fix'}  {line}")
    if not all(ok for ok, _ in report):
        sys.exit(2)


def window_line(meta):
    return f"window: {meta['pkg']} \"{meta.get('window') or ''}\""


def start(args):
    folder, meta = start_session(args.serial, args.out, args.screen)
    print(folder)
    print(window_line(meta))


def press(args):
    folder, meta = open_session(args.dir)
    press_keys(folder, meta, args.action, args.times)


def go(args):
    folder, meta = open_session(args.dir)
    if not goto(folder, meta, args.label):
        raise NotReady(f"the walk ended without reaching an element named {args.label!r}; check the screen with `a11y-audit look`")


def look(args):
    folder, meta = open_session(args.dir)
    path = folder / f"look-{len(list(folder.glob('look-*.png'))) + 1:02}.png"
    path.write_bytes(adb(meta["serial"], "exec-out", "screencap", "-p", binary=True))
    print(path)


def stop(args):
    stop_session(*open_session(args.dir))


def walk(args, activate=()):
    """Walks the open screen with TalkBack from its first element, then activates each named element."""
    folder, meta = start_session(args.serial, args.out, args.screen)
    print(window_line(meta))
    app = getattr(args, "app", None)
    if app and meta["pkg"] != app:
        discard_session(folder, meta)
        raise NotReady(f"the window on top belongs to {meta['pkg']} (\"{meta.get('window') or ''}\"), not to {app}, so "
                       "nothing was captured: close it or open the app, then run the command again")
    try:
        press_keys(folder, meta, "first", 1)
        press_keys(folder, meta, "next", args.steps)
        for name in activate:
            print(f"activate {name!r}:")
            if goto(folder, meta, name):
                press_keys(folder, meta, "activate", 1)
            else:
                print("!! not reached, so not activated")
    finally:
        stop_session(folder, meta)


def audit(args):
    setup(args)
    services = adb(args.serial, "shell", "settings", "get", "secure", "enabled_accessibility_services")
    was_on = "talkback" in services.casefold()
    try:
        if not was_on:
            talkback(argparse.Namespace(serial=args.serial, state="on"))
        walk(args, args.activate)
    finally:
        if not was_on:
            talkback(argparse.Namespace(serial=args.serial, state="off"))
        release(args)


def capture(args):
    if args.auto:
        walk(args)
        return
    warn_if_not_ready(args.serial)
    folder = output_dir(args.out, args.screen)
    log = folder / LOG_FILE
    copying = stream_log(args.serial, log)
    try:
        snapshot(args.serial, folder / "screen-start.png")
        note = ""
        if not args.now:
            viewer = follow(log)
            print(f"Walk '{args.screen}' with TalkBack, then press Enter to save. Type a note first to keep it in notes.md.\n")
            note = input().strip()
            viewer.set()
        # Dumped again because the screen can change after the capture starts (a sheet opened, a scroll).
        snapshot(args.serial, folder / "screen-end.png", atf=True)
        session = read_session(log, dumps=2, atf=True)
    finally:
        stop_process(copying)
        log.unlink(missing_ok=True)
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
    log = folder / LOG_FILE
    copying = stream_log(args.serial, log)
    try:
        for step in range(args.steps + 1):
            if step:
                adb(args.serial, "shell", "input", "keyevent", "KEYCODE_TAB")
                time.sleep(0.5)
            snapshot(args.serial, steps / f"step-{step:02}.png")
            session = read_session(log, dumps=step + 1)
            sequence = input_focus_sequence(dumps(parse_lines(session)))
            current = sequence[-1] if sequence else None
            name = (label(current) or current.get("id")) if current else "(no input focus)"
            print(f"{step:02} {name}", flush=True)
            if keyboard_ending(sequence):
                break
    finally:
        stop_process(copying)
        log.unlink(missing_ok=True)
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
    cap.add_argument("--now", action="store_true", help="don't wait for a walk: capture the screen as it is")
    cap.set_defaults(func=capture)
    aud = sub.add_parser("audit", help="set up, walk the screen with TalkBack, save, run the rules and release")
    aud.add_argument("screen", help="name for the screen, used as folder name")
    aud.add_argument("--app", help="the audited app's package: stop if the window on top isn't its own")
    aud.add_argument("--activate", action="append", default=[], metavar="LABEL",
                     help="after the walk, activate the element with this name and report what focus does; repeatable")
    aud.add_argument("--steps", type=int, default=60, help="maximum number of moves (default: 60)")
    aud.add_argument("--apk", help="the logger's APK to install when it is missing, instead of downloading it")
    aud.add_argument("--out", default="audits", help="base folder (default: audits)")
    aud.add_argument("--serial", help="adb device serial, when more than one is connected")
    aud.set_defaults(func=audit)
    doc = sub.add_parser("doctor", help="check that the device is ready and say how to fix what isn't")
    doc.add_argument("--serial", help="adb device serial, when more than one is connected")
    doc.set_defaults(func=doctor)
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
    got = sub.add_parser("goto", help="move TalkBack to the element whose name contains the text")
    got.add_argument("label", help="text of the element's name, in any case")
    got.add_argument("--dir", help="session folder (default: the open one)")
    got.set_defaults(func=go)
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
    set_.add_argument("--apk", help="the logger's APK to install when it is missing, instead of downloading it")
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
    try:
        args.func(args)
    except NotReady as problem:
        print(f"error: {problem}", file=sys.stderr)
        sys.exit(2)
