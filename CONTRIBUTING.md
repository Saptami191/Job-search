# Contributing

## Local setup

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Copy the sanitized files from `examples/` before running the CLI. Never add
personal profiles, `.env` files, databases, browser sessions, job history, or
generated application materials to a pull request.

## Tests and checks

Run:

```powershell
python -m pytest
python -m compileall job_scout
python -m build --no-isolation
```

Tests should be deterministic and use temporary directories or mocked responses.
Do not make requests to job boards or submit applications from tests.

## Pull requests

- Keep changes focused and explain behavior changes.
- Add or update tests for changed behavior.
- Update the README or changelog when user-facing behavior changes.
- Preserve the human approval gate and responsible-source-collection rules.
