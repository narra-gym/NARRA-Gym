import { BenchmarkEvaluationPayload } from '../types';

export const BENCHMARK_EMOTIONAL_FORM_VERSION = 'benchmark_emotional_human_v4';
export const BENCHMARK_EMOTIONAL_FORM_VERSION_V3 = 'benchmark_emotional_human_v3';
export const BENCHMARK_EMOTIONAL_FORM_VERSION_V2 = 'benchmark_emotional_human_v2';
export const BENCHMARK_EMOTIONAL_FORM_VERSION_V1 = 'benchmark_emotional_human_v1';
export const BENCHMARK_PLACEHOLDER_FORM_VERSION = 'benchmark_placeholder_v1';

export type BenchmarkStoryScoreKey =
  | 'story_relevance'
  | 'story_coherence'
  | 'story_empathy'
  | 'story_surprise'
  | 'story_engagement'
  | 'story_complexity'
  | 'character_shaping';

export type BenchmarkUxScoreKey =
  | 'ux_story_satisfaction'
  | 'ux_perceived_story_quality'
  | 'ux_process_engagement'
  | 'ux_use_again_intent';

export type BenchmarkScoreKey = BenchmarkStoryScoreKey | BenchmarkUxScoreKey;

export interface BenchmarkScaleOption {
  value: number;
  title: string;
  description?: string;
}

export interface BenchmarkScoreItem {
  key: BenchmarkScoreKey;
  label: string;
  helper?: string;
  scaleLabel?: string;
  scaleHint?: string;
  displayMode?: 'descriptive' | 'compact' | 'anchored';
  scaleOptions: BenchmarkScaleOption[];
}

export interface BenchmarkScoreSection {
  id: 'story_quality' | 'user_experience';
  title: string;
  description: string;
  items: BenchmarkScoreItem[];
}

const STORY_RELEVANCE_OPTIONS: BenchmarkScaleOption[] = [
  { value: 1, title: '1', description: "The story does not meaningfully connect to the user's emotional situation or core dilemma." },
  { value: 2, title: '2', description: "The story shows only a weak or occasional connection to the user's situation." },
  { value: 3, title: '3', description: 'The story is broadly relevant, though some turns feel generic or loosely matched.' },
  { value: 4, title: '4', description: "The story matches the user's situation well, with only small gaps in fit." },
  { value: 5, title: '5', description: "The story is deeply aligned with the user's emotional situation and core dilemma." },
];

const STORY_COHERENCE_OPTIONS: BenchmarkScaleOption[] = [
  { value: 1, title: '1', description: 'The story feels disjointed, with major breaks in logic, causality, or character behaviour.' },
  { value: 2, title: '2', description: 'Several parts are hard to follow because the narrative logic is unstable.' },
  { value: 3, title: '3', description: 'The story is generally understandable, though some transitions or reactions feel shaky.' },
  { value: 4, title: '4', description: 'The story is coherent and easy to follow, with only minor inconsistencies.' },
  { value: 5, title: '5', description: 'The story is consistently logical, well-structured, and clear from beginning to end.' },
];

const STORY_EMPATHY_OPTIONS: BenchmarkScaleOption[] = [
  { value: 1, title: '1', description: 'The emotional tone feels flat, misread, or emotionally disconnected.' },
  { value: 2, title: '2', description: 'The story shows limited emotional understanding and only occasional nuance.' },
  { value: 3, title: '3', description: 'The story recognises the emotional situation, though its understanding feels uneven.' },
  { value: 4, title: '4', description: 'The story conveys strong emotional understanding with clear care and sensitivity.' },
  { value: 5, title: '5', description: 'The story demonstrates deep emotional insight, nuance, and attunement throughout.' },
];

const STORY_SURPRISE_OPTIONS: BenchmarkScaleOption[] = [
  { value: 1, title: '1', description: 'The story feels fully predictable and offers no meaningful new turn.' },
  { value: 2, title: '2', description: 'The story includes only slight freshness, with very familiar developments.' },
  { value: 3, title: '3', description: 'The story has some interesting turns, though they are moderately expected.' },
  { value: 4, title: '4', description: 'The story introduces a surprising and meaningful development that still fits the narrative.' },
  { value: 5, title: '5', description: 'The story delivers a memorable, insightful turn that feels both surprising and well-earned.' },
];

const STORY_ENGAGEMENT_OPTIONS: BenchmarkScaleOption[] = [
  { value: 1, title: '1', description: 'The story feels dull and does not sustain interest.' },
  { value: 2, title: '2', description: 'The story holds attention only in brief moments.' },
  { value: 3, title: '3', description: 'The story is moderately engaging, with some strong beats and some weaker stretches.' },
  { value: 4, title: '4', description: 'The story remains engaging for most of the experience and encourages continued interaction.' },
  { value: 5, title: '5', description: 'The story is consistently compelling and makes the evaluator want to keep going.' },
];

const STORY_COMPLEXITY_OPTIONS: BenchmarkScaleOption[] = [
  { value: 1, title: '1', description: 'The story feels very simple, with little tension, layering, or development.' },
  { value: 2, title: '2', description: 'The story shows limited depth, with only a small amount of narrative layering.' },
  { value: 3, title: '3', description: 'The story has some complexity, though its emotional or narrative layers stay fairly light.' },
  { value: 4, title: '4', description: 'The story contains clear layers of tension, development, and emotional texture.' },
  { value: 5, title: '5', description: 'The story feels richly layered, with strong depth, tension, and evolving complexity.' },
];

const CHARACTER_SHAPING_OPTIONS: BenchmarkScaleOption[] = [
  { value: 1, title: '1', description: "The character feels flat, inconsistent, or disconnected from the user's situation." },
  { value: 2, title: '2', description: 'The character shows limited personality or relevance, and may behave in uneven or weakly justified ways.' },
  { value: 3, title: '3', description: "The character is generally recognisable and somewhat relevant, though the portrayal, consistency, or fit to the user's situation remains uneven." },
  { value: 4, title: '4', description: "The character is well-shaped, mostly consistent, and clearly connected to the user's emotional situation or psychological need." },
  { value: 5, title: '5', description: "The character is vivid, coherent, and deeply relevant to the user's situation, with convincing motivations, behaviour, and emotional fit throughout." },
];

const FIVE_POINT_COMPACT_OPTIONS: BenchmarkScaleOption[] = [
  { value: 1, title: '1' },
  { value: 2, title: '2' },
  { value: 3, title: '3' },
  { value: 4, title: '4' },
  { value: 5, title: '5' },
];

const USE_AGAIN_OPTIONS: BenchmarkScaleOption[] = [
  { value: 1, title: '1', description: 'I definitely would not want to use this system again.' },
  { value: 3, title: '2', description: 'I am unsure whether I would use this system again.' },
  { value: 5, title: '3', description: 'I would be very willing to use this system again.' },
];

export const BENCHMARK_STORY_SCORE_ITEMS: BenchmarkScoreItem[] = [
  {
    key: 'story_relevance',
    label: 'Story Relevance',
    helper: "Measures how closely the story aligns with the user's emotional situation and central dilemma.",
    scaleLabel: '5-point anchored rubric',
    displayMode: 'descriptive',
    scaleOptions: STORY_RELEVANCE_OPTIONS,
  },
  {
    key: 'story_coherence',
    label: 'Story Coherence',
    helper: 'Measures the clarity and internal consistency of plot, causality, and character behaviour.',
    scaleLabel: '5-point anchored rubric',
    displayMode: 'descriptive',
    scaleOptions: STORY_COHERENCE_OPTIONS,
  },
  {
    key: 'story_empathy',
    label: 'Story Empathy',
    helper: 'Measures how fully the story understands and conveys the emotional reality of the situation.',
    scaleLabel: '5-point anchored rubric',
    displayMode: 'descriptive',
    scaleOptions: STORY_EMPATHY_OPTIONS,
  },
  {
    key: 'story_surprise',
    label: 'Story Surprise',
    helper: 'Measures the degree of fresh insight or meaningful narrative turn in the story.',
    scaleLabel: '5-point anchored rubric',
    displayMode: 'descriptive',
    scaleOptions: STORY_SURPRISE_OPTIONS,
  },
  {
    key: 'story_engagement',
    label: 'Story Engagement',
    helper: 'Measures how strongly the story sustains interest and motivates continued reading or interaction.',
    scaleLabel: '5-point anchored rubric',
    displayMode: 'descriptive',
    scaleOptions: STORY_ENGAGEMENT_OPTIONS,
  },
  {
    key: 'story_complexity',
    label: 'Story Complexity',
    helper: 'Measures the level of layering, depth, and emotional texture in the story.',
    scaleLabel: '5-point anchored rubric',
    displayMode: 'descriptive',
    scaleOptions: STORY_COMPLEXITY_OPTIONS,
  },
  {
    key: 'character_shaping',
    label: 'Character Shaping',
    helper: "Measures the overall quality of the generated character in terms of how clearly the character is shaped, how consistently the character's motivations and behaviour are maintained, and how meaningfully the character connects to the user's emotional situation or psychological need.",
    scaleLabel: '5-point anchored rubric',
    displayMode: 'descriptive',
    scaleOptions: CHARACTER_SHAPING_OPTIONS,
  },
];

export const BENCHMARK_UX_SCORE_ITEMS: BenchmarkScoreItem[] = [
  {
    key: 'ux_story_satisfaction',
    label: 'How satisfied are you with the final story?',
    scaleLabel: '5-point response scale',
    scaleHint: '1 = very dissatisfied, 5 = very satisfied',
    displayMode: 'compact',
    scaleOptions: FIVE_POINT_COMPACT_OPTIONS,
  },
  {
    key: 'ux_perceived_story_quality',
    label: 'What do you think is the overall quality of the final story?',
    scaleLabel: '5-point response scale',
    scaleHint: '1 = very low, 5 = very high',
    displayMode: 'compact',
    scaleOptions: FIVE_POINT_COMPACT_OPTIONS,
  },
  {
    key: 'ux_process_engagement',
    label: 'How helpful was the interaction process for the emotional task?',
    scaleLabel: '5-point response scale',
    scaleHint: '1 = not helpful at all, 5 = extremely helpful',
    displayMode: 'compact',
    scaleOptions: FIVE_POINT_COMPACT_OPTIONS,
  },
  {
    key: 'ux_use_again_intent',
    label: 'How willing would you be to use this system again in a similar situation?',
    scaleLabel: '3-point anchored intent scale',
    displayMode: 'anchored',
    scaleOptions: USE_AGAIN_OPTIONS,
  },
];

export const BENCHMARK_SCORE_SECTIONS: BenchmarkScoreSection[] = [
  {
    id: 'story_quality',
    title: 'Story Quality',
    description: 'Evaluate the final story using question-specific anchored descriptions.',
    items: BENCHMARK_STORY_SCORE_ITEMS,
  },
  {
    id: 'user_experience',
    title: 'User Experience',
    description: 'Answer the post-session experience questions using the response scales provided.',
    items: BENCHMARK_UX_SCORE_ITEMS,
  },
];

export const BENCHMARK_STORY_SCORE_KEYS = BENCHMARK_STORY_SCORE_ITEMS.map(item => item.key);
export const BENCHMARK_UX_SCORE_KEYS = BENCHMARK_UX_SCORE_ITEMS.map(item => item.key);
export const BENCHMARK_SCORE_KEYS = [...BENCHMARK_STORY_SCORE_KEYS, ...BENCHMARK_UX_SCORE_KEYS];

export type BenchmarkScores = Record<BenchmarkScoreKey, number>;

export const createEmptyBenchmarkScores = (): BenchmarkScores => ({
  story_relevance: 0,
  story_coherence: 0,
  story_empathy: 0,
  story_surprise: 0,
  story_engagement: 0,
  story_complexity: 0,
  character_shaping: 0,
  ux_story_satisfaction: 0,
  ux_perceived_story_quality: 0,
  ux_process_engagement: 0,
  ux_use_again_intent: 0,
});

const clampScore = (value: unknown): number => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return 0;
  }
  return Math.max(0, Math.min(5, Math.round(parsed)));
};

export const isCurrentBenchmarkRubricFeedback = (feedback?: Record<string, any> | null): boolean =>
  feedback?.form_version === BENCHMARK_EMOTIONAL_FORM_VERSION;

export const isLegacyBenchmarkRubricFeedback = (feedback?: Record<string, any> | null): boolean =>
  Boolean(feedback?.feedback_type === 'benchmark_session_end' && feedback?.form_version && !isCurrentBenchmarkRubricFeedback(feedback));

export const getBenchmarkScoresFromFeedback = (feedback?: Record<string, any> | null): BenchmarkScores => {
  if (!isCurrentBenchmarkRubricFeedback(feedback)) {
    return createEmptyBenchmarkScores();
  }

  const rawScores = feedback?.scores || {};
  return BENCHMARK_SCORE_KEYS.reduce((acc, key) => {
    acc[key] = clampScore(rawScores[key]);
    return acc;
  }, createEmptyBenchmarkScores());
};

export const computeBenchmarkOverallRating = (scores: Partial<Record<BenchmarkScoreKey, number>>): number => {
  const storyScores = BENCHMARK_STORY_SCORE_KEYS.map(key => clampScore(scores[key]));
  if (storyScores.some(value => value <= 0)) {
    return 0;
  }

  const average = storyScores.reduce((sum, value) => sum + value, 0) / BENCHMARK_STORY_SCORE_KEYS.length;
  return clampScore(Math.round(average));
};

export const buildBenchmarkEvaluationPayload = ({
  storyId,
  userId,
  participantId,
  sessionId,
  scores,
  comment,
}: {
  storyId?: string;
  userId?: string;
  participantId?: string | null;
  sessionId?: string | null;
  scores: BenchmarkScores;
  comment?: string | null;
}): BenchmarkEvaluationPayload => ({
  story_id: storyId,
  user_id: userId,
  participant_id: participantId || null,
  session_id: sessionId || null,
  rating: computeBenchmarkOverallRating(scores),
  scores,
  comment: comment?.trim() || null,
  feedback_type: 'benchmark_session_end',
  form_version: BENCHMARK_EMOTIONAL_FORM_VERSION,
});

export const getBenchmarkRubricVersionLabel = (formVersion?: string | null): string => {
  if (formVersion === BENCHMARK_EMOTIONAL_FORM_VERSION) {
    return 'Emotional Human v4';
  }
  if (formVersion === BENCHMARK_EMOTIONAL_FORM_VERSION_V3) {
    return 'Emotional Human v3';
  }
  if (formVersion === BENCHMARK_EMOTIONAL_FORM_VERSION_V2) {
    return 'Emotional Human v2';
  }
  if (formVersion === BENCHMARK_EMOTIONAL_FORM_VERSION_V1) {
    return 'Emotional Human v1';
  }
  if (formVersion === BENCHMARK_PLACEHOLDER_FORM_VERSION) {
    return 'Legacy Placeholder';
  }
  if (formVersion) {
    return formVersion;
  }
  return 'Unversioned';
};
