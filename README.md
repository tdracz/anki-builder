# Anki Vocabulary Builder

Build rich Anki flashcard decks from a plain word list. Cards include IPA pronunciation, audio, definitions, etymology, example sentences, synonyms, antonyms, and images — scraped automatically from language-specific dictionaries.

Supports **English** and **German** out of the box, with a plugin architecture that makes adding new languages straightforward.

---

## Language support

| Language | Code | Dictionary source | Default deck |
|---|---|---|---|
| English | `en` | [The Free Dictionary](https://www.thefreedictionary.com) + [Free Thesaurus](https://www.freethesaurus.com) | English Vocabulary |
| German | `de` | [DWDS](https://www.dwds.de) (Digitales Wörterbuch der deutschen Sprache) | German Vocabulary |

**English cards** include: IPA, audio, definitions with POS groups, etymology, example sentences from literature, synonyms, antonyms, and an optional image.

**German cards** include: IPA, audio, definitions with genus-annotated POS (`noun (das)`, `noun (der)`, `noun (die)`), etymology, curated usage examples from DWDS, synonyms (via OpenThesaurus), and an optional image.

---

## Requirements

- Python 3.11+
- Node.js 18+ (for the frontend build)
- [Anki](https://apps.ankiweb.net/) desktop app with the **AnkiConnect** add-on

---

## Install AnkiConnect

This is required regardless of how you run the app.

1. Open Anki
2. Go to **Tools → Add-ons → Get Add-ons…**
3. Enter code: `2055492159`
4. Restart Anki

AnkiConnect exposes a local API on `http://localhost:8765`. The app uses this to push cards directly into your deck — no manual import/export needed.

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

### Install Python dependencies

```bash
cd anki-builder
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Build the frontend (first run only)

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
2. **Select a language** (English or German) in the language selector
3. **Import words** — drag a `.txt` file (one word per line) into the Import panel
4. The app scrapes each word from the appropriate dictionary and pushes cards to Anki automatically
5. **Browse** the word list and click any word to preview its card
6. **Edit** any field inline and save — changes are pushed to Anki immediately if **Auto Sync** is on, otherwise they queue as pending
7. Use the **Sync to Anki** button to flush the queue at any time (required when Auto Sync is off, or when Anki wasn't running during import)

---

## Word file format

Plain text, one word per line. German nouns can be entered with or without their article.

```
serendipity
melancholy
ephemeral
```

```
Haus
laufen
schön
```

---

## AI-powered translation (optional)

The app can translate words into any target language using the OpenAI API. Configure it in the **Settings** page:

- **OpenAI API key** — your API key
- **OpenAI model** — e.g. `gpt-4o-mini` (default)
- **Target language** — the language to translate into (e.g. `Polish`, `Spanish`)
- **OpenAI base URL** — optional, for compatible third-party APIs

Once configured, translations appear on the card back and are synced to Anki.

---

## Adding a new language

1. Create `backend/languages/yourlang.py` implementing `LanguageModule`
2. Register it in `backend/languages/__init__.py`

The module must implement two methods:

```python
def fetch(self, word: str) -> WordData:
    """Scrape all card data for a word from the language's dictionary."""

def should_fetch_image(self, data: WordData) -> bool:
    """Return True if fetching an image makes sense for this word."""
```

See `backend/languages/english.py` or `backend/languages/german.py` for complete examples.

---

## CLI usage (no UI)

```bash
python scrape.py words.txt --lang en
python scrape.py words.txt --lang de
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
