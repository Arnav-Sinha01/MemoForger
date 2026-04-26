# MemoForge

MemoForge is a local-first study assistant that turns documents into clean summaries, flashcards, and export-ready study packs using Ollama-hosted LLMs.

It supports PDF, DOCX, XLSX, PPTX, and TXT inputs and can export outputs as DOCX, PDF, PPTX, CSV, JSON, and Anki `.apkg`.

## What It Does

- Ingests multi-format study material from local files.
- Chunks and processes content for LLM generation.
- Generates:
  - Flashcards only
  - Summary only
  - Flashcards + Summary
- Lets users select the Ollama model from the UI.
- Verifies generated cards in a dedicated Verification & Export Hub before saving.
- Exports cleaned content to multiple study formats.

## Core Features

- Local LLM inference with Ollama (`qwen3-vl:2b` default).
- Auto-bootstrap launcher script for Windows (`Start MemoForge.ps1`):
  - Creates virtual environment if missing
  - Installs Python dependencies
  - Installs Ollama (via winget) if missing
  - Starts Ollama service if needed
  - Launches the app
- Drag-and-drop + file picker upload workflow.
- Per-chunk progress and failure visibility.
- Content sanitization to reduce JSON/code artifacts in generated output.

## Supported Input Formats

- `.pdf`
- `.txt`
- `.docx`
- `.xlsx`
- `.pptx`

## Supported Export Formats

- `DOCX (.docx)`
- `PDF (.pdf)`
- `PowerPoint (.pptx)`
- `Anki Deck (.apkg)`
- `CSV (.csv)`
- `JSON (.json)`

## Tech Stack

- Python 3.11+
- CustomTkinter
- Ollama local inference API
- PyMuPDF
- python-docx
- python-pptx
- pandas + openpyxl
- genanki

## Project Structure

- `main.py` - application entry point + orchestration controller
- `app_frame.py` - main UI frame, queue, config, and launch controls
- `ingestion_engine.py` - file parsers + chunking pipeline
- `vlm_pipeline.py` - Ollama model calls + output parsing
- `verification_hub.py` - review/edit/filter/export UI and export engines
- `Start MemoForge.ps1` - robust launcher with dependency/Ollama bootstrap
- `Launch MemoForge.bat` - simple Python launcher
- `Build-MemoForgeExe.ps1` - PyInstaller build script
- `Build MemoForge EXE.bat` - build wrapper

## Installation

### Option A (recommended): one-click launcher on Windows

1. Double-click `Start MemoForge.ps1`.
2. Wait for first-run setup to finish.
3. App starts automatically.

If PowerShell execution policy blocks scripts, run:

```powershell
powershell -ExecutionPolicy Bypass -File ".\\Start MemoForge.ps1"
```

### Option B: manual setup

```powershell
py -3.11 -m venv venv
.\\venv\\Scripts\\python -m pip install --upgrade pip
.\\venv\\Scripts\\python -m pip install -r requirements.txt
.\\venv\\Scripts\\python main.py
```

## Ollama Setup

- Install from [Ollama Downloads](https://ollama.com/download/windows) if not already present.
- Pull a model (example):

```powershell
ollama pull qwen3-vl:2b
```

- Start service if not already running:

```powershell
ollama serve
```

The app can list available local models and use the selected model for generation.

## Usage Flow

1. Launch MemoForge.
2. Drop files into the upload zone.
3. Select output mode, model, and generation settings.
4. Click `GENERATE`.
5. Review results in Verification & Export Hub.
6. Filter/edit if needed.
7. Click `CONFIRM & SAVE` and choose export format.

## Troubleshooting

### App fails to start

- Confirm Python 3.11+ is installed.
- Run `Start MemoForge.ps1` from PowerShell to see detailed startup logs.

### Model connection errors

- Check Ollama service:

```powershell
ollama list
```

- If no models appear, pull one:

```powershell
ollama pull qwen3-vl:2b
```

### Parse failures or malformed output

- Reduce temperature.
- Lower max flashcards per chunk.
- Try a stronger/alternative model.
- Re-run generation for failed chunks.

### Anki export fails

- Ensure dependency is installed:

```powershell
.\\venv\\Scripts\\python -m pip install genanki
```

## Build EXE

```powershell
powershell -ExecutionPolicy Bypass -File ".\\Build-MemoForgeExe.ps1"
```

Output binary:

- `dist\\MemoForge.exe`

## Notes

- This is a local-first app and is designed to keep document processing on-device.
- Performance and output quality depend on selected model, hardware, and document complexity.
