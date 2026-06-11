"""
Image fetcher — searches DuckDuckGo Images and downloads the first safe result.
Falls back gracefully: if no image is found, returns None (card works without it).
"""

import hashlib
import logging
import re
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import requests

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# Allowed image MIME types
_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_EXT_MAP = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def fetch_image(query: str, media_dir: Path) -> Optional[str]:
    """
    Search DuckDuckGo Images for `query`, download the first result to
    `media_dir`, and return the filename. Returns None on any failure.
    """
    urls = _ddg_image_urls(query)
    for url in urls[:5]:  # try up to 5 candidates
        filename = _download_image(url, query, media_dir)
        if filename:
            return filename
    logger.warning("No image found for query: %s", query)
    return None


def _ddg_image_urls(query: str) -> list[str]:
    """Scrape DuckDuckGo Images for image URLs."""
    try:
        # Step 1: get vqd token
        search_url = f"https://duckduckgo.com/?q={quote_plus(query)}&iax=images&ia=images"
        resp = requests.get(search_url, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        vqd_match = re.search(r'vqd=(["\'])([^"\']+)\1', resp.text)
        if not vqd_match:
            logger.debug("Could not extract vqd token for query: %s", query)
            return []
        vqd = vqd_match.group(2)

        # Step 2: fetch image results JSON
        api_url = (
            f"https://duckduckgo.com/i.js"
            f"?q={quote_plus(query)}&vqd={vqd}&f=,,,,,&p=1&v7exp=a"
        )
        resp = requests.get(api_url, headers={**_HEADERS, "Referer": search_url}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return [r["image"] for r in data.get("results", []) if r.get("image")]
    except Exception as exc:
        logger.warning("DuckDuckGo image search failed: %s", exc)
        return []


def _download_image(url: str, query: str, media_dir: Path) -> Optional[str]:
    """Download an image URL and save it. Returns filename or None."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15, stream=True)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip()
        if content_type not in _ALLOWED_TYPES:
            return None
        ext = _EXT_MAP.get(content_type, ".jpg")
        # Stable filename based on query
        slug = re.sub(r"[^a-z0-9]", "_", query.lower())[:40]
        h = hashlib.md5(url.encode()).hexdigest()[:8]
        filename = f"{slug}_{h}{ext}"
        dest = media_dir / filename
        if not dest.exists():
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
        return filename
    except Exception as exc:
        logger.debug("Failed to download image %s: %s", url, exc)
        return None
