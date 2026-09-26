import logging
from typing import Any, Dict

from reachy_interview_coach.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)

ACTIONS = ("consent_given", "consent_declined", "next_question", "finish_interview")

EVALUATION_RUNNING_HINT = (
    "The evaluation (speech, camera and content analysis) is running in the background; its result will be "
    "delivered to you automatically as a message in about a minute. Say one or two sentences: thank the "
    "candidate and tell them the evaluation takes about a minute and you will speak up as soon as it is ready. "
    "Then wait. Do not invent any feedback and do not call finish_interview again unless the candidate asks."
)


class InterviewControl(Tool):
    """Drive the interview: record consent, fetch the next question, close and evaluate."""

    name = "interview_control"
    description = (
        "Control the job interview flow. Call with action=consent_given or consent_declined right after the "
        "candidate answered whether their behaviour may be analysed. Call action=next_question whenever you are "
        "ready to ask the next question; it returns the exact question to ask plus a hint for follow-ups. "
        "Call action=finish_interview after the last answer, or whenever the candidate asks for the evaluation, "
        "feedback, results or the camera/body-language analysis; it returns the evaluation (content, speech and "
        "camera metrics) or tells you it is still running. Never claim that no camera or speech data exists."
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
                session.finish()
                if deps.interview_begin_evaluation is not None:
                    deps.interview_begin_evaluation()
                return {
                    "status": "no_more_questions",
                    "next": EVALUATION_RUNNING_HINT,
                }
            return {
                "status": "ask_this_question",
                "number": asked.number,
                "total": len(session.questions),
                "kind": asked.question.kind,
                "question": asked.question.text,
                "follow_up_hint": asked.question.interviewer_hint,
            }

        # finish_interview. Must return immediately: while a tool result is pending the realtime backend
        # refuses to answer the user ("Cannot generate a response while function call outputs are pending").
        session.finish()
        if deps.interview_begin_evaluation is None or deps.interview_evaluation_result is None:
            return {
                "status": "interview_finished",
                "analysis_enabled": session.analysis_enabled,
                "answers": session.answer_summaries(),
                "next": "Give brief feedback on the content of the answers only; no analysis data is available.",
            }
        deps.interview_begin_evaluation()
        result = deps.interview_evaluation_result()
        if result is None:
            return {"status": "evaluation_running", "next": EVALUATION_RUNNING_HINT}
        if result.pop("already_presented", False):
            result["next"] = (
                "You have already presented this feedback. Use these data only to answer follow-up questions; "
                "do not repeat the whole feedback."
            )
        else:
            result["next"] = (
                "Say the spoken_feedback aloud (you may rephrase slightly, keep it under 8 sentences), then mention "
                "that the detailed HTML report has been saved. Do not read out raw metrics beyond what "
                "spoken_feedback contains."
            )
        return result
