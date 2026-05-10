# Security Policy

## Supported versions

| Version | Security fixes |
|---|---|
| 0.1.x | Yes |
| < 0.1 | No |

Only the latest release in the `0.1.x` line receives security patches.
If you are on an older version, upgrade before reporting.

---

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.** Public
disclosure before a fix is available puts everyone using PixelDump at risk.

Send an email to **param1111.chordiya@gmail.com** with:

- **Subject:** `SECURITY: pixeldump — <one-line description>`
- **Version affected:** the exact version you were running (`pip show pixeldump`)
- **Steps to reproduce:** a minimal, concrete sequence of steps that triggers
  the issue. If a script or input file is needed, attach it.
- **Impact assessment:** what an attacker could do with this — data exposure,
  arbitrary file writes, key leakage, etc. Your best guess is fine; we will
  verify independently.
- **Environment:** OS, Python version, provider (Claude / Ollama / neither)

You do not need to have a fix ready. A clear reproduction is enough.

---

## What happens next

| Timeline | Action |
|---|---|
| Within 48 hours | Acknowledgment that the report was received |
| Within 7 days | Initial assessment: confirmed, needs more info, or not a vulnerability |
| Within 90 days | Patch released for confirmed critical or high-severity issues |
| At release | GitHub Security Advisory published; CVE requested if warranted |

For lower-severity issues the timeline may be longer. We will keep you updated
either way.

Once a fix ships, we are happy to credit you in the advisory and changelog
unless you prefer to stay anonymous.

---

## Scope

### In scope

These are the areas where we are most concerned about security issues:

- **Path traversal** — the mover phase constructs destination paths from
  user-provided directories and LLM-generated folder names. Anything that could
  cause a file to land outside the intended output tree is a serious bug.
- **EXIF injection** — malformed EXIF data that causes unexpected behavior
  during parsing (e.g., directory traversal via an embedded path, or a crash
  that leaks memory contents).
- **API key exposure** — any code path that could write the `ANTHROPIC_API_KEY`
  or Ollama credentials to logs, manifests, or stdout.
- **Command injection** — the CLI accepts user-supplied paths and passes them
  to filesystem operations. Inputs that escape their intended context are in
  scope.
- **Manifest tampering** — the JSON manifests stored in `.pixeldump/` are read
  back for undo operations. Malformed or adversarially crafted manifests that
  cause unintended file operations are in scope.

### Out of scope

- Vulnerabilities in upstream dependencies (`Pillow`, `anthropic`, `textual`,
  etc.) that are already tracked by those projects. Report those upstream.
- Bugs that require physical access to the machine running PixelDump.
- Issues in development-only tooling (`ruff`, `mypy`, `pre-commit`) that do
  not affect the installed package.
- Denial-of-service via pathologically large input files — PixelDump is a
  local CLI tool, not a server; resource exhaustion from your own files is
  expected behavior.
- Theoretical issues with no concrete reproduction path.

---

## A note on LLM-generated folder names

PixelDump sends photo thumbnails to Claude or Ollama and uses the model's
response as a folder name. The `sanitize_name` function in `core/namer.py`
strips everything that is not `[a-z0-9_]` and clamps length to 40 characters
before any name touches the filesystem. If you find a way to bypass this
sanitization and write to an unintended path, that is a high-severity report.
