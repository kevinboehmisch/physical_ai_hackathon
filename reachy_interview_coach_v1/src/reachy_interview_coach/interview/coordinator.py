"""Wire session, recorders and analyzers together and produce the final evaluation."""

import logging
from typing import Any
from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray

from reachy_interview_coach.moves import MovementManager
from reachy_interview_coach.interview.report import write_report
from reachy_interview_coach.interview.arduino import ArduinoDisplay, detect_port
from reachy_interview_coach.interview.session import InterviewSession
from reachy_interview_coach.interview.settings import InterviewSettings
from reachy_interview_coach.interview.listening import ListeningBehaviour
from reachy_interview_coach.interview.audio_metrics import SpeechReport, SpeechAnalyzer, AnswerAudioRecorder
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

    def start(self, frame_source: FrameSource | None, movement_manager: MovementManager | None) -> None:
        """Start background behaviour; ``frame_source`` is None when the camera is disabled."""
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

    def stop(self) -> None:
        """Stop background behaviour and drop any buffered audio."""
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
            self.speech_report = self.speech_analyzer.analyze_session(self.session, self.recorder)
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

    def evaluate(self) -> dict[str, Any]:
        """Run all analyses (blocking; call from a worker thread) and return a compact summary for the LLM.

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
