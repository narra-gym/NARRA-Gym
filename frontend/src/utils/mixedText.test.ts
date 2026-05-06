import { buildInlineFlowItems, parseMixedText } from './mixedText';

describe('mixedText utilities', () => {
  it('splits narration and dialogue while keeping a compact single line break', () => {
    expect(parseMixedText('*The room goes quiet.*\n\n"Not yet," you say.')).toEqual([
      { kind: 'narration', text: 'The room goes quiet.' },
      { kind: 'dialogue', text: '\n"Not yet," you say.' },
    ]);
  });

  it('normalizes escaped line breaks from model output', () => {
    expect(parseMixedText('*The room goes quiet.*\\n\\n"Not yet," you say.')).toEqual([
      { kind: 'narration', text: 'The room goes quiet.' },
      { kind: 'dialogue', text: '\n"Not yet," you say.' },
    ]);
  });

  it('falls back to a single dialogue segment for plain text', () => {
    expect(parseMixedText('She slides the folder across the desk.')).toEqual([
      { kind: 'dialogue', text: 'She slides the folder across the desk.' },
    ]);
  });

  it('builds inline-flow items with narration and dialogue fonts', () => {
    const items = buildInlineFlowItems('*Rain taps the window.* "Come with me."', {
      dialogue: '400 16px "Segoe UI"',
      narration: '400 italic 15px "Georgia"',
    });

    expect(items).toEqual([
      { text: 'Rain taps the window.', font: '400 italic 15px "Georgia"' },
      { text: ' "Come with me."', font: '400 16px "Segoe UI"' },
    ]);
  });
});
