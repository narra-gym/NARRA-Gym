import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch


CURRENT_DIR = os.path.dirname(__file__)
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
BACKEND_SRC = os.path.abspath(os.path.join(CURRENT_DIR, "..", "src"))
for path in (BACKEND_DIR, BACKEND_SRC):
    if path not in sys.path:
        sys.path.insert(0, path)


import main  # noqa: E402
from config import settings  # noqa: E402
from models import StoryStep4Input  # noqa: E402
from models import StoryStep5Input  # noqa: E402


class LLMRequestOptionTests(unittest.TestCase):
    def test_openrouter_gpt5_uses_reasoning_none(self):
        route = {
            "model_name": "openai/gpt-5.4",
            "provider": "openrouter",
            "transport_provider": "openrouter",
        }

        self.assertEqual(
            settings.get_llm_request_options(route),
            {"extra_body": {"reasoning": {"effort": "none"}}},
        )

    def test_openrouter_gemini_uses_minimal_reasoning(self):
        route = {
            "model_name": "google/gemini-3.1-pro-preview",
            "provider": "openrouter",
            "transport_provider": "openrouter",
        }

        self.assertEqual(
            settings.get_llm_request_options(route),
            {
                "extra_body": {
                    "reasoning": {
                        "effort": settings.LLM_MIN_REASONING_EFFORT,
                        "exclude": True,
                    }
                }
            },
        )

    def test_openrouter_qwen_disables_reasoning_when_supported(self):
        route = {
            "model_name": "qwen/qwen3.5-397b-a17b",
            "provider": "openrouter",
            "transport_provider": "openrouter",
        }

        self.assertEqual(
            settings.get_llm_request_options(route),
            {"extra_body": {"reasoning": {"enabled": False}}},
        )

    def test_doubao_route_disables_thinking(self):
        route = {
            "model_name": "doubao/seed-2.0-pro",
            "provider": "doubao",
            "transport_provider": "ark",
        }

        self.assertEqual(
            settings.get_llm_request_options(route),
            {"extra_body": {"thinking": {"type": "disabled"}}},
        )

    def test_direct_openai_route_uses_minimal_reasoning_effort(self):
        route = {
            "model_name": "gpt-5.4",
            "provider": "openai",
            "transport_provider": "openai",
        }

        self.assertEqual(
            settings.get_llm_request_options(route),
            {"extra_body": {"reasoning_effort": settings.LLM_MIN_REASONING_EFFORT}},
        )


class Step5ConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_stories_db = dict(main.stories_db)

    def tearDown(self):
        main.stories_db.clear()
        main.stories_db.update(self.original_stories_db)

    async def test_step5_schedules_scene_image_generation_in_background(self):
        story_id = "step5-background-task"
        main.stories_db[story_id] = {
            "id": story_id,
            "title": "Harbor Lights",
            "high_concept_premise": "A reunion at sea.",
            "cinematic_theme": "Hope",
            "emotional_undercurrent": "Relief",
            "setting": {"primary_location": "Harbor"},
            "characters": [{"id": "guide", "name": "Guide", "role": "npc"}],
            "acts": [{"act_number": 1, "title": "Arrival"}],
            "status": "in_progress",
            "session_id": "session-1",
            "participant_id": "participant-1",
        }

        llm_payload = {
            "opening_sequence": {
                "description": "A foggy harbor at sunrise.",
                "location": "Harbor",
                "mood": "Quiet hope",
                "inciting_incident": "A ship horn cuts through the mist.",
            },
            "initial_dialogue": [{"character_id": "guide", "content": "Look there."}],
            "branching_choices": [{"id": "c1", "text": "Walk to the dock"}],
            "hidden_elements": [],
        }
        scheduled_coroutines = []

        def _capture_task(coro):
            scheduled_coroutines.append(coro)
            return None

        with patch.object(main, "run_llm_completion", new=AsyncMock(return_value={"content": json.dumps(llm_payload), "error": None})), \
             patch.object(main, "_image_api_key_available", return_value=True), \
             patch.object(main, "_save_story_snapshot_locally", new=AsyncMock()), \
             patch.object(main, "standardize_story_response", side_effect=lambda payload: payload), \
             patch.object(main.experiment_store, "log_story_event"), \
             patch.object(main.asyncio, "create_task", side_effect=_capture_task):
            response = await main.create_story_step5(StoryStep5Input(story_id=story_id))

        for coro in scheduled_coroutines:
            coro.close()

        self.assertEqual(response.story_id, story_id)
        self.assertEqual(len(scheduled_coroutines), 1)
        self.assertEqual(scheduled_coroutines[0].cr_code.co_name, "_generate_scene_background_image")

    async def test_step4_skips_blueprint_review_when_disabled(self):
        story_id = "step4-skip-review"
        original_flag = settings.ENABLE_STORY_BLUEPRINT_REVIEW
        settings.ENABLE_STORY_BLUEPRINT_REVIEW = False
        main.stories_db[story_id] = {
            "id": story_id,
            "title": "Harbor Lights",
            "high_concept_premise": "A reunion at sea.",
            "cinematic_theme": "Hope",
            "emotional_undercurrent": "Relief",
            "setting": {"primary_location": "Harbor"},
            "characters": [{"id": "guide", "name": "Guide", "role": "npc"}],
            "status": "in_progress",
            "session_id": "session-1",
            "participant_id": "participant-1",
        }

        try:
            with patch.object(main, "run_llm_completion", new=AsyncMock(return_value={"content": json.dumps([{"id": "act-1", "title": "Arrival"}]), "error": None})), \
                 patch.object(main, "critique_and_refine_story", new=AsyncMock(side_effect=AssertionError("review should be skipped"))), \
                 patch.object(main.experiment_store, "log_story_event"):
                response = await main.create_story_step4(StoryStep4Input(story_id=story_id))

            self.assertEqual(response.story_id, story_id)
            self.assertEqual(response.acts, [{"id": "act-1", "title": "Arrival"}])
        finally:
            settings.ENABLE_STORY_BLUEPRINT_REVIEW = original_flag
