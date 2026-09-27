"""Importing main with a half-configured feature must exit, not improvise.

main.py resolves payment and discovery configuration at import time, so each
case here imports it in a fresh subprocess with its own environment. That keeps
the import side effects out of this process and makes the cases independent of
one another and of their order.
"""

import subprocess
import sys

import pytest

VALID_KEY = "11" * 32
PUBLIC_URL = "https://agent.example.test"

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]

# Only the variables main.py reads are passed, so the developer's own
# environment cannot make a case pass or fail.
_BASE_ENV = {
    "PATH": "/usr/bin:/bin",
    "PYTHONPATH": str(REPO_ROOT),
    "RATE_LIMIT": "false",
}


def _import_main(tmp_path, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", "import main"],
        cwd=REPO_ROOT,
        env={**_BASE_ENV, "BITAGENT_DATA_DIR": str(tmp_path), **env},
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.mark.parametrize(
    ("label", "env"),
    [
        ("payments enabled, no wallet", {"PAYMENTS_ENABLED": "true"}),
        (
            "discovery enabled, no key",
            {
                "PAYMENTS_ENABLED": "false",
                "NOSTR_DISCOVERY_ENABLED": "true",
                "PUBLIC_URL": PUBLIC_URL,
            },
        ),
        (
            "discovery enabled, malformed key",
            {
                "PAYMENTS_ENABLED": "false",
                "NOSTR_DISCOVERY_ENABLED": "true",
                "NOSTR_PRIVATE_KEY": "ff" * 31,
                "PUBLIC_URL": PUBLIC_URL,
            },
        ),
        (
            "discovery enabled, no public url",
            {
                "PAYMENTS_ENABLED": "false",
                "NOSTR_DISCOVERY_ENABLED": "true",
                "NOSTR_PRIVATE_KEY": VALID_KEY,
            },
        ),
        (
            "discovery enabled, loopback public url",
            {
                "PAYMENTS_ENABLED": "false",
                "NOSTR_DISCOVERY_ENABLED": "true",
                "NOSTR_PRIVATE_KEY": VALID_KEY,
                "PUBLIC_URL": "http://127.0.0.1:8000",
            },
        ),
        (
            "discovery enabled, key outside the curve order",
            {
                "PAYMENTS_ENABLED": "false",
                "NOSTR_DISCOVERY_ENABLED": "true",
                "NOSTR_PRIVATE_KEY": "ff" * 32,
                "PUBLIC_URL": PUBLIC_URL,
            },
        ),
        (
            "discovery enabled, credentials in public url",
            {
                "PAYMENTS_ENABLED": "false",
                "NOSTR_DISCOVERY_ENABLED": "true",
                "NOSTR_PRIVATE_KEY": VALID_KEY,
                "PUBLIC_URL": "https://operator:s3cret@agent.example.test",
            },
        ),
    ],
)
def test_incomplete_configuration_refuses_to_start(tmp_path, label, env):
    result = _import_main(tmp_path, **env)
    assert result.returncode != 0, f"{label}: the app started anyway"
    assert "Refusing to start" in result.stderr, f"{label}: no clear refusal, got {result.stderr}"
    # The refusal is also the place a key or an embedded URL credential would leak.
    for secret in (env.get("NOSTR_PRIVATE_KEY"), "s3cret"):
        if secret:
            assert secret not in result.stderr, f"{label}: leaked a secret into the refusal"


def test_private_free_mode_imports_cleanly(tmp_path):
    """The StartOS default: payments off, discovery off, nothing else set."""
    result = _import_main(tmp_path, PAYMENTS_ENABLED="false", NOSTR_DISCOVERY_ENABLED="false")
    assert result.returncode == 0, result.stderr
    assert "Refusing to start" not in result.stderr
