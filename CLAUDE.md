# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Board Digitizer** – a single-file Python CLI tool that digitizes Metaplan/workshop board photos using the OpenRouter Vision API. It produces two Markdown files per image: a raw transcription (`_Raw.md`) and an executive summary (`_Summary.md`).

## Setup & Running

```bash
# Install dependencies
pip install -r requirements.txt

# Configure API key (required)
cp .env.example .env
# Edit .env and set OPENROUTER_API_KEY=sk-or-v1-...

# Test API connection
python digitize_board.py --test

# Process a single image
python digitize_board.py --image board.jpg --template retrospektive

# Batch process a folder
python digitize_board.py --batch ./fotos/ --template ideensammlung
```

## Architecture

Everything lives in `digitize_board.py` (single-file, ~720 lines). No tests, no sub-packages.

**Top-level constants** (all configurable inline):
- `BOARD_TEMPLATES` (~line 45): Dict of template names → context strings. To add a new template, extend this dict and add the key to the `argparse choices` list (~line 574).
- `SYSTEM_PROMPT_TEMPLATE` (~line 71): The system prompt injected into every API call. Extend here for language changes or domain-specific rules.
- `CONFIDENCE_SECTION` (~line 96): Extra prompt appended when `--confidence` is passed.

**`BoardDigitizer` class** (the only class, ~line 103):
- Configured once via `__init__` (api_key, model, fallback_model, output_dir, max_tokens, template, context, confidence)
- Class constants: `MAX_RETRIES = 3`, `RETRY_BASE_DELAY = 2` (exponential backoff in seconds)
- Processing pipeline in `process_board()` (~line 457) – orchestrates 4 steps sequentially:
  1. `analyze_structure()` – sends image to API, gets layout/color/vote analysis
  2. `transcribe_raw()` – sends image + structure analysis, gets verbatim transcription
  3. `clean_and_enrich()` – text-only API call to resolve abbreviations, sort by votes
  4. `synthesize_summary()` – text-only API call to produce executive summary
- `_call_api()` (~line 180): handles retries, HTTP error codes, and fallback to `FALLBACK_MODEL` on exhaustion
- `_encode_image()`: Base64-encodes JPG/PNG/WEBP for the vision API

**Configuration priority** (highest to lowest): CLI args → `.env` file → hardcoded defaults.

## .env Variables

| Variable | Required | Default |
|---|---|---|
| `OPENROUTER_API_KEY` | **Yes** | – |
| `DEFAULT_MODEL` | No | `google/gemini-2.0-flash` |
| `FALLBACK_MODEL` | No | `anthropic/claude-sonnet-4-5` |
| `OUTPUT_DIR` | No | `./output` |
| `MAX_TOKENS` | No | `4000` |

## Output

Per image, two files are written to `OUTPUT_DIR` (default `./output/`):
- `{stem}_Raw.md` – verbatim transcription with structure analysis header
- `{stem}_Summary.md` – executive summary + detailed report

Logs are written to `digitize_board.log` in the working directory.
