# Anki Vocabulary Builder

Build rich Anki flashcard decks from a plain word list. Cards include IPA pronunciation, audio, definitions, etymology, example sentences from literature, and images — scraped automatically from The Free Dictionary.

---

## Requirements

- Python 3.11+
- Node.js 18+ (for the frontend build)
- [Anki](https://apps.ankiweb.net/) desktop app with the **AnkiConnect** add-on

---

## Quick start (recommended)

```bash
cd anki-builder
./run.sh          # macOS / Linux
run.bat           # Windows
```

That's it. On first run the script will:
1. Create a Python virtual environment (`.venv/`)
2. Install Python dependencies
3. Install Node dependencies
4. Build the frontend
5. Start the server and open the browser

On subsequent runs it skips steps that are already done and goes straight to starting.

**Options** (passed through to the server):
```
--rebuild      Force a frontend rebuild before starting
--port 8080    Use a different port (default: 8000)
--no-browser   Don't open the browser automatically
```

---

## Manual setup (alternative)

1. Open Anki
2. Go to **Tools → Add-ons → Get Add-ons…**
3. Enter code: `2055492159`
4. Restart Anki

AnkiConnect exposes a local API on `http://localhost:8765`. The app uses this to push cards directly into your deck — no manual import/export needed.

### 2. Install Python dependencies

```bash
cd anki-builder
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Build the frontend (first run only)

```bash
cd frontend
npm install
npm run build
cd ..
```

---

## Running the app

```bash
python start.py
```

This starts the server at `http://localhost:8000` and opens the browser automatically.

Options:
```
--port 8080       Use a different port
--no-browser      Don't open the browser automatically
--rebuild         Force a frontend rebuild before starting
```

---

## Usage

1. **Start Anki** and make sure AnkiConnect is installed (green dot in the top bar)
2. **Import words** — drag a `.txt` file (one word per line) into the Import panel
3. The app scrapes each word and pushes cards to Anki automatically
4. **Browse** the word list and click any word to preview its card
5. **Edit** any field inline and save — changes sync to Anki immediately
6. If Anki wasn't running during import, click **Sync to Anki** to flush the queue

---

## Word file format

Plain text, one word per line:

```
serendipity
melancholy
ephemeral
sycophant
```

---

## Adding a new language

1. Create `backend/languages/yourlang.py` implementing `LanguageModule`
2. Register it in `backend/languages/__init__.py`

See `backend/languages/english.py` for a complete example.

---

## CLI usage (no UI)

```bash
python scrape.py words.txt --lang en
python scrape.py --list-langs
```

---

## Data storage

All data is stored in your user directory:

| Platform | Path |
|---|---|
| macOS / Linux | `~/.local/share/anki-builder/` |
| Windows | `%APPDATA%\anki-builder\` |

- `words.db` — SQLite database
- `media/` — downloaded audio and images

---

## Building a standalone executable

Requires PyInstaller:

```bash
pip install pyinstaller
npm run build --prefix frontend   # build frontend first
pyinstaller anki-builder.spec
```

The executable is written to `dist/anki-builder`.
