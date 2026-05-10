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
[![Tests](https://img.shields.io/badge/tests-170%20passing-brightgreen.svg)](#)
[![Type Checked](https://img.shields.io/badge/mypy-strict-blue.svg)](#)

**PixelDump** is an agentic AI photo organizer that uses vision LLMs to sort your camera roll into intelligently named folders. It deduplicates near-identical shots, groups photos into events, and writes folder names with the energy of a chronically-online friend.

</div>

---

## ✨ what it does

- 📸 **Sorts photos into events** — uses EXIF dates + GPS clustering, not just "by year"
- 🧠 **Vision-LLM classification** — Claude API or local Ollama (Gemma 3 / LLaVA)
- 💀 **Catches duplicates** — exact (SHA-256) and near-duplicate (perceptual hash)
- 🏷️ **Three naming vibes** — corporate, chaotic, or unhinged (your call)
- 📂 **Year/month folder layout** — `2024/2024_03_event_name/`
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
| `--mode corporate` 🏢 | `2024_03_japan_trip` · `2024_06_sarah_birthday` · `2024_07_office_holiday_party` |
| `--mode chaotic` 🔥 | `2024_03_ate_good_in_tokyo` · `2024_06_main_character_moment` · `2024_07_the_old_people_gathered` |
| `--mode unhinged` 🫠 | `2024_03_proof_i_went_outside_once` · `2024_06_emotional_support_sunset` · `2024_07_what_the_dog_doin` |

## 🧠 provider setup

PixelDump works with Anthropic's Claude API (best vision quality) or Ollama (local & free).

**Claude (recommended for accuracy):**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
pixeldump setup
```

**Ollama (local, free, slower):**

```bash
# install ollama from https://ollama.com
ollama pull gemma3
pixeldump setup
```

If both are configured, PixelDump auto-detects and prefers Claude. Override with `--provider`.

## 📁 output structure

After a run, your photo directory looks like this:

```
Photos/
├── 2024/
│   ├── 2024_03_ate_good_in_tokyo/
│   ├── 2024_06_birthday_party/
│   ├── 2024_07_proof_i_had_friends/
│   ├── 2024_misc/
│   └── 2024_screenshots/
├── 2023/
│   └── ...
├── _review/
│   ├── duplicates/        # near-identical shots, kept the highest-res one
│   ├── no_date/           # photos with no EXIF date
│   └── low_confidence/    # photos the AI wasn't sure about
└── .pixeldump/
    ├── manifests/         # one JSON per run, used for undo
    ├── runs/              # per-run logs
    └── thumbnails/        # cached thumbnails
```

## 🧰 all flags

```
pixeldump run TARGET [OPTIONS]

  --provider [claude|ollama|auto]      vision LLM provider
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

Rough rule of thumb with Claude: **~$0.001 per photo**, since PixelDump batches photos by event and only sends one classification call per cluster (not per photo). A 1,500-photo library typically costs under $2. Use `--estimate` to see the exact number for your library before running.

Local Ollama is free, just slower. Bring your GPU energy.

## 🔒 your photos stay yours

- **Local Ollama** sees nothing leave your machine
- **Claude API** receives 512px thumbnails (not full-resolution photos), and Anthropic does not train on API inputs
- **Nothing is ever deleted.** Files are moved, never removed. Every operation is logged and reversible.

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

*built by people who have absolutely been roasted by their own camera rolls*

</div>
