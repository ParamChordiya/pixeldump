<div align="center">

```
  ____  _____  ___  _  _____  ___   _   _  __  __  ____
 |  _ \|_ _\ \/ / |/ \|  _  || _ \ | | | ||  \/  ||  _ \
 | |_) || | \  /| | _ | |_| || | || | | | || |\/| || |_) |
 |  __/ | | /  \| ||_||  _  || |_||_|_|_|||_|  |_||  __/
 |_|   |___/_/\_\_|   |_| |_||___/         |_|     |_|
```

### *because your camera roll is a cry for help* 🫠

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-236%20passing-brightgreen.svg)](#)
[![Type Checked](https://img.shields.io/badge/mypy-strict-blue.svg)](#)

**PixelDump** is an agentic AI photo organizer that uses vision LLMs to sort your camera roll into intelligently named folders. It deduplicates near-identical shots, groups photos into events, and writes folder names with the energy of a chronically-online friend.

</div>

---

## ✨ what it does

- 📸 **Sorts photos into events** — uses EXIF dates + GPS clustering, not just "by year"
- 🧠 **Vision-LLM classification** — Claude Code (no API key), Claude API, or local Ollama (Gemma 3 / LLaVA)
- 💀 **Catches duplicates** — exact (SHA-256) and near-duplicate (perceptual hash)
- 🏷️ **Three naming vibes** — corporate, chaotic, or unhinged (your call)
- 📂 **Granular document routing** — screenshots, bills, boarding passes, prescriptions, and more each land in their own typed folder automatically
- ↩️ **Undo support** — every move is logged in a manifest, fully reversible
- 🛟 **Dry-run by default** — preview before anything moves
- 🔁 **Resumable** — interrupt a run, pick up where you left off
- 🧾 **Receipt at the end** — stats, easter eggs, and a roast

## 🚀 quick start

```bash
pip install pixeldump
pixeldump run ~/Pictures/CameraRoll
```

The first run drops you into an interactive wizard. After that, flags are your friends:

```bash
# show me what you'd do, don't actually move anything (default)
pixeldump run ~/Photos --dry-run

# yes, do it
pixeldump run ~/Photos --apply

# use claude-code provider (no API key needed)
pixeldump run ~/Photos --provider claude-code --apply

# corporate mode, sass off, batch hard
pixeldump run ~/Photos --mode corporate --sass 0 --apply

# how much will Claude cost me?
pixeldump run ~/Photos --estimate

# undo the last run
pixeldump undo ~/Photos/.pixeldump/manifests/20260509_143022.json
```

## 🏷️ naming modes (with real examples)

The vision model looks at the photos and writes the folder name based on what it actually sees. Pick your aesthetic:

| Mode | Example output |
|---|---|
| `--mode corporate` 🏢 | `2024_03/tokyo_client_summit/` · `2024_06/sarah_alex_wedding_tuscany/` · `2024_07/team_offsite_q2_2024/` |
| `--mode chaotic` 🔥 | `2024_03/ate_in_tokyo_fr/` · `2024_06/main_character_bali_era/` · `2024_07/family_chaos_thanksgiving/` |
| `--mode unhinged` 🫠 | `2024_03/proof_i_touched_grass/` · `2024_06/the_yassification_of_brunch/` · `2024_07/my_villain_era_in_milan/` |

## 🧠 provider setup

PixelDump supports three vision providers. Run `pixeldump setup` to configure whichever you want.

**Claude Code (recommended — no API key required):**

If you already have [Claude Code](https://claude.ai/code) installed and logged in, PixelDump reuses your existing session. Nothing extra to configure.

```bash
# confirm claude is on your PATH
claude --version
pixeldump setup   # pick "claude-code"
```

**Claude API (best accuracy, pay-per-use):**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
pixeldump setup   # pick "claude"
```

**Ollama (fully local, free, slower):**

```bash
# install ollama from https://ollama.com
ollama pull gemma3
pixeldump setup   # pick "ollama"
```

Auto-detection order when `--provider auto` (the default): **claude-code → claude API → ollama**. Override with `--provider claude-code`, `--provider claude`, or `--provider ollama`.

## 📁 output structure

After a run, your photo directory looks like this:

```
Photos/
├── 2024/
│   ├── 2024_03/                        # month folder groups all events from that month
│   │   ├── ate_good_in_tokyo/          # LLM-named event subfolders live inside
│   │   └── cherry_blossom_picnic/
│   ├── 2024_06/
│   │   ├── sarah_alex_wedding_tuscany/
│   │   └── main_character_bali_era/
│   │
│   ├── screenshots/                    # document-type folders sit flat under the year
│   ├── screenshots_apps/
│   ├── screenshots_conversations/
│   ├── screenshots_social/
│   ├── screenshots_memes/
│   ├── screenshots_web/
│   ├── screenshots_maps/
│   │
│   ├── documents_receipts/
│   ├── documents_bills/
│   ├── documents_financial/            # bank statements, credit cards, tax docs, paychecks
│   ├── documents_ids/                  # passports, licences, insurance cards, visas
│   ├── documents_travel/               # boarding passes, hotel confirmations, event tickets
│   ├── documents_medical/              # prescriptions, lab results, vaccine records
│   ├── documents_legal/                # contracts, leases, certificates
│   └── documents_misc/                 # menus, business cards, whiteboards, QR codes
│
├── 2023/
│   └── ...
├── _review/
│   ├── duplicates/        # near-identical shots — highest-res copy kept
│   ├── no_date/           # photos with no EXIF date
│   └── low_confidence/    # photos the AI wasn't sure about (confidence < 0.5)
└── .pixeldump/
    ├── manifests/         # one JSON per run, used for undo
    ├── runs/              # per-run logs
    └── thumbnails/        # cached thumbnails
```

Events land in `YYYY/YYYY_MM/event_name/` so each month is its own browsable folder. Documents and screenshots sit flat under the year (`YYYY/documents_receipts/`) since they accumulate all year and don't need month grouping.

## 🧰 all flags

```
pixeldump run TARGET [OPTIONS]

  --provider [claude-code|claude|ollama|auto]  vision LLM provider (default: auto)
  --mode [corporate|chaotic|unhinged]  folder name vibe (default: chaotic)
  --sass [0-3]                         personality intensity (default: 2)
  --burst-hours INT                    event clustering gap (default: 72h)
  --batch-size INT                     photos per LLM batch (default: 5)
  --concurrency INT                    parallel hashing workers (default: 4)
  --include-videos                     also sort .mp4/.mov by date
  --skip-duplicates                    don't run dup detection
  --skip-clustering                    classify each photo individually
  --output PATH                        sort into a different dir (copy mode)
  --dry-run / --apply                  preview vs. execute (default: dry-run)
  --quiet                              minimal output, no live dashboard
  --no-wizard                          skip the interactive wizard
  --estimate                           print cost estimate and exit

pixeldump undo MANIFEST [--yes]        reverse a previous run
pixeldump status TARGET                show the most recent manifest
pixeldump config [--reset]             show or reset config
pixeldump setup                        re-run provider setup
```

## 💸 cost

**Claude Code**: free — runs inside your existing Claude Code subscription, no extra charges.

**Claude API**: rough rule of thumb **~$0.001 per photo**, since PixelDump batches photos by event and sends one classification call per cluster (not per photo). A 1,500-photo library typically costs under $2. Use `--estimate` to see the exact number for your library before running.

**Ollama**: free, just slower. Bring your GPU energy.

## 🔒 your photos stay yours

- **Claude Code** reuses your local CLI session — 512px thumbnails are passed to the local `claude` process, same data boundary as using Claude Code interactively
- **Local Ollama** sees nothing leave your machine
- **Claude API** receives 512px thumbnails (not full-resolution photos), and Anthropic does not train on API inputs
- **Nothing is ever deleted.** Files are moved, never removed. Every operation is logged and reversible.
- **Config files** containing API keys are written with owner-only permissions (mode 0600)

## 🛠️ development

```bash
git clone https://github.com/your-handle/pixeldump
cd pixeldump
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install

make test           # pytest
make lint           # ruff
make typecheck      # mypy --strict
```

Architecture: see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Contributing: see [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md).

## 🤝 contributing

Issues and PRs welcome. Look for [`good first issue`](https://github.com/your-handle/pixeldump/labels/good%20first%20issue) labels. The sass engine especially welcomes new lines — see `src/pixeldump/assets/sass_lines.json`.

## 📜 license

MIT. See [LICENSE](LICENSE).

---

<div align="center">

*built by me because my photos folder was a crime scene*

</div>
