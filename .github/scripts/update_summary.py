#!/usr/bin/env python3
"""Post-commit: update session-summary.md date and HEAD SHA."""
import re, subprocess, sys
from pathlib import Path

summary = Path(".github/session-summary.md")
if not summary.exists():
    sys.exit(0)

sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
today = __import__("datetime").date.today().isoformat()

content = summary.read_text(encoding="utf-8")
content = re.sub(r"(?<=Session Summary — )\S+", today, content)
content = re.sub(r"(?<=`dev`（`)[^`]+", sha, content)
summary.write_text(content, encoding="utf-8")
