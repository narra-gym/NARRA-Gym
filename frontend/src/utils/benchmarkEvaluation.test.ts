import {
  BENCHMARK_EMOTIONAL_FORM_VERSION,
  BENCHMARK_EMOTIONAL_FORM_VERSION_V3,
  BENCHMARK_EMOTIONAL_FORM_VERSION_V2,
  BENCHMARK_EMOTIONAL_FORM_VERSION_V1,
  BENCHMARK_PLACEHOLDER_FORM_VERSION,
  BENCHMARK_SCORE_KEYS,
  buildBenchmarkEvaluationPayload,
  computeBenchmarkOverallRating,
  createEmptyBenchmarkScores,
  getBenchmarkScoresFromFeedback,
  getBenchmarkRubricVersionLabel,
  isLegacyBenchmarkRubricFeedback,
} from './benchmarkEvaluation';

describe('benchmarkEvaluation utilities', () => {
  it('computes overall rating from the seven story-quality dimensions only', () => {
    const scores = {
      ...createEmptyBenchmarkScores(),
      story_relevance: 4,
      story_coherence: 5,
      story_empathy: 4,
      story_surprise: 3,
      story_engagement: 4,
      story_complexity: 4,
      character_shaping: 4,
      ux_story_satisfaction: 2,
      ux_perceived_story_quality: 2,
      ux_process_engagement: 5,
      ux_use_again_intent: 5,
    };

    expect(computeBenchmarkOverallRating(scores)).toBe(4);
  });

  it('builds a complete payload with all eleven score keys', () => {
    const scores = {
      ...createEmptyBenchmarkScores(),
      story_relevance: 5,
      story_coherence: 4,
      story_empathy: 5,
      story_surprise: 4,
      story_engagement: 5,
      story_complexity: 4,
      character_shaping: 5,
      ux_story_satisfaction: 4,
      ux_perceived_story_quality: 4,
      ux_process_engagement: 5,
      ux_use_again_intent: 4,
    };

    const payload = buildBenchmarkEvaluationPayload({
      storyId: 'story-1',
      userId: 'user-1',
      participantId: 'participant-1',
      sessionId: 'session-1',
      scores,
      comment: '  Strong emotional turn, but one beat felt too generic.  ',
    });

    expect(payload.form_version).toBe(BENCHMARK_EMOTIONAL_FORM_VERSION);
    expect(payload.feedback_type).toBe('benchmark_session_end');
    expect(payload.rating).toBe(5);
    expect(payload.comment).toBe('Strong emotional turn, but one beat felt too generic.');
    expect(Object.keys(payload.scores).sort()).toEqual([...BENCHMARK_SCORE_KEYS].sort());
  });

  it('does not reuse legacy placeholder scores for the new rubric', () => {
    const legacyFeedback = {
      feedback_type: 'benchmark_session_end',
      form_version: BENCHMARK_PLACEHOLDER_FORM_VERSION,
      scores: {
        overall_rating: 4,
        dimension_1: 4,
        dimension_2: 5,
        dimension_3: 4,
      },
      comment: 'Legacy note still visible.',
    };

    const scores = getBenchmarkScoresFromFeedback(legacyFeedback);

    expect(isLegacyBenchmarkRubricFeedback(legacyFeedback)).toBe(true);
    expect(Object.values(scores)).toEqual(new Array(BENCHMARK_SCORE_KEYS.length).fill(0));
  });

  it('loads current rubric scores and labels versions clearly', () => {
    const feedback = {
      feedback_type: 'benchmark_session_end',
      form_version: BENCHMARK_EMOTIONAL_FORM_VERSION,
      scores: {
        story_relevance: 4,
        story_coherence: 4,
        story_empathy: 5,
        story_surprise: 3,
        story_engagement: 4,
        story_complexity: 4,
        character_shaping: 4,
        ux_story_satisfaction: 4,
        ux_perceived_story_quality: 4,
        ux_process_engagement: 5,
        ux_use_again_intent: 4,
      },
    };

    const scores = getBenchmarkScoresFromFeedback(feedback);

    expect(scores.story_empathy).toBe(5);
    expect(scores.ux_use_again_intent).toBe(4);
    expect(scores.character_shaping).toBe(4);
    expect(getBenchmarkRubricVersionLabel(feedback.form_version)).toBe('Emotional Human v4');
    expect(getBenchmarkRubricVersionLabel(BENCHMARK_EMOTIONAL_FORM_VERSION_V3)).toBe('Emotional Human v3');
    expect(getBenchmarkRubricVersionLabel(BENCHMARK_EMOTIONAL_FORM_VERSION_V2)).toBe('Emotional Human v2');
    expect(getBenchmarkRubricVersionLabel(BENCHMARK_EMOTIONAL_FORM_VERSION_V1)).toBe('Emotional Human v1');
    expect(getBenchmarkRubricVersionLabel(BENCHMARK_PLACEHOLDER_FORM_VERSION)).toBe('Legacy Placeholder');
  });
});
