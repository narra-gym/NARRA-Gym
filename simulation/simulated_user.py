"""LLM-driven simulated user agent.

The agent is asked, at each step, to emit a single JSON action for the current
phase of the NARRA-Gym flow. The runner translates that JSON into HTTP calls
against the SUT.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .llm import LLMClient
from .personas import Persona

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are role-playing a real human user of an interactive
therapeutic story app called NARRA-Gym. You will go through several phases:

1. emotional_need        — share what's going on, in your own voice
2. clarifying_questions  — answer profiling questions (multiple-choice or free-text)
3. keyword_selection     — pick keywords that should appear in your story
4. interactive_play      — read the unfolding story and respond, either by
                           sending a free-text message or selecting one of the
                           offered branching choices
5. ending                — decide when you've had enough and want the story to end

ABSOLUTE RULES
- Stay fully in character. Never mention you are an AI, language model, or simulator.
- Match your persona's verbosity, tone, formality, emoji habits, and punctuation.
- Honor your persona's resistance patterns. Don't be more cooperative than your persona would be.
- Do NOT narrate your own thoughts in the message sent to the app. Put them in `internal_state` instead.
- Reply with a SINGLE JSON object only. No markdown, no commentary outside the JSON.

OUTPUT SCHEMA
You must always reply with one of these JSON shapes:

  // emotional_need phase
  { "action": "submit_emotional_need",
    "content": "<2-6 sentences in your own voice>",
    "internal_state": "<one short sentence about how you actually feel right now>" }

  // clarifying_questions phase — answers a SINGLE question
  { "action": "answer_question",
    "question": "<copy the question verbatim>",
    "content": "<the answer text. If the question is multiple-choice, you may copy
                one of the options verbatim, or join several with ', ' for multi-select,
                or write a custom short answer if allowsCustom is true.>",
    "internal_state": "<one short sentence>" }

  // keyword_selection phase — pick 1-4 keywords from suggested list
  { "action": "select_keywords",
    "content": ["keyword1", "keyword2"],
    "internal_state": "<one short sentence>" }

  // interactive_play phase
  { "action": "send_message",
    "content": "<your reply, in your persona's voice>",
    "internal_state": "<one short sentence>" }

  // interactive_play phase, when picking a branching choice instead
  { "action": "select_choice",
    "choice_id": "<one of the offered choice ids>",
    "choice_text": "<copy the matching choice text>",
    "internal_state": "<one short sentence>" }

  // any phase, when you have decided you want to leave / end
  { "action": "end_story",
    "content": "<a short final line in your voice, optional>",
    "internal_state": "<one short sentence>" }

If the system has just produced the final scene or an "Ending is available"
signal, prefer `end_story` if your end_condition is met. Otherwise keep going
until your max_user_turns is reached.
"""


@dataclass
class TurnRecord:
    """One observable step of the simulated session, for logging."""

    turn_index: int
    phase: str
    user_action: Dict[str, Any]
    sut_visible_excerpt: str = ""
    raw_llm_output: str = ""
    internal_state: str = ""
    notes: List[str] = field(default_factory=list)


class SimulatedUser:
    """Wraps an LLM as a stateful, persona-faithful user."""

    def __init__(self, persona: Persona, llm: LLMClient, log_internal: bool = True):
        self.persona = persona
        self.llm = llm
        self.log_internal = log_internal
        self.turn_index = 0
        self.transcript: List[TurnRecord] = []

    # ── Public API ────────────────────────────────────────────────────────

    def next_action(
        self,
        *,
        phase: str,
        sut_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Ask the LLM what the user does next."""
        self.turn_index += 1
        user_prompt = self._build_user_prompt(phase=phase, sut_state=sut_state)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            action = self.llm.chat_json(messages, max_tokens=900)
        except Exception as exc:
            logger.error("Simulated user LLM failed at turn %d: %s", self.turn_index, exc)
            action = self._fallback_action(phase)

        action = self._sanitize_action(action, phase, sut_state)

        record = TurnRecord(
            turn_index=self.turn_index,
            phase=phase,
            user_action=action,
            sut_visible_excerpt=self._visible_excerpt(sut_state),
            raw_llm_output=json.dumps(action, ensure_ascii=False),
            internal_state=str(action.get("internal_state", "")) if self.log_internal else "",
        )
        self.transcript.append(record)
        return action

    # ── Prompt assembly ───────────────────────────────────────────────────

    def _build_user_prompt(self, *, phase: str, sut_state: Dict[str, Any]) -> str:
        parts: List[str] = []
        parts.append("YOUR PERSONA (stay in character):")
        parts.append(self.persona.card_for_prompt())
        parts.append("")
        parts.append(f"CURRENT PHASE: {phase}")
        parts.append(f"TURN INDEX: {self.turn_index}  (max user turns: {self.persona.max_user_turns})")

        if phase == "emotional_need":
            parts.append("")
            parts.append("Share, in your own voice, what brought you here today. "
                         "Use your persona's emotional_need as the seed but rewrite it naturally.")

        elif phase == "clarifying_questions":
            question = sut_state.get("question", {})
            parts.append("")
            parts.append("The app is asking you ONE question. Answer it.")
            parts.append("Question payload:")
            parts.append(json.dumps(question, ensure_ascii=False, indent=2))
            parts.append(
                "If it has 'options', you may copy one option verbatim, "
                "join several with ', ' (only if questionType=='multiple'), "
                "or write a custom short answer when allowsCustom is true."
            )

        elif phase == "keyword_selection":
            keywords = sut_state.get("keywords", [])
            profile_keywords = sut_state.get("profile_keywords", {})
            parts.append("")
            parts.append("The app suggests these keywords for your story.")
            parts.append(f"Suggested keywords: {json.dumps(keywords, ensure_ascii=False)}")
            if profile_keywords:
                parts.append(f"Profile keyword groups: {json.dumps(profile_keywords, ensure_ascii=False)}")
            parts.append("Pick 1-4 keywords that resonate. You may also propose your own (still 1-4 total).")

        elif phase == "interactive_play":
            parts.append("")
            parts.append("Below is the most recent stretch of the unfolding story. "
                         "React as your persona would.")
            parts.append("")
            parts.append("--- recent story messages (oldest first) ---")
            parts.append(self._format_recent_messages(sut_state.get("recent_messages", [])))
            parts.append("--- end of recent messages ---")
            parts.append("")
            choices = sut_state.get("choices") or []
            if choices:
                parts.append("The app is offering branching choices RIGHT NOW:")
                for choice in choices:
                    parts.append(
                        f"  - id={choice.get('id')}  text={choice.get('text')!r}"
                    )
                parts.append("You may either select_choice (use one of the ids above) "
                             "or send_message (free-text reply).")
            else:
                parts.append("No branching choices are offered right now. Use send_message.")

            ending_available = bool(sut_state.get("ending_available"))
            if ending_available:
                parts.append("NOTE: an explicit ending is currently available. "
                             "If your end_condition is satisfied, prefer end_story.")

        elif phase == "ending":
            parts.append("")
            parts.append("This is your last action. Use end_story.")

        if self.transcript:
            parts.append("")
            parts.append("Your most recent internal state (for continuity, not visible to the app):")
            parts.append(f"  {self.transcript[-1].internal_state or '(none)'}")

        parts.append("")
        parts.append("Reply with ONLY the JSON object for this action.")
        return "\n".join(parts)

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _format_recent_messages(messages: List[Dict[str, Any]]) -> str:
        if not messages:
            return "(no prior messages)"
        rendered: List[str] = []
        for msg in messages[-12:]:
            speaker = msg.get("speaker") or msg.get("character_id") or "system"
            role = msg.get("role", "")
            content = (msg.get("content") or "").strip()
            if not content:
                continue
            content = content.replace("\n", " ")
            if len(content) > 800:
                content = content[:800] + "…"
            rendered.append(f"[{role}|{speaker}] {content}")
        return "\n".join(rendered) or "(no prior messages)"

    @staticmethod
    def _visible_excerpt(sut_state: Dict[str, Any]) -> str:
        msgs = sut_state.get("recent_messages") or []
        if not msgs:
            return ""
        last = msgs[-1]
        text = (last.get("content") or "")[:240]
        return text

    def _sanitize_action(
        self,
        action: Dict[str, Any],
        phase: str,
        sut_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not isinstance(action, dict):
            action = self._fallback_action(phase)

        kind = action.get("action")
        if not kind:
            action = self._fallback_action(phase)
            return action

        if phase == "interactive_play" and kind == "select_choice":
            choices = sut_state.get("choices") or []
            chosen_id = action.get("choice_id")
            valid_ids = {c.get("id") for c in choices}
            if chosen_id not in valid_ids:
                if choices:
                    fallback = choices[0]
                    action["choice_id"] = fallback.get("id")
                    action["choice_text"] = fallback.get("text")
                    action.setdefault("internal_state", "")
                    action["_repaired"] = "invalid_choice_id"
                else:
                    action = {
                        "action": "send_message",
                        "content": action.get("content")
                        or "i'm not sure what to do here",
                        "internal_state": action.get("internal_state", ""),
                        "_repaired": "no_choices_offered",
                    }
        return action

    def _fallback_action(self, phase: str) -> Dict[str, Any]:
        if phase == "emotional_need":
            return {
                "action": "submit_emotional_need",
                "content": self.persona.emotional_need or "i don't really know how to say this",
                "internal_state": "(fallback)",
                "_repaired": "llm_failure",
            }
        if phase == "clarifying_questions":
            return {
                "action": "answer_question",
                "question": "",
                "content": "i'd rather not say",
                "internal_state": "(fallback)",
                "_repaired": "llm_failure",
            }
        if phase == "keyword_selection":
            return {
                "action": "select_keywords",
                "content": [],
                "internal_state": "(fallback)",
                "_repaired": "llm_failure",
            }
        if phase == "interactive_play":
            return {
                "action": "send_message",
                "content": "ok",
                "internal_state": "(fallback)",
                "_repaired": "llm_failure",
            }
        return {
            "action": "end_story",
            "content": "",
            "internal_state": "(fallback)",
            "_repaired": "llm_failure",
        }
