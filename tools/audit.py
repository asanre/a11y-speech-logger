#!/usr/bin/env python3
"""The `a11y-audit` command from a clone: `python3 tools/audit.py`. The code is in `a11y_audit/`."""

from a11y_audit.records import *  # noqa: F401,F403
from a11y_audit.contrast import *  # noqa: F401,F403
from a11y_audit.rules import *  # noqa: F401,F403
from a11y_audit.keyboard import *  # noqa: F401,F403
from a11y_audit.talkback import *  # noqa: F401,F403
from a11y_audit.device import *  # noqa: F401,F403
from a11y_audit.draft import *  # noqa: F401,F403
from a11y_audit.findings import *  # noqa: F401,F403
from a11y_audit.preview import *  # noqa: F401,F403
from a11y_audit.walk import *  # noqa: F401,F403
from a11y_audit.cli import *  # noqa: F401,F403

if __name__ == "__main__":
    main()  # noqa: F405
