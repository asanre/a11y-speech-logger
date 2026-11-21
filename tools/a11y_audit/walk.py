"""A capture session: the virtual keyboard, the presses and what each one produced."""

import argparse
import datetime
import json
import os
import shlex
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from .device import LOG_TAG, adb, adb_cmd, read_session, records_of, snapshot, warn_if_not_ready
from .findings import rules
from .keyboard import KEYBOARD_STUCK_STEPS, keyboard_ending
from .records import dumps, label, parse_record
from .talkback import PACKAGE, key_reports, talkback_modifiers

FOCUS_WINDOW_ACTION = f"{PACKAGE}.FOCUS_WINDOW"
ACTIVATE_ACTION = f"{PACKAGE}.ACTIVATE"
ACTIVE_SESSION = Path.home() / ".cache" / "a11y-speech-logger" / "active"
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
# Long enough for TalkBack to speak, and for a stop with no speech to count as SILENT_FOCUS.
TALKBACK_STEP_S = 1.5
# Time for Android to add the virtual keyboard before the first key.
KEYBOARD_SETTLE_S = 2


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


def live_line(record):
    """A short line per record to follow the walk; session.txt keeps the full records."""
    def quoted(text, limit=160):
        text = text if len(text) <= limit else text[:limit] + "…"
        return json.dumps(text, ensure_ascii=False)

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
    return f"[{kind}] {quoted(record.get('text') or record.get('class') or '')}"


def follow(serial):
    """Prints the log as it is written, until the returned process is terminated."""
    proc = subprocess.Popen(adb_cmd(serial, "logcat", "-s", f"{LOG_TAG}:I", "-v", "raw"),
                            stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")

    def pump():
        for line in proc.stdout:
            record = parse_record(line.rstrip("\n"))
            if record and (shown := live_line(record)):
                print(shown, flush=True)

    threading.Thread(target=pump, daemon=True).start()
    return proc


def start_session(serial, out, screen):
    """Connects the virtual keyboard through a background relay that outlives this process, puts
    accessibility focus in the app's window, clears the log and dumps the tree."""
    if ACTIVE_SESSION.exists():
        sys.exit(f"error: a session is open in {ACTIVE_SESSION.read_text().strip()}; run `stop` first")
    warn_if_not_ready(serial)
    services = adb(serial, "shell", "settings", "get", "secure", "enabled_accessibility_services")
    if "talkback" not in services.casefold():
        sys.exit("error: TalkBack is off; turn it on with `a11y-audit talkback on`")
    if not adb(serial, "shell", "command -v hid || true").strip():
        sys.exit("error: this device has no `hid` tool, so TalkBack can't be driven; walk it by hand with `capture`")
    folder = output_dir(out, screen).resolve()
    keys = folder / ".keys"
    register = {"id": 1, "command": "register", "name": "A11y Audit Keyboard", "vid": 0x18D1, "pid": 0x0001,
                "bus": "usb", "descriptor": HID_DESCRIPTOR}
    keys.write_text(json.dumps(register) + "\n")
    relay = subprocess.Popen(["sh", "-c", f"tail -n +1 -f {shlex.quote(str(keys))} | "
                              f"{shlex.join(adb_cmd(serial, 'shell', 'hid', '-'))}"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    meta = {"serial": serial, "relay": relay.pid, "walk_from": -1, "pkg": None}
    # Written now, so `stop` can disconnect the keyboard if anything below fails.
    (folder / ".session.json").write_text(json.dumps(meta))
    ACTIVE_SESSION.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_SESSION.write_text(str(folder))
    time.sleep(KEYBOARD_SETTLE_S)
    # Done before the log is cleared, so this focus, which TalkBack didn't choose, stays out of the session.
    adb(serial, "shell", "am", "broadcast", "-a", FOCUS_WINDOW_ACTION)
    time.sleep(1)
    adb(serial, "logcat", "-c")
    snapshot(serial, folder / "screen-start.png")
    first_dump = dumps([r for r in map(parse_record, read_session(serial, dumps=1).splitlines()) if r])
    meta["pkg"] = first_dump[0][0].get("pkg") if first_dump else None
    (folder / ".session.json").write_text(json.dumps(meta))
    return folder, meta


def open_session(directory):
    if directory:
        folder = Path(directory)
    else:
        folder = Path(ACTIVE_SESSION.read_text().strip()) if ACTIVE_SESSION.exists() else None
    if not folder or not (folder / ".session.json").exists():
        sys.exit("error: no open session; run `start` first")
    return folder, json.loads((folder / ".session.json").read_text())


def new_walk(folder, meta, since):
    meta["walk_from"] = since
    (folder / ".session.json").write_text(json.dumps(meta))


def press_keys(folder, meta, action, times):
    """Presses a TalkBack shortcut (or activates) up to `times` times and prints what each press
    produced. Going forward, it stops when the walk is over and returns why. The end is only looked
    for in the focuses since the walk began: after `first`, `activate` or the end of the last walk."""
    idle = 0
    for _ in range(times):
        before = records_of(meta["serial"])
        last_t = before[-1]["t"] if before else -1
        if action in ("first", "activate"):
            new_walk(folder, meta, last_t)
        if action == "activate":
            adb(meta["serial"], "shell", "am", "broadcast", "-a", ACTIVATE_ACTION)
            time.sleep(TALKBACK_STEP_S)
        for modifier in () if action == "activate" else talkback_modifiers(meta.get("modifier")):
            with (folder / ".keys").open("a") as keys:
                for report in key_reports(modifier, action):
                    keys.write(json.dumps({"id": 1, "command": "report", "report": report}) + "\n")
            time.sleep(TALKBACK_STEP_S)
            if any(r["kind"] == "focus" and r["t"] > last_t for r in records_of(meta["serial"])):
                if meta.get("modifier") != modifier:
                    meta["modifier"] = modifier
                    (folder / ".session.json").write_text(json.dumps(meta))
                break
        records = records_of(meta["serial"])
        new = [r for r in records if r["t"] > last_t]
        for record in new:
            if (record["kind"] != "speech" or record["text"]) and (shown := live_line(record)):
                print(shown, flush=True)
        moved = any(r["kind"] == "focus" for r in new)
        if not moved:
            print("    (focus didn't move)", flush=True)
        elif not any(r["kind"] == "speech" and r["text"] for r in new):
            print("    (nothing spoken)", flush=True)
        idle = 0 if moved else idle + 1
        focuses = [r for r in records if r["kind"] == "focus" and r["t"] > meta["walk_from"]]
        if action == "next" and (ending := talkback_walk_ending(focuses, meta["pkg"], idle)):
            print(f"walk ended: {ending}", flush=True)
            new_walk(folder, meta, records[-1]["t"])
            return ending
    return None


def stop_session(folder, meta):
    try:
        snapshot(meta["serial"], folder / "screen-end.png", atf=True)
        session = read_session(meta["serial"], dumps=2, atf=True)
        (folder / "session.txt").write_text(session, encoding="utf-8")
    finally:
        try:
            os.killpg(meta["relay"], signal.SIGTERM)  # closing the relay disconnects the keyboard
        except ProcessLookupError:
            pass
        for leftover in (folder / ".keys", folder / ".session.json", ACTIVE_SESSION):
            leftover.unlink(missing_ok=True)
    print(f"saved {folder}")
    rules(argparse.Namespace(dir=folder))
