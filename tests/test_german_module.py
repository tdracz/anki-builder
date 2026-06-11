"""
Tests for the German language module — DWDS HTML parsing logic.
Uses static HTML fixtures so no real HTTP requests are made.
"""

import pytest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup

from backend.languages.german import GermanModule, _clean
from backend.languages.base import WordData

MODULE = GermanModule()

# ---------------------------------------------------------------------------
# HTML fixtures (minimal but structurally faithful to real DWDS pages)
# ---------------------------------------------------------------------------

def _make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


# --- Haus (noun, Neutrum) ---
_HAUS_HTML = """
<html><body>
<article class="dwdswb-artikel">
  <span class="dwdswb-ipa">haʊ̯s</span>

  <div class="dwdswb-ft-blocks">
    <span class="dwdswb-ft-blocklabel">Grammatik</span>
    <span class="dwdswb-ft-blocktext">Substantiv (Neutrum) · Genitiv Singular: Hauses · Nominativ Plural: Häuser</span>
  </div>

  <div class="dwdswb-lesart">
    <span class="dwdswb-definition">aus Wänden und Dach errichtetes Gebäude für Menschen</span>
  </div>
  <div class="dwdswb-lesart">
    <span class="dwdswb-definition">zum Wohnen, Wohnhaus</span>
  </div>
  <div class="dwdswb-lesart">
    <span class="dwdswb-definition">das eigene Heim</span>
  </div>

  <span class="dwdswb-kompetenzbeispiel">ein großes, mehrstöckiges Haus</span>
  <span class="dwdswb-kompetenzbeispiel">das Haus bauen, kaufen, besitzen</span>
  <span class="dwdswb-kompetenzbeispiel">wir haben ein neues Haus gekauft</span>

  <div class="etymwb-entry">Haus n. ahd. hūs 'Gebäude, Familie' (8. Jh.)</div>

  <div class="ot-synset">
    <a href="/wb/Gebäude">Gebäude</a>
    <a href="/wb/Bauwerk">Bauwerk</a>
    <a href="/wb/Gemäuer">Gemäuer</a>
  </div>
</article>
<script>dwds_host_api = 'https://www.dwds.de/'</script>
<script>/* audio: https://www.dwds.de/audio/001/das_Haus.mp3 */</script>
</body></html>
"""

# --- laufen (verb) ---
_LAUFEN_HTML = """
<html><body>
<article class="dwdswb-artikel">
  <span class="dwdswb-ipa">ˈlaʊ̯fn̩</span>

  <div class="dwdswb-ft-blocks">
    <span class="dwdswb-ft-blocklabel">Grammatik</span>
    <span class="dwdswb-ft-blocktext">Verb · läuft , lief , ist / hat gelaufen</span>
  </div>

  <div class="dwdswb-lesart">
    <span class="dwdswb-definition">sich zu Fuß fortbewegen, gehen</span>
  </div>
  <div class="dwdswb-lesart">
    <span class="dwdswb-definition">sich gleichmäßig bewegen</span>
  </div>
  <div class="dwdswb-lesart">
    <span class="dwdswb-definition">von Flüssigkeiten: fließen</span>
  </div>

  <span class="dwdswb-kompetenzbeispiel">das Kind konnte bereits mit einem Jahr laufen</span>
  <span class="dwdswb-kompetenzbeispiel">wir sind bei dem schönen Wetter gelaufen</span>

  <div class="etymwb-entry">laufen Verb, mittelhochdeutsch loufen, althochdeutsch (h)loufan</div>

  <div class="ot-synset">
    <a href="/wb/gehen">gehen</a>
    <a href="/wb/rennen">rennen</a>
    <a href="/wb/sprinten">sprinten</a>
  </div>
</article>
<script>/* dwds.de/audio/001/laufen.mp3 */</script>
</body></html>
"""

# --- schön (adjective) ---
_SCHOEN_HTML = """
<html><body>
<article class="dwdswb-artikel">
  <span class="dwdswb-ipa">ʃøːn</span>

  <div class="dwdswb-ft-blocks">
    <span class="dwdswb-ft-blocklabel">Grammatik</span>
    <span class="dwdswb-ft-blocktext">Adjektiv</span>
  </div>

  <div class="dwdswb-lesart">
    <span class="dwdswb-definition">ästhetisches Empfinden sehr angenehm berührend</span>
  </div>
  <div class="dwdswb-lesart">
    <span class="dwdswb-definition">gut, ordentlich, erfreulich</span>
  </div>

  <span class="dwdswb-kompetenzbeispiel">ein schönes Gemälde</span>
</article>
<script>/* dwds.de/audio/001/schoen.mp3 */</script>
</body></html>
"""

# --- word not found (no dwdswb-artikel) ---
_NOT_FOUND_HTML = """
<html><body>
  <div class="alert-danger">Fehlerstatus 404</div>
</body></html>
"""

# --- die Frau (Femininum) ---
_FRAU_HTML = """
<html><body>
<article class="dwdswb-artikel">
  <span class="dwdswb-ipa">fraʊ̯</span>
  <div class="dwdswb-ft-blocks">
    <span class="dwdswb-ft-blocklabel">Grammatik</span>
    <span class="dwdswb-ft-blocktext">Substantiv (Femininum) · Genitiv Singular: Frau</span>
  </div>
  <div class="dwdswb-lesart">
    <span class="dwdswb-definition">weiblicher Mensch</span>
  </div>
</article>
</body></html>
"""

# --- der Mann (Maskulinum) ---
_MANN_HTML = """
<html><body>
<article class="dwdswb-artikel">
  <span class="dwdswb-ipa">man</span>
  <div class="dwdswb-ft-blocks">
    <span class="dwdswb-ft-blocklabel">Grammatik</span>
    <span class="dwdswb-ft-blocktext">Substantiv (Maskulinum) · Genitiv Singular: Mannes</span>
  </div>
  <div class="dwdswb-lesart">
    <span class="dwdswb-definition">männlicher Mensch</span>
  </div>
</article>
</body></html>
"""


# ---------------------------------------------------------------------------
# IPA
# ---------------------------------------------------------------------------

class TestExtractIPA:
    def test_extracts_ipa_noun(self):
        soup = _make_soup(_HAUS_HTML)
        assert MODULE._extract_ipa(soup) == "haʊ̯s"

    def test_extracts_ipa_verb(self):
        soup = _make_soup(_LAUFEN_HTML)
        assert MODULE._extract_ipa(soup) == "ˈlaʊ̯fn̩"

    def test_extracts_ipa_adjective(self):
        soup = _make_soup(_SCHOEN_HTML)
        assert MODULE._extract_ipa(soup) == "ʃøːn"

    def test_returns_none_when_no_ipa(self):
        soup = _make_soup("<html><body><article class='dwdswb-artikel'></article></body></html>")
        assert MODULE._extract_ipa(soup) is None


# ---------------------------------------------------------------------------
# Audio URL
# ---------------------------------------------------------------------------

class TestExtractAudioUrl:
    def test_extracts_audio_url_noun(self):
        soup = _make_soup(_HAUS_HTML)
        url = MODULE._extract_audio_url(soup)
        assert url == "https://www.dwds.de/audio/001/das_Haus.mp3"

    def test_extracts_audio_url_verb(self):
        soup = _make_soup(_LAUFEN_HTML)
        url = MODULE._extract_audio_url(soup)
        assert url == "https://www.dwds.de/audio/001/laufen.mp3"

    def test_returns_none_when_no_audio(self):
        soup = _make_soup("<html><body><article class='dwdswb-artikel'></article></body></html>")
        assert MODULE._extract_audio_url(soup) is None

    def test_url_starts_with_https(self):
        soup = _make_soup(_HAUS_HTML)
        url = MODULE._extract_audio_url(soup)
        assert url.startswith("https://")


# ---------------------------------------------------------------------------
# POS extraction
# ---------------------------------------------------------------------------

class TestExtractPOS:
    def test_noun_neutrum(self):
        soup = _make_soup(_HAUS_HTML)
        assert MODULE._extract_pos(soup) == "noun (das)"

    def test_noun_femininum(self):
        soup = _make_soup(_FRAU_HTML)
        assert MODULE._extract_pos(soup) == "noun (die)"

    def test_noun_maskulinum(self):
        soup = _make_soup(_MANN_HTML)
        assert MODULE._extract_pos(soup) == "noun (der)"

    def test_verb(self):
        soup = _make_soup(_LAUFEN_HTML)
        assert MODULE._extract_pos(soup) == "verb"

    def test_adjective(self):
        soup = _make_soup(_SCHOEN_HTML)
        assert MODULE._extract_pos(soup) == "adjective"

    def test_returns_none_when_no_grammatik(self):
        soup = _make_soup("<html><body><article class='dwdswb-artikel'></article></body></html>")
        assert MODULE._extract_pos(soup) is None


# ---------------------------------------------------------------------------
# Definition extraction
# ---------------------------------------------------------------------------

class TestExtractDefinitions:
    def test_extracts_noun_definitions(self):
        soup = _make_soup(_HAUS_HTML)
        defs = MODULE._extract_definitions(soup, "noun (das)")
        actual = [d for d in defs if not d.startswith("__")]
        assert len(actual) == 3
        assert "aus Wänden und Dach errichtetes Gebäude für Menschen" in actual

    def test_prepends_pos_marker(self):
        soup = _make_soup(_HAUS_HTML)
        defs = MODULE._extract_definitions(soup, "noun (das)")
        assert defs[0] == "__pos:noun (das)__"

    def test_no_pos_marker_when_pos_is_none(self):
        soup = _make_soup(_HAUS_HTML)
        defs = MODULE._extract_definitions(soup, None)
        assert not defs[0].startswith("__pos:")

    def test_extracts_verb_definitions(self):
        soup = _make_soup(_LAUFEN_HTML)
        defs = MODULE._extract_definitions(soup, "verb")
        actual = [d for d in defs if not d.startswith("__")]
        assert len(actual) == 3

    def test_caps_at_ten_definitions(self):
        many = "".join(
            f'<div class="dwdswb-lesart"><span class="dwdswb-definition">Def {i}</span></div>'
            for i in range(15)
        )
        html = f"<html><body><article class='dwdswb-artikel'>{many}</article></body></html>"
        soup = _make_soup(html)
        defs = MODULE._extract_definitions(soup, "noun")
        actual = [d for d in defs if not d.startswith("__")]
        assert len(actual) <= 10

    def test_deduplicates_definitions(self):
        html = """
        <html><body><article class='dwdswb-artikel'>
          <div class="dwdswb-lesart"><span class="dwdswb-definition">gleiche Definition</span></div>
          <div class="dwdswb-lesart"><span class="dwdswb-definition">gleiche Definition</span></div>
          <div class="dwdswb-lesart"><span class="dwdswb-definition">andere Definition</span></div>
        </article></body></html>
        """
        soup = _make_soup(html)
        defs = MODULE._extract_definitions(soup, None)
        assert defs.count("gleiche Definition") == 1

    def test_returns_only_pos_marker_when_no_definitions(self):
        soup = _make_soup("<html><body><article class='dwdswb-artikel'></article></body></html>")
        defs = MODULE._extract_definitions(soup, "noun")
        assert defs == ["__pos:noun__"]


# ---------------------------------------------------------------------------
# Etymology extraction
# ---------------------------------------------------------------------------

class TestExtractEtymology:
    def test_extracts_etymology_noun(self):
        soup = _make_soup(_HAUS_HTML)
        etym = MODULE._extract_etymology(soup)
        assert etym is not None
        assert "ahd." in etym

    def test_extracts_etymology_verb(self):
        soup = _make_soup(_LAUFEN_HTML)
        etym = MODULE._extract_etymology(soup)
        assert "mittelhochdeutsch" in etym

    def test_returns_none_when_no_etymology(self):
        soup = _make_soup("<html><body><article class='dwdswb-artikel'></article></body></html>")
        assert MODULE._extract_etymology(soup) is None


# ---------------------------------------------------------------------------
# Sentence extraction
# ---------------------------------------------------------------------------

class TestExtractSentences:
    def test_extracts_sentences_noun(self):
        soup = _make_soup(_HAUS_HTML)
        sents = MODULE._extract_sentences(soup)
        assert len(sents) == 3
        assert "ein großes, mehrstöckiges Haus" in sents

    def test_extracts_sentences_verb(self):
        soup = _make_soup(_LAUFEN_HTML)
        sents = MODULE._extract_sentences(soup)
        assert len(sents) == 2

    def test_caps_at_six_sentences(self):
        many = "".join(
            f'<span class="dwdswb-kompetenzbeispiel">Satz {i}.</span>'
            for i in range(10)
        )
        html = f"<html><body><article class='dwdswb-artikel'>{many}</article></body></html>"
        soup = _make_soup(html)
        assert len(MODULE._extract_sentences(soup)) <= 6

    def test_deduplicates_sentences(self):
        html = """
        <html><body><article class='dwdswb-artikel'>
          <span class="dwdswb-kompetenzbeispiel">gleicher Satz</span>
          <span class="dwdswb-kompetenzbeispiel">gleicher Satz</span>
          <span class="dwdswb-kompetenzbeispiel">anderer Satz</span>
        </article></body></html>
        """
        soup = _make_soup(html)
        sents = MODULE._extract_sentences(soup)
        assert sents.count("gleicher Satz") == 1

    def test_returns_empty_when_no_examples(self):
        soup = _make_soup("<html><body><article class='dwdswb-artikel'></article></body></html>")
        assert MODULE._extract_sentences(soup) == []


# ---------------------------------------------------------------------------
# Synonym extraction
# ---------------------------------------------------------------------------

class TestExtractSynonyms:
    def test_extracts_synonyms_noun(self):
        soup = _make_soup(_HAUS_HTML)
        syns = MODULE._extract_synonyms(soup)
        assert "Gebäude" in syns
        assert "Bauwerk" in syns

    def test_extracts_synonyms_verb(self):
        soup = _make_soup(_LAUFEN_HTML)
        syns = MODULE._extract_synonyms(soup)
        assert "rennen" in syns

    def test_uses_only_first_synset(self):
        html = """
        <html><body><article class='dwdswb-artikel'>
          <div class="ot-synset">
            <a href="/wb/A">Wort A</a>
          </div>
          <div class="ot-synset">
            <a href="/wb/B">Wort B</a>
          </div>
        </article></body></html>
        """
        soup = _make_soup(html)
        syns = MODULE._extract_synonyms(soup)
        assert "Wort A" in syns
        assert "Wort B" not in syns

    def test_caps_at_fifteen(self):
        links = "".join(f'<a href="/wb/w{i}">Wort{i}</a>' for i in range(20))
        html = f"<html><body><article class='dwdswb-artikel'><div class='ot-synset'>{links}</div></article></body></html>"
        soup = _make_soup(html)
        assert len(MODULE._extract_synonyms(soup)) <= 15

    def test_deduplicates_synonyms(self):
        html = """
        <html><body><article class='dwdswb-artikel'>
          <div class="ot-synset">
            <a href="/wb/a">Gebäude</a>
            <a href="/wb/b">Gebäude</a>
            <a href="/wb/c">Bauwerk</a>
          </div>
        </article></body></html>
        """
        soup = _make_soup(html)
        syns = MODULE._extract_synonyms(soup)
        assert syns.count("Gebäude") == 1

    def test_returns_empty_when_no_synsets(self):
        soup = _make_soup("<html><body><article class='dwdswb-artikel'></article></body></html>")
        assert MODULE._extract_synonyms(soup) == []


# ---------------------------------------------------------------------------
# _clean helper
# ---------------------------------------------------------------------------

class TestClean:
    def test_normalises_nbsp(self):
        assert _clean("text\xa0here") == "text here"

    def test_collapses_multiple_spaces(self):
        assert _clean("too   many   spaces") == "too many spaces"

    def test_strips_edges(self):
        assert _clean("  hello  ") == "hello"


# ---------------------------------------------------------------------------
# should_fetch_image
# ---------------------------------------------------------------------------

class TestShouldFetchImage:
    def _data(self, pos=None, definitions=None):
        return WordData(
            word="test",
            language_code="de",
            pos=pos,
            definitions=definitions or [],
        )

    def test_noun_gets_image(self):
        assert MODULE.should_fetch_image(self._data(pos="noun (das)")) is True

    def test_verb_gets_image(self):
        assert MODULE.should_fetch_image(self._data(pos="verb")) is True

    def test_adjective_gets_image(self):
        assert MODULE.should_fetch_image(self._data(pos="adjective")) is True

    def test_adverb_no_image(self):
        assert MODULE.should_fetch_image(self._data(pos="adverb")) is False

    def test_preposition_no_image(self):
        assert MODULE.should_fetch_image(self._data(pos="preposition")) is False

    def test_no_info_gets_image(self):
        assert MODULE.should_fetch_image(self._data()) is True


# ---------------------------------------------------------------------------
# Integration: fetch() with mocked HTTP
# ---------------------------------------------------------------------------

class TestFetchIntegration:
    def _mock_get(self, html: str):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.text = html
        mock_resp.status_code = 200
        return mock_resp

    def test_fetch_noun(self):
        with patch.object(MODULE._session, "get", return_value=self._mock_get(_HAUS_HTML)):
            data = MODULE.fetch("Haus")
        assert data.word == "Haus"
        assert data.language_code == "de"
        assert data.ipa == "haʊ̯s"
        assert data.pos == "noun (das)"
        assert len([d for d in data.definitions if not d.startswith("__")]) == 3
        assert not data.not_found

    def test_fetch_verb(self):
        with patch.object(MODULE._session, "get", return_value=self._mock_get(_LAUFEN_HTML)):
            data = MODULE.fetch("laufen")
        assert data.pos == "verb"
        assert data.ipa == "ˈlaʊ̯fn̩"
        assert "rennen" in data.synonyms

    def test_fetch_adjective(self):
        with patch.object(MODULE._session, "get", return_value=self._mock_get(_SCHOEN_HTML)):
            data = MODULE.fetch("schön")
        assert data.pos == "adjective"

    def test_fetch_not_found_returns_not_found(self):
        with patch.object(MODULE._session, "get", return_value=self._mock_get(_NOT_FOUND_HTML)):
            data = MODULE.fetch("xyznotaword")
        assert data.not_found is True

    def test_fetch_sets_source_url(self):
        with patch.object(MODULE._session, "get", return_value=self._mock_get(_HAUS_HTML)):
            data = MODULE.fetch("Haus")
        assert "dwds.de/wb/Haus" in data.source_url

    def test_fetch_includes_etymology(self):
        with patch.object(MODULE._session, "get", return_value=self._mock_get(_HAUS_HTML)):
            data = MODULE.fetch("Haus")
        assert data.etymology is not None
        assert "ahd." in data.etymology

    def test_fetch_includes_sentences(self):
        with patch.object(MODULE._session, "get", return_value=self._mock_get(_HAUS_HTML)):
            data = MODULE.fetch("Haus")
        assert len(data.sentences) == 3

    def test_fetch_includes_audio_url(self):
        with patch.object(MODULE._session, "get", return_value=self._mock_get(_HAUS_HTML)):
            data = MODULE.fetch("Haus")
        assert data.audio_url == "https://www.dwds.de/audio/001/das_Haus.mp3"

    def test_fetch_http_404_returns_not_found(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch.object(MODULE._session, "get", return_value=mock_resp):
            data = MODULE.fetch("xyznotaword")
        assert data.not_found is True
