import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import ExperimentMode from './ExperimentMode';
import { useStory } from '../contexts/StoryContext';

jest.mock('axios');
jest.mock('../components/ShaderBackground', () => () => <div data-testid="shader-background" />);
jest.mock('../components/BenchmarkSessionHistoryDialog', () => () => null);

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

describe('ExperimentMode', () => {
  const startExperimentSession = jest.fn();
  const clearExperimentSession = jest.fn();
  const loadHistoricalStory = jest.fn();
  const mockConfigRequest = (blindModeEnabled: boolean) => {
    mockedAxios.get.mockImplementation((url: string) => {
      if (url.includes('/experiments/config')) {
        return Promise.resolve({
          data: {
            blind_benchmark_mode_enabled: blindModeEnabled,
          },
        });
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`));
    });
  };

  beforeEach(() => {
    delete process.env.REACT_APP_BENCHMARK_RANDOM_MODE;
    mockedAxios.get.mockReset();
    startExperimentSession.mockReset();
    clearExperimentSession.mockReset();
    loadHistoricalStory.mockReset();
    mockNavigate.mockReset();

    mockedUseStory.mockReturnValue({
      story: null,
      storyId: null,
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
      experimentSession: null,
      experimentMode: false,
      startExperimentSession,
      clearExperimentSession,
      loadHistoricalStory,
    });
  });

  it('shows unavailable models as disabled and starts with the first available model', async () => {
    startExperimentSession.mockResolvedValue({
      participant_id: 'participant-1',
      session_id: 'session-1',
      mode: 'benchmark',
      started_at: '2026-04-04T00:00:00Z',
      selected_model: 'openai/gpt-5.4',
      condition: {
        id: 'baseline',
        name: 'Baseline',
        description: 'Baseline condition',
        active: true,
        assignment_count: 0,
        llm_config: {},
      },
    });

    mockedAxios.get.mockImplementation((url: string) => {
      if (url.includes('/experiments/config')) {
        return Promise.resolve({
          data: {
            blind_benchmark_mode_enabled: false,
          },
        });
      }
      if (url.includes('/experiments/models')) {
        return Promise.resolve({
          data: [
            {
              id: 'doubao/seed-2.0-pro',
              label: 'Doubao Seed 2.0 Pro (Official)',
              provider: 'doubao',
              available: false,
              availability_reason: 'Doubao is unavailable in this environment.',
            },
            {
              id: 'openai/gpt-5.4',
              label: 'OpenAI GPT-5.4',
              provider: 'openrouter',
              available: true,
            },
          ],
        });
      }
      if (url.includes('/experiments/sessions')) {
        return Promise.resolve({ data: [] });
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`));
    });

    render(<ExperimentMode />);

    await screen.findByText('OpenAI GPT-5.4');
    expect(screen.getByText('Doubao is unavailable in this environment.')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Doubao Seed 2.0 Pro (Official)'));
    fireEvent.click(screen.getByRole('button', { name: /start benchmark session/i }));

    await waitFor(() => {
      expect(startExperimentSession).toHaveBeenCalledWith('openai/gpt-5.4');
    });
    expect(mockNavigate).toHaveBeenCalledWith('/start');
  });

  it('renders blind benchmark invite code input and starts with an invite code', async () => {
    process.env.REACT_APP_BENCHMARK_RANDOM_MODE = '1';
    mockConfigRequest(true);

    startExperimentSession.mockResolvedValue({
      participant_id: 'blind-07',
      session_id: 'session-7',
      mode: 'benchmark',
      started_at: '2026-04-04T00:00:00Z',
      selected_model: null,
      blind_mode: true,
      blind_code: 7,
      blind_invite_code: 'NCN7-CV5X',
      blind_session_index: 1,
      blind_total_sessions: 4,
      blind_completed_count: 0,
      blind_remaining_count: 4,
      blind_finished: false,
      condition: {
        id: 'baseline',
        name: 'Baseline',
        description: 'Baseline condition',
        active: true,
        assignment_count: 0,
        llm_config: {},
      },
    });

    render(<ExperimentMode />);

    expect(await screen.findByLabelText(/Invite Code/i)).toBeInTheDocument();
    expect(screen.queryByText('Select Model')).not.toBeInTheDocument();
    expect(screen.getByText(/Global benchmark history is intentionally hidden in blind mode/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Invite Code/i), { target: { value: 'ncn7-cv5x' } });
    fireEvent.click(screen.getByRole('button', { name: /Start Blind Benchmark Session/i }));

    await waitFor(() => {
      expect(startExperimentSession).toHaveBeenCalledWith(null, undefined, 'NCN7-CV5X');
    });
    expect(mockNavigate).toHaveBeenCalledWith('/start');
  });

  it('allows quick test code zero in blind benchmark mode', async () => {
    process.env.REACT_APP_BENCHMARK_RANDOM_MODE = '1';
    mockConfigRequest(true);

    startExperimentSession.mockResolvedValue({
      participant_id: 'blind-00',
      session_id: 'session-quick-test',
      mode: 'benchmark',
      started_at: '2026-04-04T00:00:00Z',
      selected_model: null,
      blind_mode: true,
      blind_code: 0,
      blind_invite_code: null,
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
    });

    render(<ExperimentMode />);

    fireEvent.change(await screen.findByLabelText(/Invite Code/i), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: /Start Blind Benchmark Session/i }));

    await waitFor(() => {
      expect(startExperimentSession).toHaveBeenCalledWith(null, undefined, '0');
    });
  });
});
