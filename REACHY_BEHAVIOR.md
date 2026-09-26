# Expected Reachy behaviour — behavioural interview

Observable robot behaviour for the Behavioural Interview Coach app. This is the spec an
implementation is checked against: what Reachy does, when, and why. Internals (scoring, metrics,
transcription) live in the build plan; this file is only about what a person in the room sees and
hears.

**Design principle:** Reachy plays a *human interviewer*, not an assistant. It is attentive, mostly
still, and sparing with motion. Every movement is either attention (where it is looking) or
acknowledgement (a beat at a turn boundary). It never gestures while the candidate is mid-sentence,
never narrates what it is doing, and never gives feedback until the debrief — because a real
interviewer doesn't.

---

## 1. Startup

| | |
|---|---|
| **Trigger** | App started from the dashboard |
| **Robot** | Wake from sleep, rise to `INIT_POSE`, antennas neutral. One short settling beat, then still |
| **Speech** | Silent. No greeting until a session actually starts |
| **Gaze** | Centre, level |

The robot must look ready and awake but must not perform. If wake-up fails, the app surfaces the
error in the web UI rather than proceeding silently.

## 2. Idle — waiting for a job posting

| | |
|---|---|
| **Trigger** | App running, no session started |
| **Robot** | Breathing motion only: a slow ~0.2 Hz pitch oscillation of ~±2°. Nothing else |
| **Speech** | Silent |
| **Gaze** | Holds the candidate's face if one is detected, otherwise centre |

Breathing is what keeps the robot from reading as switched off. It must stay subtle enough that a
person stops noticing it within a few seconds.

## 3. Session opening

| | |
|---|---|
| **Trigger** | Candidate submits the job-posting URL |
| **Robot** | Brief acknowledging nod once the plan is built |
| **Speech** | States the company, role, and the shape of the session — for example: *"I'll be interviewing you for the Google Software Engineering Internship. Six behavioural questions, about forty minutes. Answer as you would in the real thing."* |
| **Gaze** | On the candidate's face |

Says the number of questions and the expected length, so the candidate can pace themselves. Does
**not** explain the rubric, list the attributes, or coach — that would contaminate the interview.

## 4. Asking a question

| | |
|---|---|
| **Robot** | Attentive/curious cue, then settles still before the last word lands |
| **Speech** | The question, once, at a measured pace. Repeated verbatim on request |
| **Gaze** | Locked on the candidate's face |
| **After** | Goes still and stays still. The silence is deliberate |

The robot must finish moving *before* it finishes speaking, so the candidate begins answering into
stillness rather than motion. The pause after a question is a real interview instrument — nothing
fills it.

## 5. While the candidate answers

| | |
|---|---|
| **Robot** | Face tracking only. Slow, low-amplitude gaze following. No emotion moves |
| **Speech** | Silent. Never interrupts, never interjects, no "mm-hm" |
| **Antennas** | Still, or one slow acknowledging dip at a natural sentence boundary — at most once per answer |

Two behaviours that are correct and worth protecting:

- **An occasional slow nod at a sentence boundary** reads as listening. More than about one per
  answer reads as a nodding toy.
- **If the answer passes ~150 seconds**, one small, unmistakable settling shift — the cue a real
  interviewer gives when an answer is running long. It does not speak and does not cut the candidate
  off.

If the candidate's face leaves the frame, the robot holds its last gaze and keeps listening. It does
not hunt for the face, and it does not comment on it.

## 6. Answer end

| | |
|---|---|
| **Trigger** | ~3 s of silence after at least 5 s of speech, or the 180 s cap |
| **Robot** | One clear acknowledging nod — the turn-boundary marker |
| **Speech** | Either the follow-up, or the next question. No evaluation, no "good answer" |
| **Gaze** | Stays on the candidate |

The nod is the only signal that the turn ended. It must be unambiguous, because the candidate needs
to know they were heard.

## 7. Follow-up

Reachy asks **at most one** follow-up per question, and only on a deterministic trigger:

| Situation | What Reachy asks |
|---|---|
| No outcome stated | *"What changed as a result?"* |
| Failure question, no lesson stated | *"What would you do differently now?"* |
| Answer under 45 s | *"Can you walk me through what you actually did, step by step?"* |

Delivered in the same flat interviewer register as the original question — a probe, not a correction.
Slight lean-in is appropriate; approval or disapproval is not.

**Deliberate non-behaviour:** when the candidate spends too long setting up context (over 30 s), Reachy
asks **nothing**. It is recorded silently for the scorecard. Interrupting would distort the very thing
being measured, and real interviewers rarely interrupt.

## 8. Between questions

| | |
|---|---|
| **Robot** | Return toward neutral, breathing resumes. One-beat pause |
| **Speech** | Straight into the next question. No filler, no progress commentary |

The candidate should feel a rhythm: question, silence, answer, nod, question. No "great, next up,
question three of six."

## 9. Scoring

| | |
|---|---|
| **Trigger** | Final question answered |
| **Robot** | Idle thinking posture — gaze slightly off-axis, as though reviewing notes |
| **Speech** | One line to set expectations: *"Give me a moment to go over your answers."* |
| **Duration** | Up to ~2 minutes on this hardware |

The off-axis gaze is doing real work: it signals *processing* rather than *frozen*, which matters
because this is the longest silence in the session. If scoring fails or is unavailable, Reachy goes
to the debrief anyway and says the content review was unavailable — it never pretends to have scored.

## 10. Debrief

| | |
|---|---|
| **Robot** | Re-engages, gaze back on the candidate. Positive cue before strengths, neutral before fixes |
| **Speech** | Three strengths, then three fixes. Specific and measured, e.g. *"You averaged a hundred and ninety words per minute — slow down and pause to structure."* |
| **Close** | Points the candidate at the scorecard page for the detail |

Tone shifts here, and only here: the interviewer becomes a coach. It does not read the whole scorecard
aloud — numbers belong on the page, not in speech. It does not soften a weak result into a good one.

## 11. Abort and teardown

| | |
|---|---|
| **Trigger** | Candidate aborts, or the app is stopped from the dashboard |
| **Robot** | Stop all motion, return safely to `INIT_POSE`, antennas neutral |
| **Speech** | Silent, or one short acknowledgement on a deliberate abort |

Teardown must be safe from any state, including mid-move and mid-speech. The daemon returns the robot
to its default position after the app exits; the app must not fight it.

---

## Motion envelope

Clamped centrally, never at call sites:

| Axis | Limit |
|---|---|
| Head pitch / roll | ±40° |
| Head yaw | ±180° |
| Body yaw | ±160° |
| Head − body yaw delta | 65° max |

- One control loop owns all motion output, at ~100 Hz.
- Gaze tracking is **slow and low-amplitude** — an interviewer's attention, not a security camera's.
- Emotion moves only ever fire at turn boundaries, never mid-answer.
- Emotion names are **enumerated from the library at startup**, not hardcoded. Only `happy` is
  confirmed to exist; anything missing falls back to a small hand-built nod or tilt.

## What Reachy deliberately does not do

- **No feedback during the interview.** No approval, no correction, no scores until the debrief.
- **No interrupting.** Not for long answers, not for rambling, not for over-long context.
- **No reaction to content.** It does not look impressed by a good answer or disappointed by a weak
  one — that would train the candidate to read the robot instead of answering the question.
- **No emotion inference.** It never claims to detect nervousness, confidence, or mood. It tracks a
  face and measures delivery; it does not read minds.
- **No gesturing.** Hands are out of frame and arms do not exist; nothing depends on body language it
  cannot see.
- **No idle chatter.** Silence between turns is intentional.

## Failure behaviour

| Failure | Behaviour |
|---|---|
| Camera unavailable | Continue audio-only. Gaze holds centre. Attention metric marked unavailable, not zero |
| Mic unavailable | Abort with a clear UI error. An interview without audio is not degradable |
| Transcription backlog | Continue asking questions; metrics catch up. Never stall the interview on it |
| Scoring model unavailable | Debrief on delivery metrics alone; state plainly that content review was unavailable |
| Wake-up or motor failure | Surface in the UI and refuse to start. Do not run an interview with a robot that cannot look at the candidate |
