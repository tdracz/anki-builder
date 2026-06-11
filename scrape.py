#!/usr/bin/env python3
"""
CLI smoke-test / standalone scraper.

Usage:
    python scrape.py words.txt
    python scrape.py words.txt --lang en
    python scrape.py words.txt --lang en --no-images
"""

import argparse
import json
import sys
from pathlib import Path

# Allow running from the project root
sys.path.insert(0, str(Path(__file__).parent))

from backend import database as db
from backend.languages import get_module, list_languages
from backend.pipeline import process_word


def main():
    parser = argparse.ArgumentParser(description="Scrape words and push to Anki.")
    parser.add_argument("wordfile", help="Text file with one word per line")
    parser.add_argument("--lang", default="en", help="Language code (default: en)")
    parser.add_argument("--no-images", action="store_true", help="Skip image fetching")
    parser.add_argument("--list-langs", action="store_true", help="List available languages")
    args = parser.parse_args()

    if args.list_langs:
        for lang in list_languages():
            print(f"  {lang['code']:6}  {lang['name']}  →  deck: {lang['deck']}")
        return

    db.init_db()

    words_path = Path(args.wordfile)
    if not words_path.exists():
        print(f"Error: file not found: {words_path}", file=sys.stderr)
        sys.exit(1)

    words = [w.strip().lower() for w in words_path.read_text().splitlines() if w.strip()]
    print(f"Loaded {len(words)} word(s) from {words_path.name}")

    new_words = []
    skipped = []
    for word in words:
        if db.word_exists(word, args.lang):
            skipped.append(word)
        else:
            new_words.append(word)

    if skipped:
        print(f"Skipping {len(skipped)} duplicate(s): {', '.join(skipped)}")

    if not new_words:
        print("Nothing to do.")
        return

    print(f"Processing {len(new_words)} new word(s)...\n")

    for i, word in enumerate(new_words, 1):
        print(f"[{i}/{len(new_words)}] {word}", end=" ", flush=True)

        def cb(w, status):
            status_icons = {
                "scraping": "🔍",
                "scraped": "📖",
                "audio_done": "🔊",
                "image_done": "🖼",
                "synced": "✅",
                "pending_sync": "⏳",
            }
            print(status_icons.get(status, status), end=" ", flush=True)

        result = process_word(word, args.lang, progress_cb=cb)
        print()  # newline after icons

        if result:
            defs = result.get("definitions") or []
            print(f"    IPA: {result.get('ipa') or '—'}")
            print(f"    POS: {result.get('pos') or '—'}")
            if defs:
                print(f"    Def: {defs[0][:80]}{'…' if len(defs[0]) > 80 else ''}")
            print()

    print("Done.")


if __name__ == "__main__":
    main()
