"""What is asked of the device through adb, and the session's log as the device writes it."""

import os
import re
import signal
import subprocess
import sys
import time

from .records import parse_lines
from .talkback import PACKAGE, setup_problems, talkback_service

DUMP_ACTION = f"{PACKAGE}.DUMP"
LOG_TAG = "A11ySpeech"
TREE_DONE = re.compile(r"^\[tree\] t=\d+ (end nodes=|no active window)", re.MULTILINE)
ATF_DONE = re.compile(r"^\[atf\] t=\d+ end ", re.MULTILINE)
# The session's log while it is open: the logger's records, copied from logcat as they are written.
LOG_FILE = ".log"
# Written to the log when the copy starts: the session is what follows it.
LOG_MARK = "[mark] t=0 session"
# The dump and the ATF checks are logged asynchronously by the service.
DUMP_TIMEOUT_S = 10
# TalkBack and the logger take a moment to start or stop after the setting changes.
SERVICE_TIMEOUT_S = 6


class NotReady(Exception):
    """The device or the session isn't in the state a command needs. The message says what to do."""


def adb_problem(stderr):
    """What an adb failure means for the person running the command, from what adb printed."""
    if "no devices" in stderr:
        return "no device is connected; plug one in or start an emulator, then check `adb devices`"
    if "more than one" in stderr:
        return "several devices are connected; pass --serial <id>, from `adb devices`"
    if "unauthorized" in stderr:
        return "the device hasn't authorized this computer; accept the USB debugging prompt on its screen"
    if "offline" in stderr:
        return "the device is offline; reconnect it, then check `adb devices`"
    if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in stderr:
        return (f"the A11y Speech Logger on the device was signed with another key (release 0.2.0 was); uninstall it "
                f"with `adb uninstall {PACKAGE}`, then run `a11y-audit setup` again")
    lines = stderr.strip().splitlines()
    return f"adb failed: {lines[-1] if lines else 'no output'}"


def adb_cmd(serial, *args):
    return ["adb"] + (["-s", serial] if serial else []) + list(args)


def adb(serial, *args, binary=False):
    try:
        result = subprocess.run(adb_cmd(serial, *args), capture_output=True)
    except FileNotFoundError:
        raise NotReady("adb is not on the PATH; install Android's platform-tools") from None
    if result.returncode:
        raise NotReady(adb_problem((result.stdout + result.stderr).decode("utf-8", "replace")))
    return result.stdout if binary else result.stdout.decode("utf-8", "replace")


def wait_until(read, done, timeout, clock=time.monotonic, sleep=time.sleep, poll=0.1):
    """Polls `read` until `done(value)` or the timeout. Returns the last value and whether it was done."""
    deadline = clock() + timeout
    while True:
        value = read()
        if done(value):
            return value, True
        if clock() >= deadline:
            return value, False
        sleep(poll)


def wait_quiet(read, quiet, timeout, clock=time.monotonic, sleep=time.sleep, poll=0.1):
    """Polls `read` until its value has stayed the same for `quiet` seconds, or the timeout."""
    start = changed = clock()
    value = read()
    while clock() - changed < quiet and clock() - start < timeout:
        sleep(poll)
        latest = read()
        if latest != value:
            value, changed = latest, clock()
    return value


def alive(pid):
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, TypeError):
        return False
    return True


def stop_process(pid):
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, TypeError):
        pass


def stream_log(serial, path):
    """Copies the logger's records to `path` from now on, in a process that outlives this one, and
    returns its pid. The device's log is left as it is: nothing is cleared, and a long session doesn't
    depend on what the device's buffer still holds."""
    command = adb_cmd(serial, "logcat", "-s", f"{LOG_TAG}:I", "-v", "raw", "-T", "1")
    with path.open("wb") as out:
        pid = subprocess.Popen(command, stdout=out, stderr=subprocess.DEVNULL, start_new_session=True).pid
    adb(serial, "shell", "log", "-t", LOG_TAG, f"'{LOG_MARK}'")
    _, marked = wait_until(lambda: LOG_MARK in path.read_text(encoding="utf-8", errors="replace"), bool, 5)
    if not marked:
        stop_process(pid)
        raise NotReady("the device's log can't be read (`adb logcat` printed nothing); reconnect the device")
    return pid


def session_text(path):
    """The session's log so far: what the device logged after the copy started."""
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    return text.partition(LOG_MARK + "\n")[2]


def records_of(path):
    return parse_lines(session_text(path))


def log_key(serial, action, t):
    """Logs a key press of the walk, so the rules can tell focus the user moved from focus the app moved."""
    adb(serial, "shell", "log", "-t", LOG_TAG, f"'[key] t={max(t, 0)} action={action}'")


def device_setup_problems(serial):
    engine = adb(serial, "shell", "settings", "get", "secure", "tts_default_synth")
    services = adb(serial, "shell", "settings", "get", "secure", "enabled_accessibility_services")
    return setup_problems(engine, services)


def warn_if_not_ready(serial):
    for problem in device_setup_problems(serial):
        print(f"warning: {problem}", file=sys.stderr)


def snapshot(serial, path, atf=False):
    extras = ["--ez", "atf", "true"] if atf else []
    adb(serial, "shell", "am", "broadcast", "-a", DUMP_ACTION, *extras)
    path.write_bytes(adb(serial, "exec-out", "screencap", "-p", binary=True))


def dump_count(log):
    return len(TREE_DONE.findall(session_text(log)))


def read_session(log, dumps, atf=False):
    """The session's log once it holds `dumps` tree dumps and, with `atf`, the ATF checks."""
    def complete(session):
        return len(TREE_DONE.findall(session)) >= dumps and (not atf or bool(ATF_DONE.search(session)))

    session, done = wait_until(lambda: session_text(log), complete, DUMP_TIMEOUT_S, poll=0.25)
    if not done:
        missing = "the tree dump" if len(TREE_DONE.findall(session)) < dumps else "the ATF checks"
        print(f"warning: {missing} didn't reach the log in {DUMP_TIMEOUT_S} s; is A11y Focus Logger still on? "
              "Check with `a11y-audit doctor`", file=sys.stderr)
    return session


def talkback_component(serial):
    """TalkBack's component, or None when the device has no TalkBack."""
    # `dumpsys accessibility` only lists the services that are on, so it can't find TalkBack to turn it on.
    installed = adb(serial, "shell", "cmd", "package", "query-services", "--brief",
                    "-a", "android.accessibilityservice.AccessibilityService")
    return talkback_service(installed) or talkback_service(adb(serial, "shell", "dumpsys", "accessibility"))


def talkback_running(serial):
    return talkback_service(adb(serial, "shell", "dumpsys", "accessibility")) is not None


def focused_window(serial):
    """The window that has input focus, as `dumpsys window` names it."""
    window = adb(serial, "shell", "dumpsys", "window")
    line = next((line.strip() for line in window.splitlines() if "mCurrentFocus" in line), "")
    return line.removeprefix("mCurrentFocus=")


def hide_keyboard(serial):
    """Closes the on-screen keyboard when it is showing: TalkBack's "first element" stays within the
    window that has its focus, and a walk that passed a text field ends on the keyboard's keys."""
    def showing():
        return "mInputShown=true" in adb(serial, "shell", "dumpsys", "input_method")

    if showing():
        adb(serial, "shell", "input", "keyevent", "KEYCODE_BACK")
        wait_until(showing, lambda shown: not shown, 3, poll=0.3)


def put_services(serial, value):
    if value:
        adb(serial, "shell", "settings", "put", "secure", "enabled_accessibility_services", value)
        adb(serial, "shell", "settings", "put", "secure", "accessibility_enabled", "1")
    else:
        adb(serial, "shell", "settings", "delete", "secure", "enabled_accessibility_services")


def version_code(dumpsys):
    match = re.search(r"versionCode=(\d+)", dumpsys)
    return int(match.group(1)) if match else None
