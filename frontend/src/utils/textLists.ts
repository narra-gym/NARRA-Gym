const normalizeQuoteVariants = (value: string): string => value
  .replace(/[\u2018\u2019]/g, "'")
  .replace(/[\u201C\u201D]/g, '"');

export const toDisplayText = (value: unknown): string => {
  if (typeof value === 'string') {
    return normalizeQuoteVariants(value).trim();
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }

  if (Array.isArray(value)) {
    return value
      .map(item => toDisplayText(item))
      .filter(Boolean)
      .join(' | ');
  }

  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const title = toDisplayText(record.title ?? record.name ?? record.label);
    const content = toDisplayText(
      record.content
      ?? record.text
      ?? record.summary
      ?? record.description
      ?? record.value
    );

    if (title && content && title !== content) {
      return `${title}: ${content}`;
    }

    return content || title;
  }

  return '';
};

export const canonicalizeTextForDedup = (value: string): string => normalizeQuoteVariants(value)
  .normalize('NFKC')
  .replace(/\r\n?/g, '\n')
  .replace(/\s+/g, ' ')
  .replace(/\s+([,.;:!?])/g, '$1')
  .trim()
  .replace(/^["']+|["']+$/g, '')
  .replace(/[.!?]+$/g, '')
  .toLowerCase();

export const dedupeTextList = (items: unknown[]): string[] => {
  const seen = new Set<string>();
  const result: string[] = [];

  items.forEach(item => {
    const trimmed = toDisplayText(item);
    if (!trimmed) return;

    const key = canonicalizeTextForDedup(trimmed);
    if (!key || seen.has(key)) return;

    seen.add(key);
    result.push(trimmed);
  });

  return result;
};
