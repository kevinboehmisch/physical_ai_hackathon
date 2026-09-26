import asyncio
import logging
from typing import Any, Dict

from reachy_interview_coach.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)

ACTIONS = ("consent_given", "consent_declined", "next_question", "finish_interview")


class InterviewControl(Tool):
    """Drive the interview: record consent, fetch the next question, close and evaluate."""

    name = "interview_control"
    description = (
        "Control the job interview flow. Call with action=consent_given or consent_declined right after the "
        "candidate answered whether their behaviour may be analysed. Call action=next_question whenever you are "
        "ready to ask the next question; it returns the exact question to ask plus a hint for follow-ups. "
        "Call action=finish_interview after the last answer; it returns the evaluation you must summarise aloud."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(ACTIONS),
                "description": "Which interview step to perform.",
            },
        },
        "required": ["action"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> Dict[str, Any]:
        """Advance the interview state machine and return what the interviewer should do next."""
        action = str(kwargs.get("action", "")).strip()
        session = deps.interview_session
        logger.info("Tool call: interview_control action=%s", action)
        if session is None:
            return {"error": "No interview session is active."}
        if action not in ACTIONS:
            return {"error": f"Unknown action {action!r}. Use one of {', '.join(ACTIONS)}."}

        if action in {"consent_given", "consent_declined"}:
            session.record_consent(action == "consent_given")
            return {
                "status": "consent_recorded",
                "analysis_enabled": session.analysis_enabled,
                "next": "Call interview_control with action=next_question to ask the first question.",
            }

        if action == "next_question":
            asked = session.next_question()
            if asked is None:
                return {
                    "status": "no_more_questions",
                    "next": "Thank the candidate briefly, then call interview_control with action=finish_interview.",
                }
            return {
                "status": "ask_this_question",
                "number": asked.number,
                "total": len(session.questions),
                "kind": asked.question.kind,
                "question": asked.question.text,
                "follow_up_hint": asked.question.interviewer_hint,
            }

        session.finish()
        if deps.interview_evaluate is None:
            result: Dict[str, Any] = {
                "status": "interview_finished",
                "analysis_enabled": session.analysis_enabled,
                "answers": session.answer_summaries(),
            }
        else:
            # Whisper and the report run for a while; keep the realtime loop responsive.
            result = await asyncio.to_thread(deps.interview_evaluate)
        result["next"] = (
            "Say the spoken_feedback aloud (you may rephrase slightly, keep it under 8 sentences), then mention that "
            "the detailed HTML report has been saved. Do not read out raw metrics beyond what spoken_feedback contains."
        )
        return result
