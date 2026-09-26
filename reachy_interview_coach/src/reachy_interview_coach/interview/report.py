"""Render the detailed HTML report (metrics + transcript + LLM feedback); no media is ever stored."""

import logging
from typing import Any
from pathlib import Path
from datetime import datetime

from jinja2 import BaseLoader, Environment, select_autoescape

from reachy_interview_coach.interview.session import InterviewSession
from reachy_interview_coach.interview.questions import ROLE_TITLE


logger = logging.getLogger(__name__)

LABELS = {
    "de": {
        "title": "Interview-Training – Bericht",
        "role": "Zielrolle",
        "date": "Datum",
        "duration": "Dauer",
        "model": "Inhaltsanalyse",
        "summary": "Gesamteindruck",
        "categories": "Feedback nach Kategorie",
        "content": "Inhalt",
        "speech": "Sprache",
        "body_language": "Körpersprache",
        "strength": "Stärke",
        "tip": "Tipp",
        "answers": "Fragen und Antworten",
        "transcript": "Transkript",
        "no_answer": "(keine Antwort erfasst)",
        "star": "STAR-Struktur",
        "concreteness": "Konkretheit",
        "technical": "Fachliche Richtigkeit",
        "wpm": "Wörter/Min",
        "fillers": "Füllwörter",
        "pauses": "Pausen > 3 s",
        "speaking": "Sprechzeit",
        "eye_contact": "Blickkontakt",
        "smile": "Lächeln",
        "hand_activity": "Handbewegung",
        "metrics": "Kennzahlen gesamt",
        "speech_metrics": "Sprache",
        "body_metrics": "Körpersprache",
        "notable": "Auffällige Momente",
        "no_video": "Keine Videoanalyse verfügbar.",
        "no_speech": "Keine Sprachanalyse verfügbar.",
        "privacy": (
            "Datenschutz: Audio und Video wurden nur im Arbeitsspeicher analysiert und nicht gespeichert. "
            "An das Sprachmodell gingen ausschließlich Transkript und Kennzahlen. Bewertet wurde nur beobachtbares "
            "Verhalten, keine Emotionen oder Persönlichkeit."
        ),
        "kinds": {"intro": "Vorstellung", "behavioral": "Verhaltensfrage", "technical": "Fachfrage"},
        "star_parts": {"situation": "Situation", "task": "Aufgabe", "action": "Handlung", "result": "Ergebnis"},
        "frames": "analysierte Bilder",
        "posture": "Haltung abgesunken",
        "head_motion": "schnelle Kopfbewegung",
        "shoulders": "Schulterneigung",
        "long_pause_count": "lange Pausen",
        "filler_rate": "Füllwörter / 100 Wörter",
        "total_words": "Wörter gesamt",
        "question_time": "Frage",
        "second": "s",
    },
    "en": {
        "title": "Interview Training – Report",
        "role": "Target role",
        "date": "Date",
        "duration": "Duration",
        "model": "Content analysis",
        "summary": "Overall impression",
        "categories": "Feedback by category",
        "content": "Content",
        "speech": "Speech",
        "body_language": "Body language",
        "strength": "Strength",
        "tip": "Tip",
        "answers": "Questions and answers",
        "transcript": "Transcript",
        "no_answer": "(no answer captured)",
        "star": "STAR structure",
        "concreteness": "Concreteness",
        "technical": "Technical correctness",
        "wpm": "words/min",
        "fillers": "filler words",
        "pauses": "pauses > 3 s",
        "speaking": "speaking time",
        "eye_contact": "eye contact",
        "smile": "smiling",
        "hand_activity": "hand movement",
        "metrics": "Overall metrics",
        "speech_metrics": "Speech",
        "body_metrics": "Body language",
        "notable": "Notable moments",
        "no_video": "No video analysis available.",
        "no_speech": "No speech analysis available.",
        "privacy": (
            "Privacy: audio and video were analysed in memory only and never stored. Only the transcript and "
            "metrics were sent to the language model. Only observable behaviour was evaluated, never emotions or "
            "personality."
        ),
        "kinds": {"intro": "Introduction", "behavioral": "Behavioral", "technical": "Technical"},
        "star_parts": {"situation": "Situation", "task": "Task", "action": "Action", "result": "Result"},
        "frames": "frames analysed",
        "posture": "posture dropped",
        "head_motion": "fast head motion",
        "shoulders": "shoulder tilt",
        "long_pause_count": "long pauses",
        "filler_rate": "fillers / 100 words",
        "total_words": "total words",
        "question_time": "question",
        "second": "s",
    },
}

TEMPLATE = """<!DOCTYPE html>
<html lang="{{ lang }}">
<head>
<meta charset="utf-8">
<title>{{ L.title }} – {{ date }}</title>
<style>
  body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #1f2933; line-height: 1.5; }
  h1 { margin-bottom: .2rem; } h2 { margin-top: 2.2rem; border-bottom: 2px solid #e4e7eb; padding-bottom: .3rem; }
  .meta { color: #52606d; font-size: .95rem; } .meta span { margin-right: 1.5rem; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem; }
  .card { background: #f5f7fa; border-radius: 10px; padding: 1rem 1.2rem; }
  .card h3 { margin: 0 0 .6rem; font-size: 1.05rem; }
  .strength::before { content: "✔ "; color: #2f855a; } .tip::before { content: "➜ "; color: #c05621; }
  .question { border: 1px solid #e4e7eb; border-radius: 10px; padding: 1rem 1.2rem; margin: 1rem 0; }
  .question h3 { margin: 0; } .kind { font-size: .8rem; text-transform: uppercase; letter-spacing: .05em; color: #52606d; }
  .transcript { background: #fffdf5; border-left: 4px solid #f6ad55; padding: .6rem .9rem; margin: .8rem 0; white-space: pre-wrap; }
  .badges span { display: inline-block; padding: .1rem .55rem; border-radius: 999px; font-size: .8rem; margin-right: .3rem; background: #e4e7eb; }
  .badges .ok { background: #c6f6d5; } .badges .miss { background: #fed7d7; }
  .badges .stars { color: #d69e2e; letter-spacing: .1em; background: none; padding: 0; }
  table { border-collapse: collapse; width: 100%; margin: .6rem 0; } td, th { text-align: left; padding: .35rem .6rem; border-bottom: 1px solid #e4e7eb; }
  th { font-weight: 600; color: #52606d; } .small { font-size: .9rem; color: #52606d; }
  .privacy { margin-top: 3rem; padding: 1rem; background: #ebf8ff; border-radius: 10px; font-size: .9rem; }
</style>
</head>
<body>
<h1>{{ L.title }}</h1>
<p class="meta">
  <span><strong>{{ L.role }}:</strong> {{ role }}</span>
  <span><strong>{{ L.date }}:</strong> {{ date }}</span>
  <span><strong>{{ L.duration }}:</strong> {{ duration }}</span>
  {% if evaluation.model %}<span><strong>{{ L.model }}:</strong> {{ evaluation.model }}</span>{% endif %}
</p>

<h2>{{ L.summary }}</h2>
<p>{{ evaluation.overall_summary }}</p>
{% if evaluation.spoken_feedback %}<p class="small">„{{ evaluation.spoken_feedback }}“</p>{% endif %}

{% if evaluation.categories %}
<h2>{{ L.categories }}</h2>
<div class="cards">
{% for key in ("content", "speech", "body_language") %}{% set cat = evaluation.categories.get(key) %}{% if cat %}
  <div class="card"><h3>{{ L[key] }}</h3>
    <p class="strength"><strong>{{ L.strength }}:</strong> {{ cat.strength }}</p>
    <p class="tip"><strong>{{ L.tip }}:</strong> {{ cat.tip }}</p></div>
{% endif %}{% endfor %}
</div>
{% endif %}

<h2>{{ L.answers }}</h2>
{% for q in questions %}
<div class="question">
  <div class="kind">{{ L.question_time }} {{ q.number }} · {{ L.kinds.get(q.kind, q.kind) }}</div>
  <h3>{{ q.text }}</h3>
  <div class="transcript">{{ q.transcript or L.no_answer }}</div>
  {% if q.eval %}
    {% if q.eval.summary %}<p class="small">{{ q.eval.summary }}</p>{% endif %}
    <p class="badges">
      {% if q.eval.star %}<strong>{{ L.star }}:</strong>
        {% for part, label in L.star_parts.items() %}<span class="{{ 'ok' if q.eval.star.get(part) else 'miss' }}">{{ label }}</span>{% endfor %}
      {% endif %}
      {% if q.eval.concreteness %}<strong>{{ L.concreteness }}:</strong> <span class="stars">{{ "★" * q.eval.concreteness }}{{ "☆" * (5 - q.eval.concreteness) }}</span>{% endif %}
      {% if q.eval.technical_correctness %}<strong>{{ L.technical }}:</strong> <span class="stars">{{ "★" * q.eval.technical_correctness }}{{ "☆" * (5 - q.eval.technical_correctness) }}</span>{% endif %}
    </p>
    {% if q.eval.strength %}<p class="strength">{{ q.eval.strength }}</p>{% endif %}
    {% if q.eval.tip %}<p class="tip">{{ q.eval.tip }}</p>{% endif %}
  {% endif %}
  {% if q.speech or q.body %}
  <p class="small">
    {% if q.speech %}
      {{ L.speaking }}: {{ q.speech.speaking_seconds }} {{ L.second }} ·
      {% if q.speech.words_per_minute %}{{ q.speech.words_per_minute }} {{ L.wpm }} · {% endif %}
      {{ L.fillers }}: {{ q.speech.filler_count }}{% if q.speech.filler_words %} ({% for w, n in q.speech.filler_words.items() %}{{ w }}×{{ n }}{{ ", " if not loop.last }}{% endfor %}){% endif %} ·
      {{ L.pauses }}: {{ q.speech.long_pauses | length }}
    {% endif %}
    {% if q.body %}
      {% if q.speech %}<br>{% endif %}
      {{ L.eye_contact }}: {{ pct(q.body.eye_contact_ratio) }} · {{ L.smile }}: {{ pct(q.body.smile_ratio) }} · {{ L.hand_activity }}: {{ pct(q.body.hand_activity_ratio) }} · {{ L.posture }}: {{ pct(q.body.posture_drop_ratio) }}
    {% endif %}
  </p>
  {% endif %}
</div>
{% endfor %}

<h2>{{ L.metrics }}</h2>
<div class="cards">
  <div class="card"><h3>{{ L.speech_metrics }}</h3>
  {% if speech %}
    <table>
      <tr><th>{{ L.wpm }}</th><td>{{ speech.words_per_minute if speech.words_per_minute is not none else "–" }}</td></tr>
      <tr><th>{{ L.filler_rate }}</th><td>{{ speech.filler_per_100_words if speech.filler_per_100_words is not none else "–" }}</td></tr>
      <tr><th>{{ L.total_words }}</th><td>{{ speech.total_words }}</td></tr>
      <tr><th>{{ L.speaking }}</th><td>{{ speech.total_speaking_seconds }} {{ L.second }}</td></tr>
      <tr><th>{{ L.long_pause_count }}</th><td>{{ speech.long_pause_count }}</td></tr>
    </table>
  {% else %}<p class="small">{{ L.no_speech }}</p>{% endif %}
  </div>
  <div class="card"><h3>{{ L.body_metrics }}</h3>
  {% if body and body.available %}
    <table>
      <tr><th>{{ L.eye_contact }}</th><td>{{ pct(body.overall.eye_contact_ratio) }}</td></tr>
      <tr><th>{{ L.smile }}</th><td>{{ pct(body.overall.smile_ratio) }}</td></tr>
      <tr><th>{{ L.hand_activity }}</th><td>{{ pct(body.overall.hand_activity_ratio) }}</td></tr>
      <tr><th>{{ L.head_motion }}</th><td>{{ pct(body.overall.head_fast_motion_ratio) }}</td></tr>
      <tr><th>{{ L.shoulders }}</th><td>{{ body.overall.shoulder_tilt_mean_deg if body.overall.shoulder_tilt_mean_deg is not none else "–" }}°</td></tr>
      <tr><th>{{ L.posture }}</th><td>{{ pct(body.overall.posture_drop_ratio) }}</td></tr>
      <tr><th>{{ L.frames }}</th><td>{{ body.frames_analysed }}</td></tr>
    </table>
  {% else %}<p class="small">{{ L.no_video }}{% if body and body.error %} ({{ body.error }}){% endif %}</p>{% endif %}
  </div>
</div>

{% if body and body.notable_moments %}
<h2>{{ L.notable }}</h2>
<table>
  <tr><th>t</th><th>{{ L.question_time }}</th><th></th></tr>
  {% for m in body.notable_moments %}
  <tr><td>{{ "%d:%02d" | format(m.at // 60, m.at % 60) }}</td><td>{{ m.question_number or "–" }}</td><td>{{ m.description }}</td></tr>
  {% endfor %}
</table>
{% endif %}

<p class="privacy">{{ L.privacy }}</p>
</body>
</html>
"""


def _pct(value: float | None) -> str:
    return "–" if value is None else f"{value * 100:.0f} %"


def render_report(
    session: InterviewSession,
    evaluation: dict[str, Any],
    speech: dict[str, Any] | None,
    body: dict[str, Any] | None,
    now: datetime | None = None,
) -> str:
    """Render the HTML for the whole interview."""
    lang = session.settings.language if session.settings.language in LABELS else "en"
    labels = LABELS[lang]
    now = now or datetime.now()
    speech_by_q = {a["question_number"]: a for a in (speech or {}).get("answers", [])}
    body_by_q = (body or {}).get("per_question", {}) if body and body.get("available") else {}
    eval_by_q = {a.get("number"): a for a in evaluation.get("answers", []) if isinstance(a, dict)}
    questions = [
        {
            "number": asked.number,
            "kind": asked.question.kind,
            "text": asked.question.text,
            "transcript": session.answer_text(asked.number),
            "eval": eval_by_q.get(asked.number),
            "speech": speech_by_q.get(asked.number),
            "body": body_by_q.get(str(asked.number)),
        }
        for asked in session.asked
    ]
    total = session.finished_at or session.elapsed()
    env = Environment(loader=BaseLoader(), autoescape=select_autoescape(default=True))
    env.globals["pct"] = _pct
    return env.from_string(TEMPLATE).render(
        lang=lang,
        L=labels,
        role=ROLE_TITLE[lang],
        date=now.strftime("%d.%m.%Y %H:%M" if lang == "de" else "%Y-%m-%d %H:%M"),
        duration=f"{int(total // 60)} min {int(total % 60)} s",
        evaluation=evaluation,
        questions=questions,
        speech=speech if speech and "error" not in speech else None,
        body=body,
    )


def write_report(
    reports_dir: Path,
    session: InterviewSession,
    evaluation: dict[str, Any],
    speech: dict[str, Any] | None,
    body: dict[str, Any] | None,
) -> Path:
    """Render and save the report as ``reports_dir/interview_<YYYYMMDD_HHMM>.html``; return the path."""
    now = datetime.now()
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"interview_{now.strftime('%Y%m%d_%H%M')}.html"
    path.write_text(render_report(session, evaluation, speech, body, now), encoding="utf-8")
    logger.info("Report written to %s", path)
    return path
