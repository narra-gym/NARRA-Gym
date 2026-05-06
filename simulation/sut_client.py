"""HTTP client wrapping the EmoNest backend API as a black-box system-under-test."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class SUTClient:
    """Synchronous wrapper around the EmoNest FastAPI server."""

    def __init__(self, base_url: str = "http://127.0.0.1:11454", timeout: float = 600.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout, trust_env=False)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SUTClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ── Generic helpers ────────────────────────────────────────────────────

    def _request(self, method: str, path: str, **kwargs) -> Any:
        response = self._client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(
                f"SUT {method} {path} failed: {response.status_code} {response.text[:500]}"
            )
        if not response.content:
            return None
        ctype = response.headers.get("content-type", "")
        if "application/json" in ctype:
            return response.json()
        return response.text

    def get(self, path: str, **kwargs) -> Any:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, json: Optional[Dict[str, Any]] = None, **kwargs) -> Any:
        return self._request("POST", path, json=json, **kwargs)

    # ── Experiment session lifecycle ──────────────────────────────────────

    def start_session(
        self,
        *,
        participant_id: Optional[str] = None,
        selected_model: Optional[str] = None,
        requested_condition_id: Optional[str] = None,
        session_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"mode": "benchmark"}
        if participant_id:
            payload["participant_id"] = participant_id
        if selected_model:
            payload["selected_model"] = selected_model
        if requested_condition_id:
            payload["requested_condition_id"] = requested_condition_id
        if session_metadata:
            payload["session_metadata"] = session_metadata
        return self.post("/experiments/session/start", json=payload)

    def list_models(self) -> List[Dict[str, Any]]:
        return self.get("/experiments/models")

    def list_conditions(self) -> List[Dict[str, Any]]:
        return self.get("/experiments/conditions")

    def export_session(self, session_id: str) -> Dict[str, Any]:
        return self.get(f"/experiments/sessions/{session_id}/export")

    # ── Story creation pipeline ───────────────────────────────────────────

    def initiate_story(
        self,
        *,
        emotional_need: str,
        session_id: Optional[str] = None,
        participant_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {"emotional_need": emotional_need, "experiment_mode": True}
        if session_id:
            payload["session_id"] = session_id
        if participant_id:
            payload["participant_id"] = participant_id
        if user_id:
            payload["user_id"] = user_id
        return self.post("/story/initiate", json=payload)

    def create_step1(
        self,
        *,
        story_id: str,
        emotional_need: str,
        answers: Dict[str, str],
        selected_keywords: List[str],
        profile_keywords: Optional[Dict[str, List[str]]] = None,
        session_id: Optional[str] = None,
        participant_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "story_id": story_id,
            "emotional_need": emotional_need,
            "answers": answers,
            "selected_keywords": selected_keywords,
        }
        if profile_keywords:
            payload["profile_keywords"] = profile_keywords
        if session_id:
            payload["session_id"] = session_id
        if participant_id:
            payload["participant_id"] = participant_id
        if user_id:
            payload["user_id"] = user_id
        return self.post("/story/create/step1", json=payload)

    def create_step(self, step: int, story_id: str) -> Dict[str, Any]:
        if step not in {2, 3, 4, 5}:
            raise ValueError(f"Step must be 2..5 for the simple call; got {step}")
        return self.post(f"/story/create/step{step}", json={"story_id": story_id})

    def get_story(self, story_id: str) -> Dict[str, Any]:
        return self.get(f"/story/{story_id}")

    # ── Interactive turns ─────────────────────────────────────────────────

    def send_message(
        self,
        *,
        story_id: str,
        content: str,
        session_id: Optional[str] = None,
        participant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"story_id": story_id, "content": content}
        if session_id:
            payload["session_id"] = session_id
        if participant_id:
            payload["participant_id"] = participant_id
        return self.post("/messages", json=payload)

    def select_choice(
        self,
        *,
        story_id: str,
        choice_id: str,
        session_id: Optional[str] = None,
        participant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"story_id": story_id, "choice_id": choice_id}
        if session_id:
            payload["session_id"] = session_id
        if participant_id:
            payload["participant_id"] = participant_id
        return self.post("/choices", json=payload)

    def end_story(self, story_id: str) -> Dict[str, Any]:
        return self.post(f"/stories/{story_id}/end")

    # ── Judge passthrough ────────────────────────────────────────────────

    def judge_session(self, *, selected_model: str, benchmark_payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.post(
            "/experiments/judge",
            json={"selected_model": selected_model, "benchmark_payload": benchmark_payload},
        )

    def submit_feedback(
        self,
        *,
        session_id: Optional[str],
        story_id: Optional[str],
        rating: int,
        scores: Optional[Dict[str, int]] = None,
        feelings: Optional[List[str]] = None,
        comment: Optional[str] = None,
        feedback_type: str = "simulated_user",
        participant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "rating": rating,
            "feedback_type": feedback_type,
        }
        if session_id:
            payload["session_id"] = session_id
        if story_id:
            payload["story_id"] = story_id
        if scores:
            payload["scores"] = scores
        if feelings:
            payload["feelings"] = feelings
        if comment:
            payload["comment"] = comment
        if participant_id:
            payload["participant_id"] = participant_id
        return self.post("/feedback", json=payload)
