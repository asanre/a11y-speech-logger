"""TalkBack's keyboard shortcuts and the device settings that turn it and the logger on."""

import re

PACKAGE = "io.github.asanre.a11ylogger"
FOCUS_LOGGER = f"{PACKAGE}/.FocusLoggerService"
LEFT_CTRL, LEFT_ALT, LEFT_META = 0x01, 0x04, 0x08
# TalkBack's modifier key: Alt on TalkBack 13 (a vendor build), Search on Google's TalkBack 17.
TALKBACK_MODIFIERS = (LEFT_ALT, LEFT_META)
# TalkBack's keyboard shortcuts, as (keys held with the modifier, key usage). Its shortcut to activate
# needs a keyboard with letters, so `activate` asks the focus logger to click instead.
TALKBACK_KEYS = {
    "next": (0, 0x4F),           # modifier+Right
    "prev": (0, 0x50),           # modifier+Left
    "first": (LEFT_CTRL, 0x50),  # modifier+Ctrl+Left, within the window that has focus
}


def talkback_modifiers(confirmed):
    """The modifiers to press a shortcut with: the one that already moved focus in this session, or
    each known one in turn until one does."""
    return (confirmed,) if confirmed else TALKBACK_MODIFIERS


def key_reports(modifier, action):
    """The keyboard reports for a TalkBack shortcut: modifiers down, the key, everything up."""
    held, key = TALKBACK_KEYS[action]
    return [[modifier | held, 0, pressed] + [0] * 5 for pressed in (0, key)] + [[0] * 8]


def talkback_service(services):
    """TalkBack's component among the accessibility services, whatever package ships it."""
    found = re.search(r"[\w.]+/[\w.]*TalkBackService", services)
    return found.group() if found else None


def setup_problems(engine, services):
    """What the logger's setup is missing, from the device's TTS engine and enabled services."""
    problems = []
    if engine.strip() != PACKAGE:
        problems.append(f"the default TTS engine is {engine.strip()!r}, so [speech] won't be captured")
    if FOCUS_LOGGER not in services and f"{PACKAGE}/{PACKAGE}.FocusLoggerService" not in services:
        problems.append("A11y Focus Logger is not enabled, so [focus] and [tree] won't be captured")
    return problems


def with_service(services, component, enabled):
    """The `enabled_accessibility_services` value with `component` added or removed, others kept."""
    kept = [s for s in services.strip().split(":") if s not in ("", "null", component)]
    return ":".join(kept + [component] if enabled else kept)


def without_logger(services):
    """The `enabled_accessibility_services` value without A11y Focus Logger, in its short or full form."""
    for component in (FOCUS_LOGGER, f"{PACKAGE}/{PACKAGE}.FocusLoggerService"):
        services = with_service(services, component, False)
    return services


def with_logger(services):
    """The `enabled_accessibility_services` value with A11y Focus Logger once, others kept."""
    return with_service(without_logger(services), FOCUS_LOGGER, True)
