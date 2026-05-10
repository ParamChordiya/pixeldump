# Architecture

PixelDump is a six-phase pipeline that turns a raw camera roll into a
date-prefixed, AI-named folder hierarchy. Each phase is a pure module in
`src/pixeldump/core/`; the orchestrator (`app.py`) wires them together and
feeds progress events to the TUI.

---

## Pipeline Overview

```
target_dir
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1 · Scanner          core/scanner.py                     │
│  scan(target_dir) → ScanResult                                  │
│  out: photos: list[PhotoMetadata], videos, skipped              │
└─────────────────────────────────────────────────────────────────┘
    │ list[PhotoMetadata]
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 2 · Hasher           core/hasher.py                      │
│  hash_all() + find_duplicates() → list[DuplicateGroup]          │
│  mutates: photo.sha256, photo.phash                             │
└─────────────────────────────────────────────────────────────────┘
    │ list[PhotoMetadata] (with hashes), list[DuplicateGroup]
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 3 · Clusterer        core/clusterer.py                   │
│  cluster() → list[EventCluster]                                 │
│  out: cluster_id like "2024-03-15_a", "no_date"                 │
└─────────────────────────────────────────────────────────────────┘
    │ list[EventCluster]
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 4 · Classifier       core/classifier.py                  │
│  classify_clusters() → dict[cluster_id, Classification]         │
│  calls VisionProvider.classify_cluster() concurrently           │
└─────────────────────────────────────────────────────────────────┘
    │ dict[str, Classification]
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 5 · Namer            core/namer.py                       │
│  name_cluster() → dict[cluster_id, FolderName]                  │
│  calls VisionProvider.name_event(), applies NamingMode          │
└─────────────────────────────────────────────────────────────────┘
    │ dict[str, FolderName]
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 6 · Mover            core/mover.py                       │
│  plan_moves() + apply_moves() → RunManifest                     │
│  out: full audit trail persisted by utils/state.py              │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
RunManifest  (persisted at .pixeldump/manifests/<run_id>.json)
```

---

## Phase 1 — Scanner

**File:** `core/scanner.py`

**Responsibility:** Recursively walk `target_dir`, identify image and video
files, extract EXIF metadata from each image, and return a structured result.

**Input:** `target_dir: Path`, `include_videos: bool`

**Output:** `ScanResult`
- `photos: list[PhotoMetadata]` — every non-video image found
- `videos: list[PhotoMetadata]` — video files (only when `include_videos=True`)
- `skipped: list[Path]` — files that failed stat/decode
- `total_size_bytes: int`
- `format_breakdown: dict[str, int]` — count per extension (`.jpg`, `.heic`, …)

**Supported image formats:** JPEG, PNG, HEIC/HEIF, WebP, GIF, TIFF, BMP, and
a range of raw formats (CR2, CR3, NEF, ARW, DNG, ORF, RW2).

**Exclusion rules:** Any path component that starts with `.` (hidden), equals
`_review`, `_videos`, `.pixeldump`, or starts with `_pixeldump` is skipped.
Zero-byte files are skipped. This prevents PixelDump from re-processing its
own output directories on subsequent runs.

**EXIF extraction** is handled by `utils/exif.py` (wrapping `exifread`):
- `date_taken` — EXIF `DateTimeOriginal`; falls back to file mtime when absent
- `gps` — latitude/longitude decoded from GPS IFD tags
- `camera_model` — `Image Make` + `Image Model`

**Design note:** The scanner produces only metadata; it never reads image
pixels. Heavy work (hashing, thumbnail generation) is deferred to later phases
so a scan of a large library is fast and cheap.

---

## Phase 2 — Hasher

**File:** `core/hasher.py`

**Responsibility:** Populate `sha256` and `phash` on each `PhotoMetadata` and
group duplicates into `DuplicateGroup`s.

**Input:** `list[PhotoMetadata]`

**Output:**
- Same list, mutated with `photo.sha256` and `photo.phash` populated
- `list[DuplicateGroup]` from `find_duplicates()`

**Exact duplicates (Pass 1):** Files sharing the same SHA-256 digest are
grouped. `_pick_kept` selects the highest-resolution copy; ties break by
`file_size` descending, then path lexicographically.

**Near-duplicates (Pass 2):** Perceptual hashes (`imagehash.phash`) are
compared pairwise using Hamming distance. Any pair within distance ≤ 5 (the
`near_duplicate_threshold`) is connected. **Union-find** groups connected
components: it handles transitive similarity chains correctly without O(n²)
cluster merging — if A≈B and B≈C, all three end up in one group even if A and
C are farther apart than the threshold.

**Why `ThreadPoolExecutor` not `ProcessPoolExecutor`:** Pillow releases the
GIL during image decoding, and `hashlib` does so for large reads. Threads
therefore achieve real I/O parallelism without the serialization overhead that
a process pool would impose when pickling `PhotoMetadata` objects back and
forth.

**Known limitation:** The pairwise O(n²) near-dup scan is acceptable up to
roughly 5,000 photos. A BK-tree is planned for larger libraries (see TODO in
`hasher.py`).

---

## Phase 3 — Clusterer

**File:** `core/clusterer.py`

**Responsibility:** Group dated photos into discrete events using time gaps and
GPS proximity. Undated photos go into a special `"no_date"` cluster.

**Input:** `list[PhotoMetadata]`, `burst_hours: int = 72`,
`gps_radius_km: float = 50.0`

**Output:** `list[EventCluster]`

**Algorithm (three passes):**

1. **Temporal split** — Sort photos by `date_taken`. Insert a cluster boundary
   wherever consecutive photos are more than `burst_hours` apart. Default of
   72 h means photos from the same long weekend stay together but separate
   weekend trips are split.

2. **GPS sub-split** — Within each temporal group, GPS-tagged photos are
   assigned greedily to running centroids. A photo joins the nearest existing
   centroid if it is within `gps_radius_km`; otherwise it starts a new
   sub-cluster. Photos without GPS are assigned to the temporally closest
   sub-cluster. **Why greedy centroid rather than DBSCAN or k-means?** The
   algorithm must work without knowing k in advance and must handle mixed
   GPS/no-GPS data. Greedy centroid is O(n·k) and deterministic given input
   order, which keeps results stable across re-runs.

3. **Day-split for large clusters** — Any group with ≥ 100 photos spanning
   more than 24 hours is split by calendar day. This prevents a week-long
   festival from producing one enormous folder.

**Cluster IDs** are stable strings like `"2024-03-15_a"`, `"2024-03-15_b"`,
etc. The suffix increments alphabetically per calendar day, with two-letter
suffixes (`aa`, `ab`, …) after the first 26.

---

## Phase 4 — Classifier

**File:** `core/classifier.py`

**Responsibility:** Send sampled photos from each cluster to a `VisionProvider`
and return a category + confidence for every cluster.

**Input:** `list[EventCluster]`, `VisionProvider`, `batch_size: int = 5`,
`concurrency: int = 4`

**Output:** `dict[str, Classification]` — keyed by `cluster_id`

**Sampling strategy:** For clusters larger than `batch_size`, photos are chosen
at evenly-spaced indices over `[0, n-1]`, guaranteeing the first and last are
always included. The `"no_date"` cluster just takes the first `batch_size`
photos.

**Concurrency:** `classify_clusters` runs each cluster in its own thread via
`ThreadPoolExecutor`. LLM API calls are network-bound; a thread pool is the
right primitive here (no CPU-bound work, no pickling needed).

**Error handling:** Any per-cluster exception produces a fallback
`Classification(category="uncategorized", confidence=0.0)` so one bad cluster
does not abort the run. Invalid category strings from the provider are also
mapped to `"uncategorized"`.

**Taxonomy validation:** `core/taxonomy.py` maintains the allowed category
list. The classifier validates provider output against it.

---

## Phase 5 — Namer

**File:** `core/namer.py`

**Responsibility:** Convert each `Classification` into a `FolderName` by
calling `VisionProvider.name_event()` with sampled thumbnails and applying
routing rules.

**Input:** `EventCluster`, `Classification`, `VisionProvider`, `NamingMode`

**Output:** `FolderName(name, date_prefix)`

**Routing rules (in priority order):**

| Condition | Result |
|---|---|
| `cluster_id == "no_date"` | `_review/no_date/` |
| `classification.confidence < 0.5` | `_review/low_confidence/` |
| `category == "documents"` and `subcategory == "screenshot"` | `{year}/screenshots/` |
| Otherwise | `{year}/{YYYY_MM}_{name}/` |

**`NamingMode`** controls the personality prompt sent to the provider:
- `corporate` — professional, descriptive names (`team_offsite_q1`)
- `chaotic` — casual, slightly unhinged (`chaotic` is the default)
- `unhinged` — full Gen-Z energy, no guardrails

**Name sanitization:** Output is lowercased, spaces/hyphens become
underscores, non-`[a-z0-9_]` characters are stripped, consecutive underscores
are collapsed, and the result is clamped to 40 characters. This runs in both
`namer.py` and each provider implementation to guarantee filesystem safety.

---

## Phase 6 — Mover

**File:** `core/mover.py`

**Responsibility:** Build the full list of `MoveOperation`s and either execute
or simulate them. Returns a `RunManifest` capturing every move.

**Input:** `list[EventCluster]`, `dict[str, FolderName]`,
`list[DuplicateGroup]`, `PipelineConfig`

**Output:** `RunManifest`

**Move planning order:**

1. **Duplicates** — all non-kept files from `DuplicateGroup`s go to
   `_review/duplicates/` first, so cluster moves never attempt to move a file
   that is already planned.
2. **Cluster moves** — each photo is placed at
   `{root}/{year}/{date_prefix}_{name}/{filename}`, or under `_review/` for
   routed clusters.

**Collision resolution:** If two photos share a filename within the same
destination folder, the second gets `_1`, the third `_2`, etc. Resolution is
tracked against a `used_destinations` set built during planning, so it works
correctly in dry-run mode too.

**`dry_run=True`** populates the manifest without touching the filesystem.
**`dry_run=False`** calls `shutil.move`, creating destination directories as
needed. Failed individual moves are logged and skipped; the run continues.

**Manifest persistence:** `apply_moves` builds and returns the `RunManifest`;
the orchestrator (`app.py`) calls `utils/state.write_manifest` to persist it.
The mover has no filesystem side effects beyond the moves themselves.

---

## Provider Abstraction

**File:** `providers/base.py`

`VisionProvider` is an abstract base class defining the interface all LLM
backends must implement:

```
VisionProvider (ABC)
├── is_available() → bool
├── estimate_cost(num_photos) → CostEstimate | None
├── classify_cluster(photos) → Classification
├── name_event(photos, category, mode) → str
└── generate_roast(stats) → str
```

### ClaudeProvider (`providers/claude.py`)

Backed by the Anthropic API using `claude-sonnet-4-20250514`. Thumbnails are
base64-encoded and sent as vision content blocks. Pricing is estimated at
$3.00/MTok input and $15.00/MTok output. Rate limit errors are retried with
exponential backoff (1 s → 2 s → 4 s). `is_available()` performs a cheap
one-token probe call and caches the result.

### OllamaProvider (`providers/ollama.py`)

Backed by a locally running Ollama server (default: `http://localhost:11434`).
Default model is `gemma3`; if it is not installed, `is_available()` falls back
through `llava` then `llama3.2-vision`. `estimate_cost` returns `None`
(local inference has no monetary cost).

### Auto-selection logic

When `provider = "auto"` (the default):

1. Check `ANTHROPIC_API_KEY` env var and `claude_api_key` from the YAML config.
2. If a key is present and `ClaudeProvider.is_available()` returns `True`, use Claude.
3. Otherwise, instantiate `OllamaProvider` with the configured host/model and use
   it if `is_available()` returns `True`.
4. If neither is available, the CLI exits with an actionable error message.

### Frozen contract warning

`providers/base.py` is a **frozen contract**. Phases 4 and 5 depend on every
method signature. Do not add, remove, or change the signature of any abstract
method without coordinating with all call sites.

---

## Type Contracts

**File:** `core/types.py`

All inter-phase data is expressed as Python dataclasses. The file is a frozen
contract — changes to any field name, type, or default break downstream
consumers.

| Type | Purpose |
|---|---|
| `PhotoMetadata` | One photo/video file: path, date, GPS, camera, dimensions, hashes |
| `ScanResult` | Output of Phase 1: lists of photos, videos, skipped, size stats |
| `DuplicateGroup` | A group of duplicates with the kept copy identified |
| `EventCluster` | A time+GPS-bounded group of photos with a stable `cluster_id` |
| `Classification` | LLM output: category, subcategory, confidence (0–1), description |
| `FolderName` | Resolved destination: `name` + `date_prefix`, `.full` property |
| `MoveOperation` | A single source→destination move with audit metadata |
| `RunManifest` | Full audit trail for a run; persisted as JSON |
| `PipelineConfig` | Per-run parameters threaded through the pipeline |
| `CostEstimate` | API cost estimate for a given photo count |
| `LibraryStats` | Aggregate run statistics shown in the TUI receipt |
| `GPSCoord` | Frozen lat/lon pair |
| `PhotoInput` | A `PhotoMetadata` plus an in-memory JPEG thumbnail, ready for LLM |
| `NamingMode` | Enum: `corporate` / `chaotic` / `unhinged` |
| `ProviderName` | Enum: `claude` / `ollama` / `auto` |
| `Phase` | Enum tracking pipeline progress for TUI updates |

`PhotoMetadata` uses `slots=True` but not `frozen=True` because the hasher
mutates `sha256` and `phash` in-place after construction.

---

## Configuration

**File:** `config.py`

Config lives at the platform-specific user config directory (resolved via
`platformdirs`):
- macOS: `~/Library/Application Support/pixeldump/config.yaml`
- Linux: `~/.config/pixeldump/config.yaml`
- Windows: `%APPDATA%\pixeldump\config.yaml`

`load_config()` merges the YAML file over `DEFAULT_CONFIG`; missing keys fall
back to defaults. CLI options override config values at runtime.

Default values:

| Key | Default |
|---|---|
| `provider` | `auto` |
| `naming_mode` | `chaotic` |
| `sass_level` | `2` |
| `burst_hours` | `72` |
| `batch_size` | `5` |
| `concurrency` | `4` |
| `default_dry_run` | `true` |
| `ollama_host` | `http://localhost:11434` |
| `ollama_model` | `gemma3` |

---

## State and Resumability

**File:** `utils/state.py`

After each run, `write_manifest(target, manifest)` serializes the
`RunManifest` to `.pixeldump/manifests/<run_id>.json` inside the target
directory. `load_manifest(path)` deserializes it for the `undo` command, which
reverses operations in reverse order using `shutil.move`.

The state directory also holds a `thumbnails/` cache. Thumbnail cache paths
are derived from the source photo path, allowing subsequent runs to skip
re-encoding.

---

## Data Flow Summary

```
scan(target_dir)
    → ScanResult.photos  (list[PhotoMetadata], hashes=None)

hash_all(photos, concurrency)
    → mutates photo.sha256, photo.phash in place

find_duplicates(photos)
    → list[DuplicateGroup]

cluster(photos, burst_hours, gps_radius_km)
    → list[EventCluster]

classify_clusters(clusters, provider, to_input_fn, batch_size, concurrency)
    → dict[cluster_id → Classification]

{for each cluster_id, classification}
name_cluster(cluster, classification, provider, mode, to_input_fn)
    → FolderName

plan_moves(clusters, folder_names, duplicates, config)
    → list[MoveOperation]

apply_moves(operations, dry_run)
    → RunManifest

write_manifest(target_dir, manifest)
    → .pixeldump/manifests/<run_id>.json
```
