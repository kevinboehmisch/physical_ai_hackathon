"""Interview trainer settings read from the environment."""

import os
import logging
from pathlib import Path
from dataclasses import dataclass


logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = ("de", "en")
DEFAULT_LANGUAGE = "de"
DEFAULT_WHISPER_MODEL = "small"
DEFAULT_CONTENT_MODEL = "Qwen/Qwen2.5-72B-Instruct"
DEFAULT_REPORTS_DIRNAME = "reports"


@dataclass(frozen=True)
class InterviewSettings:
    """Runtime settings for the interview trainer."""

    language: str
    whisper_model: str
    content_model: str
    reports_dir: Path
    arduino_port: str | None


def _resolve_language() -> str:
    candidate = (os.getenv("INTERVIEW_LANGUAGE") or DEFAULT_LANGUAGE).strip().lower()
    if candidate not in SUPPORTED_LANGUAGES:
        logger.warning("Unsupported INTERVIEW_LANGUAGE=%r, using %r", candidate, DEFAULT_LANGUAGE)
        return DEFAULT_LANGUAGE
    return candidate


def load_interview_settings(instance_path: str | Path | None = None) -> InterviewSettings:
    """Build settings from environment variables, resolving the reports directory."""
    reports_env = os.getenv("INTERVIEW_REPORTS_DIR")
    if reports_env:
        reports_dir = Path(reports_env).expanduser()
    else:
        base = Path(instance_path) if instance_path else Path(__file__).resolve().parents[3]
        reports_dir = base / DEFAULT_REPORTS_DIRNAME
    return InterviewSettings(
        language=_resolve_language(),
        whisper_model=(os.getenv("INTERVIEW_WHISPER_MODEL") or DEFAULT_WHISPER_MODEL).strip(),
        content_model=(os.getenv("INTERVIEW_CONTENT_MODEL") or DEFAULT_CONTENT_MODEL).strip(),
        reports_dir=reports_dir,
        arduino_port=(os.getenv("INTERVIEW_ARDUINO_PORT") or "").strip() or None,
    )
