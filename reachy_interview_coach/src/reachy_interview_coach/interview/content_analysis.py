"""Content evaluation of the answers via the Hugging Face Inference API.

Only the transcript and numeric metrics are sent; no audio, no images. The model is asked for
strictly observable, constructive feedback and must never judge emotions or personality.
"""

import json
import logging
from typing import Any

from huggingface_hub import InferenceClient

from reachy_interview_coach.interview.session import InterviewSession
from reachy_interview_coach.interview.questions import ROLE_TITLE, ROLE_SUMMARY


logger = logging.getLogger(__name__)

CATEGORIES = ("content", "speech", "body_language")

SYSTEM_PROMPT = {
    "de": (
        "Du bist ein erfahrener, wohlwollender Interview-Coach für Software-Bewerbungsgespräche. "
        "Du bewertest ausschließlich beobachtbares Verhalten und Gesagtes: Struktur, Konkretheit, fachliche "
        "Richtigkeit, Sprechtempo, Füllwörter, Pausen, Blickkontakt, Körperhaltung. "
        "Du stellst niemals Diagnosen zu Gefühlen, Stress, Nervosität, Charakter oder Persönlichkeit. "
        "Du antwortest ausschließlich mit einem JSON-Objekt im vorgegebenen Schema, in deutscher Sprache, "
        "konstruktiv und konkret."
    ),
    "en": (
        "You are an experienced, supportive interview coach for software engineering interviews. "
        "You only evaluate observable behaviour and what was said: structure, concreteness, technical correctness, "
        "speaking pace, filler words, pauses, eye contact, posture. "
        "You never diagnose emotions, stress, nervousness, character or personality. "
        "You reply exclusively with one JSON object in the given schema, in English, constructive and specific."
    ),
}

OUTPUT_SCHEMA = """{
  "answers": [
    {
      "number": 1,
      "summary": "one sentence: what the candidate said",
      "star": {"situation": true, "task": false, "action": true, "result": false} or null if not a behavioral question,
      "concreteness": 1-5 (5 = specific examples, numbers, names of tools/decisions),
      "technical_correctness": 1-5 or null if not a technical question,
      "strength": "one specific thing that worked well in this answer",
      "tip": "one concrete, actionable suggestion for this answer"
    }
  ],
  "categories": {
    "content": {"strength": "...", "tip": "..."},
    "speech": {"strength": "...", "tip": "..."} or null if metrics.speech is missing,
    "body_language": {"strength": "...", "tip": "..."} or null if metrics.body_language is missing
  },
  "overall_summary": "2-3 sentences",
  "spoken_feedback": "what the robot says out loud: max 8 short sentences, warm, one strength and one tip per available category only, mentions that a detailed HTML report has been saved"
}

Rules: every statement about speech or body language must be backed by a number in metrics. If a metric block is
missing, do not mention that category at all (no guesses about eye contact, posture, pace or fillers)."""


def _metrics_for_prompt(speech: dict[str, Any] | None, body: dict[str, Any] | None) -> dict[str, Any]:
    """Reduce the raw metric dicts to the fields worth showing the model."""
    out: dict[str, Any] = {}
    if speech and "error" not in speech:
        out["speech"] = {
            "overall": {k: v for k, v in speech.items() if k != "answers"},
            "per_question": {
                str(a["question_number"]): {
                    "words_per_minute": a.get("words_per_minute"),
                    "word_count": a.get("word_count"),
                    "filler_count": a.get("filler_count"),
                    "filler_words": a.get("filler_words"),
                    "long_pauses_over_3s": len(a.get("long_pauses", [])),
                    "speaking_seconds": a.get("speaking_seconds"),
                }
                for a in speech.get("answers", [])
            },
        }
    if body and body.get("available"):
        out["body_language"] = {
            "overall": body.get("overall"),
            "per_question": body.get("per_question"),
            "notable_moments": body.get("notable_moments", [])[:10],
        }
    return out


def build_user_prompt(
    session: InterviewSession,
    speech: dict[str, Any] | None,
    body: dict[str, Any] | None,
) -> str:
    """Assemble the text-only prompt: role, questions, transcripts and metrics."""
    lang = session.settings.language
    questions = []
    for asked in session.asked:
        questions.append(
            {
                "number": asked.number,
                "kind": asked.question.kind,
                "question": asked.question.text,
                "evaluation_hint": asked.question.evaluation_hint,
                "answer_transcript": session.answer_text(asked.number) or "",
            }
        )
    payload = {
        "role": {"title": ROLE_TITLE[lang], "summary": ROLE_SUMMARY[lang]},
        "questions": questions,
        "metrics": _metrics_for_prompt(speech, body),
        "metric_notes": {
            "eye_contact_ratio": "share of analysed frames where the head faced the robot's camera and the gaze was centred",
            "hand_activity_ratio": "share of frames with fast wrist movement while hands were visible (fidgeting or gesturing)",
            "posture_drop_ratio": "share of frames where the head-to-shoulder distance dropped notably vs. the start (slouching)",
            "words_per_minute": "typical conversational range is roughly 110-160 in German, 130-170 in English",
        },
    }
    instructions = {
        "de": (
            "Bewerte die folgenden Interviewantworten für die genannte Rolle. Für Verhaltensfragen (kind=behavioral) "
            "prüfe die STAR-Struktur. Für Fachfragen (kind=technical) prüfe die fachliche Richtigkeit anhand des "
            "evaluation_hint, ohne die Lösung vorzusagen. Nutze die Kennzahlen nur als beobachtbare Fakten. "
            "Antworte genau in diesem JSON-Schema:\n"
        ),
        "en": (
            "Evaluate the following interview answers for the given role. For behavioral questions check the STAR "
            "structure. For technical questions check correctness against evaluation_hint without giving away the "
            "solution. Use the metrics only as observable facts. Reply exactly in this JSON schema:\n"
        ),
    }
    return instructions[lang] + OUTPUT_SCHEMA + "\n\nDATA:\n" + json.dumps(payload, ensure_ascii=False, indent=1)


def fallback_evaluation(session: InterviewSession, speech: dict[str, Any] | None) -> dict[str, Any]:
    """Metric-only feedback used when the language model is unavailable."""
    lang = session.settings.language
    overall = speech or {}
    wpm = overall.get("words_per_minute")
    fillers = sum(a.get("filler_count", 0) for a in overall.get("answers", [])) if overall.get("answers") else None
    if lang == "de":
        spoken = (
            "Danke für das Gespräch. Die inhaltliche Auswertung war gerade nicht erreichbar, "
            "deshalb bekommst du nur die Kennzahlen. "
        )
        if wpm:
            spoken += f"Dein Sprechtempo lag bei etwa {wpm:.0f} Wörtern pro Minute. "
        if fillers is not None:
            spoken += f"Ich habe {fillers} Füllwörter gezählt. "
        spoken += "Den ausführlichen HTML-Bericht habe ich gespeichert."
        summary = "Inhaltliche Bewertung nicht verfügbar; nur Kennzahlen."
    else:
        spoken = "Thanks for the interview. The content evaluation was unavailable, so here are only the metrics. "
        if wpm:
            spoken += f"Your speaking pace was about {wpm:.0f} words per minute. "
        if fillers is not None:
            spoken += f"I counted {fillers} filler words. "
        spoken += "I saved the detailed HTML report."
        summary = "Content evaluation unavailable; metrics only."
    return {
        "answers": [],
        "categories": {},
        "overall_summary": summary,
        "spoken_feedback": spoken,
        "model": None,
    }


class ContentAnalyzer:
    """Ask a hosted chat model for structured feedback on transcript + metrics."""

    def __init__(self, model: str, language: str) -> None:
        """Use ``model`` (Hugging Face repo id) through the logged-in Inference API account."""
        self.model = model
        self.language = language if language in SYSTEM_PROMPT else "en"
        self._client = InferenceClient()

    def evaluate(
        self,
        session: InterviewSession,
        speech: dict[str, Any] | None,
        body: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Return the parsed JSON evaluation; falls back to metric-only feedback on any failure."""
        if not session.asked:
            return fallback_evaluation(session, speech)
        prompt = build_user_prompt(session, speech, body)
        logger.info("Content analysis: sending %d chars of transcript+metrics to %s", len(prompt), self.model)
        try:
            response = self._client.chat_completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT[self.language]},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2500,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content or ""
            result = json.loads(text)
        except Exception:
            logger.exception("Content analysis failed; using metric-only fallback")
            return fallback_evaluation(session, speech)
        if not isinstance(result, dict) or "spoken_feedback" not in result:
            logger.error("Content analysis returned unexpected structure: %.200s", text)
            return fallback_evaluation(session, speech)
        result.setdefault("answers", [])
        result.setdefault("overall_summary", "")
        kept, dropped = self._allowed_categories(result.get("categories"), speech, body)
        result["categories"] = kept
        if dropped:
            # The model talked about behaviour it had no data for; rebuild the spoken part from kept categories only.
            logger.warning("Dropping %s feedback: no metrics were available for it", ", ".join(dropped))
            result["spoken_feedback"] = compose_spoken_feedback(kept, self.language)
        result["model"] = getattr(response, "model", None) or self.model
        return result

    @staticmethod
    def _allowed_categories(
        categories: Any,
        speech: dict[str, Any] | None,
        body: dict[str, Any] | None,
    ) -> tuple[dict[str, dict[str, str]], list[str]]:
        """Keep only categories backed by data; return (kept, dropped-category-names)."""
        if not isinstance(categories, dict):
            return {}, []
        allowed = {"content"}
        if speech and "error" not in speech:
            allowed.add("speech")
        if body and body.get("available"):
            allowed.add("body_language")
        kept: dict[str, dict[str, str]] = {}
        dropped: list[str] = []
        for key in CATEGORIES:
            value = categories.get(key)
            if key in allowed and isinstance(value, dict) and value.get("strength") and value.get("tip"):
                kept[key] = {"strength": str(value["strength"]), "tip": str(value["tip"])}
            elif key not in allowed and value:
                dropped.append(key)
        return kept, dropped


def compose_spoken_feedback(categories: dict[str, dict[str, str]], language: str) -> str:
    """Deterministic spoken summary from category feedback (used when the model output could not be trusted)."""
    names = {
        "de": {"content": "Zum Inhalt", "speech": "Zur Sprache", "body_language": "Zur Körpersprache"},
        "en": {"content": "On content", "speech": "On speech", "body_language": "On body language"},
    }[language if language in SYSTEM_PROMPT else "en"]
    parts = ["Danke für das Gespräch." if language == "de" else "Thank you for the interview."]
    for key, value in categories.items():
        parts.append(f"{names[key]}: {value['strength']} {value['tip']}")
    parts.append(
        "Den ausführlichen HTML-Bericht habe ich gespeichert."
        if language == "de"
        else "I saved the detailed HTML report."
    )
    return " ".join(parts)
