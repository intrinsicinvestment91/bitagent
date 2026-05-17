# CI Failure Diagnosis — Runs 25977738781 and 25977797499

## Summary

Both failed runs have the same root cause and the same first failing test.

| Field | Run 1 (PR branch) | Run 2 (main) |
|---|---|---|
| Workflow | CI | CI |
| Branch | `feat/agent-registry` | `main` |
| Commit SHA | `fa88715` | `0b68e34` |
| Failing job | `test` → Run tests | `test` → Run tests |
| Failing command | `pytest tests/agents/ tests/integration/ tests/security/ -v --tb=short -x` |  |
| Failure type | **Test collection** |  |
| First failing test | `tests/agents/test_registry_router.py::TestRegistryList::test_empty_registry_returns_zero` |  |

## First Traceback

```
FAILED tests/agents/test_registry_router.py::TestRegistryList::test_empty_registry_returns_zero
- Failed: async def functions are not natively supported.
You need to install a suitable plugin for your async framework, for example:
  - anyio
  - pytest-asyncio
  ...
```

## Root Cause

`test_registry_router.py` uses `async def` test methods. pytest-asyncio only runs async test functions automatically when `asyncio_mode = auto`. In CI it defaults to `STRICT` because no `pytest.ini` exists inside the repository.

The config file that sets `asyncio_mode = auto` lives at `/home/charlie/pytest.ini` — one directory above the project root. pytest walks up from the invocation directory and finds it locally but GitHub Actions runs from `/home/runner/work/bitagent/bitagent/`, where no config file exists in any ancestor directory within the checkout tree.

### Local vs CI config resolution

| Environment | `pytest.ini` found | `asyncio_mode` |
|---|---|---|
| Local (Python 3.13.9, pytest 8.4.2) | `/home/charlie/pytest.ini` | `auto` |
| CI (Python 3.11.15, pytest 9.0.3) | *(none in checkout)* | `strict` (default) |

### Diagnosis questions

- **Did PR 10 mix Packet 15 + 16?** No. Packet 15 was merged separately as PR #9. PR #10 contains only Packet 16 (registry endpoint). The affected test file is `test_registry_router.py`, introduced in Packet 16.
- **Did CI fail on `main` or only the PR branch?** Both — the same commit was on the PR branch when CI ran, and then merged to `main` before the second run.
- **Is failure from registry endpoint code?** No. The endpoint and router code are correct. Failure is in test collection only.
- **Is failure from discovery singleton state leaking?** No — the singleton is patched via `unittest.mock.patch` in every test; state does not leak.
- **Is failure from async WebSocket query tests?** No — `TestWsQuery` and `TestQueryEvents` use `asyncio.run()` in sync methods and pass on both local and CI.
- **Is failure from import path or missing route registration?** No — 44 tests pass before the first failure; imports are fine.

## Minimal Fix

Add a `pytest.ini` at the project root so the config is committed to the repository and available in CI:

```ini
[pytest]
asyncio_mode = auto
addopts = -q
testpaths = tests
```

This is identical to the parent-directory config that makes tests pass locally. No test code changes required.

**Alternative (not chosen):** Add `pytestmark = pytest.mark.asyncio` at the top of `test_registry_router.py`. This would work but leaves the project without a committed pytest config, guaranteeing the same failure pattern for any future async test file.

## Validation Commands

```bash
# Simulate CI (strict default, no parent ini)
PYTHONPATH=. pytest tests/agents/ tests/integration/ tests/security/ -p no:cacheprovider --override-ini="asyncio_mode=strict" -q

# Normal local run after fix
PYTHONPATH=. pytest tests/agents/ tests/integration/ tests/security/ -q
```

## Rollback Plan

Delete `pytest.ini` from the project root to revert to parent-directory config resolution. This does not revert any test or source code.
