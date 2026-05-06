import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import StoryInteraction from './StoryInteraction';
import { useStory } from '../contexts/StoryContext';

jest.mock('../components/DebugPanel', () => () => null);
jest.mock('../components/InteractiveElement', () => ({
  __esModule: true,
  default: ({ htmlCode }: any) => <div data-testid="interactive-element">{htmlCode}</div>,
}));
jest.mock('../components/SpacetimeWarp', () => () => <div data-testid="spacetime-warp" />);
jest.mock('../components/FeedbackWidget', () => () => <div data-testid="feedback-widget" />);
jest.mock('../components/MixedRichText', () => ({
  __esModule: true,
  default: ({ content }: any) => <div>{content}</div>,
}));
jest.mock('../components/TranscriptPane', () => ({
  __esModule: true,
  default: ({ messages, renderMessage }: any) => (
    <div data-testid="transcript-pane">
      {messages.map((message: any, index: number) => (
        <div key={message.id || index}>{renderMessage(message, index)}</div>
      ))}
    </div>
  ),
}));

const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => mockNavigate,
}));

jest.mock('../contexts/StoryContext', () => ({
  ...jest.requireActual('../contexts/StoryContext'),
  useStory: jest.fn(),
}));

const mockedUseStory = useStory as jest.MockedFunction<typeof useStory>;

const buildStory = (overrides: Record<string, any> = {}) => ({
  id: 'story-1',
  userId: 'participant-1',
  title: 'Shared Space',
  theme: 'Trust and uncertainty',
  setting: 'Shared Loft',
  emotionalGoal: 'Clarity',
  status: 'active',
  createdAt: '2026-04-04T00:00:00Z',
  updatedAt: '2026-04-04T00:05:00Z',
  previousScenes: [],
  dialogueSummaries: [],
  dialogueCount: 2,
  exchangeCount: 1,
  conclusionCountdown: 0,
  storyMemory: {
    whatJustHappened: 'The conversation is sharpening.',
    currentGoal: 'Understand what changed in the room.',
    openTensions: ['Nobody has named the real issue yet.'],
    activeClues: ['A late-night message is still sitting unread.'],
    lastMajorTurningPoint: 'The room finally stopped pretending everything was fine.',
  },
  storyProgress: {
    currentActIndex: 0,
    actCount: 3,
    currentActTitle: 'Act I',
    currentActPurpose: 'Establish the shared emotional pressure.',
    sceneLocation: 'Shared Loft',
  },
  sceneInfoPanel: {
    recap: 'The conversation is sharpening.',
    sceneLocation: 'Shared Loft',
    objective: 'Understand what changed in the room.',
    currentTension: 'Something important is still unsaid.',
    immediateStakes: 'If nobody names it, the trust in the room will keep eroding.',
    locationStatus: 'The shared loft feels tense but unchanged.',
    clueSummary: ['A late-night message is still sitting unread.'],
    tensionSummary: ['Nobody has named the real issue yet.'],
  },
  storyState: {
    currentObjective: 'Understand what changed in the room.',
    currentTension: 'Something important is still unsaid.',
    immediateStakes: 'If nobody names it, the trust in the room will keep eroding.',
    locationStatus: 'The shared loft feels tense but unchanged.',
    relationshipShift: 'The guide stops pretending everything is routine.',
    latestReveal: 'Someone deliberately held back the key detail.',
    emotionalBeat: 'Tight but restrained.',
  },
  interactiveElementHistory: [],
  characters: [
    {
      id: 'protagonist',
      name: 'You',
      role: 'protagonist',
      description: 'Trying to make sense of the room.',
      personality: 'Attentive and cautious.',
      relationship: 'Self',
    },
    {
      id: 'guide_alpha',
      name: 'Guide Alpha',
      role: 'npc',
      description: 'A guide who notices every hesitation.',
      personality: 'Measured and observant.',
      relationship: 'An uneasy ally.',
    },
    {
      id: 'archivist_beta',
      name: 'Archivist Beta',
      role: 'npc',
      description: 'The keeper of the room’s hidden records.',
      personality: 'Precise and guarded.',
      relationship: 'A stranger with leverage.',
    },
  ],
  castStatuses: [
    {
      characterId: 'protagonist',
      name: 'You',
      role: 'protagonist',
      relationship: 'Self',
      currentStatus: 'Still here.',
      lastSeen: 'I need the truth.',
      inSceneNow: true,
    },
    {
      characterId: 'guide-alpha',
      name: 'Guide Alpha',
      role: 'npc',
      relationship: 'An uneasy ally.',
      currentStatus: 'Watching you closely.',
      lastSeen: 'I stayed because this matters.',
      inSceneNow: true,
    },
    {
      characterId: 'archivist-beta',
      name: 'Archivist Beta',
      role: 'npc',
      relationship: 'A stranger with leverage.',
      currentStatus: 'Still somewhere off-screen.',
      lastSeen: '',
      inSceneNow: false,
    },
  ],
  currentScene: {
    id: 'scene-1',
    description: 'A shared loft with a narrow kitchen alcove and a table no one is ready to leave.',
    setting: 'Shared Loft',
    location: 'Shared Loft',
    characters: ['protagonist', 'guide_alpha'],
    messages: [
      {
        id: 'm1',
        characterId: 'protagonist',
        content: 'Tell me what changed.',
        timestamp: '2026-04-04T00:00:00Z',
        type: 'text',
      },
      {
        id: 'm2',
        characterId: 'npc',
        content: 'You already know the room feels different.',
        timestamp: '2026-04-04T00:00:05Z',
        type: 'text',
      },
    ],
    choices: [],
    emotionalTone: 'steady',
    scene_transition_caption: '',
    hiddenElements: {},
    sceneElements: {},
    sceneDynamics: {
      transitionRequired: false,
      newLocation: '',
      timeProgression: '',
      narrativeAdvancement: 'The scene tightens around a concrete truth.',
      sceneTransitionCaption: '',
    },
    storyState: {
      currentObjective: 'Understand what changed in the room.',
      currentTension: 'Something important is still unsaid.',
      immediateStakes: 'If nobody names it, the trust in the room will keep eroding.',
      locationStatus: 'The shared loft feels tense but unchanged.',
      relationshipShift: 'The guide stops pretending everything is routine.',
      latestReveal: 'Someone deliberately held back the key detail.',
      emotionalBeat: 'Tight but restrained.',
    },
  },
  ...overrides,
});

const buildContext = (storyOverrides: Record<string, any> = {}) => ({
  story: buildStory(storyOverrides) as any,
  storyId: 'story-1',
  clarifyingQuestions: null,
  questionsData: null,
  keywords: null,
  loading: false,
  error: null,
  userId: 'participant-1',
  emotionalNeed: '',
  submitEmotionalNeed: jest.fn(),
  initiateStory: jest.fn(),
  submitAnswersAndCreateStory: jest.fn(),
  sendMessage: jest.fn(),
  selectChoice: jest.fn(),
  endStory: jest.fn(),
  storyGenerationProgress: 0,
  currentGenerationStep: 0,
  generationStatus: '',
  getStoryGenerationProgress: jest.fn(),
  storyReflection: null,
  interactiveElement: null,
  dialogueCount: 2,
  pacingRecommendation: null,
  generateStoryReflection: jest.fn(),
  generateInteractiveElement: jest.fn(),
  clearInteractiveElement: jest.fn(),
  profileKeywords: null,
  fastForward: false,
  setFastForward: jest.fn(),
  appendMessageToCurrentScene: jest.fn(),
  emotionHistory: [],
  experimentSession: null,
  experimentMode: false,
  startExperimentSession: jest.fn(),
  clearExperimentSession: jest.fn(),
  loadHistoricalStory: jest.fn(),
});

const getCharacterCardText = (name: string): string => {
  const nodes = screen.getAllByText(name);
  for (const startNode of nodes) {
    let node: HTMLElement | null = startNode as HTMLElement;
    while (node) {
      const text = node.textContent || '';
      if (text.includes('On screen now') || text.includes('Off screen')) {
        return text;
      }
      node = node.parentElement;
    }
  }
  return '';
};

describe('StoryInteraction', () => {
  beforeEach(() => {
    mockNavigate.mockReset();
    mockedUseStory.mockReturnValue(buildContext() as any);
  });

  it('shows an NPC as present when inSceneNow is true even if the streamed message uses a generic npc id', async () => {
    mockedUseStory.mockReturnValue(buildContext({
      characters: [
        {
          id: 'protagonist',
          name: 'You',
          role: 'protagonist',
          description: 'Trying to make sense of the room.',
          personality: 'Attentive and cautious.',
          relationship: 'Self',
        },
        {
          id: 'guide_alpha',
          name: 'Guide Alpha',
          role: 'npc',
          description: 'A guide who notices every hesitation.',
          personality: 'Measured and observant.',
          relationship: 'An uneasy ally.',
        },
      ],
      castStatuses: [
        {
          characterId: 'protagonist',
          name: 'You',
          role: 'protagonist',
          relationship: 'Self',
          currentStatus: 'Still here.',
          lastSeen: 'I need the truth.',
          inSceneNow: true,
        },
        {
          characterId: 'guide-alpha',
          name: 'Guide Alpha',
          role: 'npc',
          relationship: 'An uneasy ally.',
          currentStatus: 'Watching you closely.',
          lastSeen: 'I stayed because this matters.',
          inSceneNow: true,
        },
      ],
    }) as any);

    render(<StoryInteraction />);

    fireEvent.click(await screen.findByRole('tab', { name: 'Cast' }));

    await waitFor(() => {
      expect(getCharacterCardText('Guide Alpha')).toContain('On screen now');
    });
    expect(screen.queryByText('Off screen')).not.toBeInTheDocument();
  });

  it('resets visible NPC presence after a real scene shift', async () => {
    const initialContext = buildContext();
    mockedUseStory.mockReturnValue(initialContext as any);
    const { rerender } = render(<StoryInteraction />);

    fireEvent.click(await screen.findByRole('tab', { name: 'Cast' }));
    expect(getCharacterCardText('Guide Alpha')).toContain('On screen now');
    expect(getCharacterCardText('Archivist Beta')).toContain('Off screen');

    mockedUseStory.mockReturnValue(buildContext({
      castStatuses: [
        {
          characterId: 'protagonist',
          name: 'You',
          role: 'protagonist',
          relationship: 'Self',
          currentStatus: 'Still here.',
          lastSeen: 'I need the truth.',
          inSceneNow: true,
        },
        {
          characterId: 'guide-alpha',
          name: 'Guide Alpha',
          role: 'npc',
          relationship: 'An uneasy ally.',
          currentStatus: 'Now left behind.',
          lastSeen: 'I stayed because this matters.',
          inSceneNow: false,
        },
        {
          characterId: 'archivist-beta',
          name: 'Archivist Beta',
          role: 'npc',
          relationship: 'A stranger with leverage.',
          currentStatus: 'Now stepping into the room.',
          lastSeen: 'You finally made it here.',
          inSceneNow: true,
        },
      ],
      currentScene: {
        ...initialContext.story.currentScene,
        location: 'Archive Annex',
        scene_transition_caption: 'MOMENTS LATER - ARCHIVE ANNEX',
        messages: [
          ...initialContext.story.currentScene.messages,
          {
            id: 'transition-1',
            characterId: 'system',
            content: '[MOMENTS LATER - ARCHIVE ANNEX]',
            timestamp: '2026-04-04T00:01:00Z',
            type: 'system',
          },
          {
            id: 'm3',
            characterId: 'archivist_beta',
            content: 'The annex keeps a better record than the loft ever did.',
            timestamp: '2026-04-04T00:01:05Z',
            type: 'text',
          },
        ],
      },
      sceneInfoPanel: {
        ...initialContext.story.sceneInfoPanel,
        sceneLocation: 'Archive Annex',
        locationStatus: 'The annex is colder and more exacting than the loft.',
      },
      storyProgress: {
        ...initialContext.story.storyProgress,
        sceneLocation: 'Archive Annex',
      },
    }) as any);

    rerender(<StoryInteraction />);

    await waitFor(() => {
      expect(getCharacterCardText('Guide Alpha')).toContain('Off screen');
      expect(getCharacterCardText('Archivist Beta')).toContain('On screen now');
    });
  });

  it('keeps the location trail tied to currentScene.location and avoids duplicate same-location entries on time jumps', async () => {
    mockedUseStory.mockReturnValue(buildContext() as any);
    const { rerender } = render(<StoryInteraction />);

    fireEvent.click(await screen.findByRole('tab', { name: 'Journey' }));
    expect(await screen.findByText('Shared Loft (Current)')).toBeInTheDocument();

    mockedUseStory.mockReturnValue(buildContext({
      currentScene: {
        ...buildContext().story.currentScene,
        location: 'Shared Loft',
        scene_transition_caption: 'MOMENTS LATER - SHARED LOFT',
      },
    }) as any);
    rerender(<StoryInteraction />);

    await waitFor(() => {
      expect(screen.getAllByText('Shared Loft (Current)')).toHaveLength(1);
    });

    mockedUseStory.mockReturnValue(buildContext({
      currentScene: {
        ...buildContext().story.currentScene,
        location: 'Kitchen Alcove',
        scene_transition_caption: 'MOMENTS LATER - KITCHEN ALCOVE',
      },
      sceneInfoPanel: {
        ...buildContext().story.sceneInfoPanel,
        sceneLocation: 'Kitchen Alcove',
      },
      storyProgress: {
        ...buildContext().story.storyProgress,
        sceneLocation: 'Kitchen Alcove',
      },
    }) as any);
    rerender(<StoryInteraction />);

    expect(await screen.findByText('Kitchen Alcove (Current)')).toBeInTheDocument();
    expect(screen.getByText('Shared Loft')).toBeInTheDocument();
  });

  it('hides the weak emotion panel and the old act progress card', async () => {
    render(<StoryInteraction />);

    expect(await screen.findByRole('tab', { name: 'State' })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Emotion' })).not.toBeInTheDocument();
    expect(screen.queryByText('Act Progress')).not.toBeInTheDocument();
    expect(screen.queryByText('Emotional Beat')).not.toBeInTheDocument();
  });
});
