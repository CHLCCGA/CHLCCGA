"""Regenerate profile status card SVG + inject papers block into README.

Reads data/status.yaml as the single source of manual data, fetches Warsaw
weather and GitHub commit stats from public APIs, then writes:
  - assets/status-card.svg
  - README.md  (papers block between <!-- papers:start --> markers)

Run with --dry-run to print outputs to stdout without writing files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_YAML = REPO_ROOT / "data" / "status.yaml"
SVG_PATH    = REPO_ROOT / "assets" / "status-card.svg"
README_PATH = REPO_ROOT / "README.md"

GITHUB_USER = "CHLCCGA"
WARSAW_TZ   = ZoneInfo("Europe/Warsaw")


def load_status() -> dict:
    """Load the hand-maintained status YAML."""
    with STATUS_YAML.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def format_warsaw_time() -> str:
    """Return current Warsaw time as 'HH:MM CET' or 'HH:MM CEST'."""
    now = datetime.now(WARSAW_TZ)
    return now.strftime("%H:%M %Z")
