export type MixedSegmentKind = 'dialogue' | 'narration';

export interface MixedSegment {
  kind: MixedSegmentKind;
  text: string;
}

const MIXED_PATTERN = /\*([^*]+)\*/g;
const ESCAPED_NEWLINE_PATTERN = /\\r\\n|\\n|\\r/g;

const normalizeMixedContent = (content: string): string => content
  .replace(/\u200B/g, '')
  .replace(/\r\n?/g, '\n')
  .replace(ESCAPED_NEWLINE_PATTERN, '\n')
  .replace(/[ \t\f\v]*\n[ \t\f\v]*/g, '\n')
  .replace(/\n{2,}/g, '\n')
  .trim();

export const hasMixedNarration = (content: string): boolean => /\*[^*]+\*/.test(content || '');

export const parseMixedText = (content: string): MixedSegment[] => {
  if (!content) return [];

  const normalizedContent = normalizeMixedContent(content);
  if (!normalizedContent) return [];

  const segments: MixedSegment[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;
  const pattern = new RegExp(MIXED_PATTERN);

  while ((match = pattern.exec(normalizedContent)) !== null) {
    if (match.index > cursor) {
      const dialogue = normalizedContent.slice(cursor, match.index);
      if (dialogue) {
        segments.push({ kind: 'dialogue', text: dialogue });
      }
    }

    if (match[1]) {
      segments.push({ kind: 'narration', text: match[1] });
    }

    cursor = match.index + match[0].length;
  }

  if (cursor < normalizedContent.length) {
    const tail = normalizedContent.slice(cursor);
    if (tail) {
      segments.push({ kind: 'dialogue', text: tail });
    }
  }

  if (!segments.length) {
    return [{ kind: 'dialogue', text: normalizedContent }];
  }

  return segments.reduce<MixedSegment[]>((acc, segment) => {
    const previous = acc[acc.length - 1];
    if (previous && previous.kind === segment.kind) {
      previous.text += segment.text;
      return acc;
    }
    acc.push({ ...segment });
    return acc;
  }, []);
};

export const buildInlineFlowItems = (
  content: string,
  fonts: { dialogue: string; narration: string },
) => parseMixedText(content).map(segment => ({
  text: segment.text,
  font: segment.kind === 'narration' ? fonts.narration : fonts.dialogue,
}));
