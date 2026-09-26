"""Active-listening behaviour: face tracking, occasional nods and small emotion moves while the user speaks."""

import math
import time
import random
import logging
import threading
from typing import Any

import numpy as np
from numpy.typing import NDArray

from reachy_mini.utils import create_head_pose
from reachy_mini.motion.move import Move
from reachy_mini.motion.recorded_move import RecordedMoves
from reachy_interview_coach.moves import MovementManager
from reachy_interview_coach.interview.session import SessionEvent, InterviewSession
from reachy_interview_coach.dance_emotion_moves import EmotionQueueMove


logger = logging.getLogger(__name__)

EMOTIONS_LIBRARY = "pollen-robotics/reachy-mini-emotions-library"

NOD_AMPLITUDE_DEG = 6.0
NOD_DURATION_S = 0.9
# Time between listening gestures while the user is talking (uniformly drawn in this window).
GESTURE_INTERVAL_S = (6.0, 12.0)
# Only every n-th gesture is a library emotion; the rest are plain nods so Reachy stays calm.
EMOTION_EVERY_N_GESTURES = 3
LISTENING_EMOTIONS = ("attentive1", "attentive2", "understanding1")
# After the user stops talking, acknowledge with a short nod this often (fraction of answers).
ACKNOWLEDGE_PROBABILITY = 0.4
ACKNOWLEDGE_EMOTION = "understanding2"
ACKNOWLEDGE_MIN_ANSWER_S = 4.0
POLL_INTERVAL_S = 0.25


class NodMove(Move):  # type: ignore[misc]
    """A single gentle nod (pitch down and back) around the neutral head pose.

    Daemon-side head tracking is active while the user talks, so the daemon adds the
    look-at offset on top of this pose; the nod therefore stays on the user.
    """

    def __init__(self, amplitude_deg: float = NOD_AMPLITUDE_DEG, duration: float = NOD_DURATION_S) -> None:
        """Create a nod of ``amplitude_deg`` peak pitch lasting ``duration`` seconds."""
        self._amplitude_deg = amplitude_deg
        self._duration = duration

    @property
    def duration(self) -> float:
        """Total duration of the nod in seconds."""
        return self._duration

    def evaluate(self, t: float) -> tuple[NDArray[np.float64] | None, NDArray[np.float64] | None, float | None]:
        """Return the head pose at time ``t``; antennas and body yaw keep the manager defaults."""
        phase = min(max(t / self._duration, 0.0), 1.0)
        pitch = self._amplitude_deg * math.sin(math.pi * phase)
        return create_head_pose(x=0, y=0, z=0, roll=0, pitch=pitch, yaw=0, degrees=True), None, 0.0


class ListeningBehaviour:
    """Drive Reachy's non-verbal listening while the candidate answers.

    - Enables daemon-side face tracking for the whole session.
    - While the user speaks (and Reachy is silent) queues a nod every 6–12 s, every third time a
      short "attentive" emotion instead.
    - When an answer ends, sometimes acknowledges it with ``understanding2``.
    """

    def __init__(
        self,
        session: InterviewSession,
        movement_manager: MovementManager,
        *,
        recorded_moves: RecordedMoves | None = None,
        rng: random.Random | None = None,
    ) -> None:
        """Attach to ``session`` events; ``recorded_moves`` is loaded lazily on first use when not given."""
        self.session = session
        self.movement_manager = movement_manager
        self._recorded_moves = recorded_moves
        self._rng = rng or random.Random()
        self._lock = threading.Lock()
        self._user_speaking = False
        self._assistant_speaking = False
        self._speech_started_at = 0.0
        self._next_gesture_at: float | None = None
        self._gesture_count = 0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        session.subscribe(self._on_session_event)

    def start(self) -> None:
        """Enable face tracking and start the gesture scheduler thread."""
        self.movement_manager.set_head_tracking(True)
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="listening-behaviour", daemon=True)
        self._thread.start()
        logger.info("Listening behaviour started (head tracking on)")

    def stop(self) -> None:
        """Stop the scheduler; head tracking is switched off by the movement manager on shutdown."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    # Session events

    def _on_session_event(self, event: SessionEvent, payload: dict[str, Any]) -> None:
        now = time.monotonic()
        if event == "user_speech_started":
            with self._lock:
                self._user_speaking = True
                self._speech_started_at = now
                self._next_gesture_at = now + self._rng.uniform(*GESTURE_INTERVAL_S)
        elif event == "user_speech_stopped":
            with self._lock:
                self._user_speaking = False
                self._next_gesture_at = None
                assistant_speaking = self._assistant_speaking
            duration = payload.get("duration") or 0.0
            if (
                not assistant_speaking
                and duration >= ACKNOWLEDGE_MIN_ANSWER_S
                and self._rng.random() < ACKNOWLEDGE_PROBABILITY
            ):
                self._queue_emotion(ACKNOWLEDGE_EMOTION)
        elif event == "assistant_speaking":
            with self._lock:
                self._assistant_speaking = bool(payload.get("speaking"))
        elif event == "finished":
            self.stop()

    # Gesture scheduling

    def _run(self) -> None:
        # Load the emotions library here, never inside session callbacks (those run in the realtime loop).
        if self._recorded_moves is None:
            try:
                self._recorded_moves = RecordedMoves(EMOTIONS_LIBRARY)
            except Exception:
                logger.exception("Emotions library unavailable; listening gestures will be nods only")
        while not self._stop_event.wait(POLL_INTERVAL_S):
            now = time.monotonic()
            with self._lock:
                due = (
                    self._user_speaking
                    and not self._assistant_speaking
                    and self._next_gesture_at is not None
                    and now >= self._next_gesture_at
                )
                if not due:
                    continue
                self._gesture_count += 1
                count = self._gesture_count
                self._next_gesture_at = now + self._rng.uniform(*GESTURE_INTERVAL_S)
            if count % EMOTION_EVERY_N_GESTURES == 0:
                self._queue_emotion(self._rng.choice(LISTENING_EMOTIONS))
            else:
                self._queue_nod()

    def _queue_nod(self) -> None:
        logger.debug("Listening gesture: nod")
        self.movement_manager.queue_move(NodMove())

    def _queue_emotion(self, name: str) -> None:
        if self._recorded_moves is None:
            self._queue_nod()
            return
        try:
            move = EmotionQueueMove(name, self._recorded_moves)
        except Exception:
            logger.exception("Could not load listening emotion %r", name)
            return
        logger.debug("Listening gesture: emotion %s", name)
        self.movement_manager.queue_move(move)
