import {
  buildBenchmarkJudgeInputSummary,
  normalizeBenchmarkJudgePayload,
} from './benchmarkJudge';

describe('benchmarkJudge utilities', () => {
  it('normalizes conclusion export shaped payloads', () => {
    const payload = {
      schema_version: 'benchmark_result_v1',
      export_type: 'benchmark_result',
      session: {
        session_id: 'session-1',
        participant_id: 'participant-1',
        selected_model: 'openai/gpt-5.4',
      },
      story: {
        id: 'story-1',
        title: 'Late Night',
      },
      dialogue_source: 'current_scene',
      dialogue: [
        { id: 'd1', speaker: 'User', role: 'user', content: 'I feel stuck.' },
        { id: 'd2', speaker: 'Guide', role: 'assistant', content: 'We can move one concrete step at a time.' },
      ],
      turn_logs: [],
      feedback_logs: [],
      llm_call_logs: [],
      participant_evaluation: {
        rating: 5,
        comment: 'Grounded and emotionally coherent.',
      },
    };

    const normalized = normalizeBenchmarkJudgePayload(payload);
    const summary = buildBenchmarkJudgeInputSummary(normalized);

    expect(normalized.schema_version).toBe('benchmark_result_v1');
    expect(normalized.export_type).toBe('benchmark_result');
    expect(normalized.participant_evaluation?.rating).toBe(5);
    expect(normalized.dialogue_source).toBe('current_scene');
    expect(normalized.final_view_story?.title).toBe('Late Night');
    expect(summary.dialogue_count).toBe(2);
    expect(summary.output_message_count).toBe(1);
  });

  it('falls back to snapshot dialogue for export bundles', () => {
    const payload = {
      export_bundle: {
        session: {
          session_id: 'session-2',
          participant_id: 'participant-2',
        },
        dialogue: [],
        turn_logs: [],
        story_snapshot: {
          id: 'story-2',
          user_id: 'participant-2',
          characters: [
            { id: 'protagonist', name: 'You', role: 'protagonist' },
            { id: 'npc-1', name: 'Guide', role: 'npc' },
          ],
          current_scene: {
            messages: [
              { id: 'm1', character_id: 'protagonist', content: 'I cannot sleep.', type: 'text' },
              { id: 'm2', character_id: 'npc-1', content: 'Then we can sit with the night for a moment.', type: 'text' },
            ],
          },
        },
      },
    };

    const normalized = normalizeBenchmarkJudgePayload(payload);

    expect(normalized.dialogue_source).toBe('story_snapshot');
    expect(normalized.dialogue).toHaveLength(2);
    expect(normalized.dialogue[1].speaker).toBe('Guide');
  });

  it('prefers turn logs before snapshot fallback when dialogue is missing', () => {
    const payload = {
      session: {
        session_id: 'session-3',
        participant_id: 'participant-3',
      },
      dialogue: [],
      turn_logs: [
        {
          id: 't1',
          turn_index: 1,
          user_input: 'I do not know what to say.',
          response_text: 'You can start with the smallest honest sentence.',
          response_character_id: 'guide',
        },
      ],
      story_snapshot: {
        id: 'story-3',
        characters: [
          { id: 'protagonist', name: 'You', role: 'protagonist' },
          { id: 'npc-1', name: 'Guide', role: 'npc' },
        ],
        current_scene: {
          messages: [
            { id: 'm1', character_id: 'protagonist', content: 'Snapshot user line', type: 'text' },
            { id: 'm2', character_id: 'npc-1', content: 'Snapshot guide line', type: 'text' },
          ],
        },
      },
    };

    const normalized = normalizeBenchmarkJudgePayload(payload);

    expect(normalized.dialogue_source).toBe('turn_logs');
    expect(normalized.dialogue).toHaveLength(2);
    expect(normalized.dialogue[0].content).toBe('I do not know what to say.');
    expect(normalized.dialogue[1].content).toBe('You can start with the smallest honest sentence.');
  });
});
