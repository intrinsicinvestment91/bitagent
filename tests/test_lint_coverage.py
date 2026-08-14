"""Every tracked Python file must be visible to the linter.

Ruff honours .gitignore. A `config.py` pattern in .gitignore — unanchored, so git
applied it at every directory level — kept src/payments/config.py out of both the
repository and every local `ruff format` run. The file was missing from a fresh
clone, and CI was the first thing to ever lint it.

This guards the general case: if an ignore rule ever hides tracked source from
ruff again, this fails instead of CI failing on a file nobody could see locally.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str) -> str:
    return subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not available")
@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff is not installed")
def test_ruff_sees_every_tracked_python_file():
    tracked = {line for line in _run("git", "ls-files", "*.py").splitlines() if line.strip()}
    if not tracked:
        pytest.skip("not a git checkout")

    visible = {
        str(Path(line).resolve().relative_to(REPO_ROOT))
        for line in _run("ruff", "check", "--show-files", ".").splitlines()
        if line.strip().endswith(".py")
    }

    hidden = tracked - visible
    assert not hidden, (
        "these tracked files are excluded from linting — check .gitignore and "
        f"the ruff exclude list: {sorted(hidden)}"
    )
