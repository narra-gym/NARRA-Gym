"""
Context Management System for the NARRA-Gym Application.
Handles user profiles, story state, user journey, and narrative summaries.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from uuid import uuid4
import json
import logging

logger = logging.getLogger(__name__)

@dataclass
class UserProfile:
    """User demographic and psychological profile."""
    user_id: str
    demographics: Dict[str, Any] = field(default_factory=dict)  # age, gender, occupation, etc.
    emotional_needs: Dict[str, Any] = field(default_factory=dict)  # core emotional challenges
    preferences: Dict[str, Any] = field(default_factory=dict)  # story preferences, interests
    summarized_background: str = ""  # LLM-generated summary of user background
    
    def update_from_answers(self, question_answers: Dict[str, str]) -> None:
        """Update profile based on questionnaire answers."""
        # Basic logic to extract information from answers
        # In a real implementation, this would be more sophisticated
        for question, answer in question_answers.items():
            if any(term in question.lower() for term in ["age", "gender", "occupation", "background"]):
                self.demographics[question] = answer
            elif any(term in question.lower() for term in ["emotional", "feeling", "challenge", "problem"]):
                self.emotional_needs[question] = answer
            elif any(term in question.lower() for term in ["interest", "hobby", "enjoy", "prefer"]):
                self.preferences[question] = answer
                
    def generate_summary(self, llm_client) -> str:
        """Generate a condensed summary of user background using LLM."""
        profile_data = asdict(self)
        prompt = f"""
        Summarize this user profile into a concise paragraph that captures essential information 
        for creating a personalized therapeutic story:
        
        {json.dumps(profile_data, indent=2)}
        
        Focus on core emotional needs, key background elements, and relevant preferences.
        Keep the summary under 200 words.
        """
        
        # In actual implementation, this would call the LLM
        response = llm_client.get_completion(prompt)
        self.summarized_background = response.get("content", "")
        return self.summarized_background


@dataclass
class Message:
    """Individual message in the story conversation."""
    id: str = field(default_factory=lambda: str(uuid4()))
    character_id: str = ""
    content: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    message_type: str = "text"  # text, choice, narration
    emotion: str = ""  # emotional tone of the message


@dataclass
class StoryState:
    """Current state of the interactive story."""
    story_id: str
    llm_model: str = ""
    current_scene_id: str = ""
    items: Dict[str, Dict] = field(default_factory=dict)  # items discovered in the story
    clues: Dict[str, Dict] = field(default_factory=dict)  # clues discovered
    messages: List[Message] = field(default_factory=list)  # full conversation history
    narrative_summary: str = ""  # LLM-generated summary of current narrative
    dialogue_counter: int = 0  # 当前对话轮数
    dialogue_summaries: List[str] = field(default_factory=list)  # 每3轮的总结
    force_advance: bool = False  # Flag to force story advancement
    conclusion_countdown: int = 0  # 当达到阈值后，在接下来的N轮内强制结局（30+5 规则）
    what_just_happened: str = ""
    current_goal: str = ""
    open_tensions: List[str] = field(default_factory=list)
    active_clues: List[str] = field(default_factory=list)
    last_major_turning_point: str = ""
    
    def add_message(self, character_id: str, content: str, message_type: str = "text", emotion: str = "") -> Message:
        """Add a new message to the conversation history."""
        message = Message(
            character_id=character_id,
            content=content,
            message_type=message_type,
            emotion=emotion
        )
        self.messages.append(message)
        return message
    
    def summarize_narrative(
        self,
        llm_client,
        message_limit: int = 10,
        model: Optional[str] = None,
        task: str = "default",
    ) -> str:
        """Generate a summary of the narrative using LLM, focusing on recent events."""
        # Get recent messages for context
        recent_messages = self.messages[-message_limit:] if len(self.messages) > message_limit else self.messages
        
        # Format messages for the prompt
        message_text = "\n".join([
            f"{msg.timestamp} - {msg.character_id}: {msg.content} [{msg.emotion}]" 
            for msg in recent_messages
        ])
        
        prompt = f"""
        Previous narrative summary: {self.narrative_summary or "No previous summary available."}
        
        Recent conversation:
        {message_text}
        
        Provide a concise summary of the story's current state, including:
        1. Key narrative developments
        2. Important emotional shifts
        3. Significant decisions or revelations
        4. Current situation and tensions
        
        Keep the summary under 250 words and focus on maintaining narrative continuity.
        """
        
        # In actual implementation, this would call the LLM
        response = llm_client.get_completion(prompt, model=model, task=task)
        self.narrative_summary = response.get("content", "")
        return self.narrative_summary


@dataclass
class UserJourney:
    """Tracks the user's progress and emotional journey through the story."""
    user_id: str
    story_id: str
    emotional_states: List[Dict[str, Any]] = field(default_factory=list)  # emotional state over time
    decisions: List[Dict[str, Any]] = field(default_factory=list)  # key decisions made
    therapeutic_progress: Dict[str, Any] = field(default_factory=dict)  # progress toward emotional goals
    journey_summary: str = ""  # LLM-generated summary of user's emotional journey
    
    def record_emotional_state(self, emotion: str, intensity: float, trigger: str) -> None:
        """Record an emotional state point in the user's journey."""
        self.emotional_states.append({
            "timestamp": datetime.now().isoformat(),
            "emotion": emotion,
            "intensity": intensity,
            "trigger": trigger
        })
    
    def record_decision(self, decision_point: str, choice: str, implications: str) -> None:
        """Record a significant decision made by the user."""
        self.decisions.append({
            "timestamp": datetime.now().isoformat(),
            "decision_point": decision_point,
            "choice": choice,
            "implications": implications
        })
    
    def summarize_journey(
        self,
        llm_client,
        model: Optional[str] = None,
        task: str = "default",
    ) -> str:
        """Generate a summary of the user's emotional journey using LLM."""
        # Format emotional states and decisions for the prompt
        emotional_text = "\n".join([
            f"{state['timestamp']} - {state['emotion']} ({state['intensity']}): {state['trigger']}" 
            for state in self.emotional_states[-5:]  # Last 5 emotional states
        ])
        
        decisions_text = "\n".join([
            f"{decision['timestamp']} - {decision['decision_point']}: {decision['choice']}" 
            for decision in self.decisions[-5:]  # Last 5 decisions
        ])
        
        prompt = f"""
        Previous journey summary: {self.journey_summary or "No previous summary available."}
        
        Recent emotional states:
        {emotional_text}
        
        Recent decisions:
        {decisions_text}
        
        Therapeutic goals:
        {json.dumps(self.therapeutic_progress, indent=2)}
        
        Provide a concise summary of the user's emotional journey, including:
        1. Emotional arc and significant shifts
        2. Pattern of decisions and their emotional impact
        3. Progress toward therapeutic goals
        4. Current emotional state and needs
        
        Keep the summary under 200 words and focus on psychological insights.
        """
        
        # In actual implementation, this would call the LLM
        response = llm_client.get_completion(prompt, model=model, task=task)
        self.journey_summary = response.get("content", "")
        return self.journey_summary


@dataclass
class Character:
    """Story character with state and development tracking."""
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    role: str = ""  # protagonist, mentor, antagonist, etc.
    description: str = ""
    personality: str = ""
    backstory: str = ""
    relationship_to_protagonist: str = ""
    arc_summary: str = ""  # LLM-generated summary of character arc


@dataclass
class StoryMetadata:
    """Core metadata about the story structure and elements."""
    story_id: str
    title: str = ""
    theme: str = ""
    setting: str = ""
    emotional_goal: str = ""
    characters: Dict[str, Character] = field(default_factory=dict)
    
    def add_character(self, character: Character) -> None:
        """Add a character to the story."""
        self.characters[character.id] = character
    
    def get_character(self, character_id: str) -> Optional[Character]:
        """Get a character by ID."""
        return self.characters.get(character_id)


class ContextManager:
    """Central manager for all story context components."""
    
    def __init__(self, llm_client):
        self.user_profiles: Dict[str, UserProfile] = {}
        self.story_states: Dict[str, StoryState] = {}
        self.user_journeys: Dict[str, UserJourney] = {}
        self.story_metadata: Dict[str, StoryMetadata] = {}
        self.llm_client = llm_client

    def _model_from_story_data(self, story_data: Dict[str, Any]) -> str:
        llm_config = story_data.get("llm_config") or {}
        return (
            str(llm_config.get("story") or llm_config.get("default") or story_data.get("selected_model") or "")
            .strip()
        )

    def _story_llm_route(self, story_id: str, llm_model: Optional[str] = None) -> Tuple[Optional[str], str]:
        state = self.story_states.get(story_id)
        model = (llm_model or (state.llm_model if state else "") or "").strip()
        if state and model:
            state.llm_model = model
        return (model or None, "story" if model else "default")
    
    def create_user_profile(self, user_id: str, seed_data: Optional[Dict[str, Any]] = None) -> UserProfile:
        """Create a new user profile."""
        profile = UserProfile(user_id=user_id)
        if seed_data:
            profile.preferences.update(seed_data)
        self.user_profiles[user_id] = profile
        return profile

    def create_story_state(self, story_id: str, story_data: Dict[str, Any]) -> StoryState:
        """Create context state from an already-built story payload."""
        user_id = story_data.get("user_id") or story_data.get("participant_id") or story_id
        if user_id not in self.user_profiles:
            self.create_user_profile(user_id)

        setting = story_data.get("setting", "")
        if isinstance(setting, dict):
            setting_text = setting.get("primary_location") or setting.get("atmosphere") or json.dumps(setting)
        else:
            setting_text = setting or ""

        self.initialize_story(
            user_id=user_id,
            story_id=story_id,
            title=story_data.get("title", ""),
            theme=story_data.get("cinematic_theme", story_data.get("theme", "")),
            setting=setting_text,
            emotional_goal=story_data.get("emotional_undercurrent", story_data.get("emotional_goal", "")),
            characters=story_data.get("characters", []),
        )

        state = self.story_states[story_id]
        state.llm_model = self._model_from_story_data(story_data)
        state.messages = []
        current_messages = story_data.get("current_scene", {}).get("messages", [])
        for msg in current_messages:
            state.add_message(
                character_id=msg.get("character_id") or msg.get("characterId", ""),
                content=msg.get("content", ""),
                message_type=msg.get("type", "text"),
                emotion=msg.get("emotion", ""),
            )
        state.dialogue_counter = len([msg for msg in current_messages if msg.get("type") != "system"])
        state.current_goal = story_data.get("protagonist_objective", "") or story_data.get("emotional_goal", "")
        self._update_story_memory(story_id)
        return state
    
    def initialize_story(self, user_id: str, story_id: str, title: str, theme: str, 
                         setting: str, emotional_goal: str, characters: List[Dict]) -> Tuple[StoryState, StoryMetadata]:
        """Initialize a new story with basic metadata."""
        # Create story metadata
        metadata = StoryMetadata(
            story_id=story_id,
            title=title,
            theme=theme,
            setting=setting,
            emotional_goal=emotional_goal
        )
        
        # Add characters
        for char_data in characters:
            character = Character(
                id=char_data.get("id", str(uuid4())),
                name=char_data.get("name", ""),
                role=char_data.get("role", ""),
                description=char_data.get("description", ""),
                personality=char_data.get("personality", ""),
                backstory=char_data.get("backstory", ""),
                relationship_to_protagonist=char_data.get("relationship", "")
            )
            metadata.add_character(character)
        
        # Create story state
        state = StoryState(story_id=story_id)
        
        # Create user journey
        journey = UserJourney(user_id=user_id, story_id=story_id)
        
        # Store in manager
        self.story_metadata[story_id] = metadata
        self.story_states[story_id] = state
        self.user_journeys[f"{user_id}:{story_id}"] = journey
        
        return state, metadata
    
    def process_message(
        self,
        story_id: str,
        character_id: str,
        content: str,
        message_type: str = "text",
        emotion: str = "",
        llm_model: Optional[str] = None,
    ) -> None:
        """Process a new message in the story conversation."""
        if story_id not in self.story_states:
            raise ValueError(f"Story {story_id} not found")
            
        # Add message to story state
        state = self.story_states[story_id]
        model, task = self._story_llm_route(story_id, llm_model)
        state.add_message(character_id, content, message_type, emotion)
        
        # 只对非 system 消息计数
        if message_type != "system":
            state.dialogue_counter += 1
            self._update_story_memory(story_id, use_llm=False)
            
            # 每3轮总结
            if state.dialogue_counter % 3 == 0:
                # 取最近3条非 system 消息
                recent_msgs = [msg for msg in state.messages if msg.message_type != "system"][-3:]
                summary_text = "\n".join([f"{msg.character_id}: {msg.content}" for msg in recent_msgs])
                # 调用 LLM 生成总结
                summary = self.llm_client.summarize_text(
                    summary_text,
                    max_length=2000,
                    model=model,
                    task=task,
                ).get("content", "")
                state.dialogue_summaries.append(summary)
                logger.info(f"[Dialogue Summary] After {state.dialogue_counter} rounds: {summary}")
                self._update_story_memory(story_id, use_llm=True, summary_seed=summary)
            
            # 每6轮对比最近两次总结
            if state.dialogue_counter % 6 == 0 and len(state.dialogue_summaries) >= 2:
                last = state.dialogue_summaries[-1]
                prev = state.dialogue_summaries[-2]
                # 简单相似度判断（可用更复杂算法）
                if last.strip() == prev.strip():
                    # 设置推进情节标志
                    state.force_advance = True
                    logger.info(f"[Force Advance] Dialogue summaries too similar, will force story advancement.")
                else:
                    state.force_advance = False
        
        # Check if we need to summarize (every 10 messages)
        if len(state.messages) % 10 == 0:
            self._update_summaries(story_id)
    
    def process_user_decision(
        self,
        user_id: str,
        story_id: str,
        decision_point: str,
        choice: str,
        implications: str,
        emotion: str,
        intensity: float,
        llm_model: Optional[str] = None,
    ) -> None:
        """Process a significant decision by the user."""
        journey_key = f"{user_id}:{story_id}"
        if journey_key not in self.user_journeys:
            raise ValueError(f"User journey for {user_id} in story {story_id} not found")
            
        # Record decision and emotional state
        journey = self.user_journeys[journey_key]
        journey.record_decision(decision_point, choice, implications)
        journey.record_emotional_state(emotion, intensity, f"Decision: {decision_point}")
        
        # Update journey summary
        model, task = self._story_llm_route(story_id, llm_model)
        journey.summarize_journey(self.llm_client, model=model, task=task)
    
    def _update_summaries(self, story_id: str) -> None:
        """Update all summaries for a story."""
        if story_id not in self.story_states:
            return
            
        # Update narrative summary
        state = self.story_states[story_id]
        model, task = self._story_llm_route(story_id)
        state.summarize_narrative(self.llm_client, model=model, task=task)
        
        # Find and update associated user journeys
        for journey_key, journey in self.user_journeys.items():
            if journey.story_id == story_id:
                journey.summarize_journey(self.llm_client, model=model, task=task)

    def _merge_memory_list(self, existing: List[str], additions: List[str], limit: int) -> List[str]:
        merged: List[str] = []
        for item in existing + additions:
            cleaned = str(item or "").strip()
            if cleaned and cleaned not in merged:
                merged.append(cleaned)
        return merged[-limit:]

    def _derive_memory_from_recent_messages(self, state: StoryState) -> None:
        recent_messages = [msg for msg in state.messages if msg.message_type != "system"][-6:]
        if not recent_messages:
            return

        latest = recent_messages[-1].content.strip()
        if latest:
            state.what_just_happened = latest[:220]

        if not state.current_goal:
            lowered = latest.lower()
            if any(marker in lowered for marker in ["need to", "must", "have to", "should", "let's", "we should"]):
                state.current_goal = latest[:160]
            else:
                state.current_goal = "Keep moving toward the next reveal."

        tension_candidates = [
            msg.content.strip()
            for msg in recent_messages
            if any(marker in msg.content.lower() for marker in ["?", "but", "unless", "danger", "risk", "threat", "secret", "truth", "can't"])
        ]
        clue_candidates = [
            msg.content.strip()
            for msg in recent_messages
            if any(marker in msg.content.lower() for marker in ["clue", "key", "map", "letter", "note", "evidence", "proof", "door", "code", "name"])
        ]
        if tension_candidates:
            state.open_tensions = self._merge_memory_list(state.open_tensions, tension_candidates[-2:], 3)
        if clue_candidates:
            state.active_clues = self._merge_memory_list(state.active_clues, clue_candidates[-2:], 4)
        if len(recent_messages) >= 2:
            turning_point = recent_messages[-2].content.strip() or recent_messages[-1].content.strip()
            if turning_point:
                state.last_major_turning_point = turning_point[:160]

    def _update_story_memory(self, story_id: str, use_llm: bool = False, summary_seed: str = "") -> None:
        """Generate concise recap buckets for UI panels and prompt context."""
        if story_id not in self.story_states:
            return

        state = self.story_states[story_id]
        recent_messages = [msg for msg in state.messages if msg.message_type != "system"][-8:]
        if not recent_messages:
            return

        self._derive_memory_from_recent_messages(state)
        if not use_llm:
            return

        model, task = self._story_llm_route(story_id)

        transcript = "\n".join([f"{msg.character_id}: {msg.content}" for msg in recent_messages])
        prompt = f"""
You are summarizing an interactive story session for a compact sidebar memory panel.

Recent dialogue:
{transcript}

Recent rolling summary:
{summary_seed or (state.dialogue_summaries[-1] if state.dialogue_summaries else "None")}

Previous memory:
- what_just_happened: {state.what_just_happened or "None"}
- current_goal: {state.current_goal or "Unknown"}
- open_tensions: {json.dumps(state.open_tensions)}
- active_clues: {json.dumps(state.active_clues)}
- last_major_turning_point: {state.last_major_turning_point or "None"}

Return JSON only:
{{
  "what_just_happened": "1-2 sentence recap",
  "current_goal": "one short sentence describing the immediate objective",
  "open_tensions": ["up to 3 unresolved tensions"],
  "active_clues": ["up to 4 clues, objects, secrets, or leads worth remembering"],
  "last_major_turning_point": "short phrase for the latest meaningful shift"
}}
"""
        try:
            response = self.llm_client.get_completion(
                prompt,
                temperature=0.3,
                model=model,
                task=task,
            )
            content = (response or {}).get("content", "").strip()
            if content:
                start = content.find("{")
                end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    parsed = json.loads(content[start:end])
                    state.what_just_happened = parsed.get("what_just_happened", state.what_just_happened)
                    state.current_goal = parsed.get("current_goal", state.current_goal)
                    state.open_tensions = list(parsed.get("open_tensions", state.open_tensions))[:3]
                    state.active_clues = list(parsed.get("active_clues", state.active_clues))[:4]
                    state.last_major_turning_point = parsed.get("last_major_turning_point", state.last_major_turning_point)
                    return
        except Exception as e:
            logger.warning(f"[Story Memory] Failed to update structured memory for {story_id}: {e}")
    
    def get_full_context(self, story_id: str, user_id: str) -> Dict[str, Any]:
        """Get the full context for LLM prompt construction."""
        if story_id not in self.story_states or story_id not in self.story_metadata:
            raise ValueError(f"Story {story_id} not found")
            
        if user_id not in self.user_profiles:
            raise ValueError(f"User {user_id} not found")
            
        journey_key = f"{user_id}:{story_id}"
        if journey_key not in self.user_journeys:
            raise ValueError(f"User journey for {user_id} in story {story_id} not found")
        
        # Get components
        profile = self.user_profiles[user_id]
        state = self.story_states[story_id]
        metadata = self.story_metadata[story_id]
        journey = self.user_journeys[journey_key]
        
        # Get recent messages (last 5)
        recent_messages = state.messages[-5:] if state.messages else []
        formatted_messages = [
            {
                "character": metadata.get_character(msg.character_id).name if metadata.get_character(msg.character_id) else "Unknown",
                "content": msg.content,
                "type": msg.message_type,
                "emotion": msg.emotion
            }
            for msg in recent_messages
        ]
        
        # Construct context
        context = {
            "user": {
                "profile_summary": profile.summarized_background,
                "emotional_needs": profile.emotional_needs
            },
            "story": {
                "title": metadata.title,
                "theme": metadata.theme,
                "setting": metadata.setting,
                "emotional_goal": metadata.emotional_goal
            },
            "current_state": {
                "narrative_summary": state.narrative_summary,
                "recent_messages": formatted_messages,
                "what_just_happened": state.what_just_happened,
                "current_goal": state.current_goal,
                "open_tensions": state.open_tensions,
                "active_clues": state.active_clues,
                "last_major_turning_point": state.last_major_turning_point,
            },
            "user_journey": {
                "journey_summary": journey.journey_summary,
                "current_emotional_state": journey.emotional_states[-1] if journey.emotional_states else {}
            }
        }
        
        return context
    
    def save_to_json(self, filepath: str) -> None:
        """Save all context data to JSON file."""
        data = {
            "user_profiles": {uid: asdict(profile) for uid, profile in self.user_profiles.items()},
            "story_states": {sid: asdict(state) for sid, state in self.story_states.items()},
            "user_journeys": {jid: asdict(journey) for jid, journey in self.user_journeys.items()},
            "story_metadata": {sid: asdict(metadata) for sid, metadata in self.story_metadata.items()}
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
            
    def load_from_json(self, filepath: str) -> None:
        """Load context data from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        # Recreate objects from dictionaries
        # This is simplified; actual implementation would need to recreate full object structure
        self.user_profiles = {uid: UserProfile(**profile_data) for uid, profile_data in data.get("user_profiles", {}).items()}
        self.story_states = {sid: StoryState(**state_data) for sid, state_data in data.get("story_states", {}).items()}
        self.user_journeys = {jid: UserJourney(**journey_data) for jid, journey_data in data.get("user_journeys", {}).items()}
        self.story_metadata = {sid: StoryMetadata(**metadata_data) for sid, metadata_data in data.get("story_metadata", {}).items()}
