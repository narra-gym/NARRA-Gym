import { canonicalizeTextForDedup, dedupeTextList, toDisplayText } from './textLists';

describe('textLists utilities', () => {
  it('deduplicates equivalent clue lines while preserving the first wording', () => {
    expect(dedupeTextList([
      "The tape was likely logged under Lena's work account, and Riley may already have heard part of the message.",
      "The tape was likely logged under Lena's work account, and Riley may already have heard part of the message.",
      "  the tape was likely logged under Lena's work account, and Riley may already have heard part of the message  ",
    ])).toEqual([
      "The tape was likely logged under Lena's work account, and Riley may already have heard part of the message.",
    ]);
  });

  it('normalizes punctuation and quote variants for comparison', () => {
    expect(canonicalizeTextForDedup('"Same clue."')).toBe(canonicalizeTextForDedup('"Same clue"'));
    expect(canonicalizeTextForDedup('Same clue.')).toBe(canonicalizeTextForDedup('Same clue'));
  });

  it('flattens structured title/content objects into display-safe text', () => {
    expect(toDisplayText({
      title: 'Open tension',
      content: 'She may still walk away before the truth lands.',
    })).toBe('Open tension: She may still walk away before the truth lands.');
  });

  it('deduplicates structured clue objects after flattening them', () => {
    expect(dedupeTextList([
      { title: 'Clue', content: 'The lantern changes color for each hidden slot.' },
      { title: 'Clue', content: 'The lantern changes color for each hidden slot.' },
      { text: 'The logbook tracks completed runs.' },
    ])).toEqual([
      'Clue: The lantern changes color for each hidden slot.',
      'The logbook tracks completed runs.',
    ]);
  });
});
