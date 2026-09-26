"""Observable body-language metrics from the robot camera using MediaPipe.

Frames are analysed in memory at a low rate and reduced to counters immediately; no image is stored or
sent anywhere. Only eye contact share, smiling share, head motion, hand activity and posture are tracked.
"""

import math
import time
import logging
import threading
import urllib.request
from typing import Any
from pathlib import Path
from dataclasses import field, dataclass
from collections.abc import Callable

import cv2
import numpy as np
from numpy.typing import NDArray

from reachy_interview_coach.interview.session import SessionEvent, InterviewSession


logger = logging.getLogger(__name__)

MODEL_URLS = {
    "face_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
    ),
    # The "lite" pose model jitters wrists by several cm between identical frames; "full" is stable and still ~60 ms.
    "pose_landmarker_full.task": (
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/"
        "pose_landmarker_full.task"
    ),
}
MODEL_CACHE_DIR = Path.home() / ".cache" / "reachy_interview_coach" / "models"

ANALYSIS_FPS = 8.0
ANALYSIS_WIDTH = 640
EYE_CONTACT_MAX_HEAD_ANGLE_DEG = 20.0
EYE_CONTACT_MAX_IRIS_OFFSET = 0.15
SMILE_THRESHOLD = 0.35
HEAD_MOTION_FAST_DEG_S = 40.0
HAND_ACTIVE_SPEED = 0.25  # normalized image units per second
SHOULDER_TILT_NOTABLE_DEG = 8.0
NOTABLE_NO_EYE_CONTACT_S = 5.0
NOTABLE_HAND_ACTIVITY_S = 6.0

# FaceLandmarker indices (478-point topology with iris)
LEFT_EYE_OUTER, LEFT_EYE_INNER, LEFT_IRIS = 33, 133, 468
RIGHT_EYE_INNER, RIGHT_EYE_OUTER, RIGHT_IRIS = 362, 263, 473
# PoseLandmarker indices
NOSE, LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_WRIST, RIGHT_WRIST = 0, 11, 12, 15, 16


def ensure_models() -> dict[str, Path]:
    """Download the MediaPipe task files once into the user cache."""
    MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for filename, url in MODEL_URLS.items():
        target = MODEL_CACHE_DIR / filename
        if not target.exists():
            logger.info("Downloading %s", url)
            urllib.request.urlretrieve(url, target)
        paths[filename] = target
    return paths


@dataclass
class FrameObservation:
    """What one analysed frame tells us, already reduced to numbers."""

    at: float
    face_visible: bool
    head_yaw_deg: float | None = None
    head_pitch_deg: float | None = None
    iris_offset: float | None = None
    eye_contact: bool = False
    smiling: bool = False
    head_speed_deg_s: float | None = None
    hands_visible: bool = False
    hand_speed: float | None = None
    shoulder_tilt_deg: float | None = None
    torso_height: float | None = None  # nose-to-shoulder distance over shoulder width; drops when slouching


@dataclass
class NotableMoment:
    """A stretch of behaviour worth pointing out, with session-relative timestamps."""

    kind: str
    start: float
    end: float
    question_number: int | None

    def to_dict(self) -> dict[str, Any]:
        """Serializable view."""
        return {
            "kind": self.kind,
            "start": round(self.start, 1),
            "end": round(self.end, 1),
            "duration": round(self.end - self.start, 1),
            "question_number": self.question_number,
        }


@dataclass
class BodyLanguageStats:
    """Aggregated counters for one question or the whole interview."""

    frames: int = 0
    face_frames: int = 0
    eye_contact_frames: int = 0
    smile_frames: int = 0
    head_speed_sum: float = 0.0
    head_speed_frames: int = 0
    head_fast_frames: int = 0
    hands_visible_frames: int = 0
    hand_active_frames: int = 0
    shoulder_tilt_sum: float = 0.0
    shoulder_tilt_frames: int = 0
    shoulder_tilt_notable_frames: int = 0
    torso_heights: list[float] = field(default_factory=list)

    def add(self, obs: FrameObservation) -> None:
        """Fold one observation into the counters."""
        self.frames += 1
        if obs.face_visible:
            self.face_frames += 1
            self.eye_contact_frames += int(obs.eye_contact)
            self.smile_frames += int(obs.smiling)
        if obs.head_speed_deg_s is not None:
            self.head_speed_sum += obs.head_speed_deg_s
            self.head_speed_frames += 1
            self.head_fast_frames += int(obs.head_speed_deg_s > HEAD_MOTION_FAST_DEG_S)
        if obs.hands_visible:
            self.hands_visible_frames += 1
            if obs.hand_speed is not None and obs.hand_speed > HAND_ACTIVE_SPEED:
                self.hand_active_frames += 1
        if obs.shoulder_tilt_deg is not None:
            self.shoulder_tilt_sum += abs(obs.shoulder_tilt_deg)
            self.shoulder_tilt_frames += 1
            self.shoulder_tilt_notable_frames += int(abs(obs.shoulder_tilt_deg) > SHOULDER_TILT_NOTABLE_DEG)
        if obs.torso_height is not None:
            self.torso_heights.append(obs.torso_height)

    def to_dict(self) -> dict[str, Any]:
        """Ratios and means for the report; None when there was nothing to measure."""

        def ratio(part: int, whole: int) -> float | None:
            return round(part / whole, 2) if whole else None

        heights = self.torso_heights
        posture_drop = None
        if len(heights) >= 20:
            first, last = np.mean(heights[: len(heights) // 4]), np.mean(heights[-len(heights) // 4 :])
            posture_drop = round(float((first - last) / first), 2) if first > 0 else None
        return {
            "frames": self.frames,
            "face_visible_ratio": ratio(self.face_frames, self.frames),
            "eye_contact_ratio": ratio(self.eye_contact_frames, self.face_frames),
            "smile_ratio": ratio(self.smile_frames, self.face_frames),
            "head_speed_mean_deg_s": round(self.head_speed_sum / self.head_speed_frames, 1)
            if self.head_speed_frames
            else None,
            "head_fast_motion_ratio": ratio(self.head_fast_frames, self.head_speed_frames),
            "hands_visible_ratio": ratio(self.hands_visible_frames, self.frames),
            "hand_activity_ratio": ratio(self.hand_active_frames, self.hands_visible_frames),
            "shoulder_tilt_mean_deg": round(self.shoulder_tilt_sum / self.shoulder_tilt_frames, 1)
            if self.shoulder_tilt_frames
            else None,
            "shoulder_tilt_notable_ratio": ratio(self.shoulder_tilt_notable_frames, self.shoulder_tilt_frames),
            "posture_drop_ratio": posture_drop,
        }


def _wrist_displacement(previous: NDArray[np.float64], current: NDArray[np.float64]) -> float:
    """Mean wrist displacement between two frames, tolerant to the pose model swapping left/right labels."""
    direct = float(np.linalg.norm(current - previous, axis=1).mean())
    if len(current) < 2:
        return direct
    swapped = float(np.linalg.norm(current[::-1] - previous, axis=1).mean())
    return min(direct, swapped)


def _forward_axis_angles(matrix: NDArray[np.float64]) -> tuple[float, float]:
    """Yaw/pitch of the face's forward axis in degrees, independent of Euler conventions and head roll."""
    forward = matrix[:3, 2].astype(float)
    norm = np.linalg.norm(forward)
    if norm == 0:
        return 0.0, 0.0
    forward /= norm
    if forward[2] < 0:
        forward = -forward
    yaw = math.degrees(math.atan2(forward[0], forward[2]))
    pitch = math.degrees(math.atan2(forward[1], math.hypot(forward[0], forward[2])))
    return yaw, pitch


def _iris_offset(landmarks: Any) -> float | None:
    """Mean horizontal iris displacement from the eye centre (0 = centred, 0.5 = at a corner)."""
    if len(landmarks) <= RIGHT_IRIS:
        return None
    offsets = []
    for outer, inner, iris in (
        (LEFT_EYE_OUTER, LEFT_EYE_INNER, LEFT_IRIS),
        (RIGHT_EYE_INNER, RIGHT_EYE_OUTER, RIGHT_IRIS),
    ):
        left_x = min(landmarks[outer].x, landmarks[inner].x)
        right_x = max(landmarks[outer].x, landmarks[inner].x)
        width = right_x - left_x
        if width <= 1e-6:
            continue
        offsets.append(abs((landmarks[iris].x - left_x) / width - 0.5))
    return float(np.mean(offsets)) if offsets else None


def _smile_score(blendshapes: Any) -> float:
    scores = [c.score for c in blendshapes if c.category_name in ("mouthSmileLeft", "mouthSmileRight")]
    return float(np.mean(scores)) if scores else 0.0


class FrameAnalyzer:
    """Stateful per-frame MediaPipe analysis (keeps previous head pose and wrist positions for speeds)."""

    def __init__(self) -> None:
        """Load both landmarkers in VIDEO mode."""
        from mediapipe.tasks.python import BaseOptions, vision

        models = ensure_models()
        self._face = vision.FaceLandmarker.create_from_options(
            vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(models["face_landmarker.task"])),
                running_mode=vision.RunningMode.VIDEO,
                num_faces=1,
                output_face_blendshapes=True,
                output_facial_transformation_matrixes=True,
            )
        )
        self._pose = vision.PoseLandmarker.create_from_options(
            vision.PoseLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(models["pose_landmarker_full.task"])),
                running_mode=vision.RunningMode.VIDEO,
                num_poses=1,
            )
        )
        self._last_head: tuple[float, float, float] | None = None  # (at, yaw, pitch)
        self._last_wrists: tuple[float, NDArray[np.float64]] | None = None
        self._last_timestamp_ms = -1

    def close(self) -> None:
        """Release MediaPipe resources."""
        self._face.close()
        self._pose.close()

    def analyze(self, frame_bgr: NDArray[np.uint8], at: float) -> FrameObservation:
        """Reduce one BGR frame to a FrameObservation."""
        import mediapipe as mp

        height, width = frame_bgr.shape[:2]
        if width > ANALYSIS_WIDTH:
            frame_bgr = cv2.resize(frame_bgr, (ANALYSIS_WIDTH, int(height * ANALYSIS_WIDTH / width)))
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        timestamp_ms = max(int(at * 1000), self._last_timestamp_ms + 1)
        self._last_timestamp_ms = timestamp_ms

        obs = FrameObservation(at=at, face_visible=False)
        face_result = self._face.detect_for_video(image, timestamp_ms)
        if face_result.face_landmarks:
            obs.face_visible = True
            landmarks = face_result.face_landmarks[0]
            if face_result.facial_transformation_matrixes:
                yaw, pitch = _forward_axis_angles(np.asarray(face_result.facial_transformation_matrixes[0]))
                obs.head_yaw_deg, obs.head_pitch_deg = yaw, pitch
                if self._last_head is not None and at > self._last_head[0]:
                    delta = math.hypot(yaw - self._last_head[1], pitch - self._last_head[2])
                    obs.head_speed_deg_s = delta / (at - self._last_head[0])
                self._last_head = (at, yaw, pitch)
            obs.iris_offset = _iris_offset(landmarks)
            head_frontal = (
                obs.head_yaw_deg is not None
                and obs.head_pitch_deg is not None
                and abs(obs.head_yaw_deg) <= EYE_CONTACT_MAX_HEAD_ANGLE_DEG
                and abs(obs.head_pitch_deg) <= EYE_CONTACT_MAX_HEAD_ANGLE_DEG
            )
            iris_centred = obs.iris_offset is None or obs.iris_offset <= EYE_CONTACT_MAX_IRIS_OFFSET
            obs.eye_contact = bool(head_frontal and iris_centred)
            if face_result.face_blendshapes:
                obs.smiling = _smile_score(face_result.face_blendshapes[0]) >= SMILE_THRESHOLD
        else:
            self._last_head = None

        pose_result = self._pose.detect_for_video(image, timestamp_ms)
        if pose_result.pose_landmarks:
            pose = pose_result.pose_landmarks[0]
            left_shoulder, right_shoulder = pose[LEFT_SHOULDER], pose[RIGHT_SHOULDER]
            if left_shoulder.visibility > 0.5 and right_shoulder.visibility > 0.5:
                dx = right_shoulder.x - left_shoulder.x
                dy = right_shoulder.y - left_shoulder.y
                # Angle of the shoulder line to the horizontal, independent of which shoulder is left in the image.
                obs.shoulder_tilt_deg = math.degrees(math.atan2(dy, abs(dx) if abs(dx) > 1e-6 else 1e-6))
                shoulder_width = math.hypot(dx, dy)
                nose = pose[NOSE]
                if nose.visibility > 0.5 and shoulder_width > 1e-3:
                    shoulder_mid_y = (left_shoulder.y + right_shoulder.y) / 2
                    obs.torso_height = (shoulder_mid_y - nose.y) / shoulder_width
            wrists = [pose[i] for i in (LEFT_WRIST, RIGHT_WRIST) if pose[i].visibility > 0.5]
            if wrists:
                obs.hands_visible = True
                positions = np.array([[w.x, w.y] for w in wrists])
                if (
                    self._last_wrists is not None
                    and at > self._last_wrists[0]
                    and self._last_wrists[1].shape == positions.shape
                ):
                    obs.hand_speed = _wrist_displacement(self._last_wrists[1], positions) / (at - self._last_wrists[0])
                self._last_wrists = (at, positions)
            else:
                self._last_wrists = None
        return obs


class VideoMetricsCollector(threading.Thread):
    """Background thread: sample the camera during answers and aggregate body-language counters."""

    def __init__(self, session: InterviewSession, frame_source: Callable[[], NDArray[np.uint8] | None]) -> None:
        """Bind to the session; frames are pulled from ``frame_source`` (robot camera)."""
        super().__init__(name="interview-video", daemon=True)
        self._session = session
        self._frame_source = frame_source
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self.per_question: dict[int, BodyLanguageStats] = {}
        self.overall = BodyLanguageStats()
        self.notable: list[NotableMoment] = []
        self._no_eye_contact_since: float | None = None
        self._hand_activity_since: float | None = None
        self.frames_analysed = 0
        self.error: str | None = None
        self.ready = threading.Event()  # set once the models are loaded (or failed to load)
        session.subscribe(self._on_session_event)

    def _on_session_event(self, event: SessionEvent, payload: dict[str, Any]) -> None:
        if event == "finished":
            self.stop()

    def stop(self) -> None:
        """Ask the thread to exit."""
        self._stop_event.set()

    def _collecting(self) -> bool:
        session = self._session
        return session.analysis_enabled and session.phase == "interview" and session.current_question is not None

    def run(self) -> None:
        """Analyse frames at ANALYSIS_FPS while a question is being answered."""
        try:
            analyzer = FrameAnalyzer()
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            logger.exception("Video analysis unavailable")
            return
        finally:
            self.ready.set()
        period = 1.0 / ANALYSIS_FPS
        logger.info("Video metrics collector started (%.0f fps)", ANALYSIS_FPS)
        try:
            while not self._stop_event.is_set():
                tick = time.monotonic()
                if self._collecting():
                    frame = self._frame_source()
                    if frame is not None:
                        at = self._session.elapsed()
                        try:
                            obs = analyzer.analyze(frame, at)
                        except Exception:
                            logger.exception("Frame analysis failed")
                        else:
                            self._record(obs)
                time.sleep(max(0.0, period - (time.monotonic() - tick)))
        finally:
            analyzer.close()
            self._close_open_moments(self._session.elapsed())
            logger.info("Video metrics collector stopped after %d frames", self.frames_analysed)

    def _record(self, obs: FrameObservation) -> None:
        current = self._session.current_question
        question_number = current.number if current else None
        with self._lock:
            self.frames_analysed += 1
            self.overall.add(obs)
            if question_number is not None:
                self.per_question.setdefault(question_number, BodyLanguageStats()).add(obs)
            self._track_moment(
                "no_eye_contact", not obs.eye_contact, obs.at, NOTABLE_NO_EYE_CONTACT_S, question_number
            )
            hands_busy = obs.hands_visible and obs.hand_speed is not None and obs.hand_speed > HAND_ACTIVE_SPEED
            self._track_moment("hand_activity", hands_busy, obs.at, NOTABLE_HAND_ACTIVITY_S, question_number)

    def _track_moment(
        self, kind: str, active: bool, at: float, min_duration: float, question_number: int | None
    ) -> None:
        attr = "_no_eye_contact_since" if kind == "no_eye_contact" else "_hand_activity_since"
        since: float | None = getattr(self, attr)
        if active and since is None:
            setattr(self, attr, at)
        elif not active and since is not None:
            if at - since >= min_duration:
                self.notable.append(NotableMoment(kind=kind, start=since, end=at, question_number=question_number))
            setattr(self, attr, None)

    def _close_open_moments(self, at: float) -> None:
        with self._lock:
            current = self._session.current_question
            number = current.number if current else None
            self._track_moment("no_eye_contact", False, at, NOTABLE_NO_EYE_CONTACT_S, number)
            self._track_moment("hand_activity", False, at, NOTABLE_HAND_ACTIVITY_S, number)

    def report(self) -> dict[str, Any]:
        """Return aggregated body-language metrics for the report and the content LLM."""
        with self._lock:
            return {
                "available": self.error is None and self.frames_analysed > 0,
                "error": self.error,
                "frames_analysed": self.frames_analysed,
                "overall": self.overall.to_dict(),
                "per_question": {str(n): stats.to_dict() for n, stats in sorted(self.per_question.items())},
                "notable_moments": [m.to_dict() for m in self.notable],
            }
