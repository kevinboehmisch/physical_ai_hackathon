"""Speech metrics from the microphone: words per minute, filler words, long pauses, answer length.

Audio is kept in RAM per question, analysed once with faster-whisper at the end of the interview and then
discarded. Nothing is written to disk.
"""

import logging
import threading
from typing import Any
from collections import Counter
from dataclasses import field, asdict, dataclass

import numpy as np
from numpy.typing import NDArray

from reachy_interview_coach.interview.session import SessionEvent, InterviewSession


logger = logging.getLogger(__name__)

WHISPER_SAMPLE_RATE = 16_000
MAX_SECONDS_PER_QUESTION = 10 * 60
UTTERANCE_PADDING_S = 0.4
LONG_PAUSE_S = 3.0
PAUSE_EXCLUDED_FROM_TEMPO_S = 1.0

FILLER_WORDS: dict[str, frozenset[str]] = {
    "de": frozenset(
        {"äh", "ähm", "ähh", "ähmm", "hm", "hmm", "mhm", "also", "halt", "quasi", "sozusagen", "irgendwie"}
    ),
    "en": frozenset({"um", "uh", "umm", "uhh", "hmm", "like", "basically", "actually", "literally"}),
}
FILLER_PHRASES: dict[str, tuple[tuple[str, ...], ...]] = {
    "de": (("weißt", "du"), ("sag", "ich", "mal"), ("ich", "mein")),
    "en": (("you", "know"), ("kind", "of"), ("sort", "of"), ("i", "mean")),
}
# Whisper tends to drop disfluencies; seeding the decoder with them keeps "äh"/"um" in the transcript.
WHISPER_INITIAL_PROMPT: dict[str, str] = {
    "de": "Ähm, also, äh, ich denke, halt, quasi, sozusagen.",
    "en": "Um, uh, like, you know, I mean, basically.",
}
_TOKEN_STRIP = ".,;:!?…\"'“”„()[]-–"


@dataclass
class QuestionAudioBuffer:
    """Mono 16 kHz microphone audio collected while one question was being answered."""

    question_number: int
    started_at: float
    chunks: list[NDArray[np.float32]] = field(default_factory=list)
    sample_count: int = 0

    def audio(self) -> NDArray[np.float32]:
        """Concatenate the recorded chunks."""
        if not self.chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self.chunks)


class AnswerAudioRecorder:
    """Tee for the microphone stream; records per question while analysis is enabled."""

    def __init__(self, session: InterviewSession) -> None:
        """Subscribe to session events so recording follows the interview flow."""
        self._session = session
        self._lock = threading.Lock()
        self._buffers: dict[int, QuestionAudioBuffer] = {}
        self._current: QuestionAudioBuffer | None = None
        self._sample_rate_warned = False
        session.subscribe(self._on_session_event)

    def _on_session_event(self, event: SessionEvent, payload: dict[str, Any]) -> None:
        if event == "question_asked":
            if not self._session.analysis_enabled:
                return
            number = int(payload["number"])
            with self._lock:
                self._current = QuestionAudioBuffer(question_number=number, started_at=self._session.elapsed())
                self._buffers[number] = self._current
        elif event == "finished":
            with self._lock:
                self._current = None

    def push(self, frame: NDArray[np.float32], sample_rate: int) -> None:
        """Append one microphone frame; cheap enough to run inside the audio loop."""
        current = self._current
        if current is None:
            return
        if sample_rate != WHISPER_SAMPLE_RATE:
            if not self._sample_rate_warned:
                logger.warning(
                    "Microphone sample rate %d Hz != %d Hz; speech metrics disabled", sample_rate, WHISPER_SAMPLE_RATE
                )
                self._sample_rate_warned = True
            return
        mono = frame[:, 0] if frame.ndim == 2 else frame
        with self._lock:
            if current.sample_count >= MAX_SECONDS_PER_QUESTION * WHISPER_SAMPLE_RATE:
                return
            current.chunks.append(np.ascontiguousarray(mono, dtype=np.float32))
            current.sample_count += mono.shape[0]

    def buffer_for(self, question_number: int) -> QuestionAudioBuffer | None:
        """Return the recorded audio for one question, if any."""
        with self._lock:
            return self._buffers.get(question_number)

    def recorded_seconds(self) -> float:
        """Total recorded audio across questions."""
        with self._lock:
            return sum(b.sample_count for b in self._buffers.values()) / WHISPER_SAMPLE_RATE

    def discard(self) -> None:
        """Drop all audio from memory."""
        with self._lock:
            self._buffers.clear()
            self._current = None


@dataclass
class WordTiming:
    """One transcribed word with session-relative timestamps."""

    word: str
    start: float
    end: float


@dataclass
class LongPause:
    """A silence longer than LONG_PAUSE_S inside an answer."""

    question_number: int
    start: float
    end: float

    @property
    def duration(self) -> float:
        """Pause length in seconds."""
        return self.end - self.start


@dataclass
class AnswerSpeechMetrics:
    """Speech metrics for one question."""

    question_number: int
    transcript: str
    word_count: int
    speaking_seconds: float
    words_per_minute: float | None
    filler_count: int
    filler_words: dict[str, int]
    long_pauses: list[LongPause]
    utterance_count: int

    def to_dict(self) -> dict[str, Any]:
        """Serializable view for the report."""
        data = asdict(self)
        data["long_pauses"] = [
            {"start": round(p.start, 1), "end": round(p.end, 1), "duration": round(p.duration, 1)}
            for p in self.long_pauses
        ]
        data["speaking_seconds"] = round(self.speaking_seconds, 1)
        data["words_per_minute"] = round(self.words_per_minute) if self.words_per_minute is not None else None
        return data


@dataclass
class SpeechReport:
    """Speech metrics across the whole interview."""

    answers: list[AnswerSpeechMetrics]
    words_per_minute: float | None
    filler_per_100_words: float | None
    total_words: int
    total_speaking_seconds: float
    long_pause_count: int

    def to_dict(self) -> dict[str, Any]:
        """Serializable view for the report and the content LLM."""
        return {
            "answers": [a.to_dict() for a in self.answers],
            "words_per_minute": round(self.words_per_minute) if self.words_per_minute is not None else None,
            "filler_per_100_words": round(self.filler_per_100_words, 1)
            if self.filler_per_100_words is not None
            else None,
            "total_words": self.total_words,
            "total_speaking_seconds": round(self.total_speaking_seconds, 1),
            "long_pause_count": self.long_pause_count,
        }


def _normalize_token(word: str) -> str:
    return word.strip().strip(_TOKEN_STRIP).lower()


def count_fillers(words: list[str], language: str) -> Counter[str]:
    """Count single-word fillers and multi-word filler phrases in a token list."""
    tokens = [_normalize_token(w) for w in words]
    counts: Counter[str] = Counter()
    for token in tokens:
        if token in FILLER_WORDS[language]:
            counts[token] += 1
    for phrase in FILLER_PHRASES[language]:
        size = len(phrase)
        for index in range(len(tokens) - size + 1):
            if tuple(tokens[index : index + size]) == phrase:
                counts[" ".join(phrase)] += 1
    return counts


def tempo_and_pauses(words: list[WordTiming], question_number: int) -> tuple[float, list[LongPause]]:
    """Speaking time without long silences, plus every pause above LONG_PAUSE_S."""
    if not words:
        return 0.0, []
    speaking = words[-1].end - words[0].start
    pauses: list[LongPause] = []
    for previous, current in zip(words, words[1:]):
        gap = current.start - previous.end
        if gap > PAUSE_EXCLUDED_FROM_TEMPO_S:
            speaking -= gap
        if gap > LONG_PAUSE_S:
            pauses.append(LongPause(question_number=question_number, start=previous.end, end=current.start))
    return max(speaking, 0.0), pauses


class SpeechAnalyzer:
    """Run faster-whisper on recorded answers and derive speech metrics."""

    def __init__(self, model_size: str, language: str) -> None:
        """Defer model loading until the first analysis."""
        self._model_size = model_size
        self._language = language
        self._model: Any = None

    def preload(self) -> None:
        """Load the Whisper model now (call from a background thread at startup)."""
        self._load_model()

    def _load_model(self) -> Any:
        if self._model is None:
            from faster_whisper import WhisperModel

            logger.info("Loading faster-whisper model %r (cpu, int8)", self._model_size)
            self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
        return self._model

    def transcribe_words(self, audio: NDArray[np.float32], time_offset: float) -> list[WordTiming]:
        """Transcribe one mono 16 kHz clip and return words with session-relative times."""
        if audio.shape[0] < WHISPER_SAMPLE_RATE // 4:
            return []
        segments, _ = self._load_model().transcribe(
            audio,
            language=self._language,
            word_timestamps=True,
            beam_size=3,
            condition_on_previous_text=False,
            initial_prompt=WHISPER_INITIAL_PROMPT[self._language],
        )
        words: list[WordTiming] = []
        for segment in segments:
            for word in segment.words or []:
                text = word.word.strip()
                if text:
                    words.append(WordTiming(word=text, start=time_offset + word.start, end=time_offset + word.end))
        return words

    def analyze_question(self, session: InterviewSession, buffer: QuestionAudioBuffer) -> AnswerSpeechMetrics:
        """Transcribe the user's utterances for one question and compute its metrics."""
        audio = buffer.audio()
        words: list[WordTiming] = []
        utterances = [
            u
            for u in session.utterances
            if u.question_number == buffer.question_number and u.started_at is not None and u.ended_at is not None
        ]
        for utterance in utterances:
            assert utterance.started_at is not None and utterance.ended_at is not None
            start_s = max(0.0, utterance.started_at - buffer.started_at - UTTERANCE_PADDING_S)
            end_s = utterance.ended_at - buffer.started_at + UTTERANCE_PADDING_S
            clip = audio[int(start_s * WHISPER_SAMPLE_RATE) : int(end_s * WHISPER_SAMPLE_RATE)]
            words.extend(self.transcribe_words(clip, buffer.started_at + start_s))

        speaking_seconds, pauses = tempo_and_pauses(words, buffer.question_number)
        fillers = count_fillers([w.word for w in words], self._language)
        wpm = len(words) / speaking_seconds * 60.0 if speaking_seconds >= 3.0 and words else None
        return AnswerSpeechMetrics(
            question_number=buffer.question_number,
            transcript=" ".join(w.word for w in words),
            word_count=len(words),
            speaking_seconds=speaking_seconds,
            words_per_minute=wpm,
            filler_count=sum(fillers.values()),
            filler_words=dict(fillers),
            long_pauses=pauses,
            utterance_count=len(utterances),
        )

    def analyze_session(
        self,
        session: InterviewSession,
        recorder: AnswerAudioRecorder,
        precomputed: dict[int, AnswerSpeechMetrics] | None = None,
    ) -> SpeechReport:
        """Compute speech metrics for every asked question and aggregate them.

        ``precomputed`` holds answers already transcribed during the interview (keyed by question number).
        """
        answers: list[AnswerSpeechMetrics] = []
        for asked in session.asked:
            if precomputed and asked.number in precomputed:
                answers.append(precomputed[asked.number])
                continue
            buffer = recorder.buffer_for(asked.number)
            if buffer is None or buffer.sample_count == 0:
                continue
            try:
                answers.append(self.analyze_question(session, buffer))
            except Exception:
                logger.exception("Speech analysis failed for question %d", asked.number)
        total_words = sum(a.word_count for a in answers)
        total_speaking = sum(a.speaking_seconds for a in answers)
        total_fillers = sum(a.filler_count for a in answers)
        return SpeechReport(
            answers=answers,
            words_per_minute=total_words / total_speaking * 60.0 if total_speaking >= 3.0 else None,
            filler_per_100_words=total_fillers / total_words * 100.0 if total_words else None,
            total_words=total_words,
            total_speaking_seconds=total_speaking,
            long_pause_count=sum(len(a.long_pauses) for a in answers),
        )
