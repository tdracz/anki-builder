"""
English language module — scrapes The Free Dictionary (thefreedictionary.com).
Only the first dictionary entry on the page is used.
"""

import re
import random
import time
import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .base import LanguageModule, WordData, WordNotFoundError

logger = logging.getLogger(__name__)

_NUM_PREFIX = re.compile(r"^\d+\.\s*")  # strips "1. ", "2. " etc.

_POS_MAP = {
    "n": "noun", "v": "verb", "adj": "adjective",
    "adv": "adverb", "prep": "preposition", "conj": "conjunction",
    "pron": "pronoun", "interj": "interjection", "tr": "verb",
    "intr": "verb", "aux": "verb",
    # Compound forms from TFD
    "tr.v": "verb", "intr.v": "verb", "aux.v": "verb",
    "pl": "noun", "pl.n": "noun",
}

# POS tags that are unlikely to benefit from an image
_ABSTRACT_POS = {"adverb", "conjunction", "preposition", "pronoun", "interjection", "article"}

# Words in a definition that suggest an abstract concept
_ABSTRACT_HINTS = (
    "the state of", "the quality of", "the condition of",
    "the act of", "the process of", "the fact of",
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class EnglishModule(LanguageModule):
    language_code = "en"
    language_name = "English"
    deck_name = "English Vocabulary"

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _get(self, url: str) -> str:
        resp = self._session.get(url, timeout=15)
        # Don't retry client errors — 404 means the word doesn't exist,
        # 429 means we're rate-limited (retrying immediately makes it worse)
        if resp.status_code in (404, 410):
            raise WordNotFoundError(f"Word not found on TFD (HTTP {resp.status_code})")
        resp.raise_for_status()
        return resp.text

    def fetch(self, word: str) -> WordData:
        url = f"https://www.thefreedictionary.com/{word.lower().replace(' ', '+')}"
        logger.info("Fetching %s", url)

        # Polite delay between requests
        time.sleep(random.uniform(1.0, 2.5))

        try:
            html = self._get(url)
        except WordNotFoundError:
            logger.info("Word not found in dictionary: '%s'", word)
            return WordData(word=word, language_code=self.language_code, not_found=True)
        except requests.RequestException as exc:
            logger.error("Failed to fetch %s: %s", word, exc)
            return WordData(word=word, language_code=self.language_code)

        soup = BeautifulSoup(html, "lxml")

        # Fetch thesaurus from freethesaurus.com (separate request)
        synonyms, antonyms, thesaurus_url = self._extract_thesaurus(word)

        return WordData(
            word=word,
            language_code=self.language_code,
            ipa=self._extract_ipa(soup),
            audio_url=self._extract_audio_url(soup, word),
            definitions=self._extract_definitions(soup),
            etymology=self._extract_etymology(soup),
            sentences=self._extract_sentences(soup),
            synonyms=synonyms,
            antonyms=antonyms,
            pos=self._extract_pos(soup),
            image_query=word,
            source_url=url,
            thesaurus_url=thesaurus_url,
        )

    # ------------------------------------------------------------------
    # Private extraction helpers
    # ------------------------------------------------------------------

    def _first_entry(self, soup: BeautifulSoup) -> Optional[BeautifulSoup]:
        """Return the first real dictionary entry section, or None.
        Skips non-dictionary sections (e.g. 'Commonly Confused Words') by
        preferring sections with data-src='hm' (American Heritage), then
        falling back to the first section that has a pronunciation span.
        """
        definition_div = soup.find("div", id="Definition")
        if not definition_div:
            return None
        sections = definition_div.find_all("section")
        if not sections:
            return None
        # Prefer American Heritage (data-src="hm")
        for sec in sections:
            if sec.get("data-src") == "hm":
                return sec
        # Fallback: first section with a pronunciation
        for sec in sections:
            if sec.find("span", class_="pron"):
                return sec
        # Last resort: first section with a pseg (definition block)
        for sec in sections:
            if sec.find("div", class_="pseg"):
                return sec
        return sections[0]

    def _extract_ipa(self, soup: BeautifulSoup) -> Optional[str]:
        entry = self._first_entry(soup)
        if not entry:
            return None
        pron = entry.find("span", class_="pron")
        if pron:
            return pron.get_text(strip=True)
        # Fallback: look in the header area
        h2 = soup.find("h2", class_="entry-word")
        if h2:
            pron = h2.find_next("span", class_="pron")
            if pron:
                return pron.get_text(strip=True)
        return None

    def _extract_audio_url(self, soup: BeautifulSoup, word: str) -> Optional[str]:
        # TFD embeds audio as <span class="snd" data-snd="CODE">
        # The audio file lives at https://img.tfd.com/hm/mp3/{CODE}.mp3
        snd = soup.find("span", class_="snd")
        if snd:
            code = snd.get("data-snd", "").strip()
            if code:
                return f"https://img.tfd.com/hm/mp3/{code}.mp3"
        # Fallback: try the word itself as the filename
        return f"https://img.tfd.com/hm/mp3/{word.lower()}.mp3"

    def _extract_definitions(self, soup: BeautifulSoup) -> list[str]:
        """
        Returns definitions as a flat list with POS group headers interleaved.
        Format: ["__pos:noun__", "def1", "def2", "__pos:adjective__", "def3"]
        The __pos:X__ markers let the UI render group headers without a schema change.
        Numbers embedded in TFD text (e.g. "1. Sadness...") are stripped.
        """
        entry = self._first_entry(soup)
        if not entry:
            return []

        result: list[str] = []
        total = 0

        for pseg in entry.find_all("div", class_="pseg"):
            # Determine POS for this group
            i_tag = pseg.find("i")
            if i_tag:
                raw = i_tag.get_text(strip=True).rstrip(".")
                pos_label = _POS_MAP.get(raw.lower(), raw.lower())
            else:
                pos_label = None

            defs: list[str] = []
            for ds in pseg.find_all(["span", "div"], class_=["ds-single", "ds-list"], recursive=False):
                # Check for sub-definitions (a. b. c.) inside this ds-list
                sds_items = ds.find_all("div", class_="sds-list")
                if sds_items:
                    for sd in sds_items:
                        text = sd.get_text(" ", strip=True)
                        text = _NUM_PREFIX.sub("", text).strip()
                        # Strip leading letter prefix (a. b. c.)
                        text = re.sub(r'^[a-z]\.\s*', '', text)
                        if text:
                            defs.append(f"__sub__{text}")
                else:
                    text = ds.get_text(" ", strip=True)
                    text = _NUM_PREFIX.sub("", text).strip()
                    if text:
                        defs.append(text)

            if defs:
                if pos_label:
                    result.append(f"__pos:{pos_label}__")
                for d in defs:
                    result.append(d)
                    total += 1
                    if total >= 10:
                        return result

        # Fallback: plain <li> items if pseg approach yielded nothing
        if not result:
            for li in entry.find_all("li"):
                text = _NUM_PREFIX.sub("", li.get_text(" ", strip=True)).strip()
                if text and len(text) > 5:
                    result.append(text)
                    if len(result) >= 10:
                        break

        return result

    def _extract_etymology(self, soup: BeautifulSoup) -> Optional[str]:
        # Etymology is inside the first section as <div class="etyseg">
        entry = self._first_entry(soup)
        if entry:
            etyseg = entry.find("div", class_="etyseg")
            if etyseg:
                return etyseg.get_text(" ", strip=True)
        # Fallback: standalone etymology div (older TFD pages)
        etym_div = soup.find("div", id="Etymology")
        if etym_div:
            p = etym_div.find("p")
            if p:
                return p.get_text(" ", strip=True)
            return etym_div.get_text(" ", strip=True) or None
        return None

    def _extract_sentences(self, soup: BeautifulSoup) -> list[str]:
        sentences = []
        seen = set()

        def add(text: str) -> None:
            text = text.strip()
            if text and text not in seen:
                seen.add(text)
                sentences.append(text)

        # Inline illustration spans within definitions
        for span in soup.find_all("span", class_="illustration"):
            add(span.get_text(" ", strip=True))

        # Sentence examples section (present on some TFD pages)
        for div_id in ("Sentences", "Thesaurus"):
            ex_div = soup.find("div", id=div_id)
            if ex_div:
                for span in ex_div.find_all("span", class_="illustration"):
                    add(span.get_text(" ", strip=True))

        return sentences[:8]

    def _extract_pos(self, soup: BeautifulSoup) -> Optional[str]:
        entry = self._first_entry(soup)
        if not entry:
            return None
        # TFD uses <span class="pos"> in some entries
        pos_tag = entry.find("span", class_="pos")
        if pos_tag:
            return pos_tag.get_text(strip=True).lower()
        # More common: <i>n.</i> / <i>v.</i> / <i>adj.</i> inside div.pseg
        pseg = entry.find("div", class_="pseg")
        if pseg:
            i_tag = pseg.find("i")
            if i_tag:
                raw = i_tag.get_text(strip=True).rstrip(".")
                return _POS_MAP.get(raw.lower(), raw.lower())
        return None

    def _extract_synonyms(self, soup: BeautifulSoup) -> list[str]:
        """Synonyms are now fetched separately from freethesaurus.com — this is a no-op."""
        return []

    def _extract_thesaurus(self, word: str) -> tuple[list[str], list[str], str]:
        """
        Fetch synonyms and antonyms from freethesaurus.com (Collins preferred).
        Returns (synonyms, antonyms, thesaurus_url).
        """
        url = f"https://www.freethesaurus.com/{word.lower().replace(' ', '+')}"
        try:
            html = self._session.get(url, timeout=15).text
        except Exception as exc:
            logger.warning("Thesaurus fetch failed for '%s': %s", word, exc)
            return [], [], url

        soup = BeautifulSoup(html, "lxml")
        synonyms: list[str] = []
        antonyms: list[str] = []
        seen_syn: set[str] = set()
        seen_ant: set[str] = set()

        # Prefer Collins (data-src="hc_thes"), fall back to American Heritage (hm_thes)
        section = soup.find("section", attrs={"data-src": "hc_thes"})
        if not section:
            section = soup.find("section", attrs={"data-src": "hm_thes"})
        if not section:
            return [], [], url

        for part in section.find_all("div", attrs={"data-part": True}):
            # Synonyms
            syn_ul = part.find("ul", class_="TSyn")
            if syn_ul:
                for a in syn_ul.find_all("a", class_="tw"):
                    text = a.get_text(strip=True)
                    if text and text.lower() not in seen_syn:
                        seen_syn.add(text.lower())
                        synonyms.append(text)

            # Antonyms
            ant_ul = part.find("ul", class_="TAnt")
            if ant_ul:
                for a in ant_ul.find_all("a", class_="tw"):
                    text = a.get_text(strip=True)
                    if text and text.lower() not in seen_ant:
                        seen_ant.add(text.lower())
                        antonyms.append(text)

        return synonyms[:15], antonyms[:10], url

    # ------------------------------------------------------------------
    # Image heuristic
    # ------------------------------------------------------------------

    def should_fetch_image(self, data: WordData) -> bool:
        if data.pos and data.pos in _ABSTRACT_POS:
            return False
        if data.definitions:
            first_def = data.definitions[0].lower()
            if any(hint in first_def for hint in _ABSTRACT_HINTS):
                return False
        return True
