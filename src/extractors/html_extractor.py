"""
HTML content extraction using Trafilatura and BeautifulSoup
"""
from typing import Optional, Dict
from loguru import logger


def extract_html_content(html: str, url: str = "") -> Optional[str]:
    """
    Extract main body text from an HTML page using Trafilatura.

    Falls back to a simple BeautifulSoup extraction if Trafilatura returns
    nothing (e.g. for pages with unusual structure).

    Args:
        html: Raw HTML string
        url: Source URL (used by Trafilatura for metadata)

    Returns:
        Extracted plain text, or None on failure
    """
    try:
        import trafilatura

        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_recall=True,
        )

        if text and len(text.strip()) > 50:
            logger.debug(f"Trafilatura extracted {len(text)} chars from {url}")
            return text.strip()

    except Exception as e:
        logger.warning(f"Trafilatura extraction failed for {url}: {e}")

    # Fallback: BeautifulSoup
    return _bs4_extract(html, url)


def _bs4_extract(html: str, url: str = "") -> Optional[str]:
    """Simple BeautifulSoup fallback extractor"""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        # Remove navigation, script, style, header, footer
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n")
        # Collapse blank lines
        import re
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

        if text:
            logger.debug(f"BS4 fallback extracted {len(text)} chars from {url}")
            return text

    except Exception as e:
        logger.error(f"BS4 extraction failed for {url}: {e}")

    return None


def extract_html_metadata(html: str, url: str = "") -> Dict:
    """
    Extract page metadata (title, description, canonical URL) from HTML

    Args:
        html: Raw HTML string
        url: Source URL

    Returns:
        Metadata dictionary
    """
    meta: Dict = {"title": "", "description": "", "canonical_url": url}

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        # Title
        title_tag = soup.find("title")
        if title_tag:
            meta["title"] = title_tag.get_text(strip=True)

        # Description
        desc = soup.find("meta", attrs={"name": "description"})
        if desc and desc.get("content"):
            meta["description"] = desc["content"]

        # OG title override
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            meta["title"] = meta["title"] or og_title["content"]

        # Canonical
        canonical = soup.find("link", rel="canonical")
        if canonical and canonical.get("href"):
            meta["canonical_url"] = canonical["href"]

    except Exception as e:
        logger.warning(f"Metadata extraction failed for {url}: {e}")

    return meta
