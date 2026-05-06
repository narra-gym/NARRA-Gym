import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


CURRENT_DIR = os.path.dirname(__file__)
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
BACKEND_SRC = os.path.abspath(os.path.join(CURRENT_DIR, "..", "src"))
for path in (BACKEND_DIR, BACKEND_SRC):
    if path not in sys.path:
        sys.path.insert(0, path)


import main  # noqa: E402
from config import (  # noqa: E402
    DEFAULT_ARK_BASE_URL,
    DEFAULT_OPENROUTER_BASE_URL,
    DOUBAO_SEED_CANONICAL_MODEL,
    Settings,
)
from experiment_store import ExperimentStore  # noqa: E402


class BenchmarkModelRoutingTests(unittest.TestCase):
    def build_settings(self, **overrides) -> Settings:
        with patch.dict(os.environ, {}, clear=True):
            base_kwargs = {
                "LLM_API_KEY": "fallback-key",
                "OPENAI_API_KEY": "fallback-key",
                "OPENROUTER_APP_NAME": "EmoNest",
            }
            base_kwargs.update(overrides)
            return Settings(
                **base_kwargs,
            )

    def build_client(self, settings: Settings, *, blind_mode: bool = False):
        fd, db_path = tempfile.mkstemp(suffix="-emobenchmark.sqlite3")
        os.close(fd)
        store = ExperimentStore(db_path)

        settings_patch = patch.object(main, "settings", settings)
        store_patch = patch.object(main, "experiment_store", store)
        env_patch = patch.dict(
            os.environ,
            {"BENCHMARK_RANDOM_MODE": "1"} if blind_mode else {},
            clear=False,
        )

        settings_patch.start()
        store_patch.start()
        env_patch.start()
        self.addCleanup(settings_patch.stop)
        self.addCleanup(store_patch.stop)
        self.addCleanup(env_patch.stop)
        def _cleanup_db():
            try:
                if os.path.exists(db_path):
                    os.remove(db_path)
            except OSError:
                pass

        self.addCleanup(_cleanup_db)

        client = TestClient(main.app)
        self.addCleanup(client.close)
        return client, store

    def test_default_benchmark_model_options_include_all_eight_models(self):
        settings = self.build_settings(
            OPENROUTER_API_KEY="openrouter-key",
            OPENROUTER_SITE_URL="https://emonest.example",
            ARK_API_KEY="ark-key",
            DOUBAO_SEED_2_0_PRO_ENDPOINT_ID="ep-20260404",
        )

        options = settings.get_benchmark_model_options()
        option_map = {option["id"]: option for option in options}

        self.assertEqual(len(options), 8)
        self.assertTrue(all("provider" in option for option in options))
        self.assertTrue(option_map["openai/gpt-5.4"]["available"])
        self.assertEqual(option_map["openai/gpt-5.4"]["provider"], "openrouter")
        self.assertTrue(option_map[DOUBAO_SEED_CANONICAL_MODEL]["available"])
        self.assertEqual(option_map[DOUBAO_SEED_CANONICAL_MODEL]["provider"], "doubao")

    def test_openrouter_route_uses_openrouter_transport(self):
        settings = self.build_settings(
            OPENROUTER_API_KEY="openrouter-key",
            OPENROUTER_SITE_URL="https://emonest.example",
            OPENROUTER_APP_NAME="EmoNest QA",
        )

        route = settings.get_model_route("openai/gpt-5.4")

        self.assertEqual(route["provider"], "openrouter")
        self.assertEqual(route["transport_provider"], "openrouter")
        self.assertEqual(route["base_url"], DEFAULT_OPENROUTER_BASE_URL)
        self.assertEqual(route["api_key"], "openrouter-key")
        self.assertEqual(route["api_model"], "openai/gpt-5.4")
        self.assertEqual(route["default_headers"]["HTTP-Referer"], "https://emonest.example")
        self.assertEqual(route["default_headers"]["X-Title"], "EmoNest QA")
        self.assertTrue(route["available"])

    def test_doubao_route_marks_missing_credentials_unavailable(self):
        settings = self.build_settings(
            OPENROUTER_API_KEY="openrouter-key",
            ARK_API_KEY=None,
        )

        route = settings.get_model_route(DOUBAO_SEED_CANONICAL_MODEL)

        self.assertEqual(route["provider"], "doubao")
        self.assertEqual(route["transport_provider"], "ark")
        self.assertEqual(route["base_url"], DEFAULT_ARK_BASE_URL)
        self.assertFalse(route["available"])
        self.assertIn("ARK_API_KEY", route["availability_reason"])

    def test_doubao_route_falls_back_to_official_model_name_without_custom_endpoint(self):
        settings = self.build_settings(
            OPENROUTER_API_KEY="openrouter-key",
            ARK_API_KEY="ark-key",
        )

        route = settings.get_model_route(DOUBAO_SEED_CANONICAL_MODEL)

        self.assertTrue(route["available"])
        self.assertEqual(route["api_model"], "doubao-seed-2-0-pro-260215")
        self.assertEqual(route["base_url"], DEFAULT_ARK_BASE_URL)

    def test_models_endpoint_returns_provider_and_availability_fields(self):
        settings = self.build_settings(
            OPENROUTER_API_KEY="openrouter-key",
            ARK_API_KEY="ark-key",
            DOUBAO_SEED_2_0_PRO_ENDPOINT_ID="ep-20260404",
        )

        with patch.object(main, "settings", settings):
            client = TestClient(main.app)
            response = client.get("/experiments/models")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 8)
        doubao = next(option for option in payload if option["id"] == DOUBAO_SEED_CANONICAL_MODEL)
        self.assertEqual(doubao["provider"], "doubao")
        self.assertTrue(doubao["available"])

    def test_start_session_endpoint_rejects_unavailable_model(self):
        settings = self.build_settings(
            OPENROUTER_API_KEY="openrouter-key",
            ARK_API_KEY=None,
        )

        with patch.object(main, "settings", settings):
            client = TestClient(main.app)
            response = client.post(
                "/experiments/session/start",
                json={
                    "selected_model": DOUBAO_SEED_CANONICAL_MODEL,
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("ARK_API_KEY", response.json()["detail"])

    def test_selected_benchmark_model_overrides_all_non_image_text_tasks(self):
        settings = self.build_settings(
            OPENROUTER_API_KEY="openrouter-key",
            OPENROUTER_SITE_URL="https://emonest.example",
            ARK_API_KEY="ark-key",
        )
        client, store = self.build_client(settings)

        response = client.post(
            "/experiments/session/start",
            json={
                "selected_model": DOUBAO_SEED_CANONICAL_MODEL,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        session = store.get_session(payload["session_id"])
        expected_config = {
            task: DOUBAO_SEED_CANONICAL_MODEL
            for task in settings.BENCHMARK_TASKS
        }

        self.assertEqual(session["selected_model"], DOUBAO_SEED_CANONICAL_MODEL)
        self.assertEqual(session["llm_config_override"], expected_config)

        experiment_meta = main.build_story_experiment_metadata(
            payload["session_id"],
            payload["participant_id"],
        )
        self.assertEqual(experiment_meta["llm_config"], expected_config)

    def test_blind_mapping_uses_each_model_ten_times(self):
        model_counts = {}
        for blind_code in range(1, 21):
            for model_id in main.get_blind_benchmark_sequence_for_code(blind_code):
                model_counts[model_id] = model_counts.get(model_id, 0) + 1

        self.assertEqual(set(model_counts.values()), {10})
        self.assertEqual(len(model_counts), 8)

    def test_blind_mode_accepts_invite_code_and_returns_invite_code(self):
        settings = self.build_settings(
            OPENROUTER_API_KEY="openrouter-key",
            OPENROUTER_SITE_URL="https://emonest.example",
            ARK_API_KEY="ark-key",
            DOUBAO_SEED_2_0_PRO_ENDPOINT_ID="ep-20260404",
        )
        client, _ = self.build_client(settings, blind_mode=True)
        invite_code = main.get_blind_invite_code(7)

        response = client.post("/experiments/session/start", json={"blind_code": invite_code})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["blind_code"], 7)
        self.assertEqual(payload["blind_invite_code"], invite_code)

    def test_blind_mode_rejects_invalid_code(self):
        settings = self.build_settings(
            OPENROUTER_API_KEY="openrouter-key",
            OPENROUTER_SITE_URL="https://emonest.example",
            ARK_API_KEY="ark-key",
            DOUBAO_SEED_2_0_PRO_ENDPOINT_ID="ep-20260404",
        )
        client, _ = self.build_client(settings, blind_mode=True)

        response = client.post("/experiments/session/start", json={"blind_code": "NOT-A-CODE"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("invite code", response.json()["detail"].lower())

    def test_blind_mode_rejects_noncanonical_model_count(self):
        settings = self.build_settings(
            OPENROUTER_API_KEY="openrouter-key",
            OPENROUTER_SITE_URL="https://emonest.example",
            ARK_API_KEY="ark-key",
            DOUBAO_SEED_2_0_PRO_ENDPOINT_ID="ep-20260404",
            BENCHMARK_MODEL_OPTIONS_JSON="""[
              {"id":"openai/gpt-5.4","label":"OpenAI GPT-5.4"},
              {"id":"anthropic/claude-opus-4.6","label":"Anthropic Claude Opus 4.6"},
              {"id":"anthropic/claude-sonnet-4.6","label":"Anthropic Claude Sonnet 4.6"},
              {"id":"google/gemini-3.1-pro-preview","label":"Google Gemini 3.1 Pro Preview"},
              {"id":"deepseek/deepseek-v3.2","label":"DeepSeek V3.2"},
              {"id":"z-ai/glm-5.1","label":"Z.AI GLM-5.1"},
              {"id":"qwen/qwen3.5-397b-a17b","label":"Qwen 3.5 397B A17B"},
              {"id":"doubao/seed-2.0-pro","label":"Doubao Seed 2.0 Pro (Official)"},
              {"id":"extra/model-9","label":"Extra Model 9"}
            ]""",
        )
        client, _ = self.build_client(settings, blind_mode=True)

        response = client.post("/experiments/session/start", json={"blind_code": 1})

        self.assertEqual(response.status_code, 400)
        self.assertIn("exactly 8 available benchmark models", response.json()["detail"])

    def test_blind_mode_reuses_active_session_and_advances_only_after_completion(self):
        settings = self.build_settings(
            OPENROUTER_API_KEY="openrouter-key",
            OPENROUTER_SITE_URL="https://emonest.example",
            ARK_API_KEY="ark-key",
            DOUBAO_SEED_2_0_PRO_ENDPOINT_ID="ep-20260404",
        )
        client, store = self.build_client(settings, blind_mode=True)

        first = client.post("/experiments/session/start", json={"blind_code": 1})
        self.assertEqual(first.status_code, 200)
        first_payload = first.json()
        self.assertTrue(first_payload["blind_mode"])
        self.assertEqual(first_payload["blind_session_index"], 1)
        self.assertIsNone(first_payload["selected_model"])

        resumed = client.post("/experiments/session/start", json={"blind_code": 1})
        self.assertEqual(resumed.status_code, 200)
        resumed_payload = resumed.json()
        self.assertEqual(resumed_payload["session_id"], first_payload["session_id"])
        self.assertEqual(resumed_payload["blind_session_index"], 1)

        stored_session = store.get_session(first_payload["session_id"])
        store.complete_session(stored_session["session_id"])

        second = client.post("/experiments/session/start", json={"blind_code": 1})
        self.assertEqual(second.status_code, 200)
        second_payload = second.json()
        self.assertNotEqual(second_payload["session_id"], first_payload["session_id"])
        self.assertEqual(second_payload["blind_session_index"], 2)
        self.assertEqual(second_payload["blind_completed_count"], 1)

    def test_blind_mode_blocks_fifth_session(self):
        settings = self.build_settings(
            OPENROUTER_API_KEY="openrouter-key",
            OPENROUTER_SITE_URL="https://emonest.example",
            ARK_API_KEY="ark-key",
            DOUBAO_SEED_2_0_PRO_ENDPOINT_ID="ep-20260404",
        )
        client, store = self.build_client(settings, blind_mode=True)

        for _ in range(4):
            response = client.post("/experiments/session/start", json={"blind_code": 1})
            self.assertEqual(response.status_code, 200)
            store.complete_session(response.json()["session_id"])

        blocked = client.post("/experiments/session/start", json={"blind_code": 1})

        self.assertEqual(blocked.status_code, 409)
        self.assertIn("already complete", blocked.json()["detail"])

    def test_quick_test_code_zero_cycles_through_hidden_slots(self):
        settings = self.build_settings(
            OPENROUTER_API_KEY="openrouter-key",
            OPENROUTER_SITE_URL="https://emonest.example",
            ARK_API_KEY="ark-key",
            DOUBAO_SEED_2_0_PRO_ENDPOINT_ID="ep-20260404",
        )
        client, store = self.build_client(settings, blind_mode=True)

        first = client.post("/experiments/session/start", json={"blind_code": 0})
        self.assertEqual(first.status_code, 200)
        first_payload = first.json()
        self.assertTrue(first_payload["quick_test_mode"])
        self.assertEqual(first_payload["blind_code"], 0)
        self.assertEqual(first_payload["blind_session_index"], 1)
        self.assertEqual(first_payload["blind_total_sessions"], 4)

        store.complete_session(first_payload["session_id"])

        second = client.post("/experiments/session/start", json={"blind_code": 0})
        self.assertEqual(second.status_code, 200)
        second_payload = second.json()
        self.assertTrue(second_payload["quick_test_mode"])
        self.assertEqual(second_payload["blind_session_index"], 2)
        self.assertEqual(second_payload["quick_test_completed_runs"], 1)

    def test_quick_test_code_zero_blocks_fifth_session(self):
        settings = self.build_settings(
            OPENROUTER_API_KEY="openrouter-key",
            OPENROUTER_SITE_URL="https://emonest.example",
            ARK_API_KEY="ark-key",
            DOUBAO_SEED_2_0_PRO_ENDPOINT_ID="ep-20260404",
        )
        client, store = self.build_client(settings, blind_mode=True)

        for _ in range(4):
            response = client.post("/experiments/session/start", json={"blind_code": 0})
            self.assertEqual(response.status_code, 200)
            store.complete_session(response.json()["session_id"])

        blocked = client.post("/experiments/session/start", json={"blind_code": 0})

        self.assertEqual(blocked.status_code, 409)
        self.assertIn("already complete", blocked.json()["detail"])

    def test_quick_test_story_starts_in_endgame_ready_state(self):
        settings = self.build_settings(
            OPENROUTER_API_KEY="openrouter-key",
            OPENROUTER_SITE_URL="https://emonest.example",
            ARK_API_KEY="ark-key",
            DOUBAO_SEED_2_0_PRO_ENDPOINT_ID="ep-20260404",
        )
        client, _ = self.build_client(settings, blind_mode=True)

        started = client.post("/experiments/session/start", json={"blind_code": 0})
        self.assertEqual(started.status_code, 200)
        session = started.json()

        story_response = client.post(
            "/stories/quickstart",
            json={
                "user_id": session["participant_id"],
                "participant_id": session["participant_id"],
                "session_id": session["session_id"],
            },
        )

        self.assertEqual(story_response.status_code, 200)
        payload = story_response.json()
        self.assertEqual(payload["story_mode"], "benchmark")
        self.assertEqual(payload["conclusion_countdown"], 1)
        self.assertTrue(
            any(choice["text"] == "End the story now" for choice in payload["current_scene"]["choices"])
        )

    def test_blind_session_detail_is_sanitized_but_export_keeps_selected_model(self):
        settings = self.build_settings(
            OPENROUTER_API_KEY="openrouter-key",
            OPENROUTER_SITE_URL="https://emonest.example",
            ARK_API_KEY="ark-key",
            DOUBAO_SEED_2_0_PRO_ENDPOINT_ID="ep-20260404",
        )
        client, store = self.build_client(settings, blind_mode=True)

        created = client.post("/experiments/session/start", json={"blind_code": 1})
        self.assertEqual(created.status_code, 200)
        session_id = created.json()["session_id"]
        participant_id = created.json()["participant_id"]
        raw_session = store.get_session(session_id)

        store.log_turn(
            session_id=session_id,
            participant_id=participant_id,
            story_id="story-1",
            action_type="choice",
            user_input="Open the door.",
            response_text="The guide nods.",
            llm_config={"story": "openai/gpt-5.4"},
            model_provider="openrouter",
        )
        store.log_llm_call(
            {
                "session_id": session_id,
                "participant_id": participant_id,
                "story_id": "story-1",
                "source": "story_turn",
                "task": "story",
                "model_provider": "openrouter",
                "model_name": "openai/gpt-5.4",
                "request_messages": [],
                "response_text": "The guide nods.",
            }
        )
        store.log_story_event(
            event_type="story_ended",
            session_id=session_id,
            participant_id=participant_id,
            story_id="story-1",
            payload={
                "final_story_snapshot": {
                    "id": "story-1",
                    "llm_config": {"story": "openai/gpt-5.4"},
                    "current_scene": {"messages": []},
                }
            },
        )

        detail = client.get(f"/experiments/sessions/{session_id}")
        self.assertEqual(detail.status_code, 200)
        detail_payload = detail.json()
        self.assertIsNone(detail_payload["session"]["selected_model"])
        self.assertEqual(detail_payload["llm_call_logs"][0]["model_name"], None)
        self.assertEqual(detail_payload["llm_call_logs"][0]["model_provider"], None)
        self.assertEqual(detail_payload["turn_logs"][0]["llm_config"], {})
        self.assertNotIn("llm_config", detail_payload["story_snapshot"])
        self.assertIsNone(detail_payload["story_snapshot"]["selected_model"])

        exported = client.get(f"/experiments/sessions/{session_id}/export")
        self.assertEqual(exported.status_code, 200)
        export_payload = exported.json()
        self.assertEqual(export_payload["session"]["selected_model"], raw_session["selected_model"])
        self.assertEqual(export_payload["llm_call_logs"][0]["model_name"], "openai/gpt-5.4")


if __name__ == "__main__":
    unittest.main()
