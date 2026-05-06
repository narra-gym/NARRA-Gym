import { Message } from '../types';
import { stripBenchmarkStateLeak } from './storyText';

const asRecord = (value: unknown): Record<string, any> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, any>
    : {};

const asArray = (value: unknown): Record<string, any>[] =>
  Array.isArray(value) ? value.map(item => asRecord(item)) : [];

export const buildMessageDisplayContent = (rawMessage: Record<string, any>): string => {
  const messageType = String(rawMessage.type || 'text');
  if (messageType === 'interactive') {
    return String(rawMessage.content || '');
  }

  const content = stripBenchmarkStateLeak(String(rawMessage.content || ''));
  if (typeof content === 'string' && /\*[^*]+\*/.test(content)) {
    return content;
  }

  const narrative = [rawMessage.direction, rawMessage.action]
    .map((value: unknown) => String(value || '').trim())
    .filter(Boolean)
    .join(' ');

  if (!narrative) {
    return content;
  }

  return content ? `*${narrative}*\n\n${content}` : `*${narrative}*`;
};

export const mapRawMessageToMessage = (
  rawMessageInput: unknown,
  fallbackId?: string,
): Message | null => {
  const rawMessage = asRecord(rawMessageInput);
  const messageType = String(rawMessage.type || 'text') as Message['type'];
  const content = buildMessageDisplayContent(rawMessage);

  if (!content && messageType !== 'typing') {
    return null;
  }

  return {
    id: String(rawMessage.id || fallbackId || `msg-${Math.random().toString(36).substring(2, 9)}`),
    characterId: rawMessage.character_id || rawMessage.characterId,
    content,
    timestamp: String(rawMessage.timestamp || new Date().toISOString()),
    type: messageType,
    delivery: String(rawMessage.delivery || ''),
    action: String(rawMessage.action || ''),
    direction: String(rawMessage.direction || ''),
    renderMode: (
      rawMessage.render_mode ||
      rawMessage.renderMode ||
      ((rawMessage.action || rawMessage.direction || /\*[^*]+\*/.test(content || '')) ? 'rp_mixed' : 'plain')
    ) as Message['renderMode'],
  };
};

export const mapRawMessagesToMessages = (rawMessages: unknown): Message[] =>
  asArray(rawMessages)
    .map((message, index) => mapRawMessageToMessage(message, `raw-message-${index}`))
    .filter((message): message is Message => Boolean(message));
