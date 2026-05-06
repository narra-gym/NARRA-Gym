import copy
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
import story_advancement  # noqa: E402
from benchmark_speed import (  # noqa: E402
    BENCHMARK_SPEED_PROFILE,
    DEFAULT_SPEED_PROFILE,
    build_runtime_story_flags,
    can_offer_end_story_choice,
    count_exchanges_from_dialogue_count,
    get_progression_count_for_dialogue_count,
)
from context_manager import ContextManager, StoryState  # noqa: E402


class _DummyLLMClient:
    def get_completion(self, *args, **kwargs):
        return {"content": '{"what_just_happened":"A turn passed.","current_goal":"Keep moving.","open_tensions":[],"active_clues":[],"last_major_turning_point":"A reveal."}'}

    def summarize_text(self, *args, **kwargs):
        return {"content": "A short rolling summary."}


def _make_messages(non_system_count: int):
    messages = []
    for index in range(non_system_count):
        character_id = "protagonist" if index % 2 == 0 else "guide"
        messages.append(
            {
                "id": f"m{index}",
                "character_id": character_id,
                "content": f"line-{index}",
                "timestamp": "2026-04-03T00:00:00",
                "type": "text",
            }
        )
    return messages


def _make_story(
    *,
    story_id: str = "story-1",
    story_mode: str = "benchmark",
    non_system_count: int = 0,
    with_transition: bool = False,
):
    benchmark = story_mode == "benchmark"
    messages = _make_messages(non_system_count)
    if with_transition:
        messages.append(
            {
                "id": "transition-initial",
                "character_id": "system",
                "content": "[MOMENTS LATER - THE BACK HALL]",
                "timestamp": "2026-04-03T00:00:00",
                "type": "system",
            }
        )
    return {
        "id": story_id,
        "story_id": story_id,
        "title": "Clockwork House",
        "theme": "Mystery",
        "cinematic_theme": "Mystery",
        "setting": "An old house full of clocks",
        "emotional_goal": "Clarity",
        "emotional_undercurrent": "Clarity",
        "status": "active",
        "participant_id": "participant-1",
        "session_id": "session-1",
        "story_mode": story_mode,
        "benchmark_speed_profile": benchmark,
        "characters": [
            {"id": "protagonist", "name": "You", "role": "protagonist"},
            {"id": "guide", "name": "Guide", "role": "npc"},
        ],
        "current_scene": {
            "messages": messages,
            "choices": [
                {"id": "c1", "text": "Open the red door"},
                {"id": "c2", "text": "Follow the ticking"},
                {"id": "c3", "text": "Call out for help"},
            ],
            "description": "Dust hangs in the air.",
            "emotional_tone": "tense",
            "location": "The front room",
            "scene_transition_caption": "MOMENTS LATER - THE BACK HALL" if with_transition else "",
        },
        "acts": [{"act_number": 1}, {"act_number": 2}],
        "current_act": 0,
        "llm_config": {},
    }


def _make_benchmark_generation_content(
    *,
    character_id: str = "guide",
    response_text: str = "The guide points to a hidden door and lowers their voice.",
    choices=None,
    tags=None,
):
    if choices is None:
        choices = [
            "Open the hidden door",
            "Ask what is behind it",
        ]
    if tags is None:
        tags = {
            "scene_shift": "no",
            "act_advance": "no",
            "ending_ready": "no",
            "objective": "Follow the newest lead before it cools.",
            "tension": "The truth may disappear if you hesitate.",
            "immediate_stakes": "Delay will cost you the clearest answer in the room.",
            "latest_reveal": "A hidden door has been quietly waiting in plain sight.",
            "relationship_shift": "The guide stops protecting you from the risk.",
            "emotional_beat": "Urgent, intimate, and finally concrete.",
            "location_status": "The room feels smaller now that the secret has a shape.",
            "next_location": "The hidden door",
        }
    tag_lines = "\n".join(f"{key}: {value}" for key, value in tags.items())
    choice_lines = "\n".join(f"- {choice}" for choice in choices)
    return (
        "<<CHARACTER_ID>>\n"
        f"{character_id}\n"
        "<<RESPONSE>>\n"
        f"{response_text}\n"
        "<<CHOICES>>\n"
        f"{choice_lines}\n"
        "<<TAGS>>\n"
        f"{tag_lines}\n"
    )


class BenchmarkSpeedProfileTests(unittest.TestCase):
    def test_turn_log_dialogue_keeps_multiline_response_as_single_record(self):
        dialogue = main.build_dialogue_records_from_turn_logs([
            {
                "id": "turn-1",
                "turn_index": 1,
                "action_type": "choice_stream",
                "user_input": "Open the hidden door.",
                "response_character_id": "guide",
                "response_text": "*The guide glances toward the hall.*\n\n\"We move now.\"",
                "created_at": "2026-04-03T00:00:00",
                "metadata": {},
            }
        ])

        self.assertEqual(len(dialogue), 2)
        self.assertEqual(dialogue[0]["content"], "Open the hidden door.")
        self.assertEqual(dialogue[1]["content"], "*The guide glances toward the hall.*\n\n\"We move now.\"")

    def test_session_dialogue_uses_opening_snapshot_plus_turn_logs_for_legacy_sessions(self):
        story_events = [
            {
                "event_type": "story_completed_generation",
                "payload": {
                    "final_story_snapshot": {
                        "characters": [
                            {"id": "protagonist", "name": "You", "role": "protagonist"},
                            {"id": "guide", "name": "Guide", "role": "npc"},
                        ],
                        "current_scene": {
                            "messages": [
                                {
                                    "id": "opening-1",
                                    "character_id": "guide",
                                    "content": "The guide waits by the hidden door.",
                                    "timestamp": "2026-04-03T00:00:00",
                                    "type": "text",
                                }
                            ]
                        },
                    }
                },
            }
        ]
        turn_logs = [
            {
                "id": "turn-1",
                "turn_index": 1,
                "action_type": "choice_stream",
                "user_input": "Open the hidden door.",
                "response_character_id": "guide",
                "response_text": "Then stay close and do not stop.",
                "created_at": "2026-04-03T00:01:00",
                "metadata": {},
            }
        ]

        dialogue, source = main.build_dialogue_records_for_session(
            story_events=story_events,
            turn_logs=turn_logs,
            story_snapshot=None,
            snapshot_event_type=None,
        )

        self.assertEqual(source, "opening_snapshot_plus_turn_logs")
        self.assertEqual(len(dialogue), 3)
        self.assertEqual(dialogue[0]["content"], "The guide waits by the hidden door.")
        self.assertEqual(dialogue[1]["content"], "Open the hidden door.")
        self.assertEqual(dialogue[2]["content"], "Then stay close and do not stop.")

    def test_benchmark_progression_uses_exchanges(self):
        self.assertEqual(count_exchanges_from_dialogue_count(9), 4)
        self.assertEqual(get_progression_count_for_dialogue_count(BENCHMARK_SPEED_PROFILE, 9), 4)
        self.assertEqual(get_progression_count_for_dialogue_count(DEFAULT_SPEED_PROFILE, 9), 9)

    def test_runtime_flags_expose_benchmark_mode(self):
        flags = build_runtime_story_flags(story={"story_mode": "benchmark"})

        self.assertEqual(flags["story_mode"], "benchmark")
        self.assertTrue(flags["benchmark_speed_profile"])
        self.assertEqual(flags["speed_profile"]["max_choices"], 3)
        self.assertEqual(flags["speed_profile"]["conclusion_countdown_turns"], 3)

    def test_endpoint_countdown_uses_profile_units(self):
        benchmark_story = _make_story(story_id="bench", story_mode="benchmark", non_system_count=32, with_transition=True)
        default_story = _make_story(story_id="default", story_mode="default", non_system_count=16)
        main.context_manager.story_states["bench"] = StoryState(story_id="bench")
        main.context_manager.story_states["default"] = StoryState(story_id="default")

        main.maybe_start_conclusion_countdown(benchmark_story)
        main.maybe_start_conclusion_countdown(default_story)

        self.assertEqual(main.context_manager.story_states["bench"].conclusion_countdown, 3)
        self.assertEqual(main.context_manager.story_states["default"].conclusion_countdown, 0)

    def test_end_choice_requires_transition_and_active_countdown(self):
        benchmark_story = _make_story(story_id="bench-no-transition", story_mode="benchmark", non_system_count=40, with_transition=False)
        transitioned_story = _make_story(story_id="bench-with-transition", story_mode="benchmark", non_system_count=40, with_transition=True)

        self.assertFalse(can_offer_end_story_choice(benchmark_story, 3))
        self.assertFalse(can_offer_end_story_choice(transitioned_story, 0))
        self.assertTrue(can_offer_end_story_choice(transitioned_story, 3))

    def test_turn_logging_includes_benchmark_telemetry(self):
        story = _make_story(non_system_count=8)
        story["llm_config"] = {"story": "openai/gpt-5.4"}
        response_messages = [{"character_id": "guide", "content": "Move now."}]

        with patch.object(main.experiment_store, "log_turn") as mock_log_turn:
            main.log_turn_if_needed(
                story=story,
                action_type="choice",
                user_input="Open the red door",
                response_messages=response_messages,
                latency_ms=1450,
                extra_metadata={
                    "reflection_used": False,
                    "interactive_used": False,
                },
            )

        metadata = mock_log_turn.call_args.kwargs["metadata"]
        self.assertTrue(metadata["benchmark_speed_profile"])
        self.assertEqual(metadata["story_mode"], "benchmark")
        self.assertEqual(metadata["exchange_count"], 4)
        self.assertEqual(metadata["latency_bucket_ms"], "1-2s")
        self.assertFalse(metadata["reflection_used"])
        self.assertFalse(metadata["interactive_used"])
        self.assertEqual(metadata["generation_mode"], "chat_native")
        self.assertEqual(metadata["state_freshness"], "derived")
        self.assertEqual(mock_log_turn.call_args.kwargs["model_provider"], "openrouter")

    def test_turn_logging_uses_story_specific_doubao_provider(self):
        story = _make_story(non_system_count=6)
        story["llm_config"] = {"story": "doubao/seed-2.0-pro"}
        response_messages = [{"character_id": "guide", "content": "Move now."}]

        with patch.object(main.experiment_store, "log_turn") as mock_log_turn:
            main.log_turn_if_needed(
                story=story,
                action_type="message",
                user_input="Keep going.",
                response_messages=response_messages,
                latency_ms=920,
            )

        self.assertEqual(mock_log_turn.call_args.kwargs["model_provider"], "doubao")

    def test_attach_story_runtime_metadata_tolerates_legacy_list_shapes(self):
        story = _make_story(non_system_count=4)
        story["story_memory"] = []
        story["story_state"] = []
        story["hidden_elements"] = []
        story["current_scene"]["scene_elements"] = []
        story["current_scene"]["scene_dynamics"] = []
        story["current_scene"]["story_state"] = []

        normalized = main.attach_story_runtime_metadata(story["id"], copy.deepcopy(story))

        self.assertIsInstance(normalized["story_memory"], dict)
        self.assertIsInstance(normalized["story_state"], dict)
        self.assertIsInstance(normalized["current_scene"], dict)
        self.assertIsInstance(normalized["current_scene"]["messages"], list)
        self.assertIsInstance(normalized["current_scene"]["choices"], list)
        self.assertIsInstance(normalized["current_scene"]["scene_elements"], dict)
        self.assertIsInstance(normalized["current_scene"]["scene_dynamics"], dict)
        self.assertIsInstance(normalized["current_scene"]["story_state"], dict)
        self.assertIn("scene_info_panel", normalized)
        self.assertIn("story_progress", normalized)
        self.assertTrue(all("render_mode" in message for message in normalized["current_scene"]["messages"]))

    def test_attach_story_runtime_metadata_marks_cast_presence_after_last_transition(self):
        story = _make_story(non_system_count=0)
        story["characters"] = [
            {"id": "protagonist", "name": "You", "role": "protagonist"},
            {"id": "guide", "name": "Guide", "role": "npc"},
            {"id": "stranger", "name": "Stranger", "role": "npc"},
        ]
        story["current_scene"]["messages"] = [
            {
                "id": "m-before",
                "character_id": "guide",
                "content": "Stay in the front room.",
                "timestamp": "2026-04-03T00:00:00",
                "type": "text",
            },
            {
                "id": "transition-1",
                "character_id": "system",
                "content": "[MOMENTS LATER - THE ANNEX]",
                "timestamp": "2026-04-03T00:01:00",
                "type": "system",
            },
            {
                "id": "m-after",
                "character_id": "stranger",
                "content": "You finally made it to the annex.",
                "timestamp": "2026-04-03T00:01:05",
                "type": "text",
            },
        ]

        normalized = main.attach_story_runtime_metadata(story["id"], copy.deepcopy(story))
        cast_statuses = {
            item["character_id"]: item
            for item in normalized["cast_statuses"]
        }

        self.assertTrue(cast_statuses["protagonist"]["in_scene_now"])
        self.assertFalse(cast_statuses["guide"]["in_scene_now"])
        self.assertTrue(cast_statuses["stranger"]["in_scene_now"])


class BenchmarkEndpointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_stories_db = dict(main.stories_db)
        self.original_story_states = dict(main.context_manager.story_states)

    def tearDown(self):
        main.stories_db.clear()
        main.stories_db.update(self.original_stories_db)
        main.context_manager.story_states.clear()
        main.context_manager.story_states.update(self.original_story_states)

    async def test_choice_endpoint_skips_reflection_in_benchmark_mode(self):
        story = _make_story(non_system_count=6)
        main.stories_db[story["id"]] = story

        with patch.object(main, "generate_reflection", new=AsyncMock(side_effect=AssertionError("reflection should be skipped"))), \
             patch.object(main, "advance_story", new=AsyncMock(return_value=story["current_scene"])) as mock_advance_story, \
             patch.object(main, "standardize_story_response", side_effect=lambda payload: payload), \
             patch.object(main, "attach_story_runtime_metadata", side_effect=lambda story_id, payload: payload), \
             patch.object(main, "extract_response_messages", return_value=[]), \
             patch.object(main, "log_turn_if_needed"), \
             patch.object(main, "log_completed_story_snapshot"):
            result = await main.select_choice(
                main.ChoiceInput(
                    story_id=story["id"],
                    choice_id="c1",
                    with_reflection=True,
                )
            )

        self.assertIs(result, story)
        self.assertIsNone(mock_advance_story.await_args.kwargs["reflection"])

    async def test_choice_endpoint_rejects_end_choice_before_it_is_unlocked(self):
        story = _make_story(story_id="benchmark-end-lock", non_system_count=8, with_transition=False)
        story["current_scene"]["choices"] = [{"id": "end_the_story_now", "text": "End the story now"}]
        main.stories_db[story["id"]] = story
        main.context_manager.story_states[story["id"]] = StoryState(story_id=story["id"], conclusion_countdown=3)

        with self.assertRaises(main.HTTPException) as exc_info:
            await main.select_choice(
                main.ChoiceInput(
                    story_id=story["id"],
                    choice_id="end_the_story_now",
                )
            )

        self.assertEqual(exc_info.exception.status_code, 400)

    async def test_progress_endpoint_keeps_step5_at_running_until_scene_exists(self):
        story = _make_story(story_id="progress-step5")
        story["status"] = "in_progress"
        story["current_step"] = 5
        story.pop("current_scene", None)
        main.stories_db[story["id"]] = story

        progress = await main.get_story_progress(story["id"])

        self.assertEqual(progress["progress"], 90)
        self.assertEqual(progress["status"], "running")

    async def test_progress_endpoint_reports_done_after_generation_finishes(self):
        story = _make_story(story_id="progress-done")
        story["status"] = "active"
        story["current_step"] = 5
        main.stories_db[story["id"]] = story

        progress = await main.get_story_progress(story["id"])

        self.assertEqual(progress["progress"], 100)
        self.assertEqual(progress["status"], "done")

    async def test_feedback_endpoint_accepts_legacy_feedback_value_payload(self):
        result = await main.submit_feedback(
            main.FeedbackInput(
                story_id="story-legacy-feedback",
                user_id="participant-legacy",
                session_id="session-legacy",
                participant_id="participant-legacy",
                feedback_type="benchmark_session_end",
                feedback_value={
                    "overall": 5,
                    "narrative": 4,
                    "emotional": 5,
                    "comment": "legacy payload still works",
                },
            )
        )

        feedback = result["feedback"]
        self.assertEqual(feedback["rating"], 5)
        self.assertEqual(feedback["scores"]["narrative"], 4)
        self.assertEqual(feedback["scores"]["emotional"], 5)
        self.assertEqual(feedback["comment"], "legacy payload still works")

    async def test_choice_stream_endpoint_emits_delta_and_done(self):
        story = _make_story(story_id="stream-choice", non_system_count=6)
        main.stories_db[story["id"]] = story

        generated = _make_benchmark_generation_content(
            response_text='*The guide leans close, rainwater still on their sleeve.*\n\n"We move now."',
            choices=["Open the hidden door", "Stop and question the guide"],
        )

        def _fake_stream(messages, model, on_chunk, task, trace_context):
            midpoint = len(generated) // 2
            on_chunk(generated[:midpoint])
            on_chunk(generated[midpoint:])
            return generated

        with patch.object(story_advancement, "stream_story_completion_sync", side_effect=_fake_stream), \
             patch.object(story_advancement, "_should_schedule_benchmark_state_patch", return_value=False), \
             patch.object(story_advancement, "is_story_stagnating", return_value=False), \
             patch.object(main, "log_turn_if_needed"), \
             patch.object(main, "log_completed_story_snapshot"):
            response = await main.stream_story_choice(
                main.ChoiceInput(
                    story_id=story["id"],
                    choice_id="c1",
                )
            )

            raw_events = []
            async for chunk in response.body_iterator:
                raw_events.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)

        parsed_events = []
        for chunk in raw_events:
            for line in chunk.splitlines():
                if line.startswith("data: "):
                    parsed_events.append(json.loads(line[6:]))

        event_types = [event["type"] for event in parsed_events]
        self.assertIn("delta", event_types)
        self.assertEqual(parsed_events[-1]["type"], "done")
        done_story = parsed_events[-1]["story"]
        self.assertEqual(done_story["current_scene"]["messages"][-1]["render_mode"], "rp_mixed")


class BenchmarkAdvanceStoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_advance_story_skips_plot_progression_and_limits_choices(self):
        story = _make_story(story_id="advance-benchmark", non_system_count=10)
        stories_db = {story["id"]: story}
        context_manager = ContextManager(_DummyLLMClient())
        context_manager.create_story_state(story["id"], story)

        with patch.object(story_advancement, "check_plot_progression", new=AsyncMock(side_effect=AssertionError("plot progression check should be skipped"))) as mock_check, \
             patch.object(story_advancement, "get_llm_completion", return_value={"content": _make_benchmark_generation_content(choices=["Open the hidden door", "Ask what is behind it", "Step away from it"]), "error": None}) as mock_get_llm_completion, \
             patch.object(story_advancement, "parse_json_response", side_effect=AssertionError("benchmark main generation should not use the legacy JSON parser")), \
             patch.object(story_advancement, "_should_schedule_benchmark_state_patch", return_value=False), \
             patch.object(story_advancement, "is_story_stagnating", return_value=False):
            updated_scene = await story_advancement.advance_story(
                story_id=story["id"],
                user_input="What changed here?",
                action_type="Message",
                context_manager=context_manager,
                stories_db=stories_db,
            )

        self.assertEqual(mock_check.await_count, 0)
        self.assertEqual(mock_get_llm_completion.call_count, 1)
        self.assertEqual(len(updated_scene["choices"]), 3)
        self.assertEqual([choice["text"] for choice in updated_scene["choices"]], ["Open the hidden door", "Ask what is behind it", "Step away from it"])
        self.assertEqual(stories_db[story["id"]]["generation_mode"], "chat_native")
        self.assertEqual(stories_db[story["id"]]["state_freshness"], "derived")
        self.assertEqual(stories_db[story["id"]]["story_state"]["latest_reveal"], "A hidden door has been quietly waiting in plain sight.")

    async def test_benchmark_choice_retry_replaces_default_fallback_choices(self):
        story = _make_story(story_id="benchmark-choice-repair", non_system_count=16)
        stories_db = {story["id"]: story}
        context_manager = ContextManager(_DummyLLMClient())
        context_manager.create_story_state(story["id"], story)
        repaired_choices = [
            "Make the guide name the person who must receive the heirloom.",
            "Grab the keys and leave before the Thursday noon deadline closes.",
            "Check the glovebox for the letter that proves who controls the estate.",
        ]

        with patch.object(story_advancement, "get_llm_completion", side_effect=[
            {"content": _make_benchmark_generation_content(choices=[]), "error": None},
            {"content": "<<CHOICES>>\n- Make the guide name the person who must receive the heirloom.\n- Grab the keys and leave before the Thursday noon deadline closes.\n- Check the glovebox for the letter that proves who controls the estate.\n", "error": None},
        ]) as mock_get_llm_completion, \
             patch.object(story_advancement, "_should_schedule_benchmark_state_patch", return_value=False), \
             patch.object(story_advancement, "is_story_stagnating", return_value=False):
            updated_scene = await story_advancement.advance_story(
                story_id=story["id"],
                user_input="Stop dodging and tell me what the letter says.",
                action_type="Message",
                context_manager=context_manager,
                stories_db=stories_db,
            )

        self.assertEqual(mock_get_llm_completion.call_count, 2)
        self.assertEqual([choice["text"] for choice in updated_scene["choices"]], repaired_choices)

    async def test_benchmark_choice_retry_keeps_fallback_when_repair_fails(self):
        story = _make_story(story_id="benchmark-choice-repair-fallback", non_system_count=16)
        stories_db = {story["id"]: story}
        context_manager = ContextManager(_DummyLLMClient())
        context_manager.create_story_state(story["id"], story)
        expected_fallback_choices = [
            "Press for the concrete truth.",
            "Take the next risky step before the lead cools.",
            "Change the leverage before the moment settles again.",
        ]

        with patch.object(story_advancement, "get_llm_completion", side_effect=[
            {"content": _make_benchmark_generation_content(choices=[]), "error": None},
            {"content": "<<CHOICES>>\n- Press for the concrete truth.\n- Take the next risky step before the lead cools.\n- Change the leverage before the moment settles again.\n", "error": None},
        ]) as mock_get_llm_completion, \
             patch.object(story_advancement, "_should_schedule_benchmark_state_patch", return_value=False), \
             patch.object(story_advancement, "is_story_stagnating", return_value=False):
            updated_scene = await story_advancement.advance_story(
                story_id=story["id"],
                user_input="Tell me why this deadline matters now.",
                action_type="Message",
                context_manager=context_manager,
                stories_db=stories_db,
            )

        self.assertEqual(mock_get_llm_completion.call_count, 2)
        self.assertEqual([choice["text"] for choice in updated_scene["choices"]], expected_fallback_choices)

    async def test_scene_transition_does_not_auto_advance_act_without_flag(self):
        story = _make_story(story_id="benchmark-no-act-advance", non_system_count=10)
        stories_db = {story["id"]: story}
        context_manager = ContextManager(_DummyLLMClient())
        context_manager.create_story_state(story["id"], story)

        with patch.object(story_advancement, "get_llm_completion", return_value={"content": _make_benchmark_generation_content(tags={"scene_shift": "yes", "act_advance": "no", "ending_ready": "no", "objective": "Follow the guide into the next room.", "tension": "The lead could vanish if you hesitate.", "immediate_stakes": "The surveillance window is closing.", "latest_reveal": "The clue points toward the back office.", "relationship_shift": "The guide stops withholding the route.", "emotional_beat": "Urgent and focused.", "location_status": "The front room no longer matters.", "next_location": "The back office"}), "error": None}), \
             patch.object(story_advancement, "_should_schedule_benchmark_state_patch", return_value=False), \
             patch.object(story_advancement, "is_story_stagnating", return_value=False):
            await story_advancement.advance_story(
                story_id=story["id"],
                user_input="Show me the next room.",
                action_type="Message",
                context_manager=context_manager,
                stories_db=stories_db,
            )

        self.assertEqual(story["current_act"], 0)
        self.assertTrue(story["current_scene"]["scene_dynamics"]["transition_required"])

    async def test_mandatory_shift_window_no_longer_invents_pseudo_transition(self):
        story = _make_story(story_id="benchmark-forced-transition", non_system_count=16)
        stories_db = {story["id"]: story}
        context_manager = ContextManager(_DummyLLMClient())
        context_manager.create_story_state(story["id"], story)

        with patch.object(story_advancement, "get_llm_completion", return_value={"content": _make_benchmark_generation_content(tags={"scene_shift": "no", "act_advance": "no", "ending_ready": "no", "objective": "Press the witness before the lead goes cold.", "tension": "The answer is almost here, but it could slip away.", "immediate_stakes": "If you stay in this beat too long, the witness may shut down.", "latest_reveal": "The witness finally admits the camera saw more than they said.", "relationship_shift": "The witness stops stonewalling you.", "emotional_beat": "Tight and exposed.", "location_status": "The room can no longer hold the pressure.", "next_location": "The same room"}), "error": None}), \
             patch.object(story_advancement, "_should_schedule_benchmark_state_patch", return_value=False), \
             patch.object(story_advancement, "is_story_stagnating", return_value=False):
            await story_advancement.advance_story(
                story_id=story["id"],
                user_input="Tell me what the camera really saw.",
                action_type="Message",
                context_manager=context_manager,
                stories_db=stories_db,
            )

        self.assertEqual(story["current_act"], 0)
        self.assertFalse(story["current_scene"]["scene_dynamics"].get("transition_required"))
        self.assertFalse(story["current_scene"].get("scene_transition_caption"))
        self.assertFalse(
            any(str(message.get("id", "")).startswith("transition-") for message in story["current_scene"]["messages"])
        )

    async def test_explicit_time_jump_same_location_still_generates_transition(self):
        story = _make_story(story_id="benchmark-time-jump", non_system_count=16)
        stories_db = {story["id"]: story}
        context_manager = ContextManager(_DummyLLMClient())
        context_manager.create_story_state(story["id"], story)

        with patch.object(story_advancement, "get_llm_completion", return_value={"content": _make_benchmark_generation_content(tags={"scene_shift": "yes", "act_advance": "no", "ending_ready": "no", "objective": "Stay in the room long enough for the truth to land.", "tension": "The silence is about to break.", "immediate_stakes": "If you move too soon, the confession may close again.", "latest_reveal": "The room itself was never the issue; the timing was.", "relationship_shift": "The guide finally lets the pause do its work.", "emotional_beat": "Measured and inevitable.", "location_status": "The same room now feels like a later version of itself.", "next_location": "The front room"}), "error": None}), \
             patch.object(story_advancement, "_should_schedule_benchmark_state_patch", return_value=False), \
             patch.object(story_advancement, "is_story_stagnating", return_value=False):
            await story_advancement.advance_story(
                story_id=story["id"],
                user_input="Wait with me a moment longer.",
                action_type="Message",
                context_manager=context_manager,
                stories_db=stories_db,
            )

        self.assertTrue(story["current_scene"]["scene_dynamics"]["transition_required"])
        self.assertEqual(story["current_scene"]["location"], "The front room")
        self.assertEqual(story["current_scene"]["scene_transition_caption"], "MOMENTS LATER - THE FRONT ROOM")
        self.assertTrue(
            any(str(message.get("id", "")).startswith("transition-") for message in story["current_scene"]["messages"])
        )

    async def test_act_advances_only_when_explicitly_requested(self):
        story = _make_story(story_id="benchmark-explicit-act-advance", non_system_count=10)
        stories_db = {story["id"]: story}
        context_manager = ContextManager(_DummyLLMClient())
        context_manager.create_story_state(story["id"], story)

        with patch.object(story_advancement, "get_llm_completion", return_value={"content": _make_benchmark_generation_content(tags={"scene_shift": "yes", "act_advance": "yes", "ending_ready": "no", "objective": "Cross into the confrontation phase.", "tension": "The truth is now in reach.", "immediate_stakes": "If you back off, the act break collapses.", "latest_reveal": "The hidden room is the real heart of the case.", "relationship_shift": "The guide finally commits to your side.", "emotional_beat": "Charged and decisive.", "location_status": "The story has clearly turned.", "next_location": "The hidden room"}), "error": None}), \
             patch.object(story_advancement, "_should_schedule_benchmark_state_patch", return_value=False), \
             patch.object(story_advancement, "is_story_stagnating", return_value=False):
            await story_advancement.advance_story(
                story_id=story["id"],
                user_input="Take me where this really starts.",
                action_type="Message",
                context_manager=context_manager,
                stories_db=stories_db,
            )

        self.assertEqual(story["current_act"], 1)

    async def test_benchmark_messages_store_mixed_render_mode_without_intro_injection(self):
        story = _make_story(story_id="benchmark-render-mode", non_system_count=0)
        stories_db = {story["id"]: story}
        context_manager = ContextManager(_DummyLLMClient())
        context_manager.create_story_state(story["id"], story)

        with patch.object(story_advancement, "get_llm_completion", return_value={"content": _make_benchmark_generation_content(response_text='*The guide wipes rain from the file folder and finally meets your eyes.*\n\n"I found the timestamp."', tags={"scene_shift": "no", "act_advance": "no", "ending_ready": "no", "objective": "Read the timestamp before the lead cools.", "tension": "The truth is almost visible.", "immediate_stakes": "If you miss the window, the evidence may disappear.", "latest_reveal": "The file holds the exact time of the handoff.", "relationship_shift": "The guide stops speaking around the evidence.", "emotional_beat": "Close and electric.", "location_status": "The room contracts around the folder.", "next_location": "The same room"}), "error": None}), \
             patch.object(story_advancement, "_should_schedule_benchmark_state_patch", return_value=False), \
             patch.object(story_advancement, "is_story_stagnating", return_value=False):
            updated_scene = await story_advancement.advance_story(
                story_id=story["id"],
                user_input="What did you find?",
                action_type="Message",
                context_manager=context_manager,
                stories_db=stories_db,
            )

        npc_messages = [message for message in updated_scene["messages"] if message.get("character_id") == "guide" and message.get("type") == "text"]
        self.assertTrue(npc_messages)
        self.assertEqual(npc_messages[-1]["render_mode"], "rp_mixed")
        self.assertNotIn("Hello, I'm Guide", npc_messages[-1]["content"])

    def test_benchmark_parser_strips_leaked_state_block(self):
        story = _make_story(story_id="leaked-tags", non_system_count=0)
        protagonist = next(character for character in story["characters"] if character["role"] == "protagonist")
        parsed = story_advancement._parse_benchmark_main_generation(
            "<<CHARACTER_ID>>\n"
            "guide\n"
            "<<RESPONSE>>\n"
            "*The guide glances at the door.*\n\n"
            "\"We still have time.\"\n"
            "scene_shift: no\n"
            "act_advance: yes\n"
            "ending_ready: yes\n"
            "objective: Finish this now.\n",
            story=story,
            protagonist=protagonist,
            target_character_id=None,
        )

        self.assertEqual(parsed["assistant_text"], "*The guide glances at the door.*\n\n\"We still have time.\"")

    async def test_benchmark_countdown_completes_after_three_turns(self):
        story = _make_story(story_id="countdown-benchmark", non_system_count=31, with_transition=True)
        stories_db = {story["id"]: story}
        context_manager = ContextManager(_DummyLLMClient())
        context_manager.create_story_state(story["id"], story)

        with patch.object(story_advancement, "check_plot_progression", new=AsyncMock(side_effect=AssertionError("plot progression check should be skipped"))), \
             patch.object(story_advancement, "get_llm_completion", return_value={"content": _make_benchmark_generation_content(response_text="The hallway narrows toward a final answer.", choices=["Keep walking", "Stop and listen"], tags={"scene_shift": "no", "ending_ready": "yes", "objective": "Finish what the corridor has been hiding.", "tension": "There is no room left for delay.", "immediate_stakes": "One more hesitation could close the ending entirely.", "latest_reveal": "The final answer is already waiting ahead.", "relationship_shift": "The guide stops holding back the truth.", "emotional_beat": "Inevitable and urgent.", "location_status": "Every sound points deeper into the corridor.", "next_location": "The final corridor"}), "error": None}), \
             patch.object(story_advancement, "_should_schedule_benchmark_state_patch", return_value=False), \
             patch.object(story_advancement, "is_story_stagnating", return_value=False):
            await story_advancement.advance_story(
                story_id=story["id"],
                user_input="I keep going.",
                action_type="Message",
                context_manager=context_manager,
                stories_db=stories_db,
            )
            self.assertEqual(context_manager.story_states[story["id"]].conclusion_countdown, 2)
            self.assertEqual(story["status"], "active")

            await story_advancement.advance_story(
                story_id=story["id"],
                user_input="I'm almost there.",
                action_type="Message",
                context_manager=context_manager,
                stories_db=stories_db,
            )
            self.assertEqual(context_manager.story_states[story["id"]].conclusion_countdown, 1)
            self.assertEqual(story["status"], "active")

            await story_advancement.advance_story(
                story_id=story["id"],
                user_input="End it cleanly.",
                action_type="Message",
                context_manager=context_manager,
                stories_db=stories_db,
            )

        self.assertEqual(context_manager.story_states[story["id"]].conclusion_countdown, 0)
        self.assertEqual(story["status"], "completed")
        self.assertTrue(
            any(
                str(choice.get("text", "")).strip().lower() == "end the story now"
                for choice in story["current_scene"]["choices"]
            )
        )

    async def test_benchmark_state_patch_runs_in_background_without_blocking_turn(self):
        story = _make_story(story_id="state-patch-benchmark", non_system_count=6)
        stories_db = {story["id"]: story}
        context_manager = ContextManager(_DummyLLMClient())
        context_manager.create_story_state(story["id"], story)

        scheduled_tasks = []

        def _fake_create_task(coro):
            scheduled_tasks.append(coro)
            coro.close()
            return None

        with patch.object(story_advancement, "get_llm_completion", return_value={"content": _make_benchmark_generation_content(), "error": None}), \
             patch.object(story_advancement, "parse_json_response", side_effect=AssertionError("benchmark main generation should not use the legacy JSON parser")), \
             patch.object(story_advancement, "_should_schedule_benchmark_state_patch", return_value=True), \
             patch.object(story_advancement.asyncio, "create_task", side_effect=_fake_create_task), \
             patch.object(story_advancement, "is_story_stagnating", return_value=False):
            updated_scene = await story_advancement.advance_story(
                story_id=story["id"],
                user_input="Show me what changed.",
                action_type="Message",
                context_manager=context_manager,
                stories_db=stories_db,
            )

        self.assertTrue(updated_scene["choices"])
        self.assertTrue(stories_db[story["id"]]["_benchmark_state_patch_scheduled"])
        self.assertTrue(stories_db[story["id"]]["_benchmark_state_patch_inflight"])
        self.assertEqual(len(scheduled_tasks), 1)

    async def test_benchmark_generation_tolerates_legacy_hidden_elements_list_shape(self):
        story = _make_story(story_id="legacy-hidden-elements", non_system_count=6)
        story["current_scene"]["hidden_elements"] = [
            {"type": "foreshadowing", "description": "A torn receipt points toward the store camera."}
        ]
        stories_db = {story["id"]: story}
        context_manager = ContextManager(_DummyLLMClient())
        context_manager.create_story_state(story["id"], story)

        with patch.object(story_advancement, "get_llm_completion", return_value={"content": _make_benchmark_generation_content(), "error": None}), \
             patch.object(story_advancement, "_should_schedule_benchmark_state_patch", return_value=False), \
             patch.object(story_advancement, "is_story_stagnating", return_value=False):
            updated_scene = await story_advancement.advance_story(
                story_id=story["id"],
                user_input="先去便利店查看监控。",
                action_type="Choice",
                context_manager=context_manager,
                stories_db=stories_db,
            )

        self.assertTrue(updated_scene["messages"])
        self.assertEqual(stories_db[story["id"]]["generation_mode"], "chat_native")


if __name__ == "__main__":
    unittest.main()
