"""
Video metadata and transcript extraction using yt-dlp
"""
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, List
from loguru import logger


def extract_video_metadata(url: str) -> Dict:
    """
    Extract metadata from a video URL without downloading the video itself.

    Relies on yt-dlp being installed and available on PATH, or the
    yt_dlp Python package.

    Args:
        url: Video URL (YouTube, Vimeo, direct MP4, etc.)

    Returns:
        Dictionary with title, description, duration, upload_date, etc.
    """
    try:
        import yt_dlp  # type: ignore

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            return {}

        return {
            "title": info.get("title", ""),
            "description": info.get("description", ""),
            "duration_seconds": info.get("duration"),
            "upload_date": info.get("upload_date"),
            "uploader": info.get("uploader", ""),
            "view_count": info.get("view_count"),
            "like_count": info.get("like_count"),
            "channel": info.get("channel", ""),
            "tags": info.get("tags", []),
            "categories": info.get("categories", []),
            "thumbnail": info.get("thumbnail", ""),
            "webpage_url": info.get("webpage_url", url),
        }

    except ImportError:
        logger.warning("yt-dlp not installed; using subprocess fallback")
        return _extract_via_subprocess(url)
    except Exception as e:
        logger.error(f"Video metadata extraction failed for {url}: {e}")
        return {}


def _extract_via_subprocess(url: str) -> Dict:
    """Fallback: call the yt-dlp CLI and parse JSON output"""
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-playlist", url],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.warning(f"yt-dlp subprocess failed: {result.stderr[:200]}")
            return {}

        info = json.loads(result.stdout)
        return {
            "title": info.get("title", ""),
            "description": info.get("description", ""),
            "duration_seconds": info.get("duration"),
            "upload_date": info.get("upload_date"),
            "uploader": info.get("uploader", ""),
            "tags": info.get("tags", []),
        }
    except Exception as e:
        logger.error(f"yt-dlp subprocess extraction failed: {e}")
        return {}


def extract_video_subtitles(url: str, lang: str = "en") -> Optional[str]:
    """
    Download and return auto-generated or manual subtitles for a video.

    Args:
        url: Video URL
        lang: Preferred subtitle language code (default "en")

    Returns:
        Subtitle text as a plain string, or None if unavailable
    """
    try:
        import yt_dlp

        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": [lang],
                "subtitlesformat": "vtt",
                "outtmpl": str(Path(tmpdir) / "%(id)s.%(ext)s"),
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            # Look for any .vtt file written
            vtt_files = list(Path(tmpdir).glob("*.vtt"))
            if not vtt_files:
                logger.debug(f"No subtitles found for {url}")
                return None

            text = _parse_vtt(vtt_files[0].read_text(encoding="utf-8"))
            logger.debug(f"Extracted {len(text)} chars of subtitles from {url}")
            return text

    except ImportError:
        logger.warning("yt-dlp not installed; cannot extract subtitles")
        return None
    except Exception as e:
        logger.error(f"Subtitle extraction failed for {url}: {e}")
        return None


def _parse_vtt(vtt_content: str) -> str:
    """
    Parse a WebVTT subtitle file and return plain text (deduplicated lines)
    """
    import re

    lines: List[str] = []
    seen: set = set()

    for line in vtt_content.splitlines():
        line = line.strip()
        # Skip VTT headers, timestamps, and blank lines
        if not line or line.startswith("WEBVTT") or "-->" in line:
            continue
        # Remove HTML tags (e.g. <00:00:01.000>)
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if clean and clean not in seen:
            lines.append(clean)
            seen.add(clean)

    return " ".join(lines)


def extract_video_full(url: str) -> Dict:
    """
    Convenience function: extract metadata + subtitles from a video URL.

    Args:
        url: Video URL

    Returns:
        Dictionary with keys: metadata, transcript, text (combined for indexing)
    """
    metadata = extract_video_metadata(url)
    transcript = extract_video_subtitles(url)

    # Build indexable text combining metadata + transcript
    parts: List[str] = []
    if metadata.get("title"):
        parts.append(metadata["title"])
    if metadata.get("description"):
        parts.append(metadata["description"])
    if transcript:
        parts.append(transcript)

    return {
        "metadata": metadata,
        "transcript": transcript,
        "text": "\n\n".join(parts),
    }
