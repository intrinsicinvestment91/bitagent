# CI Failure Analysis Plan

## CI Run Summary

| Field | Value |
|---|---|
| Workflow | CI |
| Job | test |
| Branch | main |
| Commit SHA | `b2ee3b262aeacc2119350389732b4bf24c898941` |
| Python version | 3.11.15 (ubuntu-24.04) |
| Failing command | `pytest tests/ -v --tb=short -x` |
| Run ID | 25160463732 |
| Also failed | run 25145179466 (`4f6971f`) — same error |

## Failure Stage

- [ ] Dependency install — succeeded cleanly
- [x] Test collection — dies here
- [ ] Test execution
- [ ] Lint/typecheck
- [ ] Packaging/deploy

## First Failure

```text
ERROR collecting tests/security/test_security_features.py
ImportError while importing test module '...tests/security/test_security_features.py'.
tests/security/test_security_features.py:18: in <module>
    from security.authentication import AuthenticationManager, RateLimiter
E   ModuleNotFoundError: No module named 'security'
```

Because `-x` is passed, pytest stops at the first collection error. No other test output follows.

## Root Cause Hypothesis

`tests/security/test_security_features.py` manipulates `sys.path` with a hardcoded absolute path
that only exists on the developer's local machine:

```python
import sys
sys.path.append('/home/charlie/bitagent/src')  # line 16

from security.authentication import AuthenticationManager, RateLimiter  # line 18
```

In CI the runner works under `/home/runner/work/bitagent/bitagent/`, so
`/home/charlie/bitagent/src` doesn't exist and the path append silently no-ops.
Pytest's default `sys.path` starts with the repo root, not `src/`, so bare
`security.*` / `identity.*` / `monitoring.*` imports fail.

This is a **pre-existing issue** — it has been the CI blocker in every run since at
least commit `ec82ad6` (Apr 25). It is not a regression from recent packet work.
The fix was identified and documented in CLAUDE.md before this analysis.

## Evidence

1. Run `25160463732` and `25145179466` both fail at the same file and line.
2. Install step exits 0 — all deps present, not a dependency issue.
3. `sys.path.append('/home/charlie/bitagent/src')` at line 16 is an absolute
   path that resolves only on the developer's machine.
4. The pattern used by the recently-fixed `tests/integration/test_agent_integration.py`
   — `from src.security.authentication import ...` — works fine in CI and locally.
5. No `pytest.ini` / `pyproject.toml` / `setup.cfg` exists, so no `pythonpath`
   setting to rescue bare imports.

## Classification

- [ ] Baseline issue
- [ ] Branch sync issue
- [ ] Dependency issue
- [x] Test issue — hardcoded absolute local path + bare module imports
- [ ] Workflow config issue
- [ ] Real regression

## Affected Files

### Primary (must fix for CI to proceed)

* `tests/security/test_security_features.py` — lines 15-23: `sys.path.append` + 6 bare imports

### Secondary (same pattern, fragile but currently passing)

* `tests/test_did_identity.py` — `sys.path.insert(0, "./src")` + `from identity.did import DIDIdentity`.
  This uses a relative path so it works when pytest is run from the repo root, but is fragile and
  uses the old bare-import style.

### No action needed

* `tests/test_agents_functionality.py`, `tests/test_agents_server.py`,
  `tests/test_security_fixes.py`, `tests/test_start9_payments.py` — all use
  `sys.path.append('.')` (repo root, not `src/`), and their imports go through
  top-level modules (`agent_wallet`, `main`, etc.) that live at the root. These work.

## Proposed Fix Plan for Cursor

### Step 1 — Remove the bad path manipulation and fix all 6 imports in `tests/security/test_security_features.py`

Delete lines 15-16:
```python
# DELETE these two lines:
import sys
sys.path.append('/home/charlie/bitagent/src')
```

Replace the 6 bare imports (lines 18-23) with `src.*` equivalents:

```python
# BEFORE
from security.authentication import AuthenticationManager, RateLimiter
from security.encryption import EncryptionManager, KeyExchange, SecureMessage, InputValidator
from security.secure_communication import SecureCommunicationManager, MessageType, SecurityLevel
from security.payment_security import PaymentSecurityManager, EscrowStatus, DisputeStatus
from identity.enhanced_did import EnhancedDIDManager, DIDMethod, CredentialType, TrustLevel
from monitoring.audit_logger import AuditLogger, EventType, SecurityEvent, LogLevel

# AFTER
from src.security.authentication import AuthenticationManager, RateLimiter
from src.security.encryption import EncryptionManager, KeyExchange, SecureMessage, InputValidator
from src.security.secure_communication import SecureCommunicationManager, MessageType, SecurityLevel
from src.security.payment_security import PaymentSecurityManager, EscrowStatus, DisputeStatus
from src.identity.enhanced_did import EnhancedDIDManager, DIDMethod, CredentialType, TrustLevel
from src.monitoring.audit_logger import AuditLogger, EventType, SecurityEvent, LogLevel
```

### Step 2 — Create missing `tests/security/__init__.py`

Create an empty `tests/security/__init__.py`. Its absence doesn't directly cause
the current error, but it matches the pattern of all other test subdirectories and
prevents namespace resolution surprises.

### Step 3 — (Optional, lower priority) Fix `tests/test_did_identity.py`

Replace:
```python
import sys
sys.path.insert(0, "./src")
from identity.did import DIDIdentity
```
With:
```python
from src.identity.did import DIDIdentity
```

This test currently passes locally only because pytest is invoked from the repo root.

### Step 4 — Run locally to confirm collection passes

```bash
pytest tests/security/test_security_features.py --collect-only
pytest tests/ --collect-only
```

### Step 5 — Run the full suite

```bash
pytest tests/ -v --tb=short -x
```

Note: Some security tests may fail at *execution* time (not collection) after the
import fix. For example:

* `TestPaymentSecurity` exercises `PaymentSecurityManager` which imports from
  `src.security.payment_security`. Verify the class has all methods exercised by
  the tests (`create_escrow_payment`, `fund_escrow`, `create_dispute`,
  `detect_payment_fraud`).
* `TestSecureCommunication` async tests require `pytest-asyncio` with
  `@pytest.mark.asyncio` and will run in `Mode.STRICT` (no `pytest.ini` sets the
  mode, so 1.x defaults to strict). Tests already have the decorator — verify
  no new asyncio warnings.

If new failures appear after the import fix, open a separate fix packet per failure
category (do not batch unrelated fixes).

## Validation Commands

```bash
# After applying fixes, verify collection is clean:
pytest tests/security/test_security_features.py --collect-only

# Full suite dry run:
pytest tests/ --collect-only

# Full suite execution (mirrors CI command exactly):
LNBITS_URL=https://demo.lnbits.com LNBITS_API_KEY=demo pytest tests/ -v --tb=short -x
```

## Risks

* After fixing the collection error, test *execution* failures in `TestPaymentSecurity`
  or `TestSecureCommunication` may surface that were previously hidden. These should
  be triaged in a follow-up packet.
* `pytest-asyncio==1.3.0` is a major-version bump from the 0.x line. No `pytest.ini`
  configures `asyncio_mode`, so it defaults to `strict`. This is fine for current
  tests (all async tests have `@pytest.mark.asyncio`), but any new async tests added
  without the decorator will fail silently in strict mode.
* Node.js 20 deprecation: `actions/checkout@v4` and `actions/setup-python@v5` print
  a deprecation warning but do not fail yet. These actions will need updating before
  September 16, 2026.

## Rollback Plan

The change is limited to test files only — no production or source code is modified.
Rolling back is a single `git revert` of the fix commit, with zero impact on
deployed behavior.

## Recommended Follow-Up Packet

**Title:** fix: resolve post-import execution failures in tests/security/test_security_features.py

**Objective:** After the import fix unblocks collection, run the security test suite and
fix any execution-level failures that surface in `TestPaymentSecurity`,
`TestSecureCommunication`, or `TestSecurityIntegration`.

**Files to inspect:**
- `src/security/payment_security.py` — verify `PaymentSecurityManager` API matches test expectations
- `src/security/secure_communication.py` — verify channel/message API matches test expectations
- `tests/security/test_security_features.py` — update test assertions if API has diverged

**Acceptance criteria:**
- `pytest tests/security/ -v` passes with 0 errors, 0 failures
- `pytest tests/ -v --tb=short -x` exits 0 in CI
