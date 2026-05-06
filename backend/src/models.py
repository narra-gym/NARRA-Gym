from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class EmotionalNeedInput(BaseModel):
    emotional_need: str
    user_id: Optional[str] = None
    participant_id: Optional[str] = None
    session_id: Optional[str] = None
    experiment_mode: Optional[bool] = False


class QuickTestStoryInput(BaseModel):
    user_id: Optional[str] = None
    participant_id: Optional[str] = None
    session_id: str


class QuestionWithOptions(BaseModel):
    question: str
    options: List[str]
    allowsCustom: bool = True
    questionType: Optional[Literal["single", "multiple"]] = "single"


class QuestionsResponse(BaseModel):
    story_id: str
    questions: List[str]
    questions_data: Optional[List[Dict[str, Any]]] = None
    keywords: List[str]
    profile_keywords: Optional[Dict[str, List[str]]] = None


class StoryAnswersInput(BaseModel):
    story_id: Optional[str] = None
    user_id: Optional[str] = None
    participant_id: Optional[str] = None
    session_id: Optional[str] = None
    experiment_mode: Optional[bool] = False
    emotional_need: Optional[str] = None
    answers: Dict[str, str]
    selected_keywords: Optional[List[str]] = None


class StoryMemoryResponse(BaseModel):
    what_just_happened: str = ""
    current_goal: str = ""
    open_tensions: List[str] = Field(default_factory=list)
    active_clues: List[str] = Field(default_factory=list)
    last_major_turning_point: str = ""


class StoryProgressResponse(BaseModel):
    current_act_index: int = 0
    act_count: int = 0
    current_act_title: str = ""
    current_act_purpose: str = ""
    scene_location: str = ""


class SceneInfoPanelResponse(BaseModel):
    recap: str = ""
    scene_location: str = ""
    objective: str = ""
    current_tension: str = ""
    immediate_stakes: str = ""
    location_status: str = ""
    clue_summary: List[str] = Field(default_factory=list)
    tension_summary: List[str] = Field(default_factory=list)


class CastStatusResponse(BaseModel):
    character_id: str
    name: str = ""
    role: str = ""
    relationship: str = ""
    current_status: str = ""
    last_seen: str = ""


class InteractiveElementHistoryResponse(BaseModel):
    summary: str = ""
    novelty_tags: List[str] = Field(default_factory=list)
    similarity_score: float = 0.0


class StoryResponse(BaseModel):
    story_id: str
    title: str
    theme: str
    setting: Any
    characters: List[Dict]
    current_scene: Dict
    emotional_goal: str
    hidden_elements: Optional[Any] = []
    high_concept_premise: Optional[str] = ""
    acts: Optional[List[Dict]] = []
    status: Optional[str] = "active"
    dialogue_summaries: Optional[List[str]] = []
    dialogue_count: Optional[int] = 0
    conclusion_countdown: Optional[int] = 0
    story_memory: Optional[StoryMemoryResponse] = None
    story_progress: Optional[StoryProgressResponse] = None
    scene_info_panel: Optional[SceneInfoPanelResponse] = None
    cast_statuses: Optional[List[CastStatusResponse]] = None
    interactive_element_history: Optional[List[InteractiveElementHistoryResponse]] = None
    story_mode: Optional[str] = "default"
    benchmark_speed_profile: Optional[bool] = False
    exchange_count: Optional[int] = 0
    pacing_profile: Optional[Dict[str, Any]] = None
    generation_mode: Optional[str] = "legacy_json"
    state_freshness: Optional[str] = "stale"
    state_updated_at: Optional[str] = None


class MessageInput(BaseModel):
    story_id: str
    user_id: Optional[str] = None
    participant_id: Optional[str] = None
    session_id: Optional[str] = None
    content: str
    with_reflection: Optional[bool] = False
    reflection: Optional[Dict[str, Any]] = None
    fast_forward: Optional[bool] = False


class ChoiceInput(BaseModel):
    story_id: str
    user_id: Optional[str] = None
    participant_id: Optional[str] = None
    session_id: Optional[str] = None
    choice_id: str
    with_reflection: Optional[bool] = False
    reflection: Optional[Dict[str, Any]] = None
    fast_forward: Optional[bool] = False


class ContextActionRequest(BaseModel):
    action: str
    filepath: str


class StoryStep1Input(BaseModel):
    """Step 1: story foundation input."""

    story_id: str
    emotional_need: str
    user_id: Optional[str] = None
    participant_id: Optional[str] = None
    session_id: Optional[str] = None
    answers: Optional[Dict[str, str]] = None
    selected_keywords: Optional[List[str]] = None
    profile_keywords: Optional[Dict[str, List[str]]] = None
    guidance_sentence: Optional[str] = None


class StoryStep1Response(BaseModel):
    """Step 1: story foundation output."""

    story_id: str
    title: str
    high_concept_premise: str
    cinematic_theme: str
    emotional_undercurrent: str
    protagonist_objective: str
    progress: int = 20


class StoryStep2Input(BaseModel):
    """Step 2: setting input."""

    story_id: str


class StoryStep2Response(BaseModel):
    """Step 2: setting output."""

    story_id: str
    setting: Dict[str, Any]
    progress: int = 40


class StoryStep3Input(BaseModel):
    """Step 3: characters input."""

    story_id: str


class StoryStep3Response(BaseModel):
    """Step 3: characters output."""

    story_id: str
    characters: List[Dict[str, Any]]
    progress: int = 60


class StoryStep4Input(BaseModel):
    """Step 4: act structure input."""

    story_id: str


class StoryStep4Response(BaseModel):
    """Step 4: act structure output."""

    story_id: str
    acts: List[Dict[str, Any]]
    progress: int = 80


class StoryStep5Input(BaseModel):
    """Step 5: opening scene input."""

    story_id: str


class StoryStep5Response(BaseModel):
    """Step 5: opening scene output."""

    story_id: str
    opening_sequence: Dict[str, Any]
    initial_dialogue: List[Dict[str, Any]]
    branching_choices: List[Dict[str, Any]]
    hidden_elements: List[Dict[str, Any]]
    progress: int = 100


class FeedbackInput(BaseModel):
    """User feedback submission."""

    story_id: Optional[str] = None
    user_id: Optional[str] = None
    participant_id: Optional[str] = None
    session_id: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5, description="1-5 star rating")
    feelings: Optional[List[str]] = None
    scores: Optional[Dict[str, int]] = None
    comment: Optional[str] = None
    feedback_type: Optional[str] = "general"
    form_version: Optional[str] = None
    feedback_value: Optional[Dict[str, Any]] = None


class ExperimentSessionStartInput(BaseModel):
    participant_id: Optional[str] = None
    mode: Optional[str] = "benchmark"
    requested_condition_id: Optional[str] = None
    selected_model: Optional[str] = None
    blind_code: Optional[Union[int, str]] = None
    participant_metadata: Optional[Dict[str, Any]] = None
    session_metadata: Optional[Dict[str, Any]] = None


class BenchmarkModelOptionResponse(BaseModel):
    id: str
    label: str
    description: Optional[str] = None
    provider: Optional[str] = None
    available: Optional[bool] = True
    availability_reason: Optional[str] = None


class BenchmarkJudgeRequest(BaseModel):
    selected_model: str
    benchmark_payload: Dict[str, Any]


class BenchmarkJudgeScoresResponse(BaseModel):
    overall_rating: int = Field(ge=1, le=5)
    emotional_alignment: int = Field(ge=1, le=5)
    narrative_coherence: int = Field(ge=1, le=5)
    supportiveness: int = Field(ge=1, le=5)


class BenchmarkJudgeSummaryResponse(BaseModel):
    summary: str
    strengths: List[str] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)


class BenchmarkJudgeInputSummaryResponse(BaseModel):
    session_id: Optional[str] = None
    story_id: Optional[str] = None
    participant_id: Optional[str] = None
    selected_model: Optional[str] = None
    dialogue_count: int = 0
    output_message_count: int = 0
    turn_log_count: int = 0
    llm_call_count: int = 0
    feedback_count: int = 0
    content_source: str = "uploaded_dialogue"
    story_title: Optional[str] = None
    total_output_tokens: int = 0


class BenchmarkJudgeSlopStatResponse(BaseModel):
    term: str
    count: int


class BenchmarkJudgeSlopStatsResponse(BaseModel):
    slop_score: float
    interpretation: str
    total_output_messages: int = 0
    total_output_tokens: int = 0
    gptism_hit_rate: float = 0.0
    repeated_bigram_ratio: float = 0.0
    repeated_trigram_ratio: float = 0.0
    high_frequency_term_ratio: float = 0.0
    repeated_sentence_prefix_ratio: float = 0.0
    top_repeated_terms: List[BenchmarkJudgeSlopStatResponse] = Field(default_factory=list)
    gptism_hits: Dict[str, int] = Field(default_factory=dict)


class BenchmarkJudgeResponse(BaseModel):
    input_summary: BenchmarkJudgeInputSummaryResponse
    judge_scores: BenchmarkJudgeScoresResponse
    judge_summary: BenchmarkJudgeSummaryResponse
    slop_stats: BenchmarkJudgeSlopStatsResponse


class ExperimentConditionResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    active: bool = True
    assignment_count: int = 0
    llm_config: Dict[str, str]
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None


class ExperimentSessionStartResponse(BaseModel):
    participant_id: str
    session_id: str
    mode: str
    started_at: str
    selected_model: Optional[str] = None
    blind_mode: bool = False
    blind_code: Optional[int] = None
    blind_invite_code: Optional[str] = None
    blind_session_index: Optional[int] = None
    blind_total_sessions: Optional[int] = None
    blind_completed_count: Optional[int] = 0
    blind_remaining_count: Optional[int] = 0
    blind_finished: Optional[bool] = False
    quick_test_mode: Optional[bool] = False
    quick_test_completed_runs: Optional[int] = 0
    condition: ExperimentConditionResponse
