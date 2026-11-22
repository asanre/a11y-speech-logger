"""A capture session: the virtual keyboard, the presses and what each one produced."""

import argparse
import datetime
import json
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from .device import (
    DUMP_ACTION,
    LOG_FILE,
    NotReady,
    adb,
    adb_cmd,
    alive,
    dump_count,
    focused_window,
    hide_keyboard,
    log_key,
    read_session,
    records_of,
    session_text,
    snapshot,
    stop_process,
    stream_log,
    wait_quiet,
    wait_until,
    warn_if_not_ready,
)
from .findings import rules
from .keyboard import KEYBOARD_STUCK_STEPS, keyboard_ending
from .records import dumps, joined, label, parse_record
from .rules import activations, name_or_place
from .talkback import PACKAGE, key_reports, moved_by_talkback, talkback_major, talkback_modifiers

FOCUS_WINDOW_ACTION = f"{PACKAGE}.FOCUS_WINDOW"
ACTIVATE_ACTION = f"{PACKAGE}.ACTIVATE"
ACTIVE_SESSION = Path.home() / ".cache" / "a11y-speech-logger" / "active"
KEYBOARD_NAME = "A11y Audit Keyboard"
# A USB keyboard with modifiers, Enter, Tab and arrows (usages 0x28-0x52) but no letters: Android
# then doesn't count it as a keyboard in the configuration, so connecting it doesn't recreate the
# activity on screen. Report: modifier bits, a reserved byte, six key usages.
HID_DESCRIPTOR = [
    0x05, 0x01, 0x09, 0x06, 0xA1, 0x01,
    0x05, 0x07, 0x19, 0xE0, 0x29, 0xE7, 0x15, 0x00, 0x25, 0x01, 0x75, 0x01, 0x95, 0x08, 0x81, 0x02,
    0x95, 0x01, 0x75, 0x08, 0x81, 0x01,
    0x95, 0x06, 0x75, 0x08, 0x15, 0x28, 0x25, 0x52, 0x05, 0x07, 0x19, 0x28, 0x29, 0x52, 0x81, 0x00,
    0xC0,
]
# How long a key is given to move TalkBack's focus, and a focus to be spoken: a stop with no speech
# for this long counts as SILENT_FOCUS.
TALKBACK_STEP_S = 1.5
# Speech is over when nothing is said for this long. TalkBack's usage hint comes 0.4 s after the name.
SPEECH_QUIET_S = 0.6
# Time for Android to add the virtual keyboard before the first key.
KEYBOARD_SETTLE_S = 5
# After an activation the app is watched for at least this long, then until nothing happens for
# ACTIVATION_QUIET_S: a chat answers a second or two after the tap.
ACTIVATION_MIN_S = 3
ACTIVATION_QUIET_S = 1
ACTIVATION_MAX_S = 8
# How many times the first dump is asked for while the logger sees no window.
WINDOW_ATTEMPTS = 12
# `goto` gives up after this many moves.
GOTO_STEPS = 80


def talkback_walk_ending(focuses, app_pkg, idle_steps=0):
    """Why a forward TalkBack walk is over: "left app" when focus went to another package (the system
    bars), "cycle" when it came back to the first element, "stopped" after presses that moved nothing:
    usually the end of the window, a trap if elements are left below."""
    if focuses and focuses[-1].get("pkg") != app_pkg:
        return "left app"
    if keyboard_ending(focuses) == "cycle":
        return "cycle"
    if idle_steps >= KEYBOARD_STUCK_STEPS:
        return "stopped"
    return None


def output_dir(base, screen):
    folder = Path(base) / datetime.date.today().isoformat() / screen
    candidate, n = folder, 2
    while candidate.exists():
        candidate, n = folder.with_name(f"{screen}-{n}"), n + 1
    candidate.mkdir(parents=True)
    return candidate


def quoted(text, limit=160):
    text = text if len(text) <= limit else text[:limit] + "…"
    return json.dumps(text, ensure_ascii=False)


def live_line(record):
    """A short line per record to follow the walk; session.txt keeps the full records."""
    kind = record["kind"]
    if kind == "speech":
        return f"    {quoted(record['text'])}"
    if kind == "focus":
        name = quoted(label(record)) if label(record) else "(no label)"
        issues = f" [{','.join(record['issues'])}]" if record["issues"] else ""
        bounds = record.get("bounds")
        where = f" [{bounds[0]},{bounds[1]}][{bounds[2]},{bounds[3]}]" if isinstance(bounds, list) else ""
        actions = f" actions={quoted(record['actions'])}" if record.get("actions") else ""
        return f"→ {record.get('class')} {name}{where}{actions}{issues}"
    if kind == "tree":
        marker = record.get("marker", "")
        return f"[tree] {marker.removeprefix('end ')}" if marker.startswith(("end", "no active")) else None
    if kind == "key":
        return None
    return f"[{kind}] {quoted(record.get('text') or record.get('class') or '')}"


def has_label(record, text):
    """Whether the element's name contains `text`, whatever the case."""
    return bool(text) and text.casefold() in label(record).casefold()


def activation_lines(outcome, opened):
    """What an activation did to focus, for whoever drives the walk: `outcome` is the activation as the
    rules see it, None when nothing was clicked; `opened` says the app showed a new window."""
    if opened:
        return ["    (a new window opened)"]
    if not outcome:
        return ["    (nothing was activated: the element has no click action)"]
    click, moves, gone = outcome
    left = f"; {name_or_place(click)} left the screen" if gone else ""
    if len(moves) > 1:
        places = ", ".join(name_or_place(m) for m in moves)
        return [f"!! focus moved {len(moves)} times on its own: {places}{left}"]
    if moves:
        return [f"!! focus moved on its own to {name_or_place(moves[0])}, {moves[0]['t'] - click['t']} ms after "
                f"the activation{left}"]
    if gone:
        return [f"!! focus lost: {name_or_place(click)} left the screen and nothing took TalkBack's focus"]
    return [f"    (focus stayed on {name_or_place(click)})"]


def follow(log):
    """Prints the session's log as it is written, until the returned event is set."""
    done = threading.Event()

    def pump():
        shown = 0
        while not done.wait(0.2):
            lines = joined(session_text(log).splitlines())
            for line in lines[shown:]:
                record = parse_record(line)
                if record and (text := live_line(record)):
                    print(text, flush=True)
            shown = len(lines)

    threading.Thread(target=pump, daemon=True).start()
    return done


def discard_session(folder, meta):
    """Closes a session that captured the wrong thing and removes its folder, so it isn't taken as evidence."""
    close_session(folder, meta)
    shutil.rmtree(folder, ignore_errors=True)


def close_session(folder, meta):
    """Disconnects the keyboard, stops copying the log and forgets the session."""
    for pid in (meta.get("relay"), meta.get("log")):
        stop_process(pid)
    for leftover in (folder / ".keys", folder / ".session.json", folder / LOG_FILE):
        leftover.unlink(missing_ok=True)
    if ACTIVE_SESSION.exists() and ACTIVE_SESSION.read_text().strip() == str(folder):
        ACTIVE_SESSION.unlink()


def clear_orphan():
    """A session whose keyboard is gone can't go on (the computer restarted, or the device was
    unplugged): it is closed, so it doesn't block the next one."""
    if not ACTIVE_SESSION.exists():
        return
    folder = Path(ACTIVE_SESSION.read_text().strip())
    state = folder / ".session.json"
    meta = json.loads(state.read_text()) if state.exists() else {}
    if alive(meta.get("relay")):
        raise NotReady(f"a session is open in {folder}; run `a11y-audit stop` first")
    close_session(folder, meta)
    ACTIVE_SESSION.unlink(missing_ok=True)
    print(f"note: closed a session left open in {folder}", file=sys.stderr)


def first_window(serial, log):
    """The window of the session's first dump. A service that has just started doesn't see the active
    window yet and logs an empty dump, so the dump is asked for again until it has one."""
    for attempt in range(WINDOW_ATTEMPTS):
        read_session(log, dumps=attempt + 1)
        if found := dumps(records_of(log)):
            return found[0][0]
        # TalkBack's prompt to send notifications can come up seconds after TalkBack starts: the logger
        # can't read it, and it covers the app.
        if "permissioncontroller" in focused_window(serial):
            adb(serial, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(0.5)
        adb(serial, "shell", "am", "broadcast", "-a", DUMP_ACTION)
    return None


def start_session(serial, out, screen):
    """Connects the virtual keyboard through a background relay that outlives this process, puts
    accessibility focus in the app's window, starts copying the log and dumps the tree."""
    clear_orphan()
    warn_if_not_ready(serial)
    services = adb(serial, "shell", "settings", "get", "secure", "enabled_accessibility_services")
    if "talkback" not in services.casefold():
        raise NotReady("TalkBack is off; turn it on with `a11y-audit talkback on`")
    if not adb(serial, "shell", "command -v hid || true").strip():
        raise NotReady("this device has no `hid` tool, so TalkBack can't be driven; "
                       "walk the screen by hand with `a11y-audit capture`")
    folder = output_dir(out, screen).resolve()
    keys = folder / ".keys"
    register = {"id": 1, "command": "register", "name": KEYBOARD_NAME, "vid": 0x18D1, "pid": 0x0001,
                "bus": "usb", "descriptor": HID_DESCRIPTOR}
    keys.write_text(json.dumps(register) + "\n")
    relay = subprocess.Popen(["sh", "-c", f"tail -n +1 -f {shlex.quote(str(keys))} | "
                              f"{shlex.join(adb_cmd(serial, 'shell', 'hid', '-'))}"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    talkback = next((s for s in services.split(":") if "talkback" in s.casefold()), "").partition("/")[0]
    meta = {"serial": serial, "relay": relay.pid, "walk_from": -1, "pkg": None,
            "talkback": talkback_major(adb(serial, "shell", "dumpsys", "package", talkback))}
    # Written now, so `stop` can disconnect the keyboard if anything below fails.
    (folder / ".session.json").write_text(json.dumps(meta))
    ACTIVE_SESSION.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_SESSION.write_text(str(folder))
    _, connected = wait_until(lambda: adb(serial, "shell", "dumpsys", "input"), lambda d: KEYBOARD_NAME in d,
                              KEYBOARD_SETTLE_S, poll=0.3)
    if not connected:
        close_session(folder, meta)
        raise NotReady("the device didn't take the virtual keyboard; reconnect it and run `a11y-audit start` again")
    # Done before the log is copied, so this focus, which TalkBack didn't choose, stays out of the session.
    adb(serial, "shell", "am", "broadcast", "-a", FOCUS_WINDOW_ACTION)
    time.sleep(1)
    log = folder / LOG_FILE
    meta["log"] = stream_log(serial, log)
    (folder / ".session.json").write_text(json.dumps(meta))
    snapshot(serial, folder / "screen-start.png")
    window = first_window(serial, log)
    if not window:
        close_session(folder, meta)
        raise NotReady("the logger sees no window on the device; unlock the screen, open the app and run the command again")
    meta["pkg"], meta["window"] = window.get("pkg"), window.get("window")
    (folder / ".session.json").write_text(json.dumps(meta))
    return folder, meta


def open_session(directory):
    if directory:
        folder = Path(directory)
    else:
        folder = Path(ACTIVE_SESSION.read_text().strip()) if ACTIVE_SESSION.exists() else None
    if not folder or not (folder / ".session.json").exists():
        raise NotReady("no session is open; run `a11y-audit start <screen>` first")
    return folder, json.loads((folder / ".session.json").read_text())


def new_walk(folder, meta, since):
    meta["walk_from"] = since
    (folder / ".session.json").write_text(json.dumps(meta))


def stuck_reason(meta):
    """Why a key moved nothing, when no key has moved TalkBack's focus yet in this session."""
    serial = meta["serial"]
    if not alive(meta.get("relay")):
        return "the virtual keyboard is gone; run `a11y-audit stop`, then `start` again"
    services = adb(serial, "shell", "settings", "get", "secure", "enabled_accessibility_services")
    if "talkback" not in services.casefold():
        return "TalkBack is off; run `a11y-audit stop`, `a11y-audit talkback on`, then `start` again"
    focused = focused_window(serial)
    if meta.get("pkg") and meta["pkg"] not in focused:
        return (f"another window is on top ({focused}); a system dialog or TalkBack's "
                "tutorial takes the keys. Close it (`adb shell input keyevent KEYCODE_BACK`) and check with `look`")
    return "TalkBack ignored the key; check the screen with `a11y-audit look`"


def send_key(folder, meta, action, last_t):
    """Presses a TalkBack shortcut, with each modifier TalkBack may use until one moves focus, and
    waits for the focus and for what TalkBack says about it."""
    log = folder / LOG_FILE
    log_key(meta["serial"], action, last_t)

    def moved(records):
        return any(r["kind"] == "focus" and r["t"] > last_t for r in records)

    for modifier in talkback_modifiers(meta.get("modifier"), meta.get("talkback")):
        seen = len(records_of(log))
        with (folder / ".keys").open("a") as keys:
            for report in key_reports(modifier, action):
                keys.write(json.dumps({"id": 1, "command": "report", "report": report}) + "\n")
        produced, did_move = wait_until(lambda: records_of(log), moved, TALKBACK_STEP_S)
        # Until TalkBack has taken a key with this modifier, focus that only followed the keyboard doesn't count.
        if did_move and (meta.get("modifier") or moved_by_talkback(produced[seen:])):
            if meta.get("modifier") != modifier:
                meta["modifier"] = modifier
                (folder / ".session.json").write_text(json.dumps(meta))
            wait_until(lambda: records_of(log),
                       lambda records: any(r["kind"] == "speech" and r["text"] and r["t"] > last_t for r in records),
                       TALKBACK_STEP_S)
            wait_quiet(lambda: len(session_text(log)), SPEECH_QUIET_S, TALKBACK_STEP_S)
            return


def activate(folder, meta, last_t):
    """Clicks the element TalkBack is on, watches the app until it settles and dumps the tree, so the
    rules see whether the element is still there."""
    log, serial = folder / LOG_FILE, meta["serial"]
    adb(serial, "shell", "am", "broadcast", "-a", ACTIVATE_ACTION)
    time.sleep(ACTIVATION_MIN_S - ACTIVATION_QUIET_S)
    wait_quiet(lambda: len(session_text(log)), ACTIVATION_QUIET_S, ACTIVATION_MAX_S - ACTIVATION_MIN_S)
    expected = dump_count(log) + 1
    adb(serial, "shell", "am", "broadcast", "-a", DUMP_ACTION)
    read_session(log, dumps=expected)


def press_once(folder, meta, action, echo=True):
    """One press, printed unless `echo` is off. Returns the records it produced."""
    log = folder / LOG_FILE
    before = records_of(log)
    last_t = before[-1]["t"] if before else -1
    if action in ("first", "activate"):
        new_walk(folder, meta, last_t)
    if action == "activate":
        activate(folder, meta, last_t)
    else:
        send_key(folder, meta, action, last_t)
    new = [r for r in records_of(log) if r["t"] > last_t]
    lines = [text for r in new if (r["kind"] != "speech" or r["text"]) and r["kind"] != "tree" and (text := live_line(r))]
    if action == "activate":
        clicked = [r for r in new if r["kind"] == "click" and r.get("pkg") == meta["pkg"]]
        opened = any(r["kind"] == "window" and r.get("pkg") == meta["pkg"] for r in new)
        outcome = next(iter(activations([{"kind": "key", "t": last_t}] + new, meta["pkg"])), None) if clicked else None
        lines += activation_lines(outcome, opened and outcome is None and bool(clicked))
    elif not any(r["kind"] == "focus" for r in new):
        lines.append("    (focus didn't move)")
        if not meta.get("modifier"):
            lines.append(f"    hint: {stuck_reason(meta)}")
    elif not any(r["kind"] == "speech" and r["text"] for r in new):
        lines.append("    (nothing spoken)")
    if echo:
        print("\n".join(lines), flush=True)
    return new


def press_keys(folder, meta, action, times, echo=True):
    """Presses a TalkBack shortcut (or activates) up to `times` times and prints what each press
    produced. Going forward, it stops when the walk is over and returns why. The end is only looked
    for in the focuses since the walk began: after `first`, `activate` or the end of the last walk."""
    idle = 0
    for _ in range(times):
        new = press_once(folder, meta, action, echo)
        idle = 0 if any(r["kind"] == "focus" for r in new) else idle + 1
        records = records_of(folder / LOG_FILE)
        focuses = [r for r in records if r["kind"] == "focus" and r["t"] > meta["walk_from"]]
        if action == "next" and (ending := talkback_walk_ending(focuses, meta["pkg"], idle)):
            if echo:
                print(f"walk ended: {ending}", flush=True)
            new_walk(folder, meta, records[-1]["t"])
            return ending
    return None


def goto(folder, meta, text):
    """Moves TalkBack to the first element whose name contains `text`, from the top of the window.
    Returns its focus record, or None when the walk ended without reaching it."""
    def reached(records):
        return next((r for r in reversed(records) if r["kind"] == "focus" and has_label(r, text)), None)

    hide_keyboard(meta["serial"])
    found = reached(press_once(folder, meta, "first", echo=False))
    idle = 0
    for _ in range(GOTO_STEPS):
        if found or idle >= KEYBOARD_STUCK_STEPS:
            break
        new = press_once(folder, meta, "next", echo=False)
        found = reached(new)
        focuses = [r for r in new if r["kind"] == "focus"]
        if any(r.get("pkg") != meta["pkg"] for r in focuses):
            break
        # A slow device can miss one key: only several in a row mean the walk is over.
        idle = 0 if focuses else idle + 1
    if found:
        print(live_line(found), flush=True)
    return found


def stop_session(folder, meta):
    log = folder / LOG_FILE
    try:
        expected = dump_count(log) + 1
        snapshot(meta["serial"], folder / "screen-end.png", atf=True)
        session = read_session(log, dumps=expected, atf=True)
        (folder / "session.txt").write_text(session, encoding="utf-8")
    finally:
        close_session(folder, meta)
    print(f"saved {folder}")
    rules(argparse.Namespace(dir=folder))
