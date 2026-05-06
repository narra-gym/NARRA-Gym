import {
  BenchmarkDialogueRecord,
  BenchmarkResultExportPayload,
  BenchmarkSessionDetail,
  Message,
} from '../types';
import {
  mapRawMessageToMessage,
  mapRawMessagesToMessages,
} from './storyMessages';

export const mergeAdjacentBenchmarkDialogueRecords = (
  dialogue: BenchmarkDialogueRecord[] = [],
): BenchmarkDialogueRecord[] => {
  const merged: BenchmarkDialogueRecord[] = [];

  dialogue.forEach((record, index) => {
    const content = String(record.content || '').trim();
    if (!content) {
      return;
    }

    const normalized: BenchmarkDialogueRecord = {
      ...record,
      id: record.id || `merged-dialogue-${index}`,
      content,
    };

    const previous = merged[merged.length - 1];
    const sameGroup = Boolean(previous)
      && previous.speaker === normalized.speaker
      && previous.role === normalized.role
      && previous.character_id === normalized.character_id
      && previous.turn_index === normalized.turn_index
      && previous.message_type === normalized.message_type;

    if (sameGroup) {
      previous.content = `${previous.content.trimEnd()}\n\n${normalized.content}`;
      return;
    }

    merged.push(normalized);
  });

  return merged;
};

export const mapBenchmarkDialogueToMessages = (dialogue: BenchmarkDialogueRecord[] = []) =>
  dialogue.map((record, index) => ({
    id: record.id || `history-message-${index}`,
    character_id: record.character_id || (record.role === 'user' ? 'protagonist' : record.role === 'system' ? 'system' : `speaker-${index}`),
    content: record.content || '',
    timestamp: record.timestamp || new Date().toISOString(),
    type: record.message_type === 'interactive' ? 'interactive' : record.role === 'system' ? 'system' : 'text',
    render_mode: /\*[^*]+\*/.test(record.content || '') ? 'rp_mixed' : 'plain',
    action: undefined,
    direction: undefined,
    delivery: undefined,
    benchmark_speaker: record.speaker || null,
    benchmark_turn_index: record.turn_index,
  }));

const mapDialogueMessagesToVisibleMessages = (dialogue: BenchmarkDialogueRecord[] = []): Message[] =>
  mapBenchmarkDialogueToMessages(dialogue)
    .map((message, index) => mapRawMessageToMessage(message, `dialogue-message-${index}`))
    .filter((message): message is Message => Boolean(message));

const extractSnapshotMessages = (snapshot: Record<string, any> | null | undefined) => {
  if (!snapshot) {
    return [];
  }
  const currentScene = snapshot.current_scene || snapshot.currentScene || {};
  return Array.isArray(currentScene.messages) ? currentScene.messages : [];
};

const buildMessageKey = (message: Message) =>
  [
    message.id,
    message.characterId || 'system',
    message.type,
    message.timestamp || '',
    message.content || '',
  ].join('::');

const dedupeVisibleMessages = (messages: Message[] = []) => {
  const seen = new Set<string>();
  const deduped: Message[] = [];

  messages.forEach(message => {
    if (message.type === 'typing') {
      return;
    }
    const key = buildMessageKey(message);
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    deduped.push(message);
  });

  return deduped;
};

export const buildVisibleMessagesFromStoryEvents = (
  storyEvents: Record<string, any>[] = [],
): Message[] => {
  const collected: Message[] = [];

  storyEvents.forEach((event, eventIndex) => {
    const payload = (event && typeof event === 'object' ? event.payload : null) || {};
    const snapshot = payload.final_story_snapshot || payload.story_snapshot || null;
    const snapshotMessages = mapRawMessagesToMessages(extractSnapshotMessages(snapshot))
      .map((message, messageIndex) => ({
        ...message,
        id: message.id || `story-event-${eventIndex}-message-${messageIndex}`,
      }));

    collected.push(...snapshotMessages);
  });

  return dedupeVisibleMessages(collected);
};

export const buildVisibleMessagesFromTurnLogs = (
  turnLogs: Record<string, any>[] = [],
): Message[] => {
  const collected: Message[] = [];

  turnLogs.forEach((turn, turnIndex) => {
    const turnId = String(turn.id || `turn-${turn.turn_index || turnIndex}`);
    const createdAt = String(turn.created_at || new Date().toISOString());
    const actionType = String(turn.action_type || 'message').toLowerCase();
    const userInput = String(turn.user_input || '').trim();
    const responseMessages = Array.isArray(turn.metadata?.response_messages)
      ? mapRawMessagesToMessages(turn.metadata.response_messages)
      : [];

    if (userInput) {
      collected.push({
        id: `${turnId}-user`,
        characterId: 'protagonist',
        content: userInput,
        timestamp: createdAt,
        type: actionType.startsWith('choice') ? 'choice' : 'text',
        renderMode: /\*[^*]+\*/.test(userInput) ? 'rp_mixed' : 'plain',
      });
    }

    if (responseMessages.length > 0) {
      collected.push(...responseMessages);
      return;
    }

    const fallbackResponse = mapRawMessageToMessage(
      {
        id: `${turnId}-response`,
        character_id: turn.response_character_id || (String(turn.response_text || '').trim() ? 'system' : undefined),
        content: turn.response_text || '',
        timestamp: createdAt,
        type: turn.response_character_id === 'system' ? 'system' : 'text',
      },
      `${turnId}-response`,
    );

    if (fallbackResponse) {
      collected.push(fallbackResponse);
    }
  });

  return dedupeVisibleMessages(collected);
};

export const buildVisibleMessagesFromBenchmarkDetail = (
  detail: BenchmarkSessionDetail | null | undefined,
): Message[] => {
  if (!detail) {
    return [];
  }

  const eventMessages = buildVisibleMessagesFromStoryEvents(detail.story_events || []);
  if (eventMessages.length > 0) {
    return eventMessages;
  }

  const finalViewMessages = mapRawMessagesToMessages(extractSnapshotMessages(detail.final_view_story || null));
  if (finalViewMessages.length > 0) {
    return finalViewMessages;
  }

  const snapshotMessages = mapRawMessagesToMessages(extractSnapshotMessages(detail.story_snapshot || null));
  if (snapshotMessages.length > 0) {
    return snapshotMessages;
  }

  const turnLogMessages = buildVisibleMessagesFromTurnLogs(detail.turn_logs || []);
  if (turnLogMessages.length > 0) {
    return turnLogMessages;
  }

  return mapDialogueMessagesToVisibleMessages(detail.dialogue || []);
};

const buildDialogueRecordsFromVisibleMessages = (
  visibleMessages: Record<string, any>[] = [],
  story: Record<string, any> | null = null,
): BenchmarkDialogueRecord[] => {
  const storyCharacters = story?.characters;
  const characters: Record<string, any>[] = Array.isArray(storyCharacters)
    ? storyCharacters as Record<string, any>[]
    : [];
  const characterMap = new Map<string, string>();
  const protagonistIds = new Set<string>(['protagonist']);

  characters.forEach(character => {
    if (!character || typeof character !== 'object') {
      return;
    }
    if (typeof character.id === 'string' && character.id.trim()) {
      characterMap.set(character.id, character.name || character.id);
      if (character.role === 'protagonist') {
        protagonistIds.add(character.id);
      }
    }
  });

  return visibleMessages
    .map((message, index) => {
      const messageType = message.type || 'text';
      if (messageType === 'typing') {
        return null;
      }

      const content = String(message.content || '').trim();
      if (!content) {
        return null;
      }

      const characterId = message.characterId || message.character_id || null;
      const isSystem = messageType === 'system' || messageType === 'interactive' || characterId === 'system';
      const isUser = !isSystem && typeof characterId === 'string' && protagonistIds.has(characterId);
      const role: BenchmarkDialogueRecord['role'] = isSystem ? 'system' : isUser ? 'user' : 'assistant';
      const speaker = isSystem
        ? 'System'
        : isUser
          ? (characterMap.get(characterId) || 'You')
          : (characterMap.get(characterId) || characterId || `Speaker ${index + 1}`);

      return {
        id: String(message.id || `visible-dialogue-${index}`),
        speaker,
        role,
        character_id: characterId,
        content,
        timestamp: message.timestamp || null,
        message_type: messageType,
        source: 'visible_messages',
      };
    })
    .filter((message): message is NonNullable<typeof message> => Boolean(message));
};

export const buildReplayStoryFromDetail = (detail: BenchmarkSessionDetail) => {
  const baseStory = detail.final_view_story || detail.story_snapshot || {};
  const visibleMessages = buildVisibleMessagesFromBenchmarkDetail(detail);

  return {
    ...baseStory,
    id: baseStory.id || detail.session.story_id || detail.session.session_id,
    story_id: baseStory.story_id || baseStory.id || detail.session.story_id || detail.session.session_id,
    user_id: baseStory.user_id || detail.session.participant_id,
    title: baseStory.title || 'Benchmark Replay',
    theme: baseStory.theme || baseStory.cinematic_theme || 'Historical Benchmark Session',
    setting: baseStory.setting || 'Historical replay',
    status: 'completed',
    characters: Array.isArray(baseStory.characters) ? baseStory.characters : [],
    current_scene: {
      id: baseStory.current_scene?.id || 'historical-conclusion',
      description: baseStory.current_scene?.description || 'Loaded historical benchmark conclusion.',
      location: baseStory.current_scene?.location || baseStory.current_scene?.setting || 'History Review',
      setting: baseStory.current_scene?.setting || baseStory.current_scene?.location || 'History Review',
      mood: baseStory.current_scene?.mood || baseStory.current_scene?.emotional_tone || 'reflective',
      emotional_tone: baseStory.current_scene?.emotional_tone || baseStory.current_scene?.mood || 'reflective',
      messages: visibleMessages.length > 0
        ? visibleMessages
        : ((baseStory.current_scene?.messages && baseStory.current_scene.messages.length > 0)
          ? baseStory.current_scene.messages
          : []),
      choices: [],
    },
    benchmark_history: detail,
  };
};

export const buildParticipantEvaluation = (feedbackLogs: Record<string, any>[] = []) => {
  if (!feedbackLogs.length) {
    return null;
  }

  const latestFeedback = feedbackLogs[feedbackLogs.length - 1] || null;
  const benchmarkFeedbackLogs = feedbackLogs.filter(
    item => item.feedback_type === 'benchmark_session_end',
  );
  const benchmarkFeedback = benchmarkFeedbackLogs[benchmarkFeedbackLogs.length - 1] || null;
  const primaryFeedback = benchmarkFeedback || latestFeedback;

  if (!primaryFeedback) {
    return null;
  }

  return {
    feedback_count: feedbackLogs.length,
    latest_feedback: latestFeedback,
    benchmark_feedback: benchmarkFeedback,
    rating: primaryFeedback.rating ?? null,
    scores: primaryFeedback.scores || {},
    comment: primaryFeedback.comment || null,
    feelings: primaryFeedback.feelings || [],
    feedback_type: primaryFeedback.feedback_type || null,
    form_version: primaryFeedback.form_version || null,
    created_at: primaryFeedback.created_at || null,
  };
};

const normalizeCharacterForExport = (character: Record<string, any>) => ({
  id: character.id,
  name: character.name,
  role: character.role,
  personality: character.personality || '',
  description: character.description || '',
  image_url: character.imageUrl || character.image_url || undefined,
});

const normalizeVisibleMessageForExport = (message: Record<string, any>) => ({
  id: message.id,
  character_id: message.characterId || message.character_id || null,
  content: message.content || '',
  timestamp: message.timestamp || null,
  type: message.type || 'text',
  render_mode: message.renderMode || message.render_mode || undefined,
  action: message.action || undefined,
  direction: message.direction || undefined,
  delivery: message.delivery || undefined,
});

const buildCompactStoryExport = (
  story: Record<string, any> | null,
  visibleMessages: Record<string, any>[] = [],
) => {
  if (!story) {
    return null;
  }

  const currentScene = story.currentScene || story.current_scene || {};
  const normalizedMessages = visibleMessages.map(normalizeVisibleMessageForExport);

  return {
    id: story.id || story.story_id || null,
    story_id: story.story_id || story.id || null,
    user_id: story.userId || story.user_id || null,
    title: story.title || 'Benchmark Session',
    theme: story.theme || story.cinematic_theme || '',
    setting: story.setting || '',
    status: story.status || 'completed',
    characters: Array.isArray(story.characters)
      ? story.characters.map(normalizeCharacterForExport)
      : [],
    current_scene: {
      id: currentScene.id || 'benchmark-export-scene',
      description: currentScene.description || '',
      location: currentScene.location || currentScene.setting || '',
      setting: currentScene.setting || currentScene.location || '',
      mood: currentScene.mood || currentScene.emotionalTone || currentScene.emotional_tone || '',
      emotional_tone: currentScene.emotionalTone || currentScene.emotional_tone || currentScene.mood || '',
      messages: normalizedMessages,
      choices: [],
    },
  };
};

export const buildBenchmarkResultExportPayload = ({
  session,
  story,
  dialogueSource,
  dialogue,
  visibleMessages,
  turnLogs,
  feedbackLogs,
  templateMode = false,
}: {
  session: Record<string, any> | null;
  story: Record<string, any> | null;
  dialogueSource: string;
  dialogue: BenchmarkDialogueRecord[];
  visibleMessages?: Record<string, any>[];
  turnLogs: Record<string, any>[];
  feedbackLogs: Record<string, any>[];
  templateMode?: boolean;
}): BenchmarkResultExportPayload => {
  const normalizedVisibleMessages = Array.isArray(visibleMessages)
    ? visibleMessages
    : mapDialogueMessagesToVisibleMessages(mergeAdjacentBenchmarkDialogueRecords(dialogue));
  const exportedDialogue = normalizedVisibleMessages.length > 0
    ? buildDialogueRecordsFromVisibleMessages(normalizedVisibleMessages, story)
    : mergeAdjacentBenchmarkDialogueRecords(dialogue);
  const compactStory = buildCompactStoryExport(story, normalizedVisibleMessages);

  return {
    schema_version: 'benchmark_result_v1',
    export_type: 'benchmark_result',
    exported_at: new Date().toISOString(),
    session,
    story: compactStory,
    dialogue_source: dialogueSource,
    dialogue: exportedDialogue,
    turn_logs: turnLogs,
    feedback_logs: feedbackLogs,
    participant_evaluation: buildParticipantEvaluation(feedbackLogs),
    final_view_story: compactStory,
    template_mode: templateMode,
  };
};

export const getBenchmarkResultFilename = (storyTitle?: string | null) => {
  const safeTitle = (storyTitle || 'benchmark-session').replace(/[^a-z0-9-_]+/gi, '_');
  return `${safeTitle}_benchmark_result.json`;
};

export const downloadJsonFile = (filename: string, payload: unknown) => {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  window.URL.revokeObjectURL(url);
  document.body.removeChild(link);
};
