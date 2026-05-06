import json
import logging
import re
from typing import Dict, Optional, List, Any

# Configure logging
logger = logging.getLogger(__name__)

def extract_json_from_response(content: str) -> str:
    """Extract the first JSON object OR array found in an LLM string response.

    Handles cases where the model wraps JSON in markdown fences, and where the
    top-level structure is either an object {...} or an array [...].
    """
    if not content:
        logger.error("Empty content provided to extract_json_from_response")
        raise ValueError("Empty content provided to extract_json_from_response")
        
    logger.debug(f"Original content length: {len(content)}")
    
    # Remove markdown code-fence wrappers if present
    if "```" in content:
        segments = [seg for seg in content.split("```") if ("{" in seg or "[" in seg)]
        if segments:
            content = segments[0]
            logger.debug(f"Extracted content from code block, new length: {len(content)}")
        else:
            logger.warning("Found code fences but no JSON content within them")

    # Check for common LLM preambles and remove them
    preamble_markers = ["Here's the JSON:", "Here is the JSON:", "JSON response:", "The story JSON:"]
    for marker in preamble_markers:
        if marker in content:
            content = content[content.find(marker) + len(marker):]
            logger.debug(f"Removed preamble '{marker}', new content length: {len(content)}")
            break

    # Determine whether the top-level JSON element is an object or an array
    first_brace = content.find("{")
    first_bracket = content.find("[")

    if first_brace == -1 and first_bracket == -1:
        logger.error("No JSON object or array markers found in content")
        raise ValueError("No JSON object or array markers found in content")

    if first_bracket != -1 and (first_brace == -1 or first_bracket < first_brace):
        # A JSON array appears before any object → extract array
        start = first_bracket
        end = content.rfind("]") + 1
        logger.debug(f"Extracting JSON array from positions {start} to {end}")
    else:
        # Default to extracting a JSON object
        start = first_brace
        end = content.rfind("}") + 1
        logger.debug(f"Extracting JSON object from positions {start} to {end}")

    if start == -1 or end == 0:
        logger.error("Found opening JSON marker but no matching closing marker")
        raise ValueError("Found opening JSON marker but no matching closing marker")
        
    # Sanity check: ensure we're not extracting an incomplete or malformed JSON
    extracted = content[start:end]
    if not extracted:
        logger.error("Extracted empty JSON string")
        raise ValueError("Extracted empty JSON string")
        
    # Check for balanced braces/brackets
    if extracted.count("{") != extracted.count("}"):
        logger.error(f"Unbalanced braces in extracted JSON: {extracted.count('{')} opening vs {extracted.count('}')} closing")
        
        # Try to fix common issues with unbalanced braces
        if extracted.count("{") > extracted.count("}"):
            missing = extracted.count("{") - extracted.count("}")
            logger.warning(f"Attempting to fix by adding {missing} closing braces")
            extracted += "}" * missing
        else:
            # More closing than opening braces - trim the excess from the end
            excess = extracted.count("}") - extracted.count("{")
            logger.warning(f"Attempting to fix by removing {excess} excess closing braces")
            extracted = extracted[:-(excess)]
            
    if extracted.count("[") != extracted.count("]"):
        logger.error(f"Unbalanced brackets in extracted JSON: {extracted.count('[')} opening vs {extracted.count(']')} closing")
        
        # Try to fix common issues with unbalanced brackets
        if extracted.count("[") > extracted.count("]"):
            missing = extracted.count("[") - extracted.count("]")
            logger.warning(f"Attempting to fix by adding {missing} closing brackets")
            extracted += "]" * missing
        else:
            # More closing than opening brackets - trim the excess from the end
            excess = extracted.count("]") - extracted.count("[")
            logger.warning(f"Attempting to fix by removing {excess} excess closing brackets")
            extracted = extracted[:-(excess)]
    
    logger.debug(f"Final extracted JSON length: {len(extracted)}")
    return extracted


def _sanitize_potential_json(text: str) -> str:
    """Apply lightweight repairs for common malformed-JSON issues."""
    sanitized = text.strip()
    replacements = {
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\ufeff": "",
    }
    for old, new in replacements.items():
        sanitized = sanitized.replace(old, new)

    # Remove control chars except common whitespace.
    sanitized = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", sanitized)
    # Remove trailing commas before a closing object/array.
    sanitized = re.sub(r",(\s*[}\]])", r"\1", sanitized)
    return sanitized


def parse_json_response(
    content: str,
    task: str = "default",
    model: Optional[str] = None,
    trace_context: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    Parse JSON from an LLM response, with deterministic cleanup first and an
    LLM-based repair attempt as a last resort for structured outputs.
    """
    parse_errors: list[str] = []

    candidates: list[str] = []
    try:
        extracted = extract_json_from_response(content)
        candidates.append(extracted)
        candidates.append(_sanitize_potential_json(extracted))
    except Exception as e:
        parse_errors.append(f"extract failed: {e}")

    candidates.append(_sanitize_potential_json(content))

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            return json.loads(candidate)
        except Exception as e:
            parse_errors.append(str(e))

    looks_structured = (
        len(content or "") > 180 and
        any(marker in (content or "") for marker in ['"scene_description"', '"cinematic_responses"', '"scene_elements"', "{", "["])
    )
    if not looks_structured:
        raise ValueError("Unable to parse non-structured response as JSON")

    try:
        from src.llm_client import get_llm_completion
        from src.config import settings

        repair_messages = [
            {
                "role": "system",
                "content": (
                    "You repair malformed JSON. Return only valid JSON. "
                    "Preserve the original structure and wording as much as possible. "
                    "Do not summarize, explain, or omit keys unless the input is clearly truncated."
                ),
            },
            {
                "role": "user",
                "content": f"Repair this into valid JSON only:\n\n{content}",
            },
        ]
        repair_response = get_llm_completion(
            messages=repair_messages,
            model=model or settings.get_llm_model(task),
            task=task,
            trace_context=trace_context,
        )
        if repair_response.get("error"):
            raise ValueError(repair_response["error"])

        repaired = _sanitize_potential_json(extract_json_from_response(repair_response.get("content", "")))
        return json.loads(repaired)
    except Exception as e:
        parse_errors.append(f"repair failed: {e}")
        raise ValueError(" | ".join(parse_errors))


def _trim_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return default


def _normalize_string_list(value: Any, limit: int) -> List[str]:
    if not isinstance(value, list):
        return []
    normalized: List[str] = []
    for item in value:
        cleaned = _trim_string(item)
        if cleaned:
            normalized.append(cleaned)
        if len(normalized) >= limit:
            break
    return normalized


def _first_non_empty_string(*values: Any) -> str:
    for value in values:
        cleaned = _trim_string(value)
        if cleaned:
            return cleaned
    return ""


def _normalize_story_state_payload(
    payload: Dict[str, Any],
    story: Dict[str, Any],
    hidden_elements: Dict[str, Any],
    scene_dynamics: Dict[str, Any],
) -> Dict[str, Any]:
    raw_state = payload.get("story_state") if isinstance(payload.get("story_state"), dict) else {}
    existing_state = story.get("story_state") if isinstance(story.get("story_state"), dict) else {}
    current_scene = story.get("current_scene", {}) if isinstance(story.get("current_scene"), dict) else {}
    scene_elements = payload.get("scene_elements") if isinstance(payload.get("scene_elements"), dict) else {}

    objective = _first_non_empty_string(
        raw_state.get("current_objective"),
        raw_state.get("objective"),
        existing_state.get("current_objective"),
        story.get("protagonist_objective"),
        story.get("emotional_goal"),
        story.get("emotional_undercurrent"),
    )
    current_tension = _first_non_empty_string(
        raw_state.get("current_tension"),
        raw_state.get("tension"),
        existing_state.get("current_tension"),
        hidden_elements.get("foreshadowing"),
        current_scene.get("inciting_incident"),
    )
    immediate_stakes = _first_non_empty_string(
        raw_state.get("immediate_stakes"),
        raw_state.get("stakes"),
        existing_state.get("immediate_stakes"),
        scene_dynamics.get("narrative_advancement"),
    )
    location_status = _first_non_empty_string(
        raw_state.get("location_status"),
        raw_state.get("scene_status"),
        existing_state.get("location_status"),
        scene_dynamics.get("new_location"),
        current_scene.get("location"),
        current_scene.get("setting"),
    )
    relationship_shift = _first_non_empty_string(
        raw_state.get("relationship_shift"),
        raw_state.get("relationship_change"),
        existing_state.get("relationship_shift"),
    )
    latest_reveal = _first_non_empty_string(
        raw_state.get("latest_reveal"),
        raw_state.get("new_reveal"),
        existing_state.get("latest_reveal"),
        hidden_elements.get("easter_egg"),
        hidden_elements.get("foreshadowing"),
    )
    emotional_beat = _first_non_empty_string(
        raw_state.get("emotional_beat"),
        scene_elements.get("atmosphere"),
        existing_state.get("emotional_beat"),
    )

    return {
        "current_objective": objective,
        "current_tension": current_tension,
        "immediate_stakes": immediate_stakes,
        "location_status": location_status,
        "relationship_shift": relationship_shift,
        "latest_reveal": latest_reveal,
        "emotional_beat": emotional_beat,
    }


def validate_story_advancement_payload(payload: Any, story: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize story advancement JSON into a stable structure for downstream use."""
    if not isinstance(payload, dict):
        raise ValueError("Story advancement payload must be a JSON object")

    characters = story.get("characters", []) if isinstance(story, dict) else []
    protagonist = get_protagonist(story) or {}
    protagonist_id = protagonist.get("id", "protagonist")
    valid_ids = {char.get("id") for char in characters if char.get("id")}
    name_to_id = {
        normalize_character_id(char.get("name", "")): char.get("id")
        for char in characters
        if char.get("name") and char.get("id")
    }

    def normalize_character_ref(character_id: Any, character_name: Any, default_id: str) -> str:
        if isinstance(character_id, str) and character_id in valid_ids:
            return character_id
        if isinstance(character_name, str):
            normalized_name = normalize_character_id(character_name)
            if normalized_name in name_to_id:
                return name_to_id[normalized_name]
        if isinstance(character_id, str):
            normalized_id = normalize_character_id(character_id)
            if normalized_id in valid_ids:
                return normalized_id
        return default_id

    normalized_responses: List[Dict[str, Any]] = []
    raw_responses = payload.get("cinematic_responses")
    if raw_responses is None:
        single = (
            payload.get("npc_response")
            or payload.get("cinematic_response")
            or payload.get("npcReply")
        )
        raw_responses = [single] if single else []
    if not isinstance(raw_responses, list):
        raw_responses = [raw_responses]

    first_non_protagonist = next((char.get("id") for char in characters if char.get("role") != "protagonist"), protagonist_id)
    for idx, response in enumerate(raw_responses):
        if not isinstance(response, dict):
            continue
        dialogue = (response.get("dialogue") or response.get("content") or "").strip()
        if not dialogue:
            continue
        default_id = protagonist_id if idx == 0 and response.get("character_name", "").lower() == protagonist.get("name", "").lower() else first_non_protagonist
        char_id = normalize_character_ref(response.get("character_id"), response.get("character_name"), default_id)
        normalized_responses.append({
            "character_id": char_id,
            "character_name": response.get("character_name") or next((char.get("name") for char in characters if char.get("id") == char_id), ""),
            "dialogue": dialogue,
            "delivery": (response.get("delivery") or "").strip(),
            "action": (response.get("action") or "").strip(),
            "direction": (response.get("direction") or "").strip(),
        })

    if not normalized_responses:
        fallback_character = first_non_protagonist or protagonist_id
        normalized_responses = [{
            "character_id": fallback_character,
            "character_name": next((char.get("name") for char in characters if char.get("id") == fallback_character), ""),
            "dialogue": "A charged silence settles over the scene before someone finally steps forward to answer.",
            "delivery": "",
            "action": "",
            "direction": "",
        }]

    raw_choices = payload.get("branching_paths") or payload.get("new_choices") or payload.get("choices") or []
    if not isinstance(raw_choices, list):
        raw_choices = []
    normalized_choices: List[Dict[str, Any]] = []
    for idx, choice in enumerate(raw_choices[:3]):
        if not isinstance(choice, dict):
            continue
        text = (choice.get("text") or choice.get("label") or "").strip()
        if not text:
            continue
        normalized_choices.append({
            "id": choice.get("id") or f"choice_{idx + 1}",
            "text": text,
            "dramatic_impact": (choice.get("dramatic_impact") or choice.get("emotionalImpact") or "").strip(),
            "visual_representation": (choice.get("visual_representation") or choice.get("nextSceneHint") or "").strip(),
        })
    if len(normalized_choices) < 2:
        normalized_choices = [
            {
                "id": "press_forward",
                "text": "Press forward toward the most immediate lead.",
                "dramatic_impact": "Escalates the scene toward a concrete reveal.",
                "visual_representation": "A decisive move deeper into the tension.",
            },
            {
                "id": "hold_and_probe",
                "text": "Pause and press for more information first.",
                "dramatic_impact": "Turns the moment into a direct confrontation or confession.",
                "visual_representation": "A tense close-up exchange where hidden truths surface.",
            },
            {
                "id": "observe_carefully",
                "text": "Stay cautious and study the room for clues.",
                "dramatic_impact": "Creates an investigative beat that can uncover hidden details.",
                "visual_representation": "Slow, deliberate attention shifts across the environment.",
            },
        ]

    scene_elements = payload.get("scene_elements") if isinstance(payload.get("scene_elements"), dict) else payload.get("sceneElements") if isinstance(payload.get("sceneElements"), dict) else {}
    scene_dynamics = payload.get("scene_dynamics") if isinstance(payload.get("scene_dynamics"), dict) else payload.get("sceneDynamics") if isinstance(payload.get("sceneDynamics"), dict) else {}
    hidden_elements = payload.get("hidden_elements") if isinstance(payload.get("hidden_elements"), dict) else payload.get("hiddenElements") if isinstance(payload.get("hiddenElements"), dict) else {}
    scene_update = payload.get("scene_update") if isinstance(payload.get("scene_update"), dict) else payload.get("sceneUpdate") if isinstance(payload.get("sceneUpdate"), dict) else {}
    story_state = _normalize_story_state_payload(payload, story, hidden_elements, scene_dynamics)

    return {
        "scene_description": (payload.get("scene_description") or "").strip(),
        "cinematic_responses": normalized_responses,
        "scene_elements": {
            "atmosphere": (scene_elements.get("atmosphere") or "").strip(),
            "visual_details": _normalize_string_list(scene_elements.get("visual_details") or scene_elements.get("visualDetails"), 6),
            "symbolic_motifs": _normalize_string_list(scene_elements.get("symbolic_motifs") or scene_elements.get("symbolicMotifs"), 4),
        },
        "branching_paths": normalized_choices,
        "scene_dynamics": {
            "transition_required": _coerce_bool(scene_dynamics.get("transition_required"), False),
            "new_location": (scene_dynamics.get("new_location") or "").strip(),
            "time_progression": (scene_dynamics.get("time_progression") or "").strip(),
            "narrative_advancement": (scene_dynamics.get("narrative_advancement") or "").strip(),
            "scene_transition_caption": (scene_dynamics.get("scene_transition_caption") or "").strip(),
        },
        "hidden_elements": {
            "easter_egg": (hidden_elements.get("easter_egg") or "").strip(),
            "foreshadowing": (hidden_elements.get("foreshadowing") or "").strip(),
        },
        "scene_update": {
            "emotional_tone": (scene_update.get("emotional_tone") or "").strip(),
        },
        "story_state": story_state,
        "npc_reply_expected": _coerce_bool(payload.get("npc_reply_expected"), True),
    }

def get_protagonist(story: Dict) -> Optional[Dict]:
    """Finds the protagonist character in the story's character list."""
    for character in story.get("characters", []):
        if character.get("role") == "protagonist":
            return character
    return None

def is_story_stagnating(story: Dict) -> bool:
    """
    Detect if the story is stuck in a repetitive pattern by analyzing recent messages and choices.
    Returns True if the story appears to be stagnating and needs intervention.
    """
    # Not enough history to determine stagnation
    if "current_scene" not in story or "messages" not in story["current_scene"]:
        return False
    
    messages = story["current_scene"]["messages"]
    if len(messages) < 4:  # Need at least 2 exchanges (4 messages) to detect patterns
        return False
    
    # Check for repetitive choices
    recent_choices = []
    for msg in messages[-8:]:  # Look at last 8 messages
        if msg.get("type") == "choice":
            recent_choices.append(msg.get("content", "").lower())
    
    # Check if same choice appears multiple times
    choice_counts = {}
    for choice in recent_choices:
        choice_counts[choice] = choice_counts.get(choice, 0) + 1
        if choice_counts[choice] > 1:
            logger.warning(f"Detected repeated choice: '{choice}'")
            return True
    
    # Check for similar NPC responses (simplified check for repetitive advice)
    npc_messages = []
    # Get protagonist ID without circular import
    protagonist = get_protagonist(story)
    protagonist_id = protagonist.get("id") if protagonist else None
    
    for msg in messages[-6:]:
        if msg.get("type") == "text" and msg.get("character_id") != protagonist_id:
            npc_messages.append(msg.get("content", "").lower())
    
    # Check for similar phrasing or repeated keywords in NPC messages
    if len(npc_messages) >= 2:
        common_phrases = ["trust", "follow", "path", "journey", "light", "shadow", "within", "courage"]
        repetition_count = 0
        
        for phrase in common_phrases:
            phrase_count = sum(1 for msg in npc_messages if phrase in msg)
            if phrase_count >= 2:
                repetition_count += 1
        
        if repetition_count >= 3:  # If multiple phrases are being repeated
            logger.warning(f"Detected repetitive NPC dialogue patterns with {repetition_count} repeated phrases")
            return True
    
    return False

def normalize_character_id(name: str) -> str:
    """
    将角色名称转换为规范化的ID格式：小写、下划线替代空格
    例如：'John Smith' -> 'john_smith'
    """
    if not name:
        return ""
    # 移除特殊字符，保留字母、数字和空格
    name = ''.join(c for c in name if c.isalnum() or c.isspace())
    # 将空格替换为下划线，转为小写
    return name.lower().replace(' ', '_')

def fix_story_character_ids(story_data):
    """
    修复故事中的角色ID问题：
    1. 确保所有角色都有规范化的ID
    2. 创建角色ID到角色对象的映射
    3. 修复消息中的角色ID引用
    
    Args:
        story_data: 故事数据对象
        
    Returns:
        修复后的故事数据对象
    """
    if not story_data or not isinstance(story_data, dict):
        return story_data
        
    # 1. 确保所有角色都有规范化的ID
    if "characters" in story_data and isinstance(story_data["characters"], list):
        # 首先规范化所有角色ID
        for char in story_data["characters"]:
            if "name" in char and ("id" not in char or not char["id"]):
                # 如果没有ID，根据名称生成
                char["id"] = normalize_character_id(char["name"])
            elif "id" in char:
                # 确保现有ID是规范化的
                original_id = char["id"]
                normalized_id = normalize_character_id(original_id)
                
                # 如果ID不规范，则更新
                if original_id != normalized_id:
                    char["id"] = normalized_id
    
        # 创建ID映射 (包括原始ID和规范化ID)
        id_mapping = {}
        name_to_id = {}
        
        for char in story_data["characters"]:
            if "id" in char:
                # 记录原始ID到规范化ID的映射
                original_id = char["id"]
                id_mapping[original_id] = original_id  # 自身映射
                # 添加去下划线版本映射，便于匹配 'cassandrablake' vs 'cassandra_blake'
                id_no_underscore = original_id.replace("_", "")
                id_mapping[id_no_underscore] = original_id
                
                # 如果有名称，也创建名称到ID的映射
                if "name" in char:
                    name = char["name"]
                    name_to_id[name.lower()] = original_id
                    # 添加规范化名称映射
                    normalized_name = normalize_character_id(name)
                    name_to_id[normalized_name] = original_id
                    # 添加无空格名称映射
                    name_to_id[name.lower().replace(" ", "")] = original_id
        
        # 2. 修复消息中的角色ID引用
        if "current_scene" in story_data and "messages" in story_data["current_scene"]:
            for msg in story_data["current_scene"]["messages"]:
                if "character_id" in msg:
                    char_id = msg["character_id"]
                    
                    # 如果ID不在映射中，尝试修复
                    if char_id not in id_mapping:
                        # 尝试规范化
                        normalized_id = normalize_character_id(char_id)
                        if normalized_id in id_mapping:
                            msg["character_id"] = normalized_id
                        # 尝试通过名称匹配
                        elif char_id.lower() in name_to_id:
                            msg["character_id"] = name_to_id[char_id.lower()]
                        # 尝试通过规范化名称匹配
                        elif normalize_character_id(char_id) in name_to_id:
                            msg["character_id"] = name_to_id[normalize_character_id(char_id)]
    
    return story_data 

def standardize_story_response(response_data):
    """
    Standardize all character IDs and field names in a story response before sending to frontend.
    This ensures consistent field naming and character ID formats across the application.
    
    Args:
        response_data: The story response data to standardize
        
    Returns:
        Standardized story response data
    """
    if not response_data or not isinstance(response_data, dict):
        return response_data
    
    # First fix character IDs
    response_data = fix_story_character_ids(response_data)
    
    # Standardize field names (character_id vs characterId)
    if "current_scene" in response_data and "messages" in response_data["current_scene"]:
        for msg in response_data["current_scene"]["messages"]:
            # Ensure character_id is present and standardized
            if "characterId" in msg and "character_id" not in msg:
                msg["character_id"] = msg["characterId"]
            elif "character_id" in msg and "characterId" not in msg:
                msg["characterId"] = msg["character_id"]
            if "renderMode" in msg and "render_mode" not in msg:
                msg["render_mode"] = msg["renderMode"]
            elif "render_mode" in msg and "renderMode" not in msg:
                msg["renderMode"] = msg["render_mode"]
    
    # Add any other standardization needed
    
    return response_data 
