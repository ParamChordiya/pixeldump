# Contributing to PixelDump

Thanks for your interest! PixelDump is built in waves: scaffolding, then
parallel module implementation, then polish. Contributions are welcome at
any stage.

## Getting set up

```bash
git clone https://github.com/pixeldump/pixeldump.git
cd pixeldump
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Common tasks

```bash
make test        # run pytest
make lint        # ruff check
make format      # ruff format + autofix
make typecheck   # mypy strict on src/
```

## Pull request flow

1. Fork and create a feature branch off `main`.
2. Make your changes. Keep PRs focused.
3. Add or update tests. Aim for tests that fail without your change and pass with it.
4. Run `make test lint typecheck` locally.
5. Open a PR using the template. Link any related issues.
6. A maintainer will review. Address feedback with new commits (do not force-push during review).

## Type contracts

The files `src/pixeldump/core/types.py` and `src/pixeldump/providers/base.py`
are frozen contracts. Wave 2 modules and external integrations rely on them.
Changes to those files require coordination with all downstream consumers
and a clear migration note in the PR description.

## Code style

- `ruff` enforces formatting and lint rules; the config lives in `pyproject.toml`.
- `mypy --strict` is enforced on `src/`.
- Use `from __future__ import annotations` in every module.
- Use `pathlib.Path` rather than bare strings for filesystem paths.

## Reporting bugs / requesting features

Use the issue templates. Discussions are open for open-ended questions.

## Code of conduct

By participating you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).
