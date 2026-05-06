// Define the common types used throughout the application

export interface User {
  id: string;
  username: string;
  emotionalNeed?: string;
  personalInfo?: {
    occupation?: string;
    interests?: string[];
    uploadedFiles?: MediaFile[];
  };
}

export interface MediaFile {
  id: string;
  type: 'image' | 'document';
  url: string;
  description?: string;
}

export interface SettingDetails {
  primary_location?: string;
  time_period?: string;
  atmosphere?: string;
  unique_elements?: string[];
}

export interface StoryMemory {
  whatJustHappened: string;
  currentGoal: string;
  openTensions: string[];
  activeClues: string[];
  lastMajorTurningPoint: string;
}

export interface StoryProgress {
  currentActIndex: number;
  actCount: number;
  currentActTitle: string;
  currentActPurpose: string;
  sceneLocation: string;
}

export interface SceneInfoPanel {
  recap: string;
  sceneLocation: string;
  objective: string;
  currentTension: string;
  immediateStakes: string;
  locationStatus: string;
  clueSummary: string[];
  tensionSummary: string[];
}

export interface CastStatus {
  characterId: string;
  name: string;
  role: string;
  relationship: string;
  currentStatus: string;
  lastSeen: string;
  inSceneNow?: boolean;
}

export interface InteractiveElementHistoryItem {
  summary: string;
  noveltyTags: string[];
  similarityScore: number;
}

export interface StoryStateMetadata {
  currentObjective: string;
  currentTension: string;
  immediateStakes: string;
  locationStatus: string;
  relationshipShift: string;
  latestReveal: string;
  emotionalBeat: string;
}

export interface SceneElements {
  atmosphere?: string;
  visualDetails?: string[];
  symbolicMotifs?: string[];
}

export interface SceneDynamics {
  transitionRequired?: boolean;
  newLocation?: string;
  timeProgression?: string;
  narrativeAdvancement?: string;
  sceneTransitionCaption?: string;
}

export interface Story {
  id: string;
  userId: string;
  title: string;
  theme: string;
  setting: string | SettingDetails;
  characters: Character[];
  currentScene: Scene;
  previousScenes: Scene[];
  emotionalGoal: string;
  status: 'active' | 'completed';
  createdAt: string;
  updatedAt: string;
  dialogueSummaries?: string[];
  dialogueCount?: number;
  exchangeCount?: number;
  conclusionCountdown?: number;
  storyMemory?: StoryMemory;
  storyProgress?: StoryProgress;
  sceneInfoPanel?: SceneInfoPanel;
  castStatuses?: CastStatus[];
  interactiveElementHistory?: InteractiveElementHistoryItem[];
  storyMode?: 'default' | 'benchmark';
  benchmarkSpeedProfile?: boolean;
  generationMode?: 'legacy_json' | 'chat_native';
  stateFreshness?: 'live' | 'derived' | 'stale';
  stateUpdatedAt?: string | null;
  pacingProfile?: {
    level: number;
    description: string;
    progressionCount: number;
    progressionUnit: string;
    exchangeCount: number;
    dialogueCount: number;
    thresholds?: Record<string, number>;
  };
  storyState?: StoryStateMetadata;
  benchmarkHistory?: BenchmarkSessionDetail | null;
}

export interface Character {
  id: string;
  name: string;
  role: 'protagonist' | 'npc' | 'system';
  description: string;
  personality: string;
  backstory?: string;
  relationship?: string; // Relationship to the user's character
  imageUrl?: string;
}

export interface Scene {
  id: string;
  description: string;
  setting: string | SettingDetails;
  location?: string;
  characters: string[]; // Character IDs present in the scene
  messages: Message[];
  choices?: Choice[];
  emotionalTone: string;
  inciting_incident?: string;
  mood?: string;
  therapeuticElements?: string[];
  scene_transition_caption?: string;
  backgroundImage?: string;
  hiddenElements?: {
    easterEgg?: string;
    foreshadowing?: string;
  };
  sceneElements?: SceneElements;
  sceneDynamics?: SceneDynamics;
  storyState?: StoryStateMetadata;
}

export interface Message {
  id: string;
  characterId?: string;
  content: string;
  timestamp: string;
  type: 'text' | 'system' | 'choice' | 'typing' | 'interactive';
  delivery?: string;
  action?: string;
  direction?: string;
  renderMode?: 'plain' | 'rp_mixed';
}

export interface Choice {
  id: string;
  text: string;
  emotionalImpact: string;
  nextSceneHint?: string;
}

export interface ExperimentCondition {
  id: string;
  name: string;
  description?: string;
  active: boolean;
  assignment_count: number;
  llm_config: Record<string, string>;
  metadata?: Record<string, any>;
  created_at?: string;
}

export interface ExperimentConfig {
  blind_benchmark_mode_enabled: boolean;
}

export interface ExperimentSession {
  participant_id: string;
  session_id: string;
  mode: string;
  started_at: string;
  selected_model?: string | null;
  blind_mode?: boolean;
  blind_code?: number | null;
  blind_invite_code?: string | null;
  blind_session_index?: number | null;
  blind_total_sessions?: number | null;
  blind_completed_count?: number;
  blind_remaining_count?: number;
  blind_finished?: boolean;
  quick_test_mode?: boolean;
  quick_test_completed_runs?: number;
  condition: ExperimentCondition;
}

export interface BenchmarkModelOption {
  id: string;
  label: string;
  description?: string;
  provider?: string;
  available?: boolean;
  availability_reason?: string;
}

export interface BenchmarkEvaluationPayload {
  story_id?: string;
  user_id?: string;
  participant_id?: string | null;
  session_id?: string | null;
  rating: number;
  scores: Record<string, number>;
  comment?: string | null;
  feedback_type: 'benchmark_session_end';
  form_version: string;
}

export interface BenchmarkSessionSummary extends ExperimentSession {
  id?: string;
  story_id?: string | null;
  status?: string;
  completed_at?: string | null;
  emotional_need?: string | null;
  turn_count?: number;
  feedback_count?: number;
  story_event_count?: number;
}

export interface BenchmarkDialogueRecord {
  id: string;
  speaker: string;
  role: string;
  character_id?: string | null;
  content: string;
  timestamp?: string | null;
  message_type?: string;
  turn_index?: number;
  source?: string;
}

export interface BenchmarkSessionDetail {
  session: BenchmarkSessionSummary;
  dialogue_source: string;
  dialogue: BenchmarkDialogueRecord[];
  story_snapshot?: Record<string, any> | null;
  final_view_story?: Record<string, any> | null;
  turn_logs: Record<string, any>[];
  feedback_logs: Record<string, any>[];
  participant_evaluation?: Record<string, any> | null;
  story_events?: Record<string, any>[];
  llm_call_logs?: Record<string, any>[];
  export_bundle?: Record<string, any> | null;
  template_mode?: boolean;
}

export interface BlindReviewSessionsResponse {
  current_session_id: string;
  sessions: BenchmarkSessionDetail[];
}

export interface BenchmarkJudgePayload {
  schema_version?: string | null;
  export_type?: string | null;
  session: Record<string, any> | null;
  dialogue_source: string;
  dialogue: BenchmarkDialogueRecord[];
  turn_logs: Record<string, any>[];
  feedback_logs: Record<string, any>[];
  llm_call_logs: Record<string, any>[];
  participant_evaluation?: Record<string, any> | null;
  story_snapshot?: Record<string, any> | null;
  final_view_story?: Record<string, any> | null;
}

export interface BenchmarkResultExportPayload {
  schema_version: string;
  export_type: string;
  exported_at: string;
  session: Record<string, any> | null;
  story: Record<string, any> | null;
  participant_evaluation: Record<string, any> | null;
  dialogue_source: string;
  dialogue: BenchmarkDialogueRecord[];
  turn_logs: Record<string, any>[];
  feedback_logs: Record<string, any>[];
  final_view_story?: Record<string, any> | null;
  template_mode?: boolean;
}

export interface BenchmarkJudgeInputSummary {
  session_id?: string | null;
  story_id?: string | null;
  participant_id?: string | null;
  selected_model?: string | null;
  dialogue_count: number;
  output_message_count: number;
  turn_log_count: number;
  llm_call_count: number;
  feedback_count: number;
  content_source: string;
  story_title?: string | null;
  total_output_tokens: number;
}

export interface BenchmarkJudgeScores {
  overall_rating: number;
  emotional_alignment: number;
  narrative_coherence: number;
  supportiveness: number;
}

export interface BenchmarkJudgeSummary {
  summary: string;
  strengths: string[];
  issues: string[];
}

export interface BenchmarkJudgeSlopStat {
  term: string;
  count: number;
}

export interface BenchmarkJudgeSlopStats {
  slop_score: number;
  interpretation: string;
  total_output_messages: number;
  total_output_tokens: number;
  gptism_hit_rate: number;
  repeated_bigram_ratio: number;
  repeated_trigram_ratio: number;
  high_frequency_term_ratio: number;
  repeated_sentence_prefix_ratio: number;
  top_repeated_terms: BenchmarkJudgeSlopStat[];
  gptism_hits: Record<string, number>;
}

export interface BenchmarkJudgeResponse {
  input_summary: BenchmarkJudgeInputSummary;
  judge_scores: BenchmarkJudgeScores;
  judge_summary: BenchmarkJudgeSummary;
  slop_stats: BenchmarkJudgeSlopStats;
}
