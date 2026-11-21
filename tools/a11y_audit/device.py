"""What is asked of the device through adb."""

import re
import subprocess
import sys
import time

from .records import parse_record
from .talkback import PACKAGE, setup_problems, talkback_service

DUMP_ACTION = f"{PACKAGE}.DUMP"
LOG_TAG = "A11ySpeech"
TREE_DONE = re.compile(r"^\[tree\] t=\d+ (end nodes=|no active window)", re.MULTILINE)
ATF_DONE = re.compile(r"^\[atf\] t=\d+ end ", re.MULTILINE)


def adb_cmd(serial, *args):
    return ["adb"] + (["-s", serial] if serial else []) + list(args)


def adb(serial, *args, binary=False):
    result = subprocess.run(adb_cmd(serial, *args), capture_output=True, check=True)
    return result.stdout if binary else result.stdout.decode("utf-8", "replace")


def records_of(serial):
    log = adb(serial, "logcat", "-d", "-s", f"{LOG_TAG}:I", "-v", "raw")
    return [r for r in map(parse_record, log.splitlines()) if r]


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


def read_session(serial, dumps, atf=False):
    """The dump and the ATF checks are logged asynchronously by the service: wait until all are in the log."""
    for _ in range(40):
        session = adb(serial, "logcat", "-d", "-s", f"{LOG_TAG}:I", "-v", "raw")
        if len(TREE_DONE.findall(session)) >= dumps and (not atf or ATF_DONE.search(session)):
            break
        time.sleep(0.25)
    return session


def talkback_component(serial):
    # `dumpsys accessibility` only lists the services that are on, so it can't find TalkBack to turn it on.
    installed = adb(serial, "shell", "cmd", "package", "query-services", "--brief",
                    "-a", "android.accessibilityservice.AccessibilityService")
    component = talkback_service(installed) or talkback_service(adb(serial, "shell", "dumpsys", "accessibility"))
    if not component:
        sys.exit("error: TalkBack is not installed")
    return component


def put_services(serial, value):
    if value:
        adb(serial, "shell", "settings", "put", "secure", "enabled_accessibility_services", value)
        adb(serial, "shell", "settings", "put", "secure", "accessibility_enabled", "1")
    else:
        adb(serial, "shell", "settings", "delete", "secure", "enabled_accessibility_services")


def version_code(dumpsys):
    match = re.search(r"versionCode=(\d+)", dumpsys)
    return int(match.group(1)) if match else None
