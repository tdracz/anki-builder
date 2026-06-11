"""
German language module — scrapes DWDS (Digitales Wörterbuch der deutschen Sprache).
https://www.dwds.de

DWDS serves all dictionary data in the initial HTML response (the JS only
renders it client-side), so a plain requests + BeautifulSoup scraper works
without any headless browser.

Data sourced per field:
  IPA          → .dwdswb-ipa
  audio        → embedded URL pattern dwds.de/audio/…
  POS / genus  → .dwdswb-ft-blocklabel "Grammatik" → sibling text
  definitions  → .dwdswb-definition (inside .dwdswb-lesart)
  etymology    → .etymwb-entry
  examples     → .dwdswb-kompetenzbeispiel
  synonyms     → .ot-synset (OpenThesaurus data embedded by DWDS)
"""

import re
import random
import time
import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .base import LanguageModule, WordData, WordNotFoundError

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.dwds.de/wb"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9",
}

# Grammatik block text → (pos_label, genus_article)
# Examples: "Substantiv (Neutrum)" → ("noun", "das")
#           "Verb · läuft , lief …"  → ("verb", None)
_GENUS_MAP = {
    "maskulinum": "der",
    "femininum":  "die",
    "neutrum":    "das",
}

_POS_MAP = {
    "substantiv":    "noun",
    "verb":          "verb",
    "adjektiv":      "adjective",
    "adverb":        "adverb",
    "präposition":   "preposition",
    "konjunktion":   "conjunction",
    "pronomen":      "pronoun",
    "interjektion":  "interjection",
    "artikel":       "article",
    "partikel":      "particle",
    "numerale":      "numeral",
    "eigenname":     "proper noun",
}

_ABSTRACT_POS = {
    "adverb", "conjunction", "preposition", "pronoun",
    "interjection", "article", "particle",
}

_ABSTRACT_HINTS = (
    "die eigenschaft", "der zustand", "der vorgang",
    "die tatsache", "der umstand",
)


class GermanModule(LanguageModule):
    language_code = "de"
    language_name = "German"
    deck_name     = "German Vocabulary"

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch(self, word: str) -> WordData:
        # DWDS lowercases verbs/adjectives but capitalises nouns — send as-is
        url = f"{_BASE_URL}/{requests.utils.quote(word)}"
        logger.info("Fetching %s", url)

        time.sleep(random.uniform(1.0, 2.5))

        try:
            html = self._get(url)
        except WordNotFoundError:
            logger.info("Word not found on DWDS: '%s'", word)
            return WordData(word=word, language_code=self.language_code, not_found=True)
        except requests.RequestException as exc:
            logger.error("Failed to fetch %s: %s", word, exc)
            return WordData(word=word, language_code=self.language_code)

        soup = BeautifulSoup(html, "lxml")

        # If DWDS redirected to a search results page (word not found)
        if not soup.find(class_="dwdswb-artikel"):
            logger.info("No DWDS article found for '%s'", word)
            return WordData(word=word, language_code=self.language_code, not_found=True)

        pos_label = self._extract_pos(soup)

        return WordData(
            word=word,
            language_code=self.language_code,
            ipa=self._extract_ipa(soup),
            audio_url=self._extract_audio_url(soup),
            definitions=self._extract_definitions(soup, pos_label),
            etymology=self._extract_etymology(soup),
            sentences=self._extract_sentences(soup),
            synonyms=self._extract_synonyms(soup),
            antonyms=[],           # DWDS doesn't provide antonyms directly
            pos=pos_label,
            image_query=word,
            source_url=url,
        )

    def should_fetch_image(self, data: WordData) -> bool:
        if data.pos and data.pos in _ABSTRACT_POS:
            return False
        if data.definitions:
            first_def = data.definitions[0].lower()
            if any(hint in first_def for hint in _ABSTRACT_HINTS):
                return False
        return True

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _get(self, url: str) -> str:
        resp = self._session.get(url, timeout=15)
        if resp.status_code in (404, 410):
            raise WordNotFoundError(f"DWDS returned HTTP {resp.status_code}")
        resp.raise_for_status()
        return resp.text

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

    def _extract_ipa(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract IPA from .dwdswb-ipa span."""
        tag = soup.find(class_="dwdswb-ipa")
        return tag.get_text(strip=True) if tag else None

    def _extract_audio_url(self, soup: BeautifulSoup) -> Optional[str]:
        """
        DWDS embeds audio as plain text in the HTML, e.g.:
            dwds.de/audio/001/das_Haus.mp3
        Extract the first occurrence and prepend https://.
        """
        m = re.search(r'(?:www\.)?dwds\.de/audio/[^\s"\'<>]+', str(soup))
        if m:
            path = m.group(0)
            # Normalise to www.dwds.de regardless of whether www. was present
            if not path.startswith("www."):
                path = "www." + path
            return "https://" + path
        return None

    def _extract_pos(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Parse the Grammatik block, e.g.:
          "Substantiv (Neutrum) · Genitiv Singular: Hauses · …"
          "Verb · läuft , lief , ist gelaufen"
          "Adjektiv"
        Returns a human-readable label like "noun (das)", "verb", "adjective".
        """
        gram_text = self._grammatik_text(soup)
        if not gram_text:
            return None

        # First token before "·" or "(" is the POS
        first_token = re.split(r"[·(]", gram_text)[0].strip().lower()
        pos_label = _POS_MAP.get(first_token, first_token)

        # For nouns, extract genus from parentheses: "(Neutrum)", "(Femininum)" etc.
        if pos_label == "noun":
            gm = re.search(r"\(([^)]+)\)", gram_text)
            if gm:
                genus_raw = gm.group(1).strip().lower()
                article = _GENUS_MAP.get(genus_raw)
                if article:
                    pos_label = f"noun ({article})"

        return pos_label

    def _grammatik_text(self, soup: BeautifulSoup) -> Optional[str]:
        """Return the raw text of the Grammatik ft-block."""
        for label_tag in soup.find_all(class_="dwdswb-ft-blocklabel"):
            if "Grammatik" in label_tag.get_text():
                sibling = label_tag.find_next_sibling(class_="dwdswb-ft-blocktext")
                if sibling:
                    return sibling.get_text(" ", strip=True)
        return None

    def _extract_definitions(
        self, soup: BeautifulSoup, pos_label: Optional[str]
    ) -> list[str]:
        """
        Collect definitions from .dwdswb-definition tags.
        Prepends a __pos:X__ marker so the pipeline HTML renderer adds a header.
        Stops after 10 actual definitions.
        """
        result: list[str] = []
        if pos_label:
            result.append(f"__pos:{pos_label}__")

        seen: set[str] = set()
        for tag in soup.find_all(class_="dwdswb-definition"):
            text = _clean(tag.get_text(" ", strip=True))
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
            if len(seen) >= 10:
                break

        return result

    def _extract_etymology(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract etymology from the embedded etymwb entry."""
        tag = soup.find(class_="etymwb-entry")
        if not tag:
            return None
        text = _clean(tag.get_text(" ", strip=True))
        return text if text else None

    def _extract_sentences(self, soup: BeautifulSoup) -> list[str]:
        """
        Extract example sentences from .dwdswb-kompetenzbeispiel spans.
        These are curated, short usage examples — ideal for Anki cards.
        """
        sentences: list[str] = []
        seen: set[str] = set()

        for tag in soup.find_all(class_="dwdswb-kompetenzbeispiel"):
            text = _clean(tag.get_text(" ", strip=True))
            if not text or text in seen or len(text) < 8:
                continue
            seen.add(text)
            sentences.append(text)
            if len(sentences) >= 6:
                break

        return sentences

    def _extract_synonyms(self, soup: BeautifulSoup) -> list[str]:
        """
        DWDS embeds OpenThesaurus synonym groups in .ot-synset blocks.
        Collect the first synonym group's words, deduplicated and capped at 15.
        """
        words: list[str] = []
        seen: set[str] = set()

        # The first ot-synset is typically the closest semantic group
        for synset in soup.find_all(class_="ot-synset"):
            for a in synset.find_all("a"):
                w = _clean(a.get_text(strip=True))
                if w and w.lower() not in seen:
                    seen.add(w.lower())
                    words.append(w)
            if words:
                break  # use only the most relevant group

        return words[:15]


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

_MULTI_SPACE = re.compile(r"  +")


def _clean(text: str) -> str:
    """Strip excess whitespace and normalise non-breaking spaces."""
    text = text.replace("\xa0", " ")
    text = _MULTI_SPACE.sub(" ", text)
    return text.strip()
