"""
Meta-planner module for enhancing story interaction and progression.
This module provides:
1. Story progression analysis and reflection generation
2. Interactive UI element generation through code
"""

import json
import logging
from typing import Dict, Any, List, Optional
import base64  # Add this import for image encoding/decoding
import os  # Add this import for file path operations
import re
import requests  # Add this import for remove.bg API
import asyncio  # Add this import for rate limiting
import time  # Add this import for rate limiting
from PIL import Image
from io import BytesIO
from pathlib import Path  # Add this import for path manipulation

try:
    import replicate  # Add this import for Replicate API
except ImportError:  # pragma: no cover - optional dependency
    replicate = None

try:
    from google import genai
except ImportError:  # pragma: no cover - optional dependency
    genai = None

from src.llm_client import get_llm_completion
from src.config import settings

# Configure logging
logger = logging.getLogger(__name__)

# Rate limiting for Replicate API (6 requests per minute for free tier)
_replicate_last_request_time = 0
_replicate_min_interval = 10.0  # 10 seconds between requests to stay under 6/min

# Prompt templates
STORY_REFLECTION_PROMPT = """
You are a storytelling analyst reviewing the current state of an interactive story.
Your task is to provide brief, actionable insights to enhance the next story response.

STORY CONTEXT:
Title: {title}
Theme: {theme}
Current Act: {current_act}
Emotional Goal: {emotional_goal}
Dialogue Count: {dialogue_count} messages in current scene

RECENT CONVERSATION:
{conversation_history}

USER'S LATEST ACTION:
{user_input}

Provide a concise reflection focusing ONLY on these key aspects:

1. PLOT STATUS:
   - Brief assessment of current narrative situation
   - Key unresolved tension points

2. USER CHOICE ANALYSIS:
   - What the user's choice/input indicates about their interests
   - How this should influence the story direction

3. STORY ADVANCEMENT STRATEGY:
   - 1-2 specific suggestions to advance the plot effectively
   - How to maintain engagement in the next response
   - PACING DIRECTIVE: Based on dialogue count in current scene:
     * If count < 10: Normal pacing is acceptable
     * If count 10-12: Begin introducing new elements or minor tension
     * If count 13-14: Strongly suggest plot acceleration or conflict escalation
     * If count >= 15: MANDATORY scene transition, location change, or major story event
     * The closer to or further beyond 15 messages, the stronger the transition should be

4. UI ELEMENT RECOMMENDATION (OPTIONAL):
   - Only recommend when a tangible, interactive artifact would create a memorable story moment
   - Think like an escape room designer or immersive theater director — the element should feel like a physical prop from the story world
   - GOOD examples: a torn letter the player unfolds, a cipher they must decode, a locked box with a combination, a hand-drawn map with hidden locations, a flickering radio to tune, a shattered mirror revealing a message
   - BAD examples: a summary card, a character profile panel, a simple list, a basic text display with a fancy border — these are boring UI, not experiences
   - PURPOSE REQUIREMENTS: The "purpose" MUST describe what the player physically DOES and what they DISCOVER (e.g., "Decode the cipher on the postcard to reveal the meeting location"). Never use vague phrases like "enhance immersion" or "provide interactivity".

Keep your analysis concise and practical - focus on how to optimize the next story response.
Provide your reflection in a simple JSON format with these exact keys.

CRITICAL: Return ONLY valid, properly formatted JSON with no additional text, markdown, or explanations.

REQUIRED JSON SCHEMA:
```json
{{
  "plot_status": {{
    "current_situation": "string (brief assessment of where the story stands)",
    "unresolved_tensions": ["string (list of key unresolved tensions)"]
  }},
  "user_choice_analysis": {{
    "user_interests": ["string (what the user's choice reveals about their interests)"],
    "influence_direction": "string (how this should shape the story direction)"
  }},
  "story_advancement_strategy": {{
    "plot_suggestions": ["string (1-2 specific ways to advance the plot)"],
    "engagement_tactics": ["string (how to maintain user engagement)"],
    "pacing_assessment": "string (whether to maintain current pace or accelerate - MUST recommend acceleration if dialogue count > 15)"
  }},
  "ui_element_recommendation": {{
    "element_type": "string (type of UI element, e.g., 'puzzle', 'map', 'letter', etc.)",
    "description": "string (brief description of what the element should contain)",
    "purpose": "string (how this element enhances the story experience)"
  }}
}}
```

Note: The "ui_element_recommendation" object should ONLY be included if a UI element would significantly enhance this moment. Otherwise, omit this field entirely.
"""

INTERACTIVE_ELEMENT_PROMPT = """
You are a world-class interactive experience designer who creates captivating, story-driven micro-experiences using HTML, CSS and JavaScript. Your creations feel like moments plucked from award-winning indie games or immersive theater — NOT generic web UI components.

Your output will be rendered inside an interactive story app. The player is deeply immersed in a narrative. Your element must AMPLIFY that immersion, not break it.

═══════════════════════════════════════════
STORY CONTEXT:
{story_context}
═══════════════════════════════════════════

ELEMENT REQUEST: {element_type}
{element_description}

CONTENT / NARRATIVE DETAILS:
{content_details}

PREVIOUS INTERACTIVE ELEMENTS ALREADY USED IN THIS STORY:
{previous_elements_summary}

═══════════════════════════════════════════
DESIGN PHILOSOPHY — READ CAREFULLY:

1. **EXPERIENCE FIRST, UI SECOND**
   You are not building a form or a dashboard. You are crafting a *moment*. Every interactive element should feel like the player is touching the story world — unfolding a letter, decoding a cipher, exploring a map, making a fateful choice. Think "escape room prop" not "web component".

2. **ATMOSPHERE IS EVERYTHING**
   - Match the story's mood: dark mystery → muted palette, candlelight glow, paper textures; hopeful journey → warm gradients, gentle particle effects, sunrise tones.
   - Use cinematic techniques: depth-of-field blur, vignette overlays, ambient micro-animations (flickering, floating dust, slow pulse).
   - Typography IS design: use font-weight, letter-spacing, and size contrast dramatically. A single word at 48px bold can be more powerful than a paragraph.

3. **DELIGHT THROUGH INTERACTION**
   - Every click, hover, or drag should have tactile feedback: subtle scale, glow, shake, or sound-like visual pulse.
   - Reveal information progressively — don't dump everything at once. Fade in, slide in, typewriter-reveal, or unlock in stages.
   - Create a sense of discovery: hidden details that appear on hover, content that reveals when a puzzle is solved, elements that react to user input in surprising ways.

4. **EXAMPLES OF GREAT INTERACTIVE ELEMENTS** (for inspiration, not literal copy):
   - A torn letter that the player "unfolds" by clicking, with handwriting font and coffee-stain texture
   - A star map where clicking constellations reveals memories
   - A locked diary with a combination lock the player must solve using story clues
   - A polaroid photo wall where dragging photos reveals connections
   - A flickering radio dial the player tunes to hear different "transmissions"
   - A shattered mirror where clicking fragments reconstructs a hidden message
   - A ticking countdown clock that creates urgency
   - A hand-drawn map with fog-of-war that clears as the player explores

5. **ANTI-PATTERNS — AVOID THESE**:
   ✗ Plain cards/boxes with text and a button — boring
   ✗ Standard form inputs styled slightly differently — lazy
   ✗ Simple lists or bullet points in a fancy container — not interactive
   ✗ Generic modals or popups — breaks immersion
   ✗ Static infographics with no real interaction — missed opportunity
   ✗ Debug consoles or readout areas — this is for the PLAYER, not a developer

6. **NOVELTY REQUIREMENT — DO NOT REPEAT YOURSELF**
   - Study the previously used interactive elements listed above.
   - Your new element MUST feel materially different in BOTH:
     1. visual identity / prop format
     2. interaction pattern
   - If a prior element was a letter to click open, do NOT make another document-reveal interaction.
   - If a prior element used clicking hotspots, prefer a different mechanic such as dragging, arranging, tuning, decoding, flipping, tracing, or timed reveal.
   - Repeating the same core metaphor, layout, or interaction style is a failure.
   - The player should feel: "this is a new kind of moment," not "this is the same widget with different text."

═══════════════════════════════════════════
TECHNICAL REQUIREMENTS:

- Vanilla HTML + CSS + JS only (no external libraries or CDN imports)
- Single self-contained HTML document with embedded <style> and <script>
- Responsive: works well in a container ~400-700px wide
- Performant: use CSS animations/transitions over JS-driven animation where possible; keep under 300 lines
- Use CSS features creatively: gradients, backdrop-filter, clip-path, mix-blend-mode, @keyframes
- If you create iframes, include sandbox="allow-scripts allow-modals"
- Do NOT include any pre-display overlays, consent banners, or explanatory text — the host app handles that

CRITICAL RESPONSE FORMAT:
- Return ONLY the raw HTML code (with embedded CSS/JS)
- No explanations, no markdown, no code fences
- Must start with <html> and be valid/complete
"""


def _summarize_interaction_pattern(html_code: str) -> str:
    html = (html_code or "").lower()
    patterns = []
    if any(token in html for token in ["drag", "draggable", "ondrag", "pointermove"]):
        patterns.append("drag-and-arrange interaction")
    if any(token in html for token in ["input", "textarea", "contenteditable", "type=\"text\"", "type='text'"]):
        patterns.append("text-entry or code-entry interaction")
    if any(token in html for token in ["slider", "range", "dial", "knob"]):
        patterns.append("tuning or slider-based interaction")
    if any(token in html for token in ["hover", "mouseenter", "mouseover"]):
        patterns.append("hover-reveal interaction")
    if any(token in html for token in ["flip", "card", "rotatey", "perspective"]):
        patterns.append("flip-or-reveal interaction")
    if any(token in html for token in ["timer", "countdown", "setinterval"]):
        patterns.append("timed interaction")
    if any(token in html for token in ["button", "onclick"]):
        patterns.append("click-to-reveal interaction")
    return patterns[0] if patterns else "tap/click interaction"


def _summarize_visual_style(element_type: str, description: str, html_code: str) -> str:
    joined = " ".join([element_type or "", description or "", html_code or ""]).lower()
    if any(token in joined for token in ["letter", "postcard", "paper", "diary", "journal"]):
        return "paper-prop aesthetic"
    if any(token in joined for token in ["map", "compass", "route", "path"]):
        return "map-like exploration aesthetic"
    if any(token in joined for token in ["radio", "signal", "frequency", "dial"]):
        return "analog-device aesthetic"
    if any(token in joined for token in ["mirror", "shard", "glass"]):
        return "fragmented reflective aesthetic"
    if any(token in joined for token in ["photo", "polaroid", "gallery"]):
        return "photo-memory aesthetic"
    if any(token in joined for token in ["lock", "safe", "cipher", "code", "puzzle"]):
        return "mystery-puzzle aesthetic"
    return f"{(element_type or 'interactive').replace('_', ' ')} aesthetic"


def build_interactive_element_summary(
    element_type: str,
    element_description: str,
    element_purpose: Optional[str],
    html_code: str,
) -> str:
    visual = _summarize_visual_style(element_type, element_description, html_code)
    interaction = _summarize_interaction_pattern(html_code)
    purpose = (element_purpose or element_description or "advance the story").strip().rstrip(".")
    return (
        f"A {visual} built as a {element_type.replace('_', ' ')}; "
        f"the player engages through {interaction} to {purpose.lower()}."
    )


def _build_interactive_element_tags(
    element_type: str,
    element_description: str,
    html_code: str,
) -> List[str]:
    joined = " ".join([element_type or "", element_description or "", html_code or ""]).lower()
    tags = {
        (element_type or "generic").replace("_", "-").lower(),
        _summarize_visual_style(element_type, element_description, html_code).replace(" ", "-"),
        _summarize_interaction_pattern(html_code).replace(" ", "-"),
    }
    keyword_groups = {
        "document": ["letter", "postcard", "paper", "diary", "journal", "note"],
        "map": ["map", "route", "path", "compass", "cartography"],
        "device": ["radio", "dial", "signal", "frequency", "knob"],
        "memory": ["photo", "polaroid", "memory", "gallery"],
        "puzzle": ["cipher", "code", "lock", "safe", "puzzle"],
        "hover": ["hover", "mouseenter", "mouseover"],
        "drag": ["drag", "draggable", "pointermove"],
        "typing": ["input", "textarea", "contenteditable"],
        "timer": ["timer", "countdown", "setinterval"],
        "flip": ["flip", "rotatey", "perspective", "card"],
        "click": ["onclick", "button", "tap", "reveal"],
    }
    for tag, markers in keyword_groups.items():
        if any(marker in joined for marker in markers):
            tags.add(tag)
    return sorted(tag for tag in tags if tag)


def _interactive_element_similarity_score(
    candidate_tags: List[str],
    previous_tags: List[str],
) -> float:
    current = set(candidate_tags)
    previous = set(previous_tags)
    if not current or not previous:
        return 0.0
    overlap = len(current & previous)
    union = len(current | previous)
    score = overlap / union if union else 0.0
    if any(tag in current and tag in previous for tag in ["document", "map", "device", "memory", "puzzle"]):
        score += 0.2
    if any(tag in current and tag in previous for tag in ["drag", "typing", "timer", "flip", "hover", "click"]):
        score += 0.2
    return min(score, 1.0)


def _summary_similarity_score(candidate_summary: str, previous_summary: str) -> float:
    candidate_tokens = {
        token for token in re.findall(r"[a-z0-9]+", (candidate_summary or "").lower())
        if len(token) > 3
    }
    previous_tokens = {
        token for token in re.findall(r"[a-z0-9]+", (previous_summary or "").lower())
        if len(token) > 3
    }
    if not candidate_tokens or not previous_tokens:
        return 0.0
    overlap = len(candidate_tokens & previous_tokens)
    union = len(candidate_tokens | previous_tokens)
    score = overlap / union if union else 0.0

    high_signal_terms = {
        "letter", "postcard", "paper", "diary", "journal",
        "map", "compass", "route", "radio", "signal", "dial",
        "mirror", "photo", "polaroid", "cipher", "lock", "puzzle",
        "hover", "drag", "typing", "timer", "countdown", "click",
    }
    repeated_high_signal = candidate_tokens & previous_tokens & high_signal_terms
    if repeated_high_signal:
        score += 0.15
    return min(score, 1.0)


def _extract_html_code(content: str) -> str:
    if "```html" in content:
        start_idx = content.find("```html") + 7
        end_idx = content.find("```", start_idx)
        return content[start_idx:end_idx].strip() if end_idx > start_idx else content
    if "```" in content:
        start_idx = content.find("```") + 3
        end_idx = content.find("```", start_idx)
        return content[start_idx:end_idx].strip() if end_idx > start_idx else content
    return content


def _build_story_trace_context(
    story_data: Dict[str, Any],
    source: str,
    task: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    session_id = story_data.get("session_id")
    if not session_id:
        return None
    return {
        "session_id": session_id,
        "participant_id": story_data.get("participant_id"),
        "story_id": story_data.get("id"),
        "source": source,
        "task": task,
        "metadata": metadata or {},
    }

async def generate_story_reflection(
    story_data: Dict[str, Any], 
    user_input: str, 
    conversation_history: str,
    dialogue_count: int = 0
) -> Dict[str, Any]:
    """
    Generate a reflection on the current story state and provide guidance
    for the next steps in the narrative.
    
    Args:
        story_data: Current story state and metadata
        user_input: The user's most recent input
        conversation_history: Recent conversation history
        dialogue_count: Number of dialogue exchanges in current scene
        
    Returns:
        A dictionary containing structured reflection and recommendations
    """
    raw_content_for_debug: str = ""  # ensure variable exists for exception logging
    try:
        llm_config = story_data.get("llm_config", {})
        # Prepare the prompt
        prompt = STORY_REFLECTION_PROMPT.format(
            title=story_data.get("title", "Untitled Story"),
            theme=story_data.get("cinematic_theme", story_data.get("theme", "")),
            current_act=story_data.get("current_act", 0) + 1,  # 1-indexed for display
            emotional_goal=story_data.get("emotional_undercurrent", story_data.get("emotional_goal", "")),
            conversation_history=conversation_history,
            user_input=user_input,
            dialogue_count=dialogue_count
        )
        
        # Call the LLM
        messages = [
            {"role": "system", "content": "You are a concise storytelling analyst focused on practical story optimization."},
            {"role": "user", "content": prompt}
        ]
        
        logger.info(f"Generating story reflection for story '{story_data.get('title', 'Untitled')}'")
        
        response = await asyncio.to_thread(
            get_llm_completion,
            messages=messages,
            model=llm_config.get("reflection", settings.get_llm_model("reflection")),
            task="reflection",
            trace_context=_build_story_trace_context(
                story_data,
                "story_reflection",
                "reflection",
                metadata={
                    "user_input": user_input,
                    "dialogue_count": dialogue_count,
                    "conversation_history": conversation_history,
                },
            ),
        )
        
        if response["error"]:
            logger.error(f"Error generating story reflection: {response['error']}")
            return {
                "success": False,
                "error": f"Failed to generate reflection: {response['error']}",
                "reflection": None
            }
        
        # Extract JSON from response
        content = response.get("content", "")
        raw_content_for_debug = content
        try:
            # Clean up the content - remove any markdown formatting or extra text
            content = content.strip()
            if "```json" in content:
                # Extract from markdown code block
                start_idx = content.find("```json") + 7
                end_idx = content.find("```", start_idx)
                if end_idx > start_idx:
                    content = content[start_idx:end_idx].strip()
            elif "```" in content:
                # Extract from generic code block
                start_idx = content.find("```") + 3
                end_idx = content.find("```", start_idx)
                if end_idx > start_idx:
                    content = content[start_idx:end_idx].strip()
            
            # Find JSON object boundaries
            start_idx = content.find('{')
            end_idx = content.rfind('}') + 1
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = content[start_idx:end_idx]
                # Try to parse the JSON
                try:
                    reflection = json.loads(json_str)
                    logger.info("Successfully extracted JSON reflection data")
                except json.JSONDecodeError:
                    # If direct parsing fails, try to clean the string further
                    # Remove any potential Unicode characters or control characters
                    import re
                    cleaned_json = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', json_str)
                    reflection = json.loads(cleaned_json)
                    logger.info("Successfully extracted JSON reflection data after cleaning")
            else:
                # If no JSON object found, create a default structure
                logger.warning("No valid JSON structure found in reflection response")
                reflection = {
                    "plot_status": {
                        "current_situation": "Unable to parse response",
                        "unresolved_tensions": ["Response parsing error"]
                    },
                    "user_choice_analysis": {
                        "user_interests": ["Unknown due to parsing error"],
                        "influence_direction": "Continue with planned story direction"
                    },
                    "story_advancement_strategy": {
                        "plot_suggestions": ["Continue with current narrative thread"],
                        "engagement_tactics": ["Focus on character development"]
                    }
                }
            
            logger.info(f"--- GENERATED REFLECTION STRUCTURE ---")
            for key in reflection:
                logger.info(f"Section: {key}")
            
            return {
                "success": True,
                "reflection": reflection,
                "raw_content": raw_content_for_debug  # Include raw content for easier debugging
            }
        except Exception as e:
            logger.exception(f"Failed to parse reflection JSON: {e}")
            # Create a fallback reflection structure
            fallback_reflection = {
                "plot_status": {
                    "current_situation": "Error parsing reflection data",
                    "unresolved_tensions": ["Parsing error occurred"]
                },
                "user_choice_analysis": {
                    "user_interests": ["Unknown due to parsing error"],
                    "influence_direction": "Continue with planned story direction"
                },
                "story_advancement_strategy": {
                    "plot_suggestions": ["Continue with current narrative thread"],
                    "engagement_tactics": ["Focus on character development"]
                }
            }
            
            return {
                "success": True,  # Return success=True with fallback data to prevent cascading failures
                "error": str(e),
                "reflection": fallback_reflection,
                "raw_content": raw_content_for_debug  # Include raw content for easier debugging
            }
            
    except Exception as e:
        logger.exception(f"Error in generate_story_reflection: {e}")
        # Also log raw content if available
        try:
            logger.error(f"Raw reflection response: {raw_content_for_debug}")
        except NameError:
            # raw_content_for_debug may not exist if we failed earlier
            pass
        return {
            "success": False,
            "error": str(e),
            "reflection": None,
            "raw_content": raw_content_for_debug
        }

async def generate_interactive_element(
    element_type: str,
    element_description: str,
    content_details: str,
            story_context: Dict[str, Any],
    element_purpose: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate an interactive UI element using HTML, CSS, and JavaScript
    to enhance the story experience.
    
    Args:
        element_type: Type of element to generate (letter, map, puzzle, etc.)
        element_description: Description of what the element should do
        content_details: Specific content to include in the element
        story_context: Current story state and metadata for context
        
    Returns:
        A dictionary containing the generated HTML/CSS/JS code
    """
    try:
        llm_config = story_context.get("llm_config", {})
        previous_summaries = story_context.get("interactive_element_summaries", []) or []
        previous_tag_memory = story_context.get("interactive_element_tags", []) or []
        previous_elements_summary = (
            "\n".join([f"- {summary}" for summary in previous_summaries[-6:]])
            if previous_summaries
            else "- None yet. This is the first major interactive element in the story."
        )
        # Format story context for the prompt
        context_str = f"""
Title: {story_context.get('title', 'Untitled Story')}
Setting: {story_context.get('setting', {}).get('primary_location', 'Unknown location')}
Time Period: {story_context.get('setting', {}).get('time_period', 'Present day')}
Atmosphere: {story_context.get('setting', {}).get('atmosphere', 'Neutral')}
"""
        
        # Prepare the prompt
        prompt = INTERACTIVE_ELEMENT_PROMPT.format(
            story_context=context_str,
            element_description=element_description,
            element_type=element_type,
            content_details=content_details,
            previous_elements_summary=previous_elements_summary,
        )
        
        # Call the LLM
        messages = [
            {"role": "system", "content": "You are an award-winning interactive experience designer. You create captivating, atmospheric micro-experiences that make players feel like they are physically touching the story world. Your work blends cinematic aesthetics with tactile interactivity — every element you build is a memorable moment, never a generic UI widget."},
            {"role": "user", "content": prompt}
        ]
        model_name = llm_config.get("interactive_element", settings.get_llm_model("interactive_element"))
        response = await asyncio.to_thread(
            get_llm_completion,
            messages=messages,
            model=model_name,
            task="interactive_element",
            trace_context=_build_story_trace_context(
                story_context,
                "interactive_element",
                "interactive_element",
                metadata={
                    "element_type": element_type,
                    "element_description": element_description,
                    "content_details": content_details,
                    "element_purpose": element_purpose,
                    "previous_elements_count": len(previous_summaries),
                },
            ),
        )
        if response["error"]:
            logger.error(f"Error generating interactive element: {response['error']}")
            return {
                "success": False,
                "error": f"Failed to generate interactive element: {response['error']}",
                "code": None
            }

        html_code = _extract_html_code(response["content"])
        element_summary = build_interactive_element_summary(
            element_type=element_type,
            element_description=element_description,
            element_purpose=element_purpose,
            html_code=html_code,
        )
        element_tags = _build_interactive_element_tags(element_type, element_description, html_code)

        should_retry = False
        similarity_score = 0.0
        closest_summary = None
        for idx, prev_summary in enumerate(previous_summaries[-6:]):
            prev_tags = previous_tag_memory[-6:][idx] if idx < len(previous_tag_memory[-6:]) else []
            tag_score = _interactive_element_similarity_score(element_tags, prev_tags)
            summary_score = _summary_similarity_score(element_summary, prev_summary)
            combined_score = max(tag_score, summary_score)
            if combined_score > similarity_score:
                similarity_score = combined_score
                closest_summary = prev_summary
        should_retry = similarity_score >= 0.58

        if should_retry:
            logger.info(
                f"Interactive element too similar to prior memory (score={similarity_score:.2f}); retrying once."
            )
            retry_prompt = (
                f"{prompt}\n\n"
                f"RETRY INSTRUCTION:\n"
                f"The previous attempt felt too similar to an earlier interactive element.\n"
                f"Closest prior element: {closest_summary}\n"
                f"Similarity score: {similarity_score:.2f}\n"
                f"You MUST produce a distinctly different prop format and interaction mechanic.\n"
                f"Avoid the prior pattern summarized as: {closest_summary}\n"
                f"Avoid these tags from the rejected attempt: {', '.join(element_tags)}.\n"
                f"Do not repeat the same visual metaphor, reveal pattern, or interaction loop.\n"
            )
            retry_response = await asyncio.to_thread(
                get_llm_completion,
                messages=[
                    messages[0],
                    {"role": "user", "content": retry_prompt},
                ],
                model=model_name,
                task="interactive_element",
                trace_context=_build_story_trace_context(
                    story_context,
                    "interactive_element",
                    "interactive_element",
                    metadata={
                        "element_type": element_type,
                        "element_description": element_description,
                        "content_details": content_details,
                        "element_purpose": element_purpose,
                        "previous_elements_count": len(previous_summaries),
                        "retry_attempt": 1,
                        "closest_summary": closest_summary,
                        "similarity_score": similarity_score,
                    },
                ),
            )
            if not retry_response.get("error"):
                retry_html = _extract_html_code(retry_response.get("content", ""))
                retry_summary = build_interactive_element_summary(
                    element_type=element_type,
                    element_description=element_description,
                    element_purpose=element_purpose,
                    html_code=retry_html,
                )
                retry_tags = _build_interactive_element_tags(element_type, element_description, retry_html)
                retry_similarity = 0.0
                for idx, prev_summary in enumerate(previous_summaries[-6:]):
                    prev_tags = previous_tag_memory[-6:][idx] if idx < len(previous_tag_memory[-6:]) else []
                    retry_similarity = max(
                        retry_similarity,
                        _interactive_element_similarity_score(retry_tags, prev_tags),
                        _summary_similarity_score(retry_summary, prev_summary),
                    )
                if retry_similarity < similarity_score:
                    html_code = retry_html
                    element_summary = retry_summary
                    element_tags = retry_tags
                    similarity_score = retry_similarity
                    logger.info(f"Accepted regenerated interactive element (score={retry_similarity:.2f}).")

        memory = story_context.setdefault("interactive_element_summaries", [])
        memory.append(element_summary)
        story_context["interactive_element_summaries"] = memory[-8:]
        tag_memory = story_context.setdefault("interactive_element_tags", [])
        tag_memory.append(element_tags)
        story_context["interactive_element_tags"] = tag_memory[-8:]
        similarity_memory = story_context.setdefault("interactive_element_similarity_scores", [])
        similarity_memory.append(round(similarity_score, 3))
        story_context["interactive_element_similarity_scores"] = similarity_memory[-8:]

        return {
            "success": True,
            "code": html_code,
            "element_type": element_type,
            "element_description": element_description,
            "purpose": element_purpose,
            "prompt": element_purpose or element_description or content_details,
            "summary": element_summary,
            "novelty_tags": element_tags,
            "similarity_score": similarity_score,
        }
            
    except Exception as e:
        logger.error(f"Error in generate_interactive_element: {e}")
        return {
            "success": False,
            "error": str(e),
            "code": None
        }

async def generate_image(
    prompt: str,
    output_path: Optional[str] = None,
    api_provider: str = "openai",
    model: str = "gpt-image-1",
    size: str = "1024x1024",
    quality: str = "standard",
    style: str = "vivid",
    save_image: bool = True,
    **kwargs
) -> Dict[str, Any]:
    if api_provider == "openai":
        return await _generate_image_openai(
            prompt=prompt,
            output_path=output_path,
            model=model,
            size=size,
            quality=quality,
            style=style,
            save_image=save_image,
            **kwargs
        )
    elif api_provider == "gemini":
        return await _generate_image_gemini(
            prompt=prompt,
            output_path=output_path,
            model=model,
            size=size,
            quality=quality,
            style=style,
            save_image=save_image,
            **kwargs
        )
    else:
        return {"success": False, "error": "Unsupported API provider"}

async def _generate_image_openai(
    prompt: str,
    output_path: Optional[str] = None,
    model: str = "gpt-image-1",
    size: str = "1024x1024",
    quality: str = "standard",
    style: str = "vivid",
    save_image: bool = True,
    **kwargs
) -> Dict[str, Any]:
    """
    Generate image using OpenAI API.
    """
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            timeout=settings.LLM_REQUEST_TIMEOUT_SECONDS,
        )
        logger.info(f"[OpenAI] Generating image with prompt: {prompt[:50]}...")
        result = client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            quality=quality
        )
        image_base64 = result.data[0].b64_json
        if save_image:
            if not output_path:
                images_dir = Path("images")
                images_dir.mkdir(exist_ok=True)
                clean_prompt = "".join(c if c.isalnum() or c in " _-" else "_" for c in prompt[:30])
                words = clean_prompt.split()
                filename = "_".join(words[:5]) + ".png"
                output_path = str(images_dir / filename)
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            image_bytes = base64.b64decode(image_base64)
            with open(output_path, "wb") as f:
                f.write(image_bytes)
            logger.info(f"[OpenAI] Image saved to: {output_path}")
            return {
                "success": True,
                "image_data": image_base64,
                "image_path": output_path
            }
        else:
            return {
                "success": True,
                "image_data": image_base64
            }
    except Exception as e:
        logger.error(f"[OpenAI] Error generating image: {e}")
        return {
            "success": False,
            "error": str(e)
        }

async def _generate_image_gemini(
    prompt: str,
    output_path: Optional[str] = None,
    model: str = "gemini-2.5-flash-image-preview",
    size: str = "1024x1024",  # Gemini API may not support size param, kept for compatibility
    quality: str = "standard",
    style: str = "vivid",
    save_image: bool = True,
    **kwargs
) -> Dict[str, Any]:
    """
    Generate image using Google Gemini API (google-genai SDK).
    """
    try:
        # 使用配置中的API key
        if genai is None:
            raise ValueError("google-genai package is not installed")
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            raise ValueError("GEMINI_API_KEY not configured in settings")

        client = genai.Client(api_key=api_key)
        logger.info(f"[Gemini] Generating image with prompt: {prompt[:50]}...")
        response = client.models.generate_content(
            model=model,
            contents=[prompt],
        )
        image_base64 = None
        for part in response.candidates[0].content.parts:
            if getattr(part, 'inline_data', None) is not None:
                # Gemini返回的data已经是base64编码的字符串,不是bytes
                raw_data = part.inline_data.data
                if isinstance(raw_data, bytes):
                    # 如果是bytes,需要先解码为字符串(base64格式)
                    image_base64 = raw_data.decode('utf-8')
                else:
                    # 如果已经是字符串,直接使用
                    image_base64 = raw_data
                if save_image:
                    if not output_path:
                        images_dir = Path("images")
                        images_dir.mkdir(exist_ok=True)
                        clean_prompt = "".join(c if c.isalnum() or c in " _-" else "_" for c in prompt[:30])
                        words = clean_prompt.split()
                        filename = "_".join(words[:5]) + ".png"
                        output_path = str(images_dir / filename)
                    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                    # 解码base64数据并保存
                    image_bytes = base64.b64decode(image_base64)
                    image = Image.open(BytesIO(image_bytes))
                    image.save(output_path)
                    logger.info(f"[Gemini] Image saved to: {output_path}")
                    return {
                        "success": True,
                        "image_data": image_base64,
                        "image_path": output_path
                    }
                else:
                    return {
                        "success": True,
                        "image_data": image_base64
                    }
        return {"success": False, "error": "No image data returned from Gemini."}
    except Exception as e:
        logger.error(f"[Gemini] Error generating image: {e}")
        return {
            "success": False,
            "error": str(e)
        }

async def remove_background(image_path: str) -> Dict[str, Any]:
    """
    Remove background from an image using configured API provider.

    Args:
        image_path: Path to the image file

    Returns:
        Dict with success status and processed image path
    """
    provider = settings.BG_REMOVAL_PROVIDER

    if provider == "replicate":
        return await _remove_background_replicate(image_path)
    elif provider == "removebg":
        return await _remove_background_removebg(image_path)
    else:
        logger.warning(f"[Background Removal] Unknown provider: {provider}, skipping")
        return {
            "success": False,
            "error": f"Unknown provider: {provider}",
            "original_path": image_path
        }

async def _remove_background_replicate(image_path: str) -> Dict[str, Any]:
    """
    Remove background using Replicate API with rate limiting.
    """
    global _replicate_last_request_time

    try:
        if replicate is None:
            logger.warning("[Replicate] Python package not installed, skipping background removal")
            return {
                "success": False,
                "error": "replicate package is not installed",
                "original_path": image_path
            }
        api_token = settings.REPLICATE_API_TOKEN
        if not api_token:
            logger.warning("[Replicate] API token not configured, skipping background removal")
            return {
                "success": False,
                "error": "REPLICATE_API_TOKEN not configured",
                "original_path": image_path
            }

        # Rate limiting: wait if necessary
        current_time = time.time()
        time_since_last_request = current_time - _replicate_last_request_time
        if time_since_last_request < _replicate_min_interval:
            wait_time = _replicate_min_interval - time_since_last_request
            logger.info(f"[Replicate] Rate limiting: waiting {wait_time:.1f}s before next request")
            await asyncio.sleep(wait_time)

        logger.info(f"[Replicate] Removing background from: {image_path}")

        # Update last request time
        _replicate_last_request_time = time.time()

        # Upload and process image with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with open(image_path, "rb") as image_file:
                    output = replicate.run(
                        "bria/remove-background",
                        input={
                            "image": image_file,
                            "content_moderation": False,
                            "preserve_partial_alpha": True
                        }
                    )

                # Write the processed image back to the same path
                with open(image_path, "wb") as out_file:
                    out_file.write(output.read())

                logger.info(f"[Replicate] Background removed successfully, saved to: {image_path}")
                return {
                    "success": True,
                    "image_path": image_path
                }
            except Exception as retry_error:
                if "429" in str(retry_error) and attempt < max_retries - 1:
                    # If rate limited, wait longer and retry
                    retry_wait = (attempt + 1) * 15  # 15s, 30s, 45s
                    logger.warning(f"[Replicate] Rate limited, retrying in {retry_wait}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_wait)
                else:
                    raise retry_error

    except Exception as e:
        logger.error(f"[Replicate] Error removing background: {e}")
        return {
            "success": False,
            "error": str(e),
            "original_path": image_path
        }

async def _remove_background_removebg(image_path: str) -> Dict[str, Any]:
    """
    Remove background using remove.bg API.
    """
    try:
        api_key = settings.REMOVEBG_API_KEY
        if not api_key:
            logger.warning("[Remove.bg] API key not configured, skipping background removal")
            return {
                "success": False,
                "error": "REMOVEBG_API_KEY not configured",
                "original_path": image_path
            }

        logger.info(f"[Remove.bg] Removing background from: {image_path}")

        # Read the image file
        with open(image_path, 'rb') as image_file:
            response = requests.post(
                'https://api.remove.bg/v1.0/removebg',
                files={'image_file': image_file},
                data={'size': 'auto'},
                headers={'X-Api-Key': api_key},
            )

        if response.status_code == requests.codes.ok:
            # Save the processed image (overwrite the original)
            with open(image_path, 'wb') as out_file:
                out_file.write(response.content)

            logger.info(f"[Remove.bg] Background removed successfully, saved to: {image_path}")
            return {
                "success": True,
                "image_path": image_path
            }
        else:
            error_msg = f"Error: {response.status_code}, {response.text}"
            logger.error(f"[Remove.bg] {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "original_path": image_path
            }

    except Exception as e:
        logger.error(f"[Remove.bg] Error removing background: {e}")
        return {
            "success": False,
            "error": str(e),
            "original_path": image_path
        }
