import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


CURRENT_DIR = os.path.dirname(__file__)
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
BACKEND_SRC = os.path.abspath(os.path.join(CURRENT_DIR, "..", "src"))
for path in (BACKEND_DIR, BACKEND_SRC):
    if path not in sys.path:
        sys.path.insert(0, path)


import main  # noqa: E402


def _browser_headers() -> dict[str, str]:
    return {
        "Origin": "http://localhost:3000",
        "Referer": "http://localhost:3000/",
        "User-Agent": "StoryGameFrontendTest/1.0",
        "X-Forwarded-For": "203.0.113.9",
    }


def _llm_response(content: str) -> dict[str, object]:
    return {"content": content, "error": None}


class FrontendAccessGateTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.original_stories_db = dict(main.stories_db)
        self.original_feedback_db = list(main.feedback_db)
        self.original_sessions = dict(main.frontend_access_sessions)
        self.original_gate_enabled = main.FRONTEND_ACCESS_GATE_ENABLED
        self.original_allowed_origins = list(main.FRONTEND_ACCESS_ALLOWED_ORIGINS)

        main.stories_db.clear()
        main.feedback_db.clear()
        main.frontend_access_sessions.clear()
        main.FRONTEND_ACCESS_GATE_ENABLED = True
        main.FRONTEND_ACCESS_ALLOWED_ORIGINS = ["http://localhost:3000"]

    def tearDown(self):
        main.stories_db.clear()
        main.stories_db.update(self.original_stories_db)
        main.feedback_db.clear()
        main.feedback_db.extend(self.original_feedback_db)
        main.frontend_access_sessions.clear()
        main.frontend_access_sessions.update(self.original_sessions)
        main.FRONTEND_ACCESS_GATE_ENABLED = self.original_gate_enabled
        main.FRONTEND_ACCESS_ALLOWED_ORIGINS = self.original_allowed_origins

    def _bootstrap_access(self) -> dict[str, str]:
        headers = _browser_headers()
        response = self.client.get("/access/session", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        token = response.json()["csrf_token"]
        auth_headers = dict(headers)
        auth_headers[main.FRONTEND_ACCESS_HEADER_NAME] = token
        return auth_headers

    def test_bootstrap_rejects_requests_without_same_origin_headers(self):
        response = self.client.get("/access/session")

        self.assertEqual(response.status_code, 403)
        self.assertIn("same-origin", response.text)

    def test_initiate_requires_frontend_access_session(self):
        response = self.client.post(
            "/story/initiate",
            headers=_browser_headers(),
            json={
                "emotional_need": "I feel overwhelmed and need comfort.",
                "user_id": "user-1",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("Frontend access session", response.text)

    def test_bootstrapped_frontend_can_complete_story_creation_flow(self):
        auth_headers = self._bootstrap_access()
        mocked_llm_outputs = [
            _llm_response(
                '[{"question":"What hurts most right now?","options":["Loneliness","Regret","Uncertainty"],"allowsCustom":true,"questionType":"single"}]'
            ),
            _llm_response('["rain","cafe","midnight"]'),
            _llm_response('{"social_inclination":["quiet"],"interests":["books"],"personality":["gentle"]}'),
            _llm_response(
                '{"title":"Rain Between Stations","high_concept_premise":"A weary commuter finds comfort in a midnight station cafe.","cinematic_theme":"Tender urban healing","emotional_undercurrent":"Grief softening into connection","protagonist_objective":"Make it through one difficult night without shutting down."}'
            ),
            _llm_response(
                '{"setting":{"world":"Present-day city","primary_location":"A station cafe after the last train","sensory_anchor":"Rain against warm windows"}}'
            ),
            _llm_response(
                '[{"id":"protagonist","name":"You","role":"protagonist","description":"A tired commuter learning to open up."},{"id":"mira","name":"Mira","role":"npc","description":"A calm barista who notices what others miss."}]'
            ),
            _llm_response(
                '[{"act_number":1,"title":"Holding It Together","summary":"The night begins with emotional distance."},{"act_number":2,"title":"Letting Someone In","summary":"The protagonist risks honesty and receives real support."}]'
            ),
            _llm_response(
                '{"opening_sequence":{"description":"Rain slides down the station windows while the cafe glows softly.","location":"Station cafe","mood":"quietly aching","inciting_incident":"A kind stranger notices the protagonist cannot stop staring at an unread message."},"initial_dialogue":[{"id":"msg-1","character_id":"mira","content":"Long night?","type":"text"}],"branching_choices":[{"id":"choice-1","text":"Admit the night has been hard"},{"id":"choice-2","text":"Deflect with a joke"}],"hidden_elements":[{"type":"memory","description":"A folded train receipt tucked into a book."}]}'
            ),
        ]

        with patch.object(main, "run_llm_completion", new=AsyncMock(side_effect=mocked_llm_outputs)), \
             patch.object(main, "generate_character_images", new=AsyncMock(return_value=None)), \
             patch.object(main, "_save_story_snapshot_locally", new=AsyncMock(return_value=None)):
            initiate_response = self.client.post(
                "/story/initiate",
                headers=auth_headers,
                json={
                    "emotional_need": "I am trying to recover from a breakup.",
                    "user_id": "user-1",
                },
            )
            self.assertEqual(initiate_response.status_code, 200, initiate_response.text)
            initiate_payload = initiate_response.json()
            story_id = initiate_payload["story_id"]

            step1_response = self.client.post(
                "/story/create/step1",
                headers=auth_headers,
                json={
                    "story_id": story_id,
                    "emotional_need": "I am trying to recover from a breakup.",
                    "user_id": "user-1",
                    "answers": {
                        "What hurts most right now?": "Loneliness",
                    },
                    "selected_keywords": ["rain", "cafe"],
                    "profile_keywords": {
                        "social_inclination": ["quiet"],
                        "interests": ["books"],
                        "personality": ["gentle"],
                    },
                    "guidance_sentence": "Keep the tone intimate and grounded.",
                },
            )
            self.assertEqual(step1_response.status_code, 200, step1_response.text)

            for path in (
                "/story/create/step2",
                "/story/create/step3",
                "/story/create/step4",
                "/story/create/step5",
            ):
                response = self.client.post(path, headers=auth_headers, json={"story_id": story_id})
                self.assertEqual(response.status_code, 200, f"{path}: {response.text}")

            complete_response = self.client.post(
                f"/story/complete/{story_id}",
                headers=auth_headers,
            )
            self.assertEqual(complete_response.status_code, 200, complete_response.text)
            story_payload = complete_response.json()

        self.assertEqual(story_payload["story_id"], story_id)
        self.assertEqual(story_payload["title"], "Rain Between Stations")
        self.assertEqual(story_payload["status"], "active")
        self.assertEqual(story_payload["current_scene"]["location"], "Station cafe")
        self.assertTrue(story_payload["current_scene"]["choices"])


if __name__ == "__main__":
    unittest.main()
