"""Interview session state: consent, asked questions, user utterances and the dialogue transcript."""

import time
import logging
import threading
from typing import Any, Literal
from datetime import datetime
from dataclasses import field, asdict, dataclass
from collections.abc import Callable

from reachy_interview_coach.interview.settings import InterviewSettings
from reachy_interview_coach.interview.questions import ROLE_TITLE, InterviewQuestion


logger = logging.getLogger(__name__)

SessionPhase = Literal["greeting", "interview", "finished"]
SessionEvent = Literal[
    "consent",
    "question_asked",
    "user_speech_started",
    "user_speech_stopped",
    "assistant_speaking",
    "user_transcript",
    "finished",
]
SessionListener = Callable[[SessionEvent, dict[str, Any]], None]


@dataclass
class AskedQuestion:
    """A question the interviewer has asked, with its session-relative timestamp."""

    number: int
    question: InterviewQuestion
    asked_at: float


@dataclass
class UserUtterance:
    """One stretch of user speech as segmented by the realtime backend."""

    question_number: int | None
    started_at: float | None = None
    ended_at: float | None = None
    text: str | None = None

    @property
    def duration(self) -> float | None:
        """Speech duration in seconds when both boundaries are known."""
        if self.started_at is None or self.ended_at is None:
            return None
        return max(0.0, self.ended_at - self.started_at)


@dataclass
class TranscriptEntry:
    """One final transcript line from either side of the conversation."""

    role: str
    text: str
    at: float


@dataclass
class InterviewSession:
    """Mutable interview state shared between the LLM tool, audio/video observers and the report."""

    settings: InterviewSettings
    questions: list[InterviewQuestion]
    phase: SessionPhase = "greeting"
    consent: bool | None = None
    asked: list[AskedQuestion] = field(default_factory=list)
    utterances: list[UserUtterance] = field(default_factory=list)
    transcript: list[TranscriptEntry] = field(default_factory=list)
    started_wall: datetime = field(default_factory=datetime.now)
    finished_at: float | None = None
    _t0: float = field(default_factory=time.monotonic, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _listeners: list[SessionListener] = field(default_factory=list, repr=False)
    _assistant_speaking: bool = field(default=False, repr=False)

    def elapsed(self) -> float:
        """Seconds since the session was created."""
        return time.monotonic() - self._t0

    def subscribe(self, listener: SessionListener) -> None:
        """Register a callback for session events (listening behaviour, hardware, ...)."""
        self._listeners.append(listener)

    def _emit(self, event: SessionEvent, payload: dict[str, Any]) -> None:
        for listener in list(self._listeners):
            try:
                listener(event, payload)
            except Exception:
                logger.exception("Session listener failed on %s", event)

    @property
    def current_question(self) -> AskedQuestion | None:
        """The most recently asked question, if any."""
        return self.asked[-1] if self.asked else None

    @property
    def analysis_enabled(self) -> bool:
        """Whether behavioural data may be collected for this session."""
        return self.consent is True

    # Realtime backend observers

    def on_activity(self, reason: str) -> None:
        """Track user speech boundaries and assistant speaking from backend activity reasons."""
        now = self.elapsed()
        with self._lock:
            if reason == "user_speech_started":
                question_number = self.current_question.number if self.current_question else None
                self.utterances.append(UserUtterance(question_number=question_number, started_at=now))
                event: SessionEvent | None = "user_speech_started"
                payload: dict[str, Any] = {"at": now, "question_number": question_number}
            elif reason == "user_speech_stopped":
                utterance = self._open_utterance()
                if utterance is not None:
                    utterance.ended_at = now
                event = "user_speech_stopped"
                payload = {"at": now, "duration": utterance.duration if utterance else None}
            elif reason == "assistant_audio_delta" and not self._assistant_speaking:
                self._assistant_speaking = True
                event = "assistant_speaking"
                payload = {"at": now, "speaking": True}
            elif reason == "assistant_transcript_done" and self._assistant_speaking:
                self._assistant_speaking = False
                event = "assistant_speaking"
                payload = {"at": now, "speaking": False}
            else:
                event = None
                payload = {}
        if event is not None:
            self._emit(event, payload)

    def on_transcript(self, role: str, text: str, final: bool) -> None:
        """Store final transcripts and attach user text to the matching utterance."""
        if not final or not text.strip():
            return
        now = self.elapsed()
        with self._lock:
            self.transcript.append(TranscriptEntry(role=role, text=text.strip(), at=now))
            if role != "user":
                return
            utterance = self._utterance_awaiting_text()
            if utterance is None:
                question_number = self.current_question.number if self.current_question else None
                utterance = UserUtterance(question_number=question_number)
                self.utterances.append(utterance)
            utterance.text = text.strip()
            payload = {
                "question_number": utterance.question_number,
                "text": utterance.text,
                "duration": utterance.duration,
            }
        self._emit("user_transcript", payload)

    def _open_utterance(self) -> UserUtterance | None:
        for utterance in reversed(self.utterances):
            if utterance.started_at is not None and utterance.ended_at is None:
                return utterance
        return None

    def _utterance_awaiting_text(self) -> UserUtterance | None:
        # Transcriptions arrive in speech order, so the oldest untexted utterance is the match.
        for utterance in self.utterances:
            if utterance.text is None and utterance.started_at is not None:
                return utterance
        return None

    # Interview flow driven by the LLM tool

    def record_consent(self, given: bool) -> None:
        """Store the participant's decision about behavioural analysis."""
        with self._lock:
            self.consent = given
            self.phase = "interview"
        logger.info("Interview consent: %s", "given" if given else "declined")
        self._emit("consent", {"given": given})

    def next_question(self) -> AskedQuestion | None:
        """Advance to the next planned question; None when the plan is exhausted."""
        with self._lock:
            index = len(self.asked)
            if index >= len(self.questions):
                return None
            asked = AskedQuestion(number=index + 1, question=self.questions[index], asked_at=self.elapsed())
            self.asked.append(asked)
            self.phase = "interview"
        logger.info("Question %d/%d asked: %s", asked.number, len(self.questions), asked.question.text)
        self._emit(
            "question_asked",
            {"number": asked.number, "total": len(self.questions), "kind": asked.question.kind},
        )
        return asked

    def finish(self) -> None:
        """Close the interview; utterances after this point are ignored."""
        with self._lock:
            if self.phase == "finished":
                return
            self.phase = "finished"
            self.finished_at = self.elapsed()
        logger.info("Interview finished after %.0f s", self.finished_at or 0.0)
        self._emit("finished", {"at": self.finished_at})

    # Derived views

    def utterances_for(self, question_number: int) -> list[UserUtterance]:
        """User utterances that belong to one question (including follow-ups)."""
        return [u for u in self.utterances if u.question_number == question_number and u.text]

    def answer_text(self, question_number: int) -> str:
        """Return the joined realtime transcript of all utterances for one question."""
        return " ".join(u.text for u in self.utterances_for(question_number) if u.text)

    def answer_summaries(self) -> list[dict[str, Any]]:
        """Per-question word count and speaking time from the realtime transcript."""
        summaries = []
        for asked in self.asked:
            utterances = self.utterances_for(asked.number)
            durations = [u.duration for u in utterances if u.duration is not None]
            text = self.answer_text(asked.number)
            summaries.append(
                {
                    "number": asked.number,
                    "kind": asked.question.kind,
                    "question": asked.question.text,
                    "answer": text,
                    "word_count": len(text.split()),
                    "speaking_seconds": round(sum(durations), 1) if durations else None,
                    "utterances": len(utterances),
                }
            )
        return summaries

    def to_dict(self) -> dict[str, Any]:
        """Serializable snapshot (transcript and metrics only, never media)."""
        return {
            "role": ROLE_TITLE[self.settings.language],
            "language": self.settings.language,
            "started": self.started_wall.isoformat(timespec="seconds"),
            "finished_after_seconds": self.finished_at,
            "consent": self.consent,
            "phase": self.phase,
            "questions": [
                {
                    "number": asked.number,
                    "asked_at": round(asked.asked_at, 1),
                    **asdict(asked.question),
                }
                for asked in self.asked
            ],
            "utterances": [asdict(u) for u in self.utterances],
            "transcript": [asdict(entry) for entry in self.transcript],
            "answers": self.answer_summaries(),
        }
