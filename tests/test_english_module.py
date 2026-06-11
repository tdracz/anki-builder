"""
Tests for the English language module — HTML parsing logic.
Uses static HTML fixtures so no real HTTP requests are made.
"""

import pytest
from bs4 import BeautifulSoup
from backend.languages.english import EnglishModule
from backend.languages.base import WordData

MODULE = EnglishModule()

# ---------------------------------------------------------------------------
# Minimal HTML fixtures that mimic TFD's structure
# ---------------------------------------------------------------------------

_SERENDIPITY_HTML = """
<html><body>
<div id="Definition">
  <section>
    <span class="pron">(sĕr′ən-dĭp′ĭ-tē)</span>
    <a class="snd" data-snd="//img.tfd.com/hm/mp3/serendipity.mp3"></a>
    <span class="pos">noun</span>
    <div class="pseg">
      <span class="ds-single">The faculty of making fortunate discoveries by accident.</span>
      <span class="illustration">It was pure serendipity that they met.</span>
    </div>
  </section>
</div>
<div id="Etymology">
  <p>From Serendip, an old name for Sri Lanka.</p>
</div>
</body></html>
"""

_NO_ENTRY_HTML = """
<html><body><p>Word not found.</p></body></html>
"""

_MULTI_DEF_HTML = """
<html><body>
<div id="Definition">
  <section>
    <span class="pron">(mĕl′ən-kŏl′ē)</span>
    <span class="pos">noun</span>
    <div class="pseg">
      <span class="ds-single">Sadness or depression of the spirits; gloom.</span>
    </div>
    <div class="pseg">
      <span class="ds-single">Black bile, formerly regarded as one of the four humors.</span>
    </div>
  </section>
</div>
</body></html>
"""


# ---------------------------------------------------------------------------
# IPA extraction
# ---------------------------------------------------------------------------

class TestExtractIPA:
    def test_extracts_ipa(self):
        soup = BeautifulSoup(_SERENDIPITY_HTML, "lxml")
        assert MODULE._extract_ipa(soup) == "(sĕr′ən-dĭp′ĭ-tē)"

    def test_returns_none_when_no_entry(self):
        soup = BeautifulSoup(_NO_ENTRY_HTML, "lxml")
        assert MODULE._extract_ipa(soup) is None


# ---------------------------------------------------------------------------
# Audio URL extraction
# ---------------------------------------------------------------------------

class TestExtractAudioUrl:
    def test_extracts_from_data_snd(self):
        soup = BeautifulSoup(_SERENDIPITY_HTML, "lxml")
        url = MODULE._extract_audio_url(soup, "serendipity")
        assert url == "https://img.tfd.com/hm/mp3/serendipity.mp3"

    def test_falls_back_to_constructed_url(self):
        soup = BeautifulSoup(_NO_ENTRY_HTML, "lxml")
        url = MODULE._extract_audio_url(soup, "serendipity")
        assert url == "https://img.tfd.com/hm/mp3/serendipity.mp3"

    def test_https_prefix_added_to_protocol_relative(self):
        html = '<html><body><a class="snd" data-snd="//example.com/audio.mp3"></a></body></html>'
        soup = BeautifulSoup(html, "lxml")
        url = MODULE._extract_audio_url(soup, "test")
        assert url.startswith("https://")


# ---------------------------------------------------------------------------
# Definition extraction
# ---------------------------------------------------------------------------

class TestExtractDefinitions:
    def test_extracts_single_definition(self):
        soup = BeautifulSoup(_SERENDIPITY_HTML, "lxml")
        defs = MODULE._extract_definitions(soup)
        assert len(defs) >= 1
        assert "fortunate discoveries" in defs[0]

    def test_extracts_multiple_definitions(self):
        soup = BeautifulSoup(_MULTI_DEF_HTML, "lxml")
        defs = MODULE._extract_definitions(soup)
        assert len(defs) == 2

    def test_returns_empty_when_no_entry(self):
        soup = BeautifulSoup(_NO_ENTRY_HTML, "lxml")
        assert MODULE._extract_definitions(soup) == []

    def test_caps_at_ten_definitions(self):
        items = "".join(f'<span class="ds-single">Def {i}.</span>' for i in range(15))
        html = f'<html><body><div id="Definition"><section><div class="pseg"><i>n.</i>{items}</div></section></div></body></html>'
        soup = BeautifulSoup(html, "lxml")
        defs = MODULE._extract_definitions(soup)
        # Filter out __pos:__ markers when counting actual definitions
        actual_defs = [d for d in defs if not d.startswith('__pos:')]
        assert len(actual_defs) <= 10


# ---------------------------------------------------------------------------
# Etymology extraction
# ---------------------------------------------------------------------------

class TestExtractEtymology:
    def test_extracts_etymology(self):
        soup = BeautifulSoup(_SERENDIPITY_HTML, "lxml")
        etym = MODULE._extract_etymology(soup)
        assert etym is not None
        assert "Serendip" in etym

    def test_returns_none_when_no_etymology(self):
        soup = BeautifulSoup(_NO_ENTRY_HTML, "lxml")
        assert MODULE._extract_etymology(soup) is None


# ---------------------------------------------------------------------------
# Sentence extraction
# ---------------------------------------------------------------------------

class TestExtractSentences:
    def test_extracts_illustration_spans(self):
        soup = BeautifulSoup(_SERENDIPITY_HTML, "lxml")
        sents = MODULE._extract_sentences(soup)
        assert any("serendipity" in s.lower() for s in sents)

    def test_caps_at_eight_sentences(self):
        items = "".join(f'<span class="illustration">Sentence {i}.</span>' for i in range(12))
        html = f"<html><body>{items}</body></html>"
        soup = BeautifulSoup(html, "lxml")
        assert len(MODULE._extract_sentences(soup)) <= 8


# ---------------------------------------------------------------------------
# POS extraction
# ---------------------------------------------------------------------------

class TestExtractPOS:
    def test_extracts_pos(self):
        soup = BeautifulSoup(_SERENDIPITY_HTML, "lxml")
        assert MODULE._extract_pos(soup) == "noun"

    def test_returns_none_when_no_pos(self):
        soup = BeautifulSoup(_NO_ENTRY_HTML, "lxml")
        assert MODULE._extract_pos(soup) is None


# ---------------------------------------------------------------------------
# should_fetch_image heuristic
# ---------------------------------------------------------------------------

class TestShouldFetchImage:
    def _data(self, pos=None, definitions=None):
        return WordData(
            word="test",
            language_code="en",
            pos=pos,
            definitions=definitions or [],
        )

    def test_noun_gets_image(self):
        assert MODULE.should_fetch_image(self._data(pos="noun")) is True

    def test_abstract_pos_no_image(self):
        for pos in ["adverb", "conjunction", "preposition", "pronoun"]:
            assert MODULE.should_fetch_image(self._data(pos=pos)) is False

    def test_abstract_definition_no_image(self):
        data = self._data(definitions=["The state of being happy."])
        assert MODULE.should_fetch_image(data) is False

    def test_concrete_definition_gets_image(self):
        data = self._data(definitions=["A large mammal with a trunk."])
        assert MODULE.should_fetch_image(data) is True

    def test_no_pos_no_definitions_gets_image(self):
        # Default: fetch image when we have no info
        assert MODULE.should_fetch_image(self._data()) is True


# ---------------------------------------------------------------------------
# Synonyms extraction
# ---------------------------------------------------------------------------

_THESAURUS_HTML = """
<html><body>
<div id="Thesaurus">
  <a href="/happy">happy</a>
  <a href="/joyful">joyful</a>
  <a href="/content">content</a>
</div>
</body></html>
"""

_NO_THESAURUS_HTML = """
<html><body><p>No thesaurus here.</p></body></html>
"""


class TestExtractSynonyms:
    def test_extract_synonyms_returns_empty(self):
        """_extract_synonyms is now a no-op (thesaurus is fetched separately)."""
        soup = BeautifulSoup(_THESAURUS_HTML, "lxml")
        assert MODULE._extract_synonyms(soup) == []

    def test_extract_thesaurus_parses_collins_format(self):
        """Test the thesaurus parser with Collins-style HTML from freethesaurus.com."""
        from unittest.mock import patch, MagicMock
        collins_html = '''
        <html><body>
        <section data-src="hc_thes">
          <h2>Synonyms for test</h2>
          <div data-part="adj">
            <h3>good</h3>
            <div class="TMCont"><div class="TCont">
              <h4>Synonyms</h4>
              <ul class="TSyn">
                <li><a class="tw" href="happy">happy</a></li>
                <li><a class="tw" href="joyful">joyful</a></li>
              </ul>
              <h4>Antonyms</h4>
              <ul class="TAnt">
                <li><a class="tw" href="sad">sad</a></li>
              </ul>
            </div></div>
          </div>
        </section>
        </body></html>
        '''
        with patch.object(MODULE._session, 'get') as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = collins_html
            mock_get.return_value = mock_resp
            syns, ants, url = MODULE._extract_thesaurus("test")

        assert "happy" in syns
        assert "joyful" in syns
        assert "sad" in ants
        assert "freethesaurus.com" in url

    def test_deduplicates_synonyms(self):
        from unittest.mock import patch, MagicMock
        html = '''
        <html><body>
        <section data-src="hc_thes">
          <div data-part="noun">
            <ul class="TSyn">
              <li><a class="tw" href="a">happy</a></li>
              <li><a class="tw" href="b">happy</a></li>
              <li><a class="tw" href="c">joyful</a></li>
            </ul>
          </div>
        </section>
        </body></html>
        '''
        with patch.object(MODULE._session, 'get') as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = html
            mock_get.return_value = mock_resp
            syns, ants, url = MODULE._extract_thesaurus("test")

        assert syns.count("happy") == 1


# ---------------------------------------------------------------------------
# POS grouping in definitions (__pos: markers)
# ---------------------------------------------------------------------------

_POS_GROUP_HTML = """
<html><body>
<div id="Definition">
  <section>
    <div class="pseg">
      <i>n.</i>
      <div class="ds-list">Sadness.</div>
      <div class="ds-list">Gloom.</div>
    </div>
    <div class="pseg">
      <i>adj.</i>
      <div class="ds-list">Feeling sad.</div>
    </div>
  </section>
</div>
</body></html>
"""


class TestDefinitionPosGrouping:
    def test_produces_pos_markers(self):
        soup = BeautifulSoup(_POS_GROUP_HTML, "lxml")
        defs = MODULE._extract_definitions(soup)
        assert "__pos:noun__" in defs
        assert "__pos:adjective__" in defs

    def test_definitions_follow_pos_markers(self):
        soup = BeautifulSoup(_POS_GROUP_HTML, "lxml")
        defs = MODULE._extract_definitions(soup)
        noun_idx = defs.index("__pos:noun__")
        assert defs[noun_idx + 1] == "Sadness."
        assert defs[noun_idx + 2] == "Gloom."

    def test_numbers_stripped_from_definitions(self):
        html = """
        <html><body><div id="Definition"><section>
          <div class="pseg"><i>n.</i>
            <div class="ds-list">1. Sadness.</div>
            <div class="ds-list">2. Gloom.</div>
          </div>
        </section></div></body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        defs = MODULE._extract_definitions(soup)
        actual_defs = [d for d in defs if not d.startswith("__pos:")]
        assert all(not d[0].isdigit() for d in actual_defs)
