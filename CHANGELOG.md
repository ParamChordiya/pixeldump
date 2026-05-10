# Changelog

All notable changes to PixelDump will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.1.0] — 2026-05-10

First public release.

### Added

#### Pipeline

- Six-phase agentic pipeline: **scan → hash → cluster → classify → name → move**
- Phase 1 (Scanner): recursive file discovery with EXIF extraction — date taken,
  GPS coordinates, camera model, image dimensions. Supports JPEG, PNG, HEIC/HEIF,
  WebP, GIF, TIFF, BMP, and raw formats (CR2, CR3, NEF, ARW, DNG, ORF, RW2).
  Hidden directories and PixelDump's own output folders are skipped automatically.
- Phase 2 (Hasher): exact duplicate detection via SHA-256; near-duplicate
  detection via perceptual hash (pHash) with configurable Hamming distance
  threshold (default ≤ 5). Concurrent hashing via `ThreadPoolExecutor`.
  Union-find grouping handles transitive similarity chains correctly.
- Phase 3 (Clusterer): event grouping by time gaps (configurable `burst_hours`,
  default 72 h) and GPS proximity (configurable `gps_radius_km`, default 50 km).
  Large multi-day clusters (≥ 100 photos, span > 24 h) are split by calendar day.
  Undated photos are collected into a dedicated `no_date` cluster.
- Phase 4 (Classifier): concurrent LLM classification of event clusters against
  a fixed taxonomy of 11 categories (life events, holidays, travel, social,
  everyday, professional, documents, nature, creative, vehicles, uncategorized).
  Per-cluster fallback to `uncategorized` on provider error.
- Phase 5 (Namer): LLM-generated folder names with three naming modes.
  Names are sanitized to `[a-z0-9_]`, max 40 characters. Low-confidence clusters
  (< 0.5) and undated photos are routed to `_review/`.
- Phase 6 (Mover): collision-safe move planning with `_1`, `_2` suffixes.
  Duplicates go to `_review/duplicates/`. Output layout: `{year}/{YYYY_MM_name}/`.
  Dry-run by default — nothing moves until `--apply` is passed.

#### AI Providers

- **Claude provider** — Anthropic API (`claude-sonnet-4-20250514`). Handles
  rate limiting with exponential backoff. Cost estimation before any API call.
- **Ollama provider** — local inference, no API key required. Tested with
  Gemma 3, LLaVA, and Llama 3.2 Vision.
- Auto provider selection: Claude is preferred when `ANTHROPIC_API_KEY` is set;
  falls back to Ollama if Claude is unreachable.
- Abstract `VisionProvider` base class — plug in any vision LLM by subclassing
  five methods.

#### Naming modes

- `--mode corporate` — clean, descriptive: `2024_03_japan_trip`
- `--mode chaotic` — personality-forward: `2024_03_ate_good_in_tokyo`
- `--mode unhinged` — chronically online: `2024_03_proof_i_went_outside_once`

#### CLI

- `pixeldump run <dir>` — main command; interactive wizard on first run
- `pixeldump run --apply` — execute moves (dry-run is the default)
- `pixeldump run --estimate` — print cost estimate without scanning
- `pixeldump run --provider <claude|ollama>` — override auto-selection
- `pixeldump run --mode <corporate|chaotic|unhinged>` — override naming mode
- `pixeldump run --sass <0-3>` — control roast intensity at completion
- `pixeldump run --quiet` — suppress TUI, plain text output only
- `pixeldump undo <manifest>` — reverse a previous run using its manifest
- `pixeldump setup` — interactive provider and preference configuration
- `pixeldump estimate <dir>` — standalone cost estimate

#### TUI

- Textual-based dashboard with live phase indicator, progress bar, activity
  log, and running stats panel
- Splash screen on startup
- Interactive setup wizard for first-time configuration
- Receipt screen at completion — stats, easter eggs, and an LLM-generated roast
  of the user's photo library

#### Reliability

- Dry-run by default — no files move without explicit `--apply`
- Every move logged to a JSON manifest at `.pixeldump/manifests/{run_id}.json`
- Resumable runs — interrupt and restart without reprocessing completed phases
- Undo support — manifest-based reversal of any previous run
- Filename collision resolution — `_1`, `_2` suffixes prevent overwrites
- Provider errors are isolated per-cluster; one bad API call does not abort
  the entire run

#### Developer tooling

- Multi-OS CI matrix: Ubuntu and macOS, Python 3.10 / 3.11 / 3.12
- PyPI publishing via OIDC trusted publishing (no stored API token)
- CodeQL security scanning on every push to `main`
- `mypy --strict` enforced on `src/` in CI and pre-commit
- `ruff` for linting and formatting
- Pre-commit hook suite: ruff, mypy, trailing-whitespace, EOF newline,
  YAML/TOML syntax checks, 500 KB file size guard
- 170 tests across 16 test files; branch coverage tracked

---

[Unreleased]: https://github.com/ParamChordiya/pixeldump/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ParamChordiya/pixeldump/releases/tag/v0.1.0
