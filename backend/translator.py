"""
AI-powered translation using OpenAI API.
Translates words with their definitions into a target language.
"""

import logging
import time
from typing import Callable, Optional

from . import database as db
from .pipeline import is_cancelled, clear_cancel

logger = logging.getLogger(__name__)

# Default prompt template — {word}, {source_language}, and {target_language} are substituted
PROMPT_TEMPLATE = (
    'Translate "{word}" to {target_language}. '
    "Provide the output the way you'd see in a {source_language}-{target_language} dictionary, "
    "but without any samples or pronunciation or word itself, just plain {target_language} definition "
    "with possibly some common {source_language} -> {target_language} phrases. "
    "Use markdown for formatting. If there are any phrases, format them as a list "
    "with {source_language} phrase being in bold. Separate phrases from the definition with a horizonal line. Here is an example of the expected output format if the Source Language would be English and Target Language would be Polish:\n\n"
    "czas. (formalny, prawniczy)\n\n"
    "**wyrzec się, zrzec się** (czegoś) pod przysięgą lub uroczyście; "
    "odwołać, zaprzeć się (przekonań, wiary, roszczeń itp.); "
    "formalnie i publicznie porzucić (pogląd, zasadę)\n\n"
    "---\n\n"
    "**to abjure one's faith** – wyrzec się wiary\n\n"
    "**to abjure allegiance** – zrzec się przysięgi wierności\n\n"
    "**to abjure heresy** – wyrzec się herezji\n\n"
    "**to abjure a claim** – zrzec się roszczenia\n\n"
    "**to abjure the realm** – wyrzec się kraju (hist., prawn.)\n\n"
    "**to abjure one's principles** – zaprzeć się swoich zasad"
)


def _get_openai_client():
    """Create an OpenAI client from stored settings. Returns None if not configured."""
    api_key = db.get_setting("openai_api_key")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        base_url = db.get_setting("openai_base_url")
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        return OpenAI(**kwargs)
    except ImportError:
        logger.error("openai package not installed. Run: pip install openai")
        return None


def translate_word(word: str, target_language: str, source_language: str = "English") -> Optional[str]:
    """
    Translate a single word using the OpenAI API.
    Returns the translation as HTML (markdown converted), or None on failure.
    """
    client = _get_openai_client()
    if not client:
        return None

    model = db.get_setting("openai_model") or "gpt-4o-mini"
    prompt = PROMPT_TEMPLATE.format(word=word, target_language=target_language, source_language=source_language)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3,
        )
        content = response.choices[0].message.content
        if not content:
            return None
        return _markdown_to_html(content.strip())
    except Exception as exc:
        logger.error("Translation failed for '%s': %s", word, exc)
        return None


def _markdown_to_html(text: str) -> str:
    """Convert markdown to HTML using the standard markdown library."""
    import markdown
    return markdown.markdown(text)


def translate_batch(
    language_code: str,
    progress_cb: Optional[Callable[[str, str], None]] = None,
) -> dict:
    """
    Translate all untranslated words for a language.
    Uses the target language from settings.
    Respects the cancellation flag between words.

    Returns {"translated": int, "failed": int, "skipped": int, "errors": list[str]}
    """
    target_language = db.get_setting("translation_target_language")
    if not target_language or target_language.lower() == "none":
        return {"translated": 0, "failed": 0, "skipped": 0, "errors": ["No target language configured."]}

    api_key = db.get_setting("openai_api_key")
    if not api_key:
        return {"translated": 0, "failed": 0, "skipped": 0, "errors": ["OpenAI API key not configured."]}

    words = db.get_untranslated_words(language_code)
    if not words:
        return {"translated": 0, "failed": 0, "skipped": 0, "errors": []}

    # Get source language name from the language module
    from .languages import get_module
    module = get_module(language_code)
    source_language = module.language_name  # e.g. "English", "German"

    clear_cancel()
    translated = 0
    failed = 0
    errors: list[str] = []

    for row in words:
        if is_cancelled():
            logger.info("Translation cancelled after %d words", translated)
            if progress_cb:
                progress_cb("", "cancelled")
            break

        word = row["word"]
        if progress_cb:
            progress_cb(word, "translating")

        result = translate_word(word, target_language, source_language)
        if result:
            db.set_translation(word, language_code, result, target_language)
            # Mark as pending_sync so the translation gets pushed to Anki
            db.set_status(word, language_code, "pending_sync")
            translated += 1
            if progress_cb:
                progress_cb(word, "translated")
        else:
            failed += 1
            errors.append(word)
            db.set_error(word, language_code, "Translation failed — check API key and model settings")
            if progress_cb:
                progress_cb(word, "translation_failed")

        # Small delay to avoid rate limiting
        time.sleep(0.2)

    return {"translated": translated, "failed": failed, "skipped": len(words) - translated - failed, "errors": errors}
