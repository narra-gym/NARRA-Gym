import { resolveSceneChoices } from './StoryContext';

describe('resolveSceneChoices', () => {
  it('maps fresh choices from the current scene', () => {
    expect(resolveSceneChoices({
      choices: [
        { id: 'c1', text: 'Open the letter', dramatic_impact: 'reveal', visual_representation: 'desk lamp' },
        { id: 'c2', text: 'Hide it away', emotionalImpact: 'avoidance', nextSceneHint: 'dark hallway' },
      ],
    })).toEqual([
      { id: 'c1', text: 'Open the letter', emotionalImpact: 'reveal', nextSceneHint: 'desk lamp' },
      { id: 'c2', text: 'Hide it away', emotionalImpact: 'avoidance', nextSceneHint: 'dark hallway' },
    ]);
  });

  it('clears stale choices when a scene payload arrives without choices', () => {
    expect(resolveSceneChoices({ id: 'scene-2' }, [
      { id: 'old-1', text: 'Old option', emotionalImpact: '', nextSceneHint: undefined },
    ])).toEqual([]);
  });

  it('falls back to previous choices only when there is no current scene payload', () => {
    const previousChoices = [
      { id: 'old-1', text: 'Old option', emotionalImpact: '', nextSceneHint: undefined },
    ];

    expect(resolveSceneChoices(undefined, previousChoices)).toEqual(previousChoices);
  });
});
