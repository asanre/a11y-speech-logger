"""Runs the rules over a capture folder and writes findings.json and the report's draft."""

import json
from pathlib import Path

from .draft import report_draft
from .keyboard import run_keyboard_rules
from .records import dumps, parse_session
from .rules import run_rules


def rules(args):
    folder = Path(args.dir)
    records = parse_session(folder / "session.txt")
    if (folder / "keyboard").is_dir():
        result = run_keyboard_rules(records, folder / "keyboard")
        (folder / "findings.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        counts = ", ".join(f"{rule}={n}" for rule, n in result["summary"].items()) or "none"
        print(f"keyboard ({result['keyboard']['ending']}): {counts} -> {folder / 'findings.json'}")
        return
    # screen-end.png matches the last dump; older captures have one screen.png, matching a single dump.
    screenshot = folder / "screen-end.png"
    if not screenshot.exists() and len(dumps(records)) == 1 and (folder / "screen.png").exists():
        screenshot = folder / "screen.png"
    result = run_rules(records, screenshot if screenshot.exists() else None)
    (folder / "findings.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    # A keyboard pass of the same screen sits in a sibling folder: its findings answer the keyboard criteria.
    keyboard_findings = folder.with_name(f"{folder.name}-keyboard") / "findings.json"
    keyboard = json.loads(keyboard_findings.read_text(encoding="utf-8")) if keyboard_findings.exists() else None
    (folder / "report-draft.md").write_text(report_draft(result, folder.name, keyboard), encoding="utf-8")
    counts = ", ".join(f"{rule}={n}" for rule, n in result["summary"].items()) or "none"
    print(f"findings: {counts} -> {folder / 'findings.json'}")
    print(f"draft of the report -> {folder / 'report-draft.md'}")
