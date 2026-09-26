# Reachy Mini — Behavioural Interview Coach: implementation specification

**Audience:** an implementing model or engineer starting cold. Everything needed is in this file.
Facts marked **VERIFIED** were checked on the target machine — trust them, do not re-derive.

---

## 1. Mission

Build one Reachy Mini Python app that:

1. Accepts a job-posting URL.
2. Recognises the company and extracts a structured `JobSpec` from the posting.
3. Builds a **tailored** behavioural interview plan — 6 questions selected and weighted from a static
   bank according to what the posting emphasises.
4. Conducts that interview aloud: Reachy asks, listens through its mic array, tracks the candidate's
   face, and reacts with prebuilt emotion moves.
5. Produces a scorecard rating answer **content** and **delivery** (pacing, disfluency, attention),
   then speaks a short debrief.

**Scope is behavioural only.** The technical/LeetCode round is a later iteration (see §18).

Development target posting: Google SWE Intern, MS, Summer 2027 —
`https://www.google.com/about/careers/applications/jobs/results/94172495052972742-software-engineering-intern-ms-summer-2027`

---

## 2. Verified environment — do not re-derive

### Hardware (when the robot is plugged in)
| Device | Node | Notes |
|---|---|---|
| Motor controller | `/dev/ttyACM0` | CH340 (`1a86:55d3`). Perms `0666` via the `.deb`'s udev rule — **no `dialout` re-login needed** |
| Camera | `/dev/video2` | Reachy Mini Camera (`38fb:1002`). **NOT** `/dev/video0` or `video1` — those are the laptop's HP webcam |
| Mic array | `alsa_input...Pollen_Robotics_Reachy_Mini_Audio...` | 2ch **@ 16 kHz** — Whisper's native rate, no resampling needed |
| Speaker | `alsa_output...Pollen_Robotics_Reachy_Mini_Audio...` | 5W |

Also present: `alsa_input...Reachy_Mini_Camera...` — a separate mic on the camera. Prefer the
`Reachy_Mini_Audio` source (the array).

### Machine
- Intel **i5-10310U**, 4 cores / 8 threads @1.7 GHz. **No NVIDIA GPU.** ~8 GB RAM free, 292 GB disk free.
- Debian **forky/sid**, x86_64.
- **No LLM API keys.** Everything runs locally.

### Toolchain already done
- **`uv` 0.12.19** installed at `~/.local/bin/uv` (add `$HOME/.local/bin` to `PATH`).
- Build deps **VERIFIED present**: `libcairo2-dev`, `pkg-config`, `libgirepository1.0-dev`,
  `build-essential`. `pkg-config --modversion cairo` → `1.18.4`.
- CPython **3.12.14** available to uv.
- Target venv: **`/home/joe/reachy/.venv`** — deliberately *outside* the shared repo, because
  teammates work on Windows and the repo has no `.gitignore`.
- Create it with an **absolute path**: `uv venv --python 3.12 /home/joe/reachy/.venv`. A relative
  path did not persist in this environment.

### Repo
`/home/joe/reachy/physical_ai_hackathon` — git, branch **`nabil`**, remote
`kevinboehmisch/physical_ai_hackathon`. **Shared hackathon repo.** Commit to `nabil`; do not push or
touch other branches without asking.

Preserve, do not rewrite:
| File | What it is |
|---|---|
| `README.md` | German-language **Windows/PowerShell** setup for `reachy-mini[mujoco]` + simulator. Teammates depend on it. *Append* a Linux/hardware section |
| `mini_test.py` | Working daemon connection smoke test |
| `test_sim.py` | Working sim connection test |
| `REACHY_BEHAVIOR.md` | Robot behaviour spec — **acceptance criteria for all motion and speech** |

---

## 3. Hard constraints and gotchas

**3.1 Python must be 3.12.** `reachy-mini` pins `PyGObject>=3.42.2,<=3.46.0` on Linux. PyGObject 3.46
is from Oct 2023 and predates Python 3.14; on 3.14 it dies with
`ImportError: cannot import name 'get_loader' from 'pkgutil'` (removed in 3.14). Debian's system
`python3-gi` is 3.57.1 — *too new* for the pin, so `--system-site-packages` does not help. The pin is
unchanged on `main`, so installing from git is not an escape. **Use 3.12.**

**3.2 The Python API is snake_case.** `AGENTS.md` documents a JS SDK in camelCase; do not copy it.
Confirmed working Python from the repo's own `mini_test.py`:

```python
from reachy_mini import ReachyMini

# Real hardware, camera + audio needed — do NOT pass media_backend
with ReachyMini() as mini:
    mini.wake_up()
    mini.goto_target(antennas=[0.8, -0.8], duration=1.0)   # RADIANS
    print(mini.get_present_antenna_joint_positions())
    mini.goto_sleep()

# Local daemon, no media (the teammates' sim path)
with ReachyMini(host='localhost', connection_mode='localhost_only',
                media_backend='no_media') as robot: ...

# No-hardware logic development
with ReachyMini(use_sim=True) as mini: ...
```

- **Antennas are radians**, not degrees.
- `ReachyMini('localhost')` **does not work** — the first positional arg is the robot *name*, not host.
- **Omit `media_backend='no_media'`** for this app — it needs camera and mic.

**3.3 Only one process may bind port 8000.** The `.deb` Reachy Mini Control desktop app and
`reachy-mini-daemon` both use it. Stop the desktop app before starting the daemon, or connection
fails confusingly.

**3.4 If PyGObject will not compile, do not burn time on it.** The installed `.deb` ships a working
daemon with its own bundled environment, exposing a REST API on `localhost:8000`
(install/start/stop apps, plus a WebRTC path). Fall back to driving robot I/O over that API while the
app's Python keeps the JD pipeline, STT, metrics and scoring. **Timebox the compile at 15 minutes.**

**3.5 No API keys anywhere.**
| Thing | Key? |
|---|---|
| `reachy-mini-app-assistant create` (default template) | No — local generator |
| `pollen-robotics/reachy-mini-emotions-library` | No — **VERIFIED public dataset**, 172 files, not gated. Motion data, not a model |
| Ollama + qwen2.5:3b | No — local |
| faster-whisper `base.en` | No — anonymous HF download |
| Piper voice | No — file download |

Do **not** depend on the published `reachy_mini_conversation_app` — it requires a cloud LLM key. Read
its `moves.py` for the pose-fusion pattern only.

**3.6 Use the DEFAULT app template**, not `--template conversation`. The conversation template's value
is a streaming cloud-LLM pipeline, which this design explicitly does not want (scoring is batch and
deferred, and there is no key). Write `speech.py` directly against the documented SDK audio API —
`start_recording()`, `get_audio_sample()`, `push_audio_sample()`, `play_sound()` — using the official
`sound_record` / `sound_play` / `sound_doa` examples as reference.

---

## 4. Architecture principle — deterministic core, LLM as a deferred layer

Everything essential is deterministic. The LLM judges **only** answer content, and only after the
interview ends.

| Layer | LLM? | Latency |
|---|---|---|
| JD parsing → tailoring | No — keyword extraction | instant |
| Question selection | No — static bank, weighted | instant |
| Delivery metrics | No — numpy + word timestamps | real-time |
| Scorecard rollup + verdict | No — stated rules | instant |
| Answer content quality | **Yes** — one short call per answer | 15–25 s, deferred |

**The app must work fully if Ollama never becomes available** — the scorecard renders with delivery
metrics and marks content "not scored". This also matches real interview practice: reactions are
immediate, judgement comes at debrief.

### Stack
| Layer | Choice |
|---|---|
| Python | 3.12 via uv |
| SDK | `reachy-mini[opencv]` |
| Motion | `RecordedMoves` emotions library + `create_head_pose` fusion |
| STT | `faster-whisper base.en` int8, `word_timestamps=True` |
| TTS | **Piper** (`piper-tts` ships an `abi3` manylinux wheel — installs clean on 3.12) → robot speaker |
| LLM | Ollama **`qwen2.5:3b-instruct-q4_K_M`** (~2 GB) |
| Vision | OpenCV **Haar cascade** on `/dev/video2` (bundled with opencv-python, no download). Not mediapipe |
| Audio metrics | plain **numpy RMS**. No librosa |
| UI | FastAPI + `static/` via `custom_app_url` |

---

## 5. What is tested

Google's four attributes: **RRK/RRKE** (role-related knowledge), **GCA** (general cognitive ability),
**Leadership** (specifically *emergent* — stepping up without the title), and **Googleyness**
(culture *add*), which is the primary focus of a behavioural round.

The four are too coarse to score against. The real scoring axes are Googleyness's five sub-dimensions:

| Sub-dimension | Probes |
|---|---|
| `ambiguity` | acting decisively without complete information |
| `bias_to_action` | a doer, not only a thinker |
| `collaborative` | making the team smarter over individual brilliance |
| `moonshot` | aiming past what seems realistic |
| `humility` | admitting error, learning from failure |

Plus a cross-cutting facet — **taking the courageous or interesting path**: evidence of calculated
risk, not a sequence of optimal decisions.

### Answer framework: SPSIL default, STAR selectable
The primary source (IGotAnOffer) *rejects* STAR — candidates cannot separate Task from Action and
routinely omit lessons learned — and substitutes **SPSIL**: Situation, Problem, Solution, Impact,
**Lessons**. Lessons is exactly what a failure question probes and exactly what STAR drops. Default
SPSIL, expose STAR labels in the UI, score components either way.

**One hard timing number: Situation ≤ 30 s.** Over-long context-setting is the most commonly named
candidate mistake. It is measurable and goes on the scorecard.

---

## 6. Question bank — `playbooks/google.py`

Twelve questions, tagged. `plan_builder` selects 6.

| id | Question | Attribute | Sub-dim |
|---|---|---|---|
| `tell_me_about_yourself` | "Tell me about yourself" | RRK | — (always) |
| `why_google` | "Why Google?" | Googleyness | — (always) |
| `recent_project` | "Tell me about a recent or interesting project you worked on" | RRK | — (always) |
| `team_conflict` | "Tell me about a time you had to resolve a conflict in a team" | Googleyness | `collaborative` |
| `favourite_product` | "What is your favourite Google product, and how would you improve it?" | Googleyness | `moonshot` |
| `last_failure` | "Tell me about the last time you failed, and what happened" | Googleyness | `humility` |
| `tradeoffs_ambiguity` | "Tell me about a time you had to handle trade-offs and ambiguity" | GCA | `ambiguity` |
| `informal_leadership` | "Tell me about a time you demonstrated leadership even though you weren't the formal manager" | Leadership | — |
| `end_to_end_owner` | "Tell me about a time you were the end-to-end owner of a project" | Leadership | `bias_to_action` |
| `something_from_nothing` | "Tell me about a time you created something from nothing" | Googleyness | `moonshot` |
| `harder_path` | "Was there a moment when you chose the harder path?" | Googleyness | courageous-path |
| `sre_inclination` | "This role could land in Software Engineering or Site Reliability. Tell me about a time you kept something running under pressure" | RRK | — (conditional) |

**Selection rule:** the three `always` openers, then fill the remaining 3 slots by descending
sub-dimension weight from the JD map, never repeating a sub-dimension. `sre_inclination` is eligible
only when `role_variants ⊇ {SWE, SRE}`.

---

## 7. How the JD tailors the interview

Deterministic, no LLM — debuggable and repeatable.

**Step 1 — Fetch.** **VERIFIED:** the Google careers page is *server-rendered*; plain `requests`/`curl`
returns HTTP 200 with qualifications and responsibilities present in the raw HTML. No browser
automation needed. Strip `<script>`/`<style>`, strip tags, unescape entities, collapse whitespace,
dedupe consecutive lines.

**Step 2 — Company detect.** URL host → playbook dict. `google.com` ⇒ Google playbook. This dict *is*
the feature; do not build a classifier.

**Step 3 — `JobSpec`** by keyword match. The posting states all of this explicitly:

```python
@dataclass
class JobSpec:
    company: str; role: str; level: str       # "intern"
    degree: str | None                         # "MS"
    languages: list[str]; languages_min: int   # [C, C++, Java, JavaScript, Python], 2
    dsa_explicit: bool                         # True
    domains: list[str]                         # AI/ML, Infrastructure, web, Unix/Linux, mobile,
                                               # distributed & parallel systems, ML, IR, NLP,
                                               # networking, large systems, security
    role_variants: list[str]                   # ["SWE", "SRE"]
    duration_weeks: int | None                 # 12
    soft_signals: list[str]                    # versatile, enthusiastic, collaborate, ...
```

**Step 4 — `JobSpec` → `InterviewPlan`** through a fixed weight table:

| JD phrase | Effect |
|---|---|
| "engineers to be **versatile and enthusiastic in addressing new problems**" | `ambiguity` **+2**, `bias_to_action` **+2** |
| "**collaborate** on multitudes of smaller projects" | `collaborative` **+2** |
| "advance the state of the art", "improve the lives of billions" | `moonshot` **+2** |
| "SWE **or** SRE … recruitment team will determine where you fit" | enables `sre_inclination` |
| domains list | becomes the `recent_project` follow-up probe set |
| "two or more general purpose programming languages" | candidate picks 2 at session start; recorded on scorecard |
| Master's degree | scorecard note: competing against PhDs and FTEs at team matching |
| "Experience with data structures or algorithms" | record `dsa_explicit`; no behavioural effect (used by iteration 2) |

Tailoring is **selection and weighting over a static bank** — never generated questions.

> Note: this example posting is **US-only** (~30 US cities, no Germany). Fine for rubric development,
> but a Germany filter would exclude it.

---

## 8. Delivery metrics — the nonverbal layer

**Measure delivery; never infer emotion.** Two things are deliberately **NOT** built:

- **Gesture analysis.** The camera sits at desk height pointed at the face; hands are out of frame.
  Any gesture score would be fabricated.
- **Emotion / "tone" classification.** Unreliable, and it would make the scorecard pseudoscience.

```python
BANDS = {
    "wpm":              (130, 160),
    "filler_per_100":   (0, 3),      # um, uh, like, you know, kind of, sort of, basically, actually
    "ttfw_s":           (1.0, 4.0),  # ~0 => scripted
    "duration_s":       (90, 120),
    "situation_s":      (0, 30),     # the one hard number
    "max_pause_s":      (0, 4.0),
    "face_centred_pct": (70, 100),
}
```

Derivation — all from one `faster-whisper` pass plus numpy:
- `wpm` = words / duration
- `filler_per_100` = filler hits / words × 100
- `ttfw_s` = first word start − TTS-end timestamp
- `max_pause_s` = largest gap between consecutive word end/start
- `situation_s` = timestamp of the first action-marker (`so I`, `I decided`, `my approach`,
  `what I did`, `I started`, `my task`). **Approximate — label it as such on the scorecard**
- `energy_var` = variance of per-frame RMS. Report as a **monotone proxy**, never as "tone"
- `face_centred_pct` = Haar detections whose box centre falls in the middle third / total frames

### Four red-flag deductions
| Red flag | Heuristic | Confidence |
|---|---|---|
| **Too polished** | `filler_per_100 < 0.5` **and** low inter-sentence pacing variance **and** `ttfw_s < 0.5` ⇒ recitation | good — absence of disfluency is real signal |
| **Avoiding the failure story** | on `last_failure`: no Lessons component **and** none of `mistake, wrong, should have, learned, in hindsight` | good |
| **Overclaiming** | "I":"we" ratio extreme toward "I" on a team story | **weak — render as a hint, never a verdict** |
| **Playing it safe** | hedging density (`it depends, maybe, probably, I guess`) with no committed stance | medium |

---

## 9. Robot behaviour

**`REACHY_BEHAVIOR.md` in this repo is the acceptance criteria.** Read it before writing `motion.py`
or `session.py`. Its organising principle: Reachy plays a *human interviewer*, not an assistant —
attentive, mostly still, sparing with motion. Load-bearing rules:

- Emotion moves fire **only at turn boundaries**, never mid-answer.
- The attentive cue on a question **must finish before the question's last word**, so the candidate
  answers into stillness rather than motion.
- At most **one** slow nod per answer. More reads as a nodding toy.
- **No feedback during the interview** — no approval, no correction, no scores until the debrief.
- **No interrupting**, ever. Not for long answers, not for rambling.
- **No reaction to content** — looking impressed or disappointed trains the candidate to read the
  robot instead of answering the question.
- Gaze tracking is slow and low-amplitude. If the face leaves frame, hold the last gaze; do not hunt.

### Motion envelope — clamp centrally in `motion.py`, never at call sites
| Axis | Limit |
|---|---|
| Head pitch / roll | ±40° |
| Head yaw | ±180° |
| Body yaw | ±160° |
| Head − body yaw delta | 65° max |

### One control loop owns all motion
Exactly one thread calls `set_target()` at ~100 Hz; every other thread only mutates shared target
vars. Pose = primary emotion move + secondary gaze offset + breathing.

```python
def control_loop(self, mini):
    while not self.stop_event.is_set():
        t = time.monotonic()                      # monotonic, never wall clock
        breathing = 2.0 * np.sin(2 * np.pi * 0.2 * t)
        pose = create_head_pose(
            yaw=self._clamp_yaw(self.target_yaw),
            pitch=self._clamp_pitch(self.target_pitch + breathing),
            degrees=True,
        )
        mini.set_target(head=pose, antennas=self.antennas)
        time.sleep(0.01)
```

Discrete reactions: `mini.play_move(moves.get(name), initial_goto_duration=1.0)` where
`moves = RecordedMoves("pollen-robotics/reachy-mini-emotions-library")`.

**Enumerate the emotions library at startup and log the available names.** Only `happy` is confirmed
to exist. Map this table to real names at runtime, falling back to a small hand-built nod/tilt when a
name is missing:

| Moment | Intent |
|---|---|
| Session opening | acknowledging nod |
| Question asked | attentive / curious |
| Mid-answer | at most one slow dip at a sentence boundary |
| Answer past 150 s | one small settling shift — never speaks |
| Answer ends | unambiguous acknowledging nod (the only signal the turn closed) |
| Scoring | idle thinking, gaze slightly off-axis (signals *processing*, not *frozen*) |
| Debrief: strength | positive |
| Debrief: fix | neutral / thoughtful |

---

## 10. File layout

Added under the repo root; nothing existing moves.

```
physical_ai_hackathon/
├── README.md                 # keep; APPEND a Linux/real-hardware section
├── mini_test.py, test_sim.py # keep as-is; mini_test.py is the 0:15 smoke test
├── REACHY_BEHAVIOR.md        # behaviour acceptance criteria
├── reachy_doc.md             # this file
├── pyproject.toml            # [project.entry-points."reachy_mini_apps"]
│                             #   interview_coach = "interview_coach.main:InterviewCoachApp"
├── plan.md                   # AGENTS.md convention: write before coding
└── interview_coach/
    ├── main.py               # InterviewCoachApp(ReachyMiniApp); custom_app_url = "http://0.0.0.0:8042"
    ├── jd.py                 # fetch_jd(url) -> str ; parse_jd(text, host) -> JobSpec
    ├── playbooks/google.py   # ATTRIBUTES, SUB_DIMS, QUESTIONS, WEIGHT_TABLE, FOLLOWUPS
    ├── plan_builder.py       # build_plan(JobSpec) -> InterviewPlan
    ├── session.py            # state machine
    ├── speech.py             # say(text) via Piper -> play_sound ; listen() -> (wav, transcript)
    ├── delivery.py           # compute(wav, transcript, t_tts_end) -> DeliveryMetrics
    ├── attention.py          # AttentionTracker thread on /dev/video2
    ├── motion.py             # the ONE control loop; react(name); set_gaze(yaw, pitch)
    ├── scoring.py            # score_content(answer) -> ContentVerdict (Ollama, deferred)
    ├── scorecard.py          # build(records) -> Scorecard ; render_html(Scorecard)
    └── static/{index.html,main.js}
```

Scaffold with (**no `--publish`** — shared repo):
```bash
cd /home/joe/reachy/physical_ai_hackathon
reachy-mini-app-assistant create interview_coach .
```
Never hand-roll the app folder — entry-point and HF-tag wiring is fiddly. The `README.md` must carry
the `reachy_mini_python_app` tag in YAML frontmatter.

### Data records
```python
@dataclass
class AnswerRecord:
    qid: str; question: str; attribute: str; sub_dim: str | None
    wav_path: str; transcript: str; words: list[Word]
    delivery: DeliveryMetrics
    flags: list[str]                        # red flags fired
    content: ContentVerdict | None = None   # filled at debrief; None if LLM unavailable

@dataclass
class ContentVerdict:
    components: dict[str, bool]   # situation/problem/solution/impact/lessons
    verdict: str                  # one of the 6 recommendation levels
    evidence: str                 # one short sentence
```

---

## 11. Session state machine — `session.py`

`IDLE → PLANNING → OPENING → ASK(i) → LISTEN(i) → [FOLLOWUP(i)] → ASK(i+1) … → SCORING → DEBRIEF → DONE`

- **OPENING** — acknowledging nod, then state company, role, question count and expected length so the
  candidate can pace themselves. Does **not** explain the rubric or list the attributes — that would
  contaminate the interview.
- **ASK** — `motion.react("curious")`, then `speech.say(question)`, record `t_tts_end`.
- **LISTEN** — `start_recording()`; end the answer when RMS stays below threshold for **3.0 s** after at
  least **5 s** of speech; hard cap **180 s**. Start at 3.0 s and tune down — 2.0 s cuts people off
  mid-thought.
- **Transcription runs in a BACKGROUND THREAD, never inline.** `base.en` int8 on 4 cores takes ~30–50 s
  for a 100 s answer, so question N's transcript and metrics land while N+1 is being answered. Inline
  transcription would put 30–50 s of dead air after every answer.
- **FOLLOWUP** — at most once per question, on a deterministic trigger:

| Trigger | Follow-up |
|---|---|
| no Impact keywords (`result, impact, reduced, increased, shipped, %`) | "What changed as a result?" |
| `last_failure` with no Lessons markers | "What would you do differently now?" |
| `duration_s < 45` | "Can you walk me through what you actually did, step by step?" |
| `situation_s > 30` | **no follow-up** — recorded as a flag only. Interrupting would distort the metric |

- **SCORING** — iterate `AnswerRecord`s through Ollama while the idle thinking move plays. On timeout or
  connection error, leave `content=None` and continue.
- **DEBRIEF** — speak 3 strengths and 3 fixes derived from worst-band metrics and weakest
  sub-dimensions; render the HTML scorecard. Tone shifts here and only here: interviewer becomes coach.
  Do not read the whole scorecard aloud — numbers belong on the page.

**Echo:** gate recording on TTS-not-playing. Turn-based interviewing makes this trivial and removes any
need for echo cancellation between the robot's own speaker and mic.

---

## 12. Scoring prompt — `scoring.py`

One call per answer, JSON only, `temperature=0`, kept tiny to hold CPU latency down:

```
You are scoring one answer in a Google behavioural interview.
Attribute: {attribute}. Sub-dimension: {sub_dim}.
Question: {question}
Answer transcript: {transcript}

Return ONLY JSON:
{"components":{"situation":bool,"problem":bool,"solution":bool,"impact":bool,"lessons":bool},
 "verdict":"strong_no_hire|no_hire|leaning_no_hire|leaning_hire|hire|strong_hire",
 "evidence":"<one sentence, max 20 words>"}
```

Validate with a strict parser. One retry on malformed JSON, then give up and leave `content=None`.

**Expect shallow judgement.** A 3B model reliably emits valid JSON and can answer "did they state an
Impact?", but its 6-point verdict will be noisy. Do not present it as authoritative; the deterministic
channels are the trustworthy output.

---

## 13. FastAPI surface — `main.py`, `custom_app_url = "http://0.0.0.0:8042"`

| Endpoint | Purpose |
|---|---|
| `POST /api/session/start` | `{jd_url, languages[], framework}` → runs JD pipeline, returns the plan |
| `GET /api/session/state` | current state, question index, live delivery metrics (UI polls this) |
| `POST /api/session/repeat` | re-speak the current question verbatim; does **not** reset timing metrics |
| `POST /api/session/abort` | return to IDLE, safely return to pose |
| `GET /api/scorecard` | the rendered scorecard |

When `custom_app_url` is set, the app serves files from `static/` inside the package; the dashboard
shows a settings icon. Reachable at `http://localhost:8042` on a Lite.

---

## 14. Scorecard

Three **independent** channels, **never blended into one number** — averaging an LLM content judgement
with an energy-variance proxy yields a figure that is neither defensible nor useful.

- **Channel A — Content** (LLM, deferred): per-answer component checklist + 6-point verdict + evidence
- **Channel B — Delivery** (deterministic): `BANDS` metrics as **raw measurements against target bands**,
  never a personality judgement
- **Channel C — Red flags** (deterministic): the four heuristics, each rendered **with its confidence level**

### `render_html` layout
1. **Header** — company, role, framework used, languages claimed, MS/team-matching note
2. **Per-question rows** — question · attribute · sub-dimension · SPSIL checklist · verdict · delivery
   metrics coloured against bands · flags fired
3. **Per-attribute rollup** — RRK · GCA · Leadership · Googleyness, the last broken out across all five
   sub-dimensions, each with worst and mean verdict
4. **Delivery summary** — each metric vs. its band across the session
5. **Overall** — the **6-point scale** Google interviewers actually record on:
   `Strong no hire · No hire · Leaning no hire · Leaning hire · Hire · Strong hire`.
   Aggregation: **worst attribute dominates**, mirroring how one strong-no sinks a hiring-committee packet
6. **Footer** — sourcing disclosure (§17)

**Do not present a 1–4 numeric scale as official.** It appears only in secondary forum sources. If shown
at all, label it "reported, unconfirmed".

---

## 15. Failure behaviour

Degrade where the interview is still valid; refuse where it is not.

| Failure | Behaviour |
|---|---|
| Camera unavailable | Continue audio-only, gaze centred. `face_centred_pct` marked **unavailable, not 0** — a missing measurement must never score as a bad one |
| Mic unavailable | **Abort** with a clear UI error. An interview without audio is not degradable |
| Transcription backlog | Keep asking questions; metrics catch up. Never stall the interview |
| Ollama unavailable / malformed JSON after one retry | `content=None`; debrief on delivery alone and say plainly that content review was unavailable |
| Wake-up or motor failure | Surface in the UI and refuse to start — do not interview with a robot that cannot look at the candidate |

---

## 16. Build order

| Step | Work |
|---|---|
| 1 | Start `ollama pull qwen2.5:3b-instruct-q4_K_M` in the background (~2 GB). Ollama itself is not yet installed and its installer needs root |
| 2 | `uv venv --python 3.12 /home/joe/reachy/.venv` (absolute path) |
| 3 | `uv pip install 'reachy-mini[opencv]'`. **Highest-risk step** — PyGObject 3.46 compiles here. Timebox 15 min; fall back per §3.4 |
| 4 | Stop the `.deb` desktop app, start `reachy-mini-daemon`, verify with `mini_test.py` minus `media_backend='no_media'` |
| 5 | `jd.py` + `playbooks/google.py` + `plan_builder.py` — pure Python, no robot, no LLM, testable standalone |
| 6 | Scaffold the app; serve JD entry + state polling |
| 7 | `motion.py` + `attention.py` — enumerate emotions, control loop, clamps, face centring |
| 8 | `speech.py` — Piper out to robot speaker, `start_recording` in, faster-whisper with word timestamps |
| 9 | `delivery.py` + `session.py` — metrics, state machine, follow-up triggers |
| 10 | `scorecard.py` — rollup, 6-point verdict, HTML, spoken debrief |
| 11 | Wire `scoring.py` to Ollama if the model landed; verify graceful degradation either way |
| 12 | Full end-to-end run |

Steps 1–3, 5 and 6 need **no robot**. `use_sim=True` also allows session logic development unplugged.

**Cut without hesitation:** general JD scraping (hardcode the Google playbook), gesture analysis,
emotion classification, streaming STT, librosa, mediapipe, publishing to the HF app store, any model
above 3B, anything belonging to the technical round.

**Downloads (~2.2 GB):** qwen2.5:3b q4 (~2 GB) · faster-whisper `base.en` (~150 MB) · one Piper voice
(~60 MB) · emotions library (small).

---

## 17. Verification

1. **Tailoring, no robot** — run the JD pipeline against the Google URL; assert `JobSpec` catches all
   five languages, `dsa_explicit=True`, both role variants, `duration_weeks=12`; assert `ambiguity`,
   `collaborative` and `moonshot` weights are raised and `sre_inclination` is enabled. Run a second
   posting (Databricks or Celonis via the public Greenhouse board API) to confirm the host→playbook map
   falls through sanely.
2. **Delivery metrics — the most important test**, because it is what makes the nonverbal claim honest.
   Record three fixed 60 s samples: fast-and-filler-heavy, well-paced, and read verbatim from a script.
   Assert wpm / filler / ttfw separate them and that the scripted one trips **too polished**.
3. **Situation ≤30 s detector** — one answer with ~10 s of context, one with ~60 s. Flag fires only on
   the second.
4. **Robot I/O** — confirm Piper output reaches the **robot** speaker and `start_recording()` captures
   the **robot** mic array at 16 kHz, not the HP webcam mic; confirm `attention.py` opens `/dev/video2`.
5. **Motion safety** — drive the loop with deliberately out-of-range targets; assert clamping holds
   pitch/roll within ±40° and head−body yaw delta within 65°.
6. **Follow-up triggers** — one answer with no Impact keywords, one under 45 s; assert the right
   follow-up fires, at most once per question, and that `situation_s > 30` fires **no** follow-up.
7. **End-to-end** — full 6-question session; scorecard renders with per-attribute rollup,
   per-sub-dimension breakdown, and a 6-point verdict.
8. **Graceful degradation** — stop Ollama mid-session; scorecard still renders with content
   "not scored", no crash. Unplug the camera mid-session; `face_centred_pct` reports **unavailable
   rather than 0** and the interview continues.
9. **Behaviour conformance** — walk `REACHY_BEHAVIOR.md` section by section during one live session. The
   two easiest things to get wrong: Reachy must be **still before it finishes asking**, and it must
   **not interrupt** an over-long Situation even though the flag fires.

---

## 18. Sourcing honesty — required

The four attributes are **not currently published by Google**. They originate with Laszlo Bock's
*Work Rules!* (2015); the re:Work page that defined them now 404s; Google's careers pages are fully
client-rendered with no extractable rubric text.

UI copy must read **"the four attributes widely reported by ex-Google interviewers and prep
platforms"** — **not** "Google's official rubric".

Research sources:
- `https://igotanoffer.com/blogs/tech/google-behavioral-interview` (note: returns HTTP 403 to
  automated fetchers but serves fine to `curl` with a browser User-Agent)
- `https://www.tryexponent.com/guides/google-software-engineer-intern-interview`
- `https://igotanoffer.com/blogs/tech/google-software-engineer-interview`

---

## 19. Next iteration — deliberately out of scope

The **technical round**: easy→medium LeetCode from a "familiar structures with a twist" bank (streaming
intervals, indexed priority queue, batching cache), on a plain textarea with **no run button** —
faithful, because real Google interviews use a shared plain-text doc with no IDE, no autocomplete and
no code execution. Scored on seven criteria of which four are process, so ~55/45
process-over-correctness, with **silence ratio while typing** as the "thinking out loud" measure.
**No system design** — explicitly not included for interns.

Most of `session.py`, `speech.py`, `delivery.py` and `scorecard.py` are reusable as-is; `jd.py` already
records `dsa_explicit` and the domain list it will need.
