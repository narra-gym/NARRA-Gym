import {
  BenchmarkDialogueRecord,
  BenchmarkJudgeInputSummary,
  BenchmarkJudgePayload,
} from '../types';

const isRecord = (value: unknown): value is Record<string, any> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const asRecord = (value: unknown): Record<string, any> => (isRecord(value) ? value : {});

const asArray = (value: unknown): any[] => (Array.isArray(value) ? value : []);

const cleanText = (value: unknown): string =>
  typeof value === 'string' ? value.replace(/\s+/g, ' ').trim() : '';

const normalizeRole = (record: Record<string, any>): BenchmarkDialogueRecord['role'] => {
  const rawRole = cleanText(record.role).toLowerCase();
  if (rawRole === 'user' || rawRole === 'assistant' || rawRole === 'system') {
    return rawRole;
  }

  const characterId = cleanText(record.character_id).toLowerCase();
  const speaker = cleanText(record.speaker).toLowerCase();
  if (characterId === 'system' || speaker === 'system') {
    return 'system';
  }
  if (characterId === 'protagonist' || speaker === 'user' || speaker === 'protagonist') {
    return 'user';
  }
  return 'assistant';
};

const normalizeDialogueRecord = (record: unknown, index: number): BenchmarkDialogueRecord | null => {
  const raw = asRecord(record);
  const content = cleanText(raw.content);
  if (!content) {
    return null;
  }

  const role = normalizeRole(raw);
  const speaker =
    cleanText(raw.speaker) ||
    (role === 'system' ? 'System' : role === 'user' ? 'User' : cleanText(raw.character_id) || `Speaker ${index + 1}`);

  return {
    id: cleanText(raw.id) || `judge-dialogue-${index}`,
    speaker,
    role,
    character_id: raw.character_id || null,
    content,
    timestamp: raw.timestamp || null,
    message_type: cleanText(raw.message_type) || cleanText(raw.type) || 'text',
    turn_index: typeof raw.turn_index === 'number' ? raw.turn_index : undefined,
    source: cleanText(raw.source) || 'uploaded_dialogue',
  };
};

const buildDialogueFromSnapshot = (
  snapshot: Record<string, any>,
  source: string,
): BenchmarkDialogueRecord[] => {
  const characters = asArray(snapshot.characters);
  const characterMap = new Map<string, string>();
  let protagonistId = '';

  characters.forEach(character => {
    const raw = asRecord(character);
    const id = cleanText(raw.id);
    if (!id) {
      return;
    }
    characterMap.set(id, cleanText(raw.name) || id);
    if (cleanText(raw.role).toLowerCase() === 'protagonist') {
      protagonistId = id;
    }
  });

  const mappedDialogue: Array<BenchmarkDialogueRecord | null> = asArray(asRecord(snapshot.current_scene).messages)
    .map((message, index) => {
      const raw = asRecord(message);
      const characterId = cleanText(raw.character_id) || 'system';
      const content = cleanText(raw.content);
      if (!content) {
        return null;
      }

      const role: BenchmarkDialogueRecord['role'] =
        characterId === 'system'
          ? 'system'
          : protagonistId && characterId === protagonistId
            ? 'user'
            : 'assistant';

      return {
        id: cleanText(raw.id) || `${source}-message-${index}`,
        speaker:
          role === 'system'
            ? 'System'
            : role === 'user'
              ? characterMap.get(characterId) || 'User'
              : characterMap.get(characterId) || characterId,
        role,
        character_id: characterId,
        content,
        timestamp: raw.timestamp || null,
        message_type: cleanText(raw.type) || 'text',
        source,
      };
    });

  return mappedDialogue.filter((item): item is BenchmarkDialogueRecord => item !== null);
};

const buildDialogueFromTurnLogs = (turnLogs: Record<string, any>[]): BenchmarkDialogueRecord[] => {
  const dialogue: BenchmarkDialogueRecord[] = [];

  turnLogs.forEach((turn, turnIndex) => {
    const turnId = cleanText(turn.id) || `turn-${turn.turn_index ?? turnIndex}`;
    const createdAt = turn.created_at || null;
    const actionType = cleanText(turn.action_type).toLowerCase() || 'message';
    const userInput = cleanText(turn.user_input);
    const responseText = cleanText(turn.response_text);

    if (userInput) {
      dialogue.push({
        id: `${turnId}-user`,
        speaker: 'User',
        role: 'user',
        character_id: null,
        content: userInput,
        timestamp: createdAt,
        message_type: actionType,
        turn_index: typeof turn.turn_index === 'number' ? turn.turn_index : undefined,
        source: 'turn_log',
      });
    }

    if (!responseText) {
      return;
    }

    const speaker = cleanText(turn.response_character_id) || 'Story';
    const role: BenchmarkDialogueRecord['role'] = speaker.toLowerCase() === 'system' ? 'system' : 'assistant';
    responseText
      .split(/\n+/)
      .map(line => line.trim())
      .filter(Boolean)
      .forEach((line, lineIndex) => {
        dialogue.push({
          id: `${turnId}-response-${lineIndex}`,
          speaker: role === 'system' ? 'System' : speaker,
          role,
          character_id: turn.response_character_id || null,
          content: line,
          timestamp: createdAt,
          message_type: 'text',
          turn_index: typeof turn.turn_index === 'number' ? turn.turn_index : undefined,
          source: 'turn_log',
        });
      });
  });

  return dialogue;
};

export const normalizeBenchmarkJudgePayload = (rawPayload: unknown): BenchmarkJudgePayload => {
  const payload = asRecord(rawPayload);
  const exportBundle = asRecord(payload.export_bundle);
  const merged = {
    ...exportBundle,
    ...payload,
  };

  const turnLogs = asArray(merged.turn_logs).map(item => asRecord(item));
  const feedbackLogs = asArray(merged.feedback_logs).map(item => asRecord(item));
  const llmCallLogs = asArray(merged.llm_call_logs).map(item => asRecord(item));
  const storySnapshot = asRecord(merged.story_snapshot);
  const participantEvaluation = asRecord(merged.participant_evaluation);
  const directFinalViewStory = asRecord(merged.final_view_story);
  const mergedStory = asRecord(merged.story);
  const payloadStory = asRecord(payload.story);
  const finalViewStory = Object.keys(directFinalViewStory).length
    ? directFinalViewStory
    : Object.keys(mergedStory).length
      ? mergedStory
      : payloadStory;

  let dialogueSource = cleanText(merged.dialogue_source) || 'uploaded_dialogue';
  let dialogue = asArray(merged.dialogue)
    .map((item, index) => normalizeDialogueRecord(item, index))
    .filter((item): item is BenchmarkDialogueRecord => Boolean(item));

  if (!dialogue.length && turnLogs.length > 0) {
    dialogue = buildDialogueFromTurnLogs(turnLogs);
    dialogueSource = 'turn_logs';
  } else if (!dialogue.length && Object.keys(storySnapshot).length > 0) {
    dialogue = buildDialogueFromSnapshot(storySnapshot, 'story_snapshot');
    dialogueSource = 'story_snapshot';
  } else if (!dialogue.length && Object.keys(finalViewStory).length > 0) {
    dialogue = buildDialogueFromSnapshot(finalViewStory, 'final_view_story');
    dialogueSource = 'final_view_story';
  }

  if (!dialogue.length) {
    throw new Error('This JSON does not contain usable dialogue, turn logs, or story snapshots.');
  }

  return {
    session: Object.keys(asRecord(merged.session)).length ? asRecord(merged.session) : null,
    dialogue_source: dialogueSource,
    dialogue,
    turn_logs: turnLogs,
    feedback_logs: feedbackLogs,
    llm_call_logs: llmCallLogs,
    participant_evaluation: Object.keys(participantEvaluation).length ? participantEvaluation : null,
    story_snapshot: Object.keys(storySnapshot).length ? storySnapshot : null,
    final_view_story: Object.keys(finalViewStory).length ? finalViewStory : null,
    schema_version: cleanText(merged.schema_version) || null,
    export_type: cleanText(merged.export_type) || null,
  };
};

const tokenCount = (text: string): number => {
  const matches = text.match(/[A-Za-z0-9']+|[\u4e00-\u9fff]/g);
  return matches ? matches.length : 0;
};

export const buildBenchmarkJudgeInputSummary = (
  payload: BenchmarkJudgePayload,
): BenchmarkJudgeInputSummary => {
  const session = payload.session || {};
  const finalViewStory = payload.final_view_story || {};
  const outputDialogue = payload.dialogue.filter(item => item.role === 'assistant' || item.role === 'system');
  const outputText = outputDialogue.map(item => item.content).join('\n');

  return {
    session_id: typeof session.session_id === 'string' ? session.session_id : typeof session.id === 'string' ? session.id : null,
    story_id:
      typeof session.story_id === 'string'
        ? session.story_id
        : typeof finalViewStory.story_id === 'string'
          ? finalViewStory.story_id
          : typeof finalViewStory.id === 'string'
            ? finalViewStory.id
            : null,
    participant_id:
      typeof session.participant_id === 'string'
        ? session.participant_id
        : typeof finalViewStory.user_id === 'string'
          ? finalViewStory.user_id
          : null,
    selected_model: typeof session.selected_model === 'string' ? session.selected_model : null,
    dialogue_count: payload.dialogue.length,
    output_message_count: outputDialogue.length,
    turn_log_count: payload.turn_logs.length,
    llm_call_count: payload.llm_call_logs.length,
    feedback_count: payload.feedback_logs.length,
    content_source: payload.dialogue_source,
    story_title: typeof finalViewStory.title === 'string' ? finalViewStory.title : null,
    total_output_tokens: tokenCount(outputText),
  };
};
