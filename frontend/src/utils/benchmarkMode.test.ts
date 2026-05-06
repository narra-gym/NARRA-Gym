import {
  getEffectiveFastForward,
  getSceneTransitionDurationMs,
  isBenchmarkStoryMode,
  shouldAnimateStoryMessage,
  shouldAutoInsertInteractiveElement,
  shouldBlockOnInteractiveElement,
  shouldPrefetchChoiceReflection,
} from './benchmarkMode';

describe('benchmarkMode utilities', () => {
  const benchmarkStory = {
    storyMode: 'benchmark' as const,
    benchmarkSpeedProfile: true,
  };

  const defaultStory = {
    storyMode: 'default' as const,
    benchmarkSpeedProfile: false,
  };

  it('detects benchmark stories from either mode field', () => {
    expect(isBenchmarkStoryMode(benchmarkStory)).toBe(true);
    expect(isBenchmarkStoryMode({ storyMode: 'benchmark', benchmarkSpeedProfile: false })).toBe(true);
    expect(isBenchmarkStoryMode(defaultStory)).toBe(false);
  });

  it('disables optional slow-path UI behavior in benchmark mode', () => {
    expect(shouldPrefetchChoiceReflection(benchmarkStory)).toBe(false);
    expect(shouldAutoInsertInteractiveElement(benchmarkStory)).toBe(false);
    expect(shouldBlockOnInteractiveElement(benchmarkStory)).toBe(false);
    expect(shouldAnimateStoryMessage(benchmarkStory)).toBe(false);
  });

  it('keeps default mode behavior unchanged', () => {
    expect(shouldPrefetchChoiceReflection(defaultStory)).toBe(true);
    expect(shouldAutoInsertInteractiveElement(defaultStory)).toBe(true);
    expect(shouldBlockOnInteractiveElement(defaultStory)).toBe(true);
    expect(shouldAnimateStoryMessage(defaultStory)).toBe(true);
  });

  it('keeps fast-forward opt-in while preserving moderated benchmark transitions', () => {
    expect(getEffectiveFastForward(benchmarkStory, false)).toBe(false);
    expect(getEffectiveFastForward(defaultStory, false)).toBe(false);
    expect(getEffectiveFastForward(defaultStory, true)).toBe(true);
    expect(getEffectiveFastForward(benchmarkStory, true)).toBe(true);
    expect(getSceneTransitionDurationMs(benchmarkStory)).toBe(3000);
    expect(getSceneTransitionDurationMs(defaultStory)).toBe(5000);
  });
});
