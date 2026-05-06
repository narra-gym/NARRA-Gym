import os
import sys
import unittest


CURRENT_DIR = os.path.dirname(__file__)
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
BACKEND_SRC = os.path.abspath(os.path.join(CURRENT_DIR, '..', 'src'))
for path in (BACKEND_DIR, BACKEND_SRC):
    if path not in sys.path:
        sys.path.insert(0, path)


from benchmark_judge import (  # noqa: E402
    compute_slop_stats,
    normalize_benchmark_judge_payload,
    parse_benchmark_judge_result,
)


class BenchmarkJudgeTests(unittest.TestCase):
    def test_normalize_payload_accepts_conclusion_export_shape(self):
        payload = {
            "schema_version": "benchmark_result_v1",
            "export_type": "benchmark_result",
            "session": {
                "session_id": "session-1",
                "participant_id": "participant-1",
                "selected_model": "openai/gpt-5.4",
            },
            "story": {
                "id": "story-1",
                "title": "Late Night",
                "user_id": "participant-1",
                "current_scene": {
                    "messages": [
                        {"id": "m1", "character_id": "protagonist", "content": "I feel stuck.", "type": "text"},
                        {"id": "m2", "character_id": "guide", "content": "Let's slow down and look at what hurts most.", "type": "text"},
                    ]
                },
                "characters": [
                    {"id": "protagonist", "name": "You", "role": "protagonist"},
                    {"id": "guide", "name": "Guide", "role": "npc"},
                ],
            },
            "dialogue_source": "current_scene",
            "dialogue": [
                {"id": "d1", "speaker": "You", "role": "user", "content": "I feel stuck."},
                {"id": "d2", "speaker": "Guide", "role": "assistant", "content": "Let's slow down and look at what hurts most."},
            ],
            "turn_logs": [],
            "llm_call_logs": [],
            "feedback_logs": [],
            "participant_evaluation": {
                "rating": 5,
                "comment": "Grounded and emotionally coherent.",
            },
        }

        normalized = normalize_benchmark_judge_payload(payload)

        self.assertEqual(normalized["schema_version"], "benchmark_result_v1")
        self.assertEqual(normalized["export_type"], "benchmark_result")
        self.assertEqual(normalized["participant_evaluation"]["rating"], 5)
        self.assertEqual(normalized["dialogue_source"], "current_scene")
        self.assertEqual(len(normalized["dialogue"]), 2)
        self.assertEqual(normalized["final_view_story"]["title"], "Late Night")

    def test_normalize_payload_accepts_session_detail_shape(self):
        payload = {
            "session": {
                "session_id": "session-2",
                "participant_id": "participant-2",
                "story_id": "story-2",
                "selected_model": "openai/gpt-5.4",
            },
            "dialogue_source": "saved_dialogue",
            "dialogue": [
                {"id": "d1", "speaker": "System", "role": "system", "content": "Rain taps against the windows."},
                {"id": "d2", "speaker": "Friend", "role": "assistant", "content": "You do not need to rush the answer."},
            ],
            "turn_logs": [{"id": "t1", "user_input": "I need help", "response_text": "Let's pause first."}],
            "feedback_logs": [{"id": "f1", "rating": 4}],
            "llm_call_logs": [{"id": "l1"}],
        }

        normalized = normalize_benchmark_judge_payload(payload)

        self.assertEqual(normalized["session"]["session_id"], "session-2")
        self.assertEqual(len(normalized["dialogue"]), 2)
        self.assertEqual(len(normalized["turn_logs"]), 1)

    def test_normalize_payload_accepts_export_bundle_with_snapshot_fallback(self):
        payload = {
            "export_bundle": {
                "session": {
                    "session_id": "session-3",
                    "participant_id": "participant-3",
                },
                "dialogue": [],
                "turn_logs": [],
                "story_snapshot": {
                    "id": "story-3",
                    "user_id": "participant-3",
                    "characters": [
                        {"id": "protagonist", "name": "You", "role": "protagonist"},
                        {"id": "npc-1", "name": "Lantern", "role": "npc"},
                    ],
                    "current_scene": {
                        "messages": [
                            {"id": "m1", "character_id": "protagonist", "content": "I cannot sleep.", "type": "text"},
                            {"id": "m2", "character_id": "npc-1", "content": "Then we can sit with the night for a moment.", "type": "text"},
                        ]
                    },
                },
            }
        }

        normalized = normalize_benchmark_judge_payload(payload)

        self.assertEqual(normalized["dialogue_source"], "story_snapshot")
        self.assertEqual(len(normalized["dialogue"]), 2)
        self.assertEqual(normalized["dialogue"][1]["speaker"], "Lantern")

    def test_normalize_payload_prefers_turn_logs_before_snapshot_fallback(self):
        payload = {
            "session": {
                "session_id": "session-4",
                "participant_id": "participant-4",
            },
            "dialogue": [],
            "turn_logs": [
                {
                    "id": "t1",
                    "turn_index": 1,
                    "user_input": "I do not know what to say.",
                    "response_text": "You can start with the smallest honest sentence.",
                    "response_character_id": "guide",
                }
            ],
            "story_snapshot": {
                "id": "story-4",
                "characters": [
                    {"id": "protagonist", "name": "You", "role": "protagonist"},
                    {"id": "npc-1", "name": "Lantern", "role": "npc"},
                ],
                "current_scene": {
                    "messages": [
                        {"id": "m1", "character_id": "protagonist", "content": "Snapshot user line", "type": "text"},
                        {"id": "m2", "character_id": "npc-1", "content": "Snapshot guide line", "type": "text"},
                    ]
                },
            },
        }

        normalized = normalize_benchmark_judge_payload(payload)

        self.assertEqual(normalized["dialogue_source"], "turn_logs")
        self.assertEqual(normalized["dialogue"][0]["content"], "I do not know what to say.")
        self.assertEqual(normalized["dialogue"][1]["content"], "You can start with the smallest honest sentence.")

    def test_parse_benchmark_judge_result_handles_fenced_json(self):
        content = """```json
        {
          "overall_rating": 4,
          "emotional_alignment": 5,
          "narrative_coherence": 4,
          "supportiveness": 5,
          "summary": "Solid supportive flow.",
          "strengths": ["Strong tone match", "Clear emotional continuity"],
          "issues": ["Needs more specificity"]
        }
        ```"""

        parsed = parse_benchmark_judge_result(content)

        self.assertEqual(parsed["judge_scores"]["overall_rating"], 4)
        self.assertEqual(parsed["judge_scores"]["supportiveness"], 5)
        self.assertEqual(parsed["judge_summary"]["strengths"][0], "Strong tone match")

    def test_parse_benchmark_judge_result_fills_defaults_for_missing_fields(self):
        parsed = parse_benchmark_judge_result('{"overall_rating": 7, "summary": "Usable output."}')

        self.assertEqual(parsed["judge_scores"]["overall_rating"], 5)
        self.assertEqual(parsed["judge_scores"]["emotional_alignment"], 3)
        self.assertTrue(parsed["judge_summary"]["strengths"])
        self.assertTrue(parsed["judge_summary"]["issues"])

    def test_compute_slop_stats_distinguishes_repetitive_output(self):
        low_slop_dialogue = [
            {"role": "assistant", "content": "You sound exhausted, and the scene responds with a quieter pace."},
            {"role": "assistant", "content": "The next beat adds a concrete choice instead of repeating the same comfort line."},
            {"role": "system", "content": "A bus sighs past the curb and pulls the story into a different image."},
        ]
        high_slop_dialogue = [
            {"role": "assistant", "content": "Take a breath. Take a breath. Take a breath. In this moment, take a breath."},
            {"role": "assistant", "content": "Softly, gently, softly, gently, in this moment, softly, gently."},
            {"role": "system", "content": "A flicker of light, a flicker of light, a flicker of light in this moment."},
        ]

        low_score = compute_slop_stats(low_slop_dialogue)
        high_score = compute_slop_stats(high_slop_dialogue)

        self.assertLess(low_score["slop_score"], high_score["slop_score"])
        self.assertLess(low_score["repeated_bigram_ratio"], high_score["repeated_bigram_ratio"])


if __name__ == '__main__':
    unittest.main()
