import { Story } from '../types';

export const isBenchmarkStoryMode = (story?: Pick<Story, 'storyMode' | 'benchmarkSpeedProfile'> | null): boolean =>
  Boolean(story?.benchmarkSpeedProfile || story?.storyMode === 'benchmark');

export const shouldPrefetchChoiceReflection = (story?: Pick<Story, 'storyMode' | 'benchmarkSpeedProfile'> | null): boolean =>
  !isBenchmarkStoryMode(story);

export const shouldAutoInsertInteractiveElement = (story?: Pick<Story, 'storyMode' | 'benchmarkSpeedProfile'> | null): boolean =>
  !isBenchmarkStoryMode(story);

export const shouldBlockOnInteractiveElement = (story?: Pick<Story, 'storyMode' | 'benchmarkSpeedProfile'> | null): boolean =>
  !isBenchmarkStoryMode(story);

export const shouldAnimateStoryMessage = (story?: Pick<Story, 'storyMode' | 'benchmarkSpeedProfile'> | null): boolean =>
  !isBenchmarkStoryMode(story);

export const getEffectiveFastForward = (
  story?: Pick<Story, 'storyMode' | 'benchmarkSpeedProfile'> | null,
  fastForward?: boolean,
): boolean => Boolean(fastForward);

export const getSceneTransitionDurationMs = (story?: Pick<Story, 'storyMode' | 'benchmarkSpeedProfile'> | null): number =>
  isBenchmarkStoryMode(story) ? 3000 : 5000;
