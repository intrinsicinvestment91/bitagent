"""Narrow regression check: no LNbits-style credentials in the tracked tree.

This is NOT a comprehensive secret scanner.

It looks for one specific mistake that has happened in this repository before: a
realistic 32-hex LNbits key committed as a literal assigned to a credential-named
field. It deliberately does not scan Git history, does not recognise other
credential formats, and does not inspect untracked files.

Matched values are never printed. A failure reports the file, the line number, and
the field name only.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()

CREDENTIAL_FIELDS = ("api_key", "admin_key", "adminkey", "invoice_key", "inkey")

# <credential field> = or :  [optional quote]  exactly 32 hex characters
# Obvious textual placeholders ("your_lnbits_api_key_here",
# "replace-with-local-demo-key") do not match and are therefore allowed.
CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?P<field>" + "|".join(CREDENTIAL_FIELDS) + r")"
    r"\s*[:=]\s*"
    r"[\"']?(?P<value>[0-9a-fA-F]{32})(?![0-9a-fA-F])",
    re.IGNORECASE,
)

SCANNED_SUFFIXES = {
    "",  # extensionless files such as Makefile, Dockerfile, LICENSE
    ".cfg",
    ".env",
    ".example",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".template",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

MAX_BYTES = 1_000_000


def _tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
        capture_output=True,
        check=True,
    )
    return [REPO_ROOT / name for name in result.stdout.decode().split("\0") if name]


def _findings() -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []
    for path in _tracked_files():
        if path.resolve() == SELF:
            continue
        if path.suffix.lower() not in SCANNED_SUFFIXES:
            continue
        try:
            if not path.is_file() or path.stat().st_size > MAX_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            match = CREDENTIAL_ASSIGNMENT.search(line)
            if match:
                found.append(
                    (
                        path.relative_to(REPO_ROOT).as_posix(),
                        lineno,
                        match.group("field").lower(),
                    )
                )
    return found


def test_no_tracked_lnbits_credentials():
    findings = _findings()
    assert not findings, (
        "Credential-shaped assignment(s) found in tracked files. Supply LNbits "
        "credentials through untracked local configuration instead. The matched "
        "values are intentionally not shown:\n"
        + "\n".join(f"  {path}:{line} -> {field}" for path, line, field in findings)
    )


def test_textual_placeholders_are_allowed():
    placeholders = (
        "LNBITS_API_KEY=your_lnbits_api_key_here",
        "LNBITS_API_KEY=your-lnbits-api-key-here",
        'api_key = "replace-with-local-demo-key"',
        'admin_key: "replace-with-local-demo-key"',
    )
    for placeholder in placeholders:
        assert CREDENTIAL_ASSIGNMENT.search(placeholder) is None
