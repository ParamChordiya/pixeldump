# Development

---

## Prerequisites

- **Python 3.10 or later** (3.11 or 3.12 recommended; CI tests all three)
- **git**
- **Ollama** (optional) — required only for testing the local provider path.
  Install from https://ollama.com and pull a vision-capable model (`gemma3`,
  `llava`, or `llama3.2-vision`).

---

## Setup

```bash
git clone https://github.com/ParamChordiya/pixeldump.git
cd pixeldump

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
pre-commit install
```

`pip install -e ".[dev]"` installs the package in editable mode plus all
development dependencies: `pytest`, `pytest-cov`, `pytest-asyncio`, `ruff`,
`mypy`, and `pre-commit`.

---

## Running the Test Suite

Run the full suite:

```bash
pytest
```

Stop on first failure:

```bash
pytest -x
```

Run a single test file with verbose output:

```bash
pytest tests/test_scanner.py -v
```

Run with coverage (branch coverage, same as CI):

```bash
pytest --cov=pixeldump --cov-report=term-missing
```

Tests live in `tests/`. The `asyncio_mode = "auto"` setting in `pyproject.toml`
means async test functions are discovered and run automatically without
explicit `@pytest.mark.asyncio` decoration.

---

## Linting and Formatting

**Lint** (check for errors, style violations, and code smells):

```bash
ruff check src/ tests/
```

**Format** (auto-apply formatting, then fix auto-fixable lint violations):

```bash
ruff format src/ tests/
ruff check --fix src/ tests/
```

**Type-check** (strict mypy, mirrors CI):

```bash
mypy src/
```

mypy is configured in strict mode in `pyproject.toml`. Third-party packages
without type stubs (`exifread`, `imagehash`, `ollama`, `pillow_heif`) have
`ignore_missing_imports = true` set per-module.

---

## Make Targets

The `Makefile` wraps the above commands:

| Target | Equivalent command(s) |
|---|---|
| `make install` | `pip install -e ".[dev]"` + `pre-commit install` |
| `make test` | `pytest` |
| `make lint` | `ruff check .` |
| `make format` | `ruff format .` then `ruff check --fix .` |
| `make typecheck` | `mypy src/` |
| `make clean` | Remove build artifacts, caches, coverage data |

---

## Pre-commit Hooks

The following hooks run automatically on every `git commit`:

| Hook | Tool | Scope |
|---|---|---|
| Lint with auto-fix | `ruff --fix` | entire repo |
| Format | `ruff-format` | entire repo |
| Type-check | `mypy` | `src/` only |
| Trailing whitespace | `pre-commit-hooks` | entire repo |
| EOF newline | `pre-commit-hooks` | entire repo |
| YAML syntax check | `pre-commit-hooks` | entire repo |
| TOML syntax check | `pre-commit-hooks` | entire repo |
| Large file guard | `pre-commit-hooks` | blocks files > 500 KB |

Run all hooks manually without committing:

```bash
pre-commit run --all-files
```

Update hook versions to their latest revisions:

```bash
pre-commit autoupdate
```

---

## Provider Setup for Local Testing

### Claude (Anthropic API)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Alternatively, store it in the PixelDump config file:

```bash
pixeldump setup
# choose "claude" and paste the key when prompted
```

The key is saved to the platform config path (e.g.,
`~/Library/Application Support/pixeldump/config.yaml` on macOS).

### Ollama (local)

1. Install Ollama: https://ollama.com/download
2. Pull a vision model:
   ```bash
   ollama pull gemma3
   ```
3. Verify the server is running:
   ```bash
   ollama list
   ```
4. Run `pixeldump setup` and choose "ollama" to save host and model to config,
   or rely on the defaults (`http://localhost:11434`, model `gemma3`).

For unit tests that exercise provider logic, the test suite uses lightweight
fakes rather than making real API calls. See `tests/` for fixture patterns.

---

## Frozen Contracts

Two files are designated **frozen contracts**. All pipeline phases and the TUI
depend on the exact signatures defined in them:

- **`src/pixeldump/core/types.py`** — all dataclass types, enums, and field
  names shared across phases.
- **`src/pixeldump/providers/base.py`** — the `VisionProvider` abstract base
  class; any change to an abstract method signature breaks both
  `ClaudeProvider` and `OllamaProvider`.

Before modifying either file:
1. Search for every import of the symbol you are changing across `src/` and
   `tests/`.
2. Open a discussion or issue describing the change and its rationale.
3. Update all consumers in the same PR; do not leave the codebase in a
   partially-migrated state.

---

## Release Process

1. Bump the version in `pyproject.toml` (`version = "X.Y.Z"`).
2. Update `CHANGELOG.md` with the changes in this release.
3. Commit both files:
   ```bash
   git add pyproject.toml CHANGELOG.md
   git commit -m "chore: release vX.Y.Z"
   ```
4. Tag the commit:
   ```bash
   git tag vX.Y.Z
   git push origin main --tags
   ```

Pushing a `v*` tag triggers the `release.yml` CI workflow, which:
- Builds the source distribution and wheel using `hatch build`.
- Publishes to PyPI via the `pypa/gh-action-pypi-publish` action using OIDC
  trusted publishing (no stored API token needed; configured under the `pypi`
  GitHub Actions environment).

Do not manually upload to PyPI. All releases go through CI.
