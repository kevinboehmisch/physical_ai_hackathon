"""Wire session, recorders and analyzers together and produce the final evaluation."""

import logging
import threading
from typing import Any
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

import numpy as np
from numpy.typing import NDArray

from reachy_interview_coach.moves import MovementManager
from reachy_interview_coach.interview.report import write_report
from reachy_interview_coach.interview.arduino import ArduinoDisplay, detect_port
from reachy_interview_coach.interview.session import InterviewSession
from reachy_interview_coach.interview.settings import InterviewSettings
from reachy_interview_coach.interview.listening import ListeningBehaviour
from reachy_interview_coach.interview.audio_metrics import (
    SpeechReport,
    SpeechAnalyzer,
    AnswerAudioRecorder,
    AnswerSpeechMetrics,
)
from reachy_interview_coach.interview.video_metrics import VideoMetricsCollector
from reachy_interview_coach.interview.content_analysis import ContentAnalyzer


logger = logging.getLogger(__name__)

FrameSource = Callable[[], NDArray[np.uint8] | None]


class InterviewCoordinator:
    """Own the analysis components for one interview and run the evaluation at the end."""

    def __init__(self, session: InterviewSession, settings: InterviewSettings) -> None:
        """Create the recorder and analyzers; nothing heavy is loaded yet."""
        self.session = session
        self.settings = settings
        self.recorder = AnswerAudioRecorder(session)
        self.speech_analyzer = SpeechAnalyzer(settings.whisper_model, settings.language)
        self.content_analyzer = ContentAnalyzer(settings.content_model, settings.language)
        self.speech_report: SpeechReport | None = None
        self.video: VideoMetricsCollector | None = None
        self.listening: ListeningBehaviour | None = None
        self.arduino: ArduinoDisplay | None = None
        # Called (from the worker thread) with the finished summary so the robot can present it unprompted.
        self.on_result: Callable[[dict[str, Any]], None] | None = None
        # Single worker: preloads Whisper, transcribes each answer while the next question is running,
        # finally runs the evaluation. Everything stays off the realtime loop.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="interview-eval")
        self._speech_cache: dict[int, AnswerSpeechMetrics] = {}
        self._evaluation: Future[dict[str, Any]] | None = None
        self._evaluation_lock = threading.Lock()
        self._result_delivered = False
        session.subscribe(self._on_session_event)

    def start(self, frame_source: FrameSource | None, movement_manager: MovementManager | None) -> None:
        """Start background behaviour; ``frame_source`` is None when the camera is disabled."""
        self._executor.submit(self._preload_models)
        if frame_source is not None:
            self.video = VideoMetricsCollector(self.session, frame_source)
            self.video.start()
        else:
            logger.info("Camera disabled; body-language metrics will be skipped")
        if movement_manager is not None:
            self.listening = ListeningBehaviour(self.session, movement_manager)
            self.listening.start()
        try:
            self.arduino = ArduinoDisplay(self.session, detect_port(self.settings.arduino_port))
            self.arduino.start()
        except Exception:
            logger.exception("Arduino display setup failed; continuing without board")
            self.arduino = None

    def _preload_models(self) -> None:
        try:
            self.speech_analyzer.preload()
        except Exception:
            logger.exception("Whisper preload failed; it will be retried at evaluation time")

    def _on_session_event(self, event: str, payload: dict[str, Any]) -> None:
        # When question N is asked, the answer to N-1 is complete: transcribe it now instead of at the end.
        if event == "question_asked" and payload.get("number", 1) > 1:
            self._executor.submit(self._transcribe_question, payload["number"] - 1)

    def _transcribe_question(self, number: int) -> None:
        if not self.session.analysis_enabled or number in self._speech_cache:
            return
        buffer = self.recorder.buffer_for(number)
        if buffer is None or buffer.sample_count == 0:
            return
        try:
            self._speech_cache[number] = self.speech_analyzer.analyze_question(self.session, buffer)
            logger.info("Answer %d transcribed early (%d words)", number, self._speech_cache[number].word_count)
        except Exception:
            logger.exception("Early speech analysis failed for question %d; will retry at evaluation", number)

    def begin_evaluation(self) -> None:
        """Start the evaluation in the background (idempotent); called as soon as the last answer is in."""
        with self._evaluation_lock:
            if self._evaluation is None:
                self.session.finish()
                logger.info("Evaluation started in the background")
                self._evaluation = self._executor.submit(self._evaluate)
                self._evaluation.add_done_callback(self._deliver_result)

    def _deliver_result(self, future: Future[dict[str, Any]]) -> None:
        if future.cancelled():
            return
        error = future.exception()
        if error is not None:
            logger.error("Evaluation failed: %s", error, exc_info=error)
            return
        if self.on_result is None:
            return
        try:
            self.on_result(future.result())
            self._result_delivered = True
        except Exception:
            logger.exception("Delivering the evaluation to the conversation failed")

    def evaluation_result(self) -> dict[str, Any] | None:
        """Return the finished evaluation without blocking, or None while it is still running."""
        with self._evaluation_lock:
            future = self._evaluation
        if future is None or not future.done() or future.cancelled() or future.exception() is not None:
            return None
        result = dict(future.result())
        result["already_presented"] = self._result_delivered
        return result

    def evaluate(self) -> dict[str, Any]:
        """Return the evaluation, starting it if needed (blocking; for tests and scripts)."""
        self.begin_evaluation()
        assert self._evaluation is not None
        return self._evaluation.result()

    def stop(self) -> None:
        """Stop background behaviour and drop any buffered audio."""
        self._executor.shutdown(wait=False, cancel_futures=True)
        if self.arduino is not None:
            self.arduino.stop()
        if self.listening is not None:
            self.listening.stop()
        if self.video is not None:
            self.video.stop()
            self.video.join(timeout=5.0)
        self.recorder.discard()

    def _speech_metrics(self) -> dict[str, Any] | None:
        try:
            self.speech_report = self.speech_analyzer.analyze_session(self.session, self.recorder, self._speech_cache)
            return self.speech_report.to_dict()
        except Exception:
            logger.exception("Speech analysis failed")
            return {"error": "speech analysis failed"}
        finally:
            self.recorder.discard()

    def _body_metrics(self) -> dict[str, Any] | None:
        if self.video is None:
            return None
        self.video.stop()
        self.video.join(timeout=5.0)
        return self.video.report()

    def _evaluate(self) -> dict[str, Any]:
        """Run all analyses and return a compact summary for the LLM.

        Without consent no audio/video metrics are computed; the answers are still evaluated on content.
        """
        session = self.session
        speech: dict[str, Any] | None = None
        body: dict[str, Any] | None = None
        if session.analysis_enabled:
            logger.info("Evaluating interview: %.0f s of answer audio recorded", self.recorder.recorded_seconds())
            speech = self._speech_metrics()
            body = self._body_metrics()
        else:
            self.recorder.discard()

        evaluation = self.content_analyzer.evaluate(session, speech, body)

        report_path: str | None = None
        try:
            report_path = str(write_report(self.settings.reports_dir, session, evaluation, speech, body))
        except Exception:
            logger.exception("Writing the HTML report failed")

        summary: dict[str, Any] = {
            "status": "interview_finished",
            "analysis_enabled": session.analysis_enabled,
            "questions_asked": len(session.asked),
            "spoken_feedback": evaluation.get("spoken_feedback"),
            "categories": evaluation.get("categories"),
            "overall_summary": evaluation.get("overall_summary"),
            "report_path": report_path,
        }
        if speech and "error" not in speech:
            summary["speech_metrics"] = {k: v for k, v in speech.items() if k != "answers"}
        if body and body.get("available"):
            summary["body_language_metrics"] = body.get("overall")
        return summary


def result_message(result: dict[str, Any]) -> str:
    """Build the conversation message that hands the finished evaluation to the realtime model."""
    feedback = result.get("spoken_feedback") or result.get("overall_summary") or ""
    report_path = result.get("report_path")
    report_note = (
        f" Finally mention that the detailed HTML report was saved as {report_path}."
        if report_path
        else " Mention that no HTML report could be written."
    )
    return (
        "[System message, do not read aloud] The interview evaluation is finished. Present this feedback to the "
        "candidate now, spoken, in your own words, at most 8 sentences, without raw numbers:\n"
        f"{feedback}\n"
        f"{report_note} Then ask whether they have questions about the feedback."
    )
