"""LocalStream variant that feeds backend activity and transcripts into the interview session."""

import asyncio
import logging
from typing import Any

from reachy_mini import ReachyMini
from reachy_interview_coach.console import LocalStream
from reachy_interview_coach.interview.session import InterviewSession
from reachy_interview_coach.conversation_handler import ConversationHandler
from reachy_interview_coach.interview.audio_metrics import AnswerAudioRecorder


logger = logging.getLogger(__name__)


class InterviewStream(LocalStream):
    """LocalStream whose observers update the InterviewSession and whose mic loop feeds the answer recorder."""

    def __init__(
        self,
        handler: ConversationHandler,
        robot: ReachyMini,
        *,
        session: InterviewSession,
        recorder: AnswerAudioRecorder,
        **kwargs: Any,
    ):
        """Store session and recorder before the base class installs the handler observers."""
        self._session = session
        self._recorder = recorder
        super().__init__(handler, robot, **kwargs)

    async def record_loop(self) -> None:
        """Forward mic frames to the realtime handler and tee them into the in-memory answer recorder."""
        input_sample_rate = self._robot.media.get_input_audio_samplerate()
        logger.debug("Audio recording started at %d Hz (interview tee active)", input_sample_rate)

        while not self._stop_event.is_set():
            audio_frame = self._robot.media.get_audio_sample()
            if audio_frame is not None and not self._mic_muted:
                self._recorder.push(audio_frame, input_sample_rate)
                await self.handler.receive((input_sample_rate, audio_frame))
                self._emit_level("user", audio_frame)
            await asyncio.sleep(0)

    def announce(self, text: str) -> None:
        """Inject ``text`` into the conversation from any thread and let the model voice a response.

        Used for the finished evaluation; unlike the /rpc ``say`` route it does not barge in on speech.
        """
        loop = self._asyncio_loop
        if loop is None or not loop.is_running():
            raise RuntimeError("announce: realtime loop is not running")
        if not self.handler._is_connected():
            raise RuntimeError("announce: no active realtime session")
        future = asyncio.run_coroutine_threadsafe(self.handler.say(text), loop)
        future.result(timeout=10.0)
        logger.info("Evaluation handed to the conversation (%d chars)", len(text))

    def _attach_observers_to_handler(self) -> None:
        """Chain session tracking in front of the JSON-RPC observers installed by LocalStream."""
        session = self._session
        rpc_activity = self._dispatch_activity
        rpc_transcript = self._dispatch_transcript

        def on_activity(reason: str) -> None:
            session.on_activity(reason)
            rpc_activity(reason)

        def on_transcript(role: str, text: str, final: bool) -> None:
            session.on_transcript(role, text, final)
            rpc_transcript(role, text, final)

        self.handler.set_activity_observer(on_activity)
        self.handler.set_transcript_observer(on_transcript)
