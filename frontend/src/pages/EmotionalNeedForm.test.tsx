import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import EmotionalNeedForm from './EmotionalNeedForm';
import { useStory } from '../contexts/StoryContext';

jest.mock('axios');
jest.mock('../components/ShaderBackground', () => () => <div data-testid="shader-background" />);

const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => mockNavigate,
}));

jest.mock('../contexts/StoryContext', () => ({
  ...jest.requireActual('../contexts/StoryContext'),
  API_BASE_URL: 'http://localhost:11454',
  useStory: jest.fn(),
}));

const mockedAxios = axios as jest.Mocked<typeof axios>;
const mockedUseStory = useStory as jest.MockedFunction<typeof useStory>;

describe('EmotionalNeedForm', () => {
  const loadHistoricalStory = jest.fn();

  beforeEach(() => {
    mockNavigate.mockReset();
    loadHistoricalStory.mockReset();
    mockedAxios.post.mockReset();

    mockedUseStory.mockReturnValue({
      story: null,
      storyId: null,
      clarifyingQuestions: null,
      questionsData: null,
      keywords: null,
      loading: false,
      error: null,
      userId: 'blind-00',
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
      dialogueCount: 0,
      pacingRecommendation: null,
      generateStoryReflection: jest.fn(),
      generateInteractiveElement: jest.fn(),
      clearInteractiveElement: jest.fn(),
      profileKeywords: null,
      fastForward: false,
      setFastForward: jest.fn(),
      appendMessageToCurrentScene: jest.fn(),
      emotionHistory: [],
      experimentSession: {
        participant_id: 'blind-00',
        session_id: 'session-quick-test',
        mode: 'benchmark',
        started_at: '2026-04-04T00:00:00Z',
        selected_model: null,
        blind_mode: true,
        blind_code: 0,
        blind_session_index: 1,
        blind_total_sessions: 4,
        blind_completed_count: 0,
        blind_remaining_count: 4,
        blind_finished: false,
        quick_test_mode: true,
        quick_test_completed_runs: 0,
        condition: {
          id: 'baseline',
          name: 'Baseline',
          description: 'Baseline condition',
          active: true,
          assignment_count: 0,
          llm_config: {},
        },
      },
      experimentMode: true,
      startExperimentSession: jest.fn(),
      clearExperimentSession: jest.fn(),
      loadHistoricalStory,
    });
  });

  it('auto-launches the quick test story for blind code zero', async () => {
    mockedAxios.post.mockResolvedValue({
      data: {
        id: 'story-quick-test',
        title: 'Lantern Room Test Run',
        current_scene: { messages: [], choices: [] },
      },
    });

    render(<EmotionalNeedForm />);

    expect(await screen.findByText(/Quick test mode is preparing a default benchmark world/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(mockedAxios.post).toHaveBeenCalledWith('http://localhost:11454/stories/quickstart', {
        user_id: 'blind-00',
        participant_id: 'blind-00',
        session_id: 'session-quick-test',
      });
    });

    expect(loadHistoricalStory).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 'story-quick-test',
        title: 'Lantern Room Test Run',
      }),
    );
    expect(mockNavigate).toHaveBeenCalledWith('/story/interaction');
  });
});
