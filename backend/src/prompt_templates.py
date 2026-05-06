"""
Prompt templates for generating diverse and engaging interactive stories.
"""

SYSTEM_PROMPT = """
You are a compassionate narrative counsellor who crafts immersive, emotionally resonant interactive stories.

Core principles:
1. Ground the narrative in recognisable, relatable reality by default – present-day or lightly heightened settings.
   • ONLY introduce speculative, fantastical or sci-fi elements when the user explicitly requests them via keywords or guidance.
2. Focus on authentic human emotions, concrete situations and everyday details.
3. Design characters with clear motivations, flaws and growth paths that readers could meet in real life.
4. Keep language vivid yet accessible – avoid dense symbolism or abstract poetry overshadowing clarity.
5. Provide meaningful choices that explore real-world dilemmas and consequences; each choice should be understandable without specialist knowledge.
6. Never trivialise the user's circumstances; offer nuance and hope grounded in believable outcomes, not magical fixes.
7. Maintain narrative consistency, logical cause-and-effect and emotional continuity from scene to scene.
8. Aim for a satisfying, grounded resolution that reflects the genre and emotional need while leaving space for user reflection.
"""



# Note: DIALOGUE_GENERATION_PROMPT and DIALOGUE_RESPONSE_SCHEMA are provided for potential future use 
# or alternative dialogue generation approaches. Currently, the system primarily uses 
# STORY_ADVANCEMENT_PROMPT and STORY_ADVANCEMENT_SCHEMA for dialogue and narrative progression.
DIALOGUE_GENERATION_PROMPT = """
Generate the next segment of this cinematic screenplay experience.

SCREENPLAY CONTEXT:
- Title: {story_title}
- High-Concept Premise: {story_theme}
- Current Setting: {current_setting}

CHARACTER INFORMATION:
- Speaking Character: {character_name}
- Character Notes: {character_background}

PREVIOUS SCENE CONTENT:
{conversation_history}

The protagonist just said:
"{user_message}"

As the screenwriter, craft {character_name}'s next dialogue/action in this scene. Your response should:

1. MAINTAIN CINEMATIC QUALITY - Use vivid, visual language that evokes strong imagery
2. HONOR CHARACTER INTEGRITY - Ensure dialogue feels authentic to this character's unique voice
3. ADVANCE THE NARRATIVE - Move the plot forward in meaningful ways
4. CREATE DRAMATIC TENSION - Introduce new elements or deepen existing conflicts
5. INCLUDE VISUAL DIRECTION - Add brief cinematic notes about atmosphere, camera angles, or character movements when relevant
6. INCORPORATE EMOTIONAL SUBTEXT - Layer dialogue with deeper meaning
7. REFERENCE EARLIER STORY ELEMENTS - Call back to prior scenes or dialogue when appropriate
8. PROVIDE CHOICE POINTS - Offer 2-3 dramatically distinct paths for the protagonist to choose

**SCENE TRANSITION INSTRUCTIONS:**
If the scene location should change or significant time should pass, provide a descriptive scene_transition_caption.
This caption should be a brief, vivid description like a cinematic title card (e.g., "THREE DAYS LATER - THE ABANDONED HOSPITAL").
Use dramatic, visual language that orients the viewer to the new setting, time, or emotional shift.

Important: Avoid delivering purely abstract or philosophical speeches. Dialogue should feel grounded, reveal intentions, or nudge the plot forward. Reserve poetic abstraction for climactic or reflective moments only.

If appropriate, subtly weave in elements from the hidden easter eggs or symbolic motifs established earlier.

Remember, this is meant to feel like an extraordinary cinematic experience - maintain the tone, pacing and quality of acclaimed films.

Format your response as a structured JSON object following the schema below.

{schema}
"""

DIALOGUE_RESPONSE_SCHEMA = """
{
  "cinematic_responses": [
    {
      "character_id": "string (the unique identifier of the character speaking)",
      "dialogue": "string (the actual spoken words of the character)",
      "delivery": "string (how the dialogue is delivered - tone, emotion, etc.)",
      "action": "string (physical actions the character performs while speaking)",
      "direction": "string (cinematic notes about camera angles, lighting, etc.)"
    }
  ],
  "scene_dynamics": {
    "atmosphere": "string (the mood and feel of the scene)",
    "visual_elements": ["string (key visual details that should be emphasized)"],
    "symbolic_references": ["string (callbacks to earlier motifs or symbols, optional)"]
  },
  "branching_paths": [
    {
      "id": "string (unique identifier for this choice)",
      "text": "string (the text shown to the user as a choice option)",
      "dramatic_impact": "string (how this choice affects the narrative direction)",
      "visual_cue": "string (visual element that accompanies this choice)"
    }
  ],
  "narrative_progression": {
    "scene_transition": "boolean (whether this dialogue causes a scene change)",
    "new_location": "string (if transitioning, where the scene moves to)",
    "time_shift": "string (if time passes, how much - 'moments later', 'hours later', etc.)",
    "plot_development": "string (how this dialogue advances the plot)"
  },
  "hidden_elements": {
    "easter_egg": "string (subtle reference or hidden detail for attentive users)",
    "foreshadowing": "string (hint about future developments in the story)"
  },
  "scene_transition_caption": "string (if scene changes, the caption to display, like 'THREE DAYS LATER - THE ABANDONED HOSPITAL')",
  "npc_reply_expected": "boolean (whether an NPC should respond to the user's next input)"
}
"""

STORY_CONCLUSION_PROMPT = """
Create a cinematic finale for this screenplay experience.

SCREENPLAY OVERVIEW:
- Title: {story_title}
- High-Concept Premise: {story_theme}
- Core Theme: {emotional_need}
- Key Sequences: {key_moments}
- Character Arcs: {character_growth}

Craft a powerful conclusion that delivers:

1. VISUAL RESOLUTION - A visually striking final sequence that resolves the central dramatic tension
2. EMOTIONAL IMPACT - A moment that feels emotionally authentic and impactful
3. THEMATIC FULFILLMENT - A clear payoff to the themes and motifs established throughout
4. SYMBOLIC CLOSURE - Visual callbacks to earlier symbolic elements
5. CHARACTER TRANSFORMATION - A clear demonstration of how the protagonist has changed
6. CINEMATIC IMPACT - A memorable final image or moment that lingers with the audience
7. ARTFUL AMBIGUITY - Just enough open-endedness to invite reflection

Your conclusion should feel like the final scenes of an acclaimed film - visually striking, emotionally powerful, and thematically rich. Depending on the narrative, this could be triumphant, bittersweet, challenging, or any other tone that authentically concludes the story.

Consider the visual language, music, pacing, and cinematic techniques that would make this ending resonate deeply.

Format your response as a structured JSON object following the schema below.

{schema}
"""

# Templates for specific emotional needs
EMOTIONAL_NEED_GUIDANCE = {
    "academic_rejection": """
    For someone dealing with academic rejection, consider:
    - Exploring themes of self-worth beyond external validation
    - Addressing perfectionism and impostor syndrome
    - Highlighting the universal nature of rejection in academic pursuits
    - Examining resilience and the iterative nature of growth
    - Including characters with diverse perspectives on achievement and failure
    """,
    
    "work_burnout": """
    For someone dealing with work burnout, consider:
    - Exploring themes of balance and boundaries
    - Addressing societal pressures around productivity and success
    - Examining the importance of personal priorities and wellbeing
    - Presenting contrasting views on professional fulfillment
    - Including characters with different relationships to work and ambition
    """,
    
    "relationship_loss": """
    For someone dealing with relationship loss, consider:
    - Exploring themes of attachment and identity
    - Addressing grief as a natural process with no timeline
    - Examining the capacity for connection and change
    - Presenting realistic perspectives on loss and moving forward
    - Including characters with varied experiences of relationship transitions
    """,
    
    # Add more as needed
}

# Example response schemas
STORY_INITIALIZATION_SCHEMA = """
{
  "title": "string",
  "high_concept_premise": "string (1-2 sentences that capture the core concept)",
  "cinematic_theme": "string (the central theme or message)",
  "setting": {
    "primary_location": "string (detailed description of main setting)",
    "time_period": "string",
    "atmosphere": "string (mood, lighting, visual tone)",
    "unique_elements": ["string (distinctive features of this world)"]
  },
  "characters": [
    {
      "id": "string",
      "name": "string",
      "role": "protagonist | antagonist | supporting | mentor | wildcard",
      "entity_type": "human | anthropomorphized_concept",
      "visual_description": "string (how they would appear on screen)",
      "personality": "string (core traits and contradictions)",
      "backstory": "string (relevant history)",
      "motivation": "string (what drives this character)",
      "special_abilities": "string (optional)",
      "symbolic_meaning": "string (what this character represents thematically)"
    }
  ],
  "opening_sequence": {
    "description": "string (visually rich description of opening)",
    "location": "string",
    "mood": "string",
    "inciting_incident": "string (the event that sets the story in motion)",
    "narrative_text": "string (screenplay style description)"
  },
  "initial_dialogue": [
    {
      "character_id": "string",
      "content": "string",
      "type": "dialogue | voice_over | internal_thought",
      "direction": "string (optional acting/visual direction)"
    }
  ],
  "branching_choices": [
    {
      "id": "string",
      "text": "string",
      "dramatic_impact": "string (how this choice affects the narrative)",
      "visual_representation": "string (how this choice might be visually presented)"
    }
  ],
  "hidden_elements": [
    {
      "type": "easter_egg | foreshadowing | symbolic_object | clue",
      "description": "string (what is hidden)",
      "location": "string (where in the narrative it appears)",
      "significance": "string (what it hints at or connects to)"
    }
  ],
  "acts": [
    {
      "id": "string",
      "title": "string",
      "purpose": "string (narrative or emotional goal)",
      "emotional_beat": "string"
    }
  ],
  "emotional_undercurrent": "string (the emotional journey being subtly addressed)"
}
"""


STORY_CONCLUSION_SCHEMA = """
{
  "final_sequence": {
    "setting": "string (the location where the story concludes)",
    "atmosphere": "string (the mood and emotional tone of the final scene)",
    "action": "string (the key actions that occur in the conclusion)",
    "dialogue": ["string (important lines spoken by characters in the final scene)"],
    "emotional_tone": "string (the predominant feeling the conclusion evokes)"
  },
  "cinematic_elements": {
    "visual_motifs": ["string (recurring visual symbols that appear in the conclusion)"],
    "soundtrack_notes": "string (music or sound design that enhances the final scene)",
    "camera_direction": "string (how the scene would be filmed - angles, movements, etc.)"
  },
  "narrative_closure": {
    "character_arcs": ["string (how each main character's journey concludes)"],
    "resolved_tensions": ["string (which conflicts or questions are answered)"],
    "deliberate_ambiguities": ["string (elements intentionally left open to interpretation)"]
  },
  "thematic_resolution": {
    "central_message": "string (the core insight or truth revealed by the story)",
    "visual_metaphor": "string (an image that encapsulates the story's meaning)",
    "emotional_impact": "string (the intended emotional effect on the audience)"
  },
  "final_image": "string (the last visual the audience sees before the story ends)"
}
"""

CLARIFYING_QUESTIONS_PROMPT_TEMPLATE = """
A user has shared their situation: "{emotional_need}"

To create a deeply personalized story that resonates with the user, I need to collect comprehensive information about their background and situation.
Generate EXACTLY 10 concrete, easy-to-answer questions, distributed across these categories:

1. PERSONAL BACKGROUND (2-3 questions):
   - Basic demographics (age, gender, occupation, education)
   - Living situation and family context
   - Cultural background or important values
   - Daily routines or lifestyle

2. SITUATION DETAILS (3-4 questions):
   - The SPECIFIC CONTEXT of their situation (who/what/when/where details)
   - SPECIFIC EXAMPLES of how this issue manifests in their life
   - The IMPACT this has had on them (specific feelings, thoughts, behaviors)
   - How long they've been experiencing this and any patterns they've noticed

3. COPING & ASPIRATIONS (2-3 questions):
   - Their PAST ATTEMPTS to address this issue
   - Current strategies (both helpful and unhelpful)
   - Their HOPES for resolution or improvement
   - What they believe might help them

4. PERSONAL INTERESTS & RESOURCES (2 questions):
   - Hobbies, interests, or activities they enjoy
   - Things that bring them comfort or joy
   - Sources of strength or support in their life
   - Creative or storytelling preferences

Your questions must:
- Be specific and straightforward rather than abstract or philosophical
- Ask for concrete examples or details when possible
- Use simple, everyday language that feels conversational
- Be respectful and direct
- Focus on information that would help craft a relevant, personalized story

VERY IMPORTANT: Each question MUST include 3-5 relevant multiple-choice options that are specific to the question and cover the most common or likely answers. The options should be diverse enough to cover a range of possible responses.

ALSO IMPORTANT: You MUST specify whether each question should be single-choice (user can select only one option) or multiple-choice (user can select multiple options). Use the "questionType" field with value "single" or "multiple" to indicate this.

AVOID:
- Overly general questions like "How do you feel about that?"
- Questions that could be answered with just "yes" or "no"
- Questions that require complex psychological self-analysis
- Repetitive questions that probe the same area
- Generic options that don't relate specifically to the question
- Options that are too similar to each other

Return EXACTLY 10 questions as a JSON-formatted array of objects. Each object should have:
1. "question": The question text
2. "options": An array of 3-5 relevant multiple-choice options
3. "allowsCustom": Boolean (true/false) indicating if the question allows a custom text answer
4. "questionType": Either "single" or "multiple" indicating whether the user can select one or multiple options

Example format:
[
  {{
    "question": "What age group do you belong to?",
    "options": ["Under 18", "18-25", "26-35", "36-50", "Over 50"],
    "allowsCustom": false,
    "questionType": "single"
  }},
  {{
    "question": "What specific emotions do you experience most frequently when facing this challenge?",
    "options": ["Anxiety and worry", "Sadness and grief", "Frustration and anger", "Shame and embarrassment"],
    "allowsCustom": true,
    "questionType": "multiple"
  }}
]

Make sure all options are relevant to the specific question and the user's situation. The options should help users answer quickly while still providing meaningful information.
"""

PLOT_PROGRESSION_CHECK_PROMPT = """
Analyze the following recent conversation from an interactive story. Determine whether meaningful PLOT PROGRESSION has occurred in these exchanges.

**Story Title:** {title}
**Story Theme:** {theme}

**Recent Conversation (Last 5 rounds):**
{recent_conversation}

**What counts as plot progression:**
- New information, secrets, or revelations were introduced
- Characters moved to a new location or environment
- A new conflict, challenge, or obstacle emerged
- A relationship between characters meaningfully changed
- The protagonist made a consequential decision
- A significant emotional turning point occurred
- A new character or important plot element appeared
- The story situation is materially different from 5 rounds ago

**What does NOT count as plot progression:**
- Characters repeating similar advice or encouragement
- Small talk or circular conversations
- Restating information already known
- Minor emotional reactions without story impact
- Characters asking questions without new answers

Respond ONLY with a JSON object:
{{
  "has_progressed": true or false,
  "reasoning": "Brief explanation (1-2 sentences)",
  "suggested_development": "If has_progressed is false, suggest ONE specific dramatic event to advance the story"
}}
"""

STORY_ADVANCEMENT_PROMPT = """
You are continuing an interactive therapeutic story. Your goal is to generate the next part of the narrative based on the user's latest action.

**STORY CONTEXT:**
- **Title:** {title}
- **Theme:** {theme}
- **Emotional Goal:** {emotional_goal}
- **Setting:** {setting}
- **Characters:** {characters}

**CONVERSATION HISTORY (Current Scene):**
{conversation_history}

**USER'S LATEST ACTION:**
- **Action Type:** {action_type}
- **Content:** {user_input}
{target_character_directive}

**YOUR TASK:**
Generate the next part of the story. You must respond as the appropriate character from their perspective. Your response should:
1. **Acknowledge the User's Input:** Directly or indirectly respond to what the user just said or did.
2. **Maintain Character Voice:** Stay true to the character's established personality and role in the story.
3. **Advance the Narrative:** Move the story forward in a meaningful way.
4. **Uphold the Therapeutic Goal:** Keep the story's emotional goal in mind. The interaction should be supportive and insightful.
5. **Reference Past Events:** Occasionally reference previous interactions or decisions when relevant.
6. **Provide New Choices:** Give the user 2-3 new, meaningful choices to continue the interaction. These choices should reflect different emotional paths or reactions.
7. **Update Scene State:** Describe the current emotional tone of the scene after your response.

**IMPORTANT CHARACTER ATTRIBUTION:**
- If the user has specifically addressed a character, ONLY respond as that character.
- If no specific character was addressed, determine the most appropriate character to respond based on the conversation context.
- NEVER speak as multiple characters in a single response. Each response must be from ONE character's perspective only.
- Ensure the character_id in your response matches the character who is speaking.
- NEVER attribute dialogue to character names directly - use the proper character_id.
- Do NOT repeatedly introduce the speaking character by name or role unless this is their first formal entrance or the protagonist explicitly asks who they are.

**CHARACTER ID REQUIREMENTS:**
- Always use the exact character_id from the character data, not the character's name
- Character IDs are lowercase with underscores (e.g., "john_smith" not "John Smith" or "John")
- Never create new character IDs - only use existing ones from the character list
- For the protagonist, use their specific ID (not "protagonist")
- If unsure which character should respond, use an NPC that's already in the scene
- Double-check that you're using the correct character_id format before responding

**OUTPUT FORMAT:**
You MUST respond with a single, valid JSON object that follows this schema. Do not add any extra text or markdown formatting around the JSON.

{schema}
"""

# The schema for story advancement responses
STORY_ADVANCEMENT_SCHEMA = """
{
  "scene_description": "string (detailed visual description of the current environment from the protagonist's first-person perspective - will be shown as a system message)",
  "cinematic_responses": [
    {
      "character_id": "string (MUST be the exact ID from the characters list, like 'protagonist', 'npc1', 'mentor' - NOT a character name)",
      "character_name": "string (the actual name of the character who is speaking, like 'Eleanor' or 'Grandpa Hank')",
      "dialogue": "string (the actual spoken words of the character)",
      "delivery": "string (how the dialogue is delivered - tone, emotion, etc.)",
      "action": "string (physical actions the character performs while speaking)",
      "direction": "string (cinematic notes about camera angles, lighting, etc.)"
    }
    // Multiple character responses can be included in this array, in the order they should speak
    // For example, first the protagonist's dialogue, then an NPC's response
  ],
  "scene_elements": {
    "atmosphere": "string (the overall mood and emotional tone of the scene)",
    "visual_details": ["string (important visual elements that should be emphasized)"],
    "symbolic_motifs": ["string (recurring visual symbols or themes in the scene)"]
  },
  "branching_paths": [
    {
      "id": "string (unique identifier for this choice)",
      "text": "string (the text shown to the user as a choice option)",
      "dramatic_impact": "string (how this choice would affect the story direction)",
      "visual_representation": "string (how this choice moment would be filmed)"
    }
  ],
  "scene_dynamics": {
    "transition_required": "boolean (whether the scene should change location/time)",
    "new_location": "string (if transitioning, where the scene should move to)",
    "time_progression": "string (how much time passes - 'moments later', 'days later', etc.)",
    "narrative_advancement": "string (how the plot progresses with this scene)",
    "scene_transition_caption": "string (the cinematic caption shown during scene transitions, like 'THREE DAYS LATER - THE ABANDONED HOSPITAL')"
  },
  "story_state": {
    "current_objective": "string (the protagonist's immediate objective after this turn)",
    "current_tension": "string (the most urgent unresolved tension now driving the scene)",
    "immediate_stakes": "string (what could be gained or lost in the next beat)",
    "location_status": "string (how the present setting feels or what has changed about it)",
    "relationship_shift": "string (optional; how a key relationship changes in this turn)",
    "latest_reveal": "string (optional; the most important reveal, clue, or confession introduced now)",
    "emotional_beat": "string (optional; the emotional beat the scene lands on)"
  },
  "hidden_elements": {
    "easter_egg": "string (subtle references or hidden details for attentive users)",
    "foreshadowing": "string (hints about future developments in the story)"
  },
  "npc_reply_expected": "boolean (whether an NPC should respond to the user's input)"
}
"""

# Updates to the keyword suggestion prompt
KEYWORD_SUGGESTION_PROMPT_TEMPLATE = """
You are a screenwriter preparing to craft an engaging screenplay.

Generate 8–10 concrete, easy-to-visualise keywords (single nouns or very short noun-phrases). Think of tangible settings, occupations, objects, or genre labels, e.g. "Forest", "War", "City", "River", "Detective", "Romance", "Hospital Ward".

Guidelines:
• Do NOT use abstract concepts (e.g. "Hope", "Transcendence", "Self-love").
• Do NOT use adjectives alone (e.g. "Lonely", "Dark").
• Each keyword should be 1–3 words and reference something the viewer can picture on screen.
• Keywords should be diverse and cover different possible story flavours (location, time period, genre, central object, etc.).
• Include a mix of conventional and unexpected elements for maximum creativity.
• Keywords should allow for various tones - from light to dark, hopeful to challenging.

USER CONTEXT:
"{emotional_need}"

Return ONLY a JSON array of strings, no markdown fences or additional prose.
"""

# Updates to the act enhancement prompt
ACT_ENHANCEMENT_PROMPT_TEMPLATE = """
You are a master screenwriter tasked with refining the act structure for an engaging screenplay. Based on the initial framework, develop rich, cinematic acts with compelling narrative arcs.

**SCREENPLAY INFORMATION:**
- Title: {title}
- High-Concept Premise: {premise}
- Core Theme: {emotional_need}
- Setting: {setting}
- Main Characters: {characters}
- Keywords to Feature: {keywords}

**CURRENT ACT STRUCTURE:**
{existing_acts}

Transform these basic acts into a compelling dramatic framework. For each act (keep the same number of acts), provide:

1. **ACT TITLE** - A thematically resonant, evocative title
2. **ACT SYNOPSIS** - A vivid paragraph describing the key events and narrative journey
3. **VISUAL PALETTE** - Combine cinematic techniques & recurring visual motifs into one concise description
4. **NARRATIVE PURPOSE** - How this act advances the story and character development
5. **CHARACTER DEVELOPMENT** - The important changes or challenges for characters
6. **KEY LOCATIONS** - 2–3 visually distinctive settings where scenes take place
7. **DRAMATIC TENSION** - The central conflict or challenge that drives this act
8. **CLIMACTIC MOMENT** - The pivotal scene that marks the act's peak
9. **TRANSITION HOOK** - How this act leads into the next (except for final act)

Style guidelines:
• Use cinematic, visually rich language
• Balance plot progression with character depth
• Incorporate the screenplay's keywords naturally
• Ensure each act has a distinctive mood and visual palette
• Create a meaningful progression across the entire act structure
• The tone can range from uplifting to challenging, depending on what best serves the story

Format your response as a structured JSON array of acts, each containing the fields described above.
"""

ACT_ENHANCEMENT_SCHEMA = """
[
  {
    "id": "string",
    "act_number": "integer",
    "title": "string",
    "synopsis": "string",
    "visual_palette": "string",
    "narrative_purpose": "string",
    "character_development": "string",
    "key_locations": ["string"],
    "dramatic_tension": "string",
    "climactic_moment": "string",
    "transition_hook": "string"
  }
]
"""

# ── Story Critic & Refine prompts ──────────────────────────────────────────

STORY_CRITIC_PROMPT = """
You are an expert story critic and creative consultant. Evaluate the following interactive story blueprint with rigorous, constructive standards.

**STORY BLUEPRINT:**
- **Title:** {title}
- **High Concept Premise:** {high_concept_premise}
- **Cinematic Theme:** {cinematic_theme}
- **Emotional Goal:** {emotional_undercurrent}
- **Setting:**
{setting}
- **Characters:**
{characters}
- **Act Structure:**
{acts}

**EVALUATION CRITERIA (score each 1-10):**

1. **Novelty** - How original and fresh is this concept? Does it avoid clichés and predictable tropes? Would it feel new to an audience?
2. **Engagement** - How compelling is the story hook? Would readers/viewers be eager to continue? Are the stakes clear and meaningful?
3. **Cinematic Quality** - Does it feel like a movie? Are there vivid visual moments, atmospheric settings, and dramatic scenes worth filming?
4. **Emotional Resonance** - Does the story effectively address the user's emotional goal? Will it create genuine emotional impact?
5. **Character Depth** - Are characters multi-dimensional with clear motivations, flaws, and growth potential? Do they serve the story?
6. **Structural Coherence** - Does the act structure flow logically? Are there clear escalations, turning points, and a satisfying arc?

Be demanding but specific. Point out EXACTLY what is weak and HOW to fix it.

**RESPOND WITH JSON ONLY:**
{{
  "overall_score": <float 1-10>,
  "dimensions": {{
    "novelty": {{"score": <int 1-10>, "feedback": "<specific critique>"}},
    "engagement": {{"score": <int 1-10>, "feedback": "<specific critique>"}},
    "cinematic_quality": {{"score": <int 1-10>, "feedback": "<specific critique>"}},
    "emotional_resonance": {{"score": <int 1-10>, "feedback": "<specific critique>"}},
    "character_depth": {{"score": <int 1-10>, "feedback": "<specific critique>"}},
    "structural_coherence": {{"score": <int 1-10>, "feedback": "<specific critique>"}}
  }},
  "key_strengths": ["<strength 1>", "<strength 2>"],
  "critical_improvements": ["<specific actionable improvement 1>", "<improvement 2>", "<improvement 3>"],
  "specific_suggestions": "<detailed paragraph with concrete suggestions for making this story more novel, engaging, and cinematic>"
}}
"""

STORY_REFINE_PROMPT = """
You are a master screenwriter tasked with polishing a story blueprint based on expert critique.

**ORIGINAL STORY BLUEPRINT:**
- **Title:** {title}
- **High Concept Premise:** {high_concept_premise}
- **Cinematic Theme:** {cinematic_theme}
- **Emotional Goal:** {emotional_undercurrent}
- **Setting:**
{setting}
- **Characters:**
{characters}
- **Act Structure:**
{acts}

**EXPERT CRITIC FEEDBACK:**
{critic_feedback}

**YOUR TASK:**
Refine the story blueprint to address the critic's feedback while preserving the story's core identity. Focus on:
1. **Increasing novelty** - Add unexpected twists, unique angles, or fresh perspectives
2. **Boosting engagement** - Sharpen hooks, raise stakes, create more compelling conflicts
3. **Enhancing cinematic quality** - Add vivid visual set-pieces, atmospheric details, memorable dramatic moments
4. **Deepening emotional resonance** - Strengthen the connection to the user's emotional goal
5. **Improving structural coherence** - Ensure smooth escalation, clear turning points, satisfying arc

**IMPORTANT RULES:**
- Preserve the title, character names, character IDs, and core setting
- Enhance and elevate, do NOT completely rewrite
- Address the specific critique points with targeted improvements
- Each act must have clear dramatic purpose and meaningful progression
- Ensure the refined version is noticeably better than the original

**RESPOND WITH JSON ONLY:**
{{
  "refined_high_concept_premise": "<polished premise that addresses critique>",
  "refined_cinematic_theme": "<sharpened theme>",
  "refined_acts": [
    {{
      "id": "string",
      "title": "string",
      "purpose": "string",
      "opening_moment": "string",
      "emotional_beat": "string",
      "climactic_moment": "string",
      "resolution_end": "string",
      "cinematic_techniques": "string",
      "visual_motifs": "string",
      "key_locations": "string",
      "emotional_transformation": "string"
    }}
  ],
  "refinement_notes": "<brief summary of key changes and why they improve the story>"
}}
"""

# 分步骤故事生成的提示词模板

STORY_STEP1_PROMPT = """
You are a master screenwriter tasked with crafting the foundational elements of an interactive story. 
The USER is the protagonist, and the story must be designed so they feel directly involved.

USER TOPIC / EMOTIONAL NEED:
{emotional_need}

SELECTED KEYWORDS (incorporate these naturally):
{keywords}

ADDITIONAL GUIDANCE CONSTRAINTS (YOU MUST FOLLOW THESE GUIDELINES):
{guidance_sentence}

CRITICAL RULES:
1. The emotional_need is the driving force of the story. 
   - Every element (premise, theme, and especially protagonist_objective) must reflect and respond to this emotional need.
   - Example: If the need is "belonging," then the protagonist_objective could be "Earn the trust of the hidden tribe before the eclipse."
   - If the need is "closure," then the objective could be "Uncover the final message left by your late father."
2. The protagonist_objective MUST be a clear, actionable goal directly tied to resolving or fulfilling the emotional_need. 
   Avoid vague or purely internal phrasing (e.g., "understand yourself"); instead use tangible, story-driven tasks.
3. The high_concept_premise should read like a cinematic movie pitch, emotionally charged and visually evocative.
4. The cinematic_theme should express the universal emotional truth behind the need (e.g., "Love can survive even in exile," "The courage to face loss defines who we are").
5. Ensure the story feels interactive, film-like, and immersive.

Respond ONLY with a JSON object containing these fields (no others):
1. title – A memorable, evocative title
2. high_concept_premise – A one-sentence summary of the story's core idea
3. cinematic_theme – The central thematic message of the story
4. protagonist_objective – A specific, actionable goal the user must accomplish, which directly addresses their emotional_need
"""



# 步骤2：世界构建
STORY_STEP2_PROMPT = """
You are a master world-builder tasked with creating a rich, immersive setting for an interactive story.
Based on the story foundation already established, create a detailed setting that brings this story to life.

STORY FOUNDATION:
Title: {title}
High Concept: {high_concept_premise}
Theme: {cinematic_theme}
Emotional Journey: {emotional_undercurrent}

Create a setting that:
1. Provides rich visual and sensory details
2. Contains unique elements that can be used for storytelling
3. Feels cinematic and immersive

Respond with a JSON object containing the "setting" field with these properties:
1. primary_location - The main location where the story takes place
2. time_period - When the story takes place
3. atmosphere - The sensory and emotional qualities of the environment
4. unique_elements - An array of 3-5 specific, unique features of this world that make it special
"""

# 步骤3：角色创建
STORY_STEP3_PROMPT = """
You are a master character designer tasked with creating compelling characters for an interactive story.
Based on the story foundation and setting already established, create characters that will bring this story to life.

STORY FOUNDATION:
Title: {title}
High Concept: {high_concept_premise}
Theme: {cinematic_theme}
Emotional Journey: {emotional_undercurrent}

SETTING:
{setting}

Create 3-5 characters that:
1. Include a protagonist the user will play as
2. Include supporting characters with distinct personalities
3. May include symbolic or anthropomorphized concepts if appropriate
4. Reflect and enhance the story's emotional journey
5. Have clear motivations and connections to the setting

Respond with a JSON array of character objects, each containing:
1. id - A unique identifier (lowercase, no spaces, use underscores instead - e.g., "john_smith" not "John Smith")
2. name - The character's name
3. role - One of: protagonist, supporting, mentor, antagonist, wildcard
4. entity_type - One of: human, anthropomorphized_concept
5. visual_description - Physical appearance and notable visual traits
6. personality - Key personality traits and mannerisms
7. backstory - Relevant history that informs their role in the story
8. motivation - What drives this character in the story
9. special_abilities - Any unique capabilities (if applicable)
10. symbolic_meaning - What this character represents thematically

IMPORTANT: Character IDs MUST follow these rules:
- Use lowercase letters only
- Replace spaces with underscores
- Use only alphanumeric characters and underscores
- Example: For a character named "Dr. Jane Smith", the ID should be "dr_jane_smith"
- CRITICAL: Character IDs must be consistent throughout the story - they are used for dialogue attribution
- CRITICAL: Never use character names as IDs - "cassandra_blake" is correct, "Cassandra Blake" is not
- CRITICAL: Double-check all character IDs match this format before finalizing
"""

# 步骤4：故事结构
STORY_STEP4_PROMPT = """
You are a master screenwriter specializing in dramatic structure. Create a compelling, cinematic act structure for this interactive story.
Based on the story elements already established, design a dramatic journey that will emotionally resonate with the user.

STORY FOUNDATION:
Title: {title}
High Concept: {high_concept_premise}
Theme: {cinematic_theme}
Emotional Journey: {emotional_undercurrent}

SETTING:
{setting}

CHARACTERS:
{characters}

Create a 3–5-act structure that:
1. Follows cinematic storytelling principles with clear dramatic arcs
2. Incorporates innovative narrative techniques (flashbacks, montages, parallel storylines, etc.)
3. Creates emotional depth through visual storytelling and symbolism
4. Provides opportunities for meaningful character development
5. Clearly shows **how each act begins and how it ends**, so the narrative momentum is explicit
6. Uses cinematic language and techniques in the descriptions

For every act, explicitly describe:
• **opening_moment** – the very first image/scene that launches this act (what the audience sees/hears as the act starts)
• **resolution_end** – the state of characters/world at the end of this act, just before transitioning to the next act (what changes or cliff-hanger occurs)

Each act should read like it could be filmed as a compelling movie sequence.

Respond with a JSON array of act objects, each containing:
1. id – A unique identifier (e.g., "act1")
2. title – An evocative title for this act
3. purpose – The narrative function of this act
4. opening_moment – A vivid snapshot of how the act starts
5. emotional_beat – The primary emotional experience of this act
6. climactic_moment – The pivotal scene or revelation in this act
7. resolution_end – How the act concludes / what changes
8. cinematic_techniques – Film techniques that would enhance this act (e.g., "slow-motion flashbacks", "aerial establishing shots")
9. visual_motifs – Recurring visual elements that carry symbolic meaning
10. key_locations – Specific settings within this act that are emotionally significant
11. emotional_transformation – How the protagonist changes emotionally during this act
"""

# 步骤5：开场和互动元素
STORY_STEP5_PROMPT = """
You are a master interactive storyteller. Create the opening sequence and interactive elements for this story.
Based on all the story elements already established, design an engaging beginning and meaningful choices.

STORY FOUNDATION:
Title: {title}
High Concept: {high_concept_premise}
Theme: {cinematic_theme}
Emotional Journey: {emotional_undercurrent}

SETTING:
{setting}

CHARACTERS:
{characters}

ACTS:
{acts}

Create these final elements:
1. An opening_sequence that establishes the setting, mood, and inciting incident
2. Initial dialogue between characters that introduces the story situation
3. Branching choices that give the user meaningful agency
4. Hidden elements that add depth and discovery to the experience
5. IMPORTANT: Whenever a character (other than the protagonist) appears for the FIRST time in any dialogue, they MUST introduce themselves clearly by name and an identifying line (e.g., "Hello, I'm Dr. Reyes, the station's chief engineer.").
   • Their first spoken line should include their name.
   • This is mandatory for every new character to avoid anonymous dialogue.

Respond with a JSON object containing:
1. opening_sequence - Object with description, location, mood, inciting_incident, and narrative_text fields
2. initial_dialogue - Array of dialogue objects with character_id, content, type, and direction fields
3. branching_choices - Array of choice objects with id, text, dramatic_impact, and visual_representation fields
4. hidden_elements - Array of hidden element objects with type, description, location, and significance fields
"""

# JSON schemas for each step
STORY_STEP1_SCHEMA = """
{
  "title": "string",
  "high_concept_premise": "string",
  "cinematic_theme": "string",
  "protagonist_objective": "string"
}
"""

STORY_STEP2_SCHEMA = """
{
  "setting": {
    "primary_location": "string",
    "time_period": "string",
    "atmosphere": "string",
    "unique_elements": ["string"]
  }
}
"""

STORY_STEP3_SCHEMA = """
[
  {
    "id": "string",
    "name": "string",
    "role": "string",
    "entity_type": "string",
    "visual_description": "string",
    "personality": "string",
    "backstory": "string",
    "motivation": "string",
    "special_abilities": "string",
    "symbolic_meaning": "string"
  }
]
"""

STORY_STEP4_SCHEMA = """
[
  {
    "id": "string",
    "title": "string",
    "purpose": "string",
    "opening_moment": "string",
    "emotional_beat": "string",
    "climactic_moment": "string",
    "resolution_end": "string",
    "cinematic_techniques": "string",
    "visual_motifs": "string",
    "key_locations": "string",
    "emotional_transformation": "string"
  }
]
"""

STORY_STEP5_SCHEMA = """
{
  "opening_sequence": {
    "description": "string",
    "location": "string",
    "mood": "string",
    "inciting_incident": "string",
    "narrative_text": "string"
  },
  "initial_dialogue": [
    {
      "character_id": "string",
      "content": "string",
      "type": "string",
      "direction": "string"
    }
  ],
  "branching_choices": [
    {
      "id": "string",
      "text": "string",
      "dramatic_impact": "string",
      "visual_representation": "string"
    }
  ],
  "hidden_elements": [
    {
      "type": "string",
      "description": "string",
      "location": "string",
      "significance": "string"
    }
  ]
}
"""

# Template to generate user profile keywords
PROFILE_KEYWORDS_PROMPT_TEMPLATE = """
You are preparing to build a concise user profile for an interactive therapeutic story. 
Based on the user's emotional need below, generate relevant keyword options the user can select from. 
For EACH of the following TOPICS produce EXACTLY 10 short, concrete, easy-to-understand keywords.

Topics:
1) social_inclination – words that describe preferred social style / interaction (e.g. "introvert", "team-player")
2) interests – hobbies or fields of strong interest (e.g. "gardening", "sci-fi movies")
3) personality – trait descriptors (e.g. "optimistic", "detail-oriented")

Guidelines:
• Keep every keyword 1–2 words (3 max).
• Use everyday English words, no jargon.
• Cover a broad spectrum so most users find something relatable.
• DO NOT repeat keywords across topics.
• Return results in the JSON format shown below – **no extra prose or markdown**.

Expected JSON format (keys must match exactly):
{{
  "social_inclination": ["keyword1", "keyword2", … (10 items total)],
  "interests": ["keyword1", … (10 items total)],
  "personality": ["keyword1", … (10 items total)]
}}

User emotional need for context:
"{emotional_need}"
""" 
