import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import StoryConclusion from './StoryConclusion';
import { useStory } from '../contexts/StoryContext';
import { buildReplayStoryFromDetail, downloadJsonFile } from '../utils/benchmarkHistory';
import {
  readLocalBenchmarkReviewHistory,
  upsertLocalBenchmarkReviewDetail,
} from '../utils/localBenchmarkReview';

jest.mock('axios');
jest.mock('../components/FeedbackWidget', () => () => <div data-testid="feedback-widget" />);
jest.mock('../components/BenchmarkEvaluationForm', () => ({
  __esModule: true,
  default: ({ sessionId, onFeedbackSaved }: any) => (
    <div data-testid={`benchmark-evaluation-form-${sessionId || 'current'}`}>
      <div>Benchmark Human Evaluation</div>
      {onFeedbackSaved && (
        <button
          type="button"
          onClick={() => onFeedbackSaved({
            id: `mock-feedback-${sessionId || 'current'}`,
            session_id: sessionId || 'session-1',
            feedback_type: 'benchmark_session_end',
            rating: 4,
            comment: 'Revised after comparison.',
            form_version: 'benchmark_emotional_human_v1',
            created_at: '2026-04-04T00:20:00Z',
            scores: {
              story_relevance: 4,
              story_coherence: 4,
            },
          })}
        >
          Mock Save {sessionId || 'current'}
        </button>
      )}
    </div>
  ),
}));
jest.mock('../components/TranscriptPane', () => () => <div data-testid="transcript-pane" />);

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

jest.mock('../utils/benchmarkHistory', () => ({
  ...jest.requireActual('../utils/benchmarkHistory'),
  downloadJsonFile: jest.fn(),
}));

const mockedUseStory = useStory as jest.MockedFunction<typeof useStory>;
const mockedDownloadJsonFile = downloadJsonFile as jest.MockedFunction<typeof downloadJsonFile>;
const mockedAxios = axios as jest.Mocked<typeof axios>;

const getLatestRating = (detail?: any) => {
  const benchmarkLogs = (detail?.feedback_logs || []).filter(
    (item: any) => item.feedback_type === 'benchmark_session_end',
  );
  return benchmarkLogs[benchmarkLogs.length - 1]?.rating;
};

describe('StoryConclusion', () => {
  const startExperimentSession = jest.fn();
  const clearExperimentSession = jest.fn();
  const loadHistoricalStory = jest.fn();

  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    mockNavigate.mockReset();
    startExperimentSession.mockReset();
    clearExperimentSession.mockReset();
    loadHistoricalStory.mockReset();
    mockedDownloadJsonFile.mockReset();
    mockedAxios.get.mockReset();
    mockedAxios.get.mockResolvedValue({
      data: {
        schema_version: 'benchmark_result_v1',
        export_type: 'benchmark_result',
      },
    });

    mockedUseStory.mockReturnValue({
      story: {
        id: 'story-1',
        userId: 'participant-1',
        title: 'Late Night',
        theme: 'Fear and courage',
        setting: 'A quiet station',
        emotionalGoal: 'Relief',
        status: 'completed',
        createdAt: '2026-04-04T00:00:00Z',
        updatedAt: '2026-04-04T00:10:00Z',
        previousScenes: [],
        characters: [
          { id: 'protagonist', name: 'You', role: 'protagonist', description: '', personality: '' },
          { id: 'guide', name: 'Guide', role: 'npc', description: '', personality: '' },
        ],
        currentScene: {
          id: 'scene-1',
          description: 'The station settles into a calm hush.',
          setting: 'A quiet station',
          characters: ['protagonist', 'guide'],
          messages: [
            {
              id: 'm1',
              characterId: 'protagonist',
              content: 'I feel stuck.',
              timestamp: '2026-04-04T00:00:00Z',
              type: 'text',
            },
            {
              id: 'm2',
              characterId: 'guide',
              content: 'We can take one concrete step at a time.',
              timestamp: '2026-04-04T00:00:05Z',
              type: 'text',
            },
          ],
          choices: [],
          emotionalTone: 'steady',
        },
        benchmarkHistory: {
          session: {
            session_id: 'session-1',
            participant_id: 'participant-1',
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
          },
          dialogue_source: 'saved_dialogue',
          dialogue: [
            { id: 'd1', speaker: 'You', role: 'user', content: 'I feel stuck.' },
            { id: 'd2', speaker: 'Guide', role: 'assistant', content: 'We can take one concrete step at a time.' },
          ],
          turn_logs: [
            {
              id: 'turn-1',
              turn_index: 1,
              user_input: 'I feel stuck.',
              response_text: 'We can take one concrete step at a time.',
            },
          ],
          story_events: [{ id: 'event-1', event_type: 'story_turn_completed' }],
          llm_call_logs: [{ id: 'llm-1', model_name: 'openai/gpt-5.4' }],
          feedback_logs: [
            {
              id: 'feedback-1',
              session_id: 'session-1',
              story_id: 'story-1',
              rating: 5,
              comment: 'Felt grounded and specific.',
              feedback_type: 'benchmark_session_end',
              form_version: 'benchmark_emotional_human_v1',
              scores: {
                story_relevance: 5,
                story_coherence: 5,
              },
              created_at: '2026-04-04T00:12:00Z',
            },
          ],
          participant_evaluation: {
            rating: 5,
            comment: 'Felt grounded and specific.',
          },
          story_snapshot: { id: 'story-1' },
          final_view_story: { id: 'story-1', title: 'Late Night' },
          template_mode: false,
        },
      } as any,
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
      },
      experimentMode: true,
      startExperimentSession,
      clearExperimentSession,
      loadHistoricalStory,
    });
  });

  it('replaces analysis export with result json export and includes participant evaluation', async () => {
    render(<StoryConclusion />);

    await screen.findByText(/Overall story score: 5\/5/i);

    expect(screen.queryByText('Session Evaluation')).not.toBeInTheDocument();
    expect(screen.getByText('Benchmark Human Evaluation')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Export Analysis/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Export Benchmark JSON/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Export Result JSON/i }));

    await waitFor(() => {
      expect(mockedDownloadJsonFile).toHaveBeenCalledWith(
        'Late_Night_benchmark_result.json',
        expect.objectContaining({
          schema_version: 'benchmark_result_v1',
          export_type: 'benchmark_result',
        }),
      );
    });
    expect(mockedAxios.get).toHaveBeenCalledWith('http://localhost:11454/experiments/sessions/session-1/export');
  });

  it('hides model labels for blind benchmark sessions', async () => {
    const baseContext = mockedUseStory();
    mockedUseStory.mockReturnValue({
      ...baseContext,
      story: {
        ...(baseContext as any).story,
        benchmarkHistory: {
          ...((baseContext as any).story?.benchmarkHistory || {}),
          session: {
            session_id: 'session-1',
            participant_id: 'blind-03',
            mode: 'benchmark',
            started_at: '2026-04-04T00:00:00Z',
            selected_model: null,
            blind_mode: true,
            blind_code: 3,
            blind_invite_code: 'LY7H-H8W8',
            blind_session_index: 2,
            blind_total_sessions: 4,
            blind_completed_count: 1,
            blind_remaining_count: 3,
            blind_finished: false,
            condition: {
              id: 'baseline',
              name: 'Baseline',
              description: 'Baseline condition',
              active: true,
              assignment_count: 0,
              llm_config: {},
            },
          },
        },
      } as any,
      experimentSession: {
        participant_id: 'blind-03',
        session_id: 'session-1',
        mode: 'benchmark',
        started_at: '2026-04-04T00:00:00Z',
        selected_model: null,
        blind_mode: true,
        blind_code: 3,
        blind_invite_code: 'LY7H-H8W8',
        blind_session_index: 2,
        blind_total_sessions: 4,
        blind_completed_count: 1,
        blind_remaining_count: 3,
        blind_finished: false,
        condition: {
          id: 'baseline',
          name: 'Baseline',
          description: 'Baseline condition',
          active: true,
          assignment_count: 0,
          llm_config: {},
        },
      },
    } as any);

    render(<StoryConclusion />);

    expect(await screen.findByText(/Invite code: LY7H-H8W8/i)).toBeInTheDocument();
    expect(screen.queryByText(/Model:/i)).not.toBeInTheDocument();
  });

  it('starts the next quick test session directly from the conclusion screen', async () => {
    startExperimentSession.mockResolvedValue({
      participant_id: 'blind-00',
      session_id: 'session-2',
      mode: 'benchmark',
      started_at: '2026-04-04T00:20:00Z',
      selected_model: null,
      blind_mode: true,
      blind_code: 0,
      blind_session_index: 2,
      blind_total_sessions: 4,
      blind_completed_count: 1,
      blind_remaining_count: 3,
      blind_finished: false,
      quick_test_mode: true,
      quick_test_completed_runs: 1,
      condition: {
        id: 'baseline',
        name: 'Baseline',
        description: 'Baseline condition',
        active: true,
        assignment_count: 0,
        llm_config: {},
      },
    });

    const baseContext = mockedUseStory();
    mockedUseStory.mockReturnValue({
      ...baseContext,
      story: {
        ...(baseContext as any).story,
        benchmarkHistory: null,
      } as any,
      experimentSession: {
        participant_id: 'blind-00',
        session_id: 'session-1',
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
      startExperimentSession,
    } as any);

    render(<StoryConclusion />);

    fireEvent.click(await screen.findByRole('button', { name: /Start Next Test Story/i }));

    await waitFor(() => {
      expect(startExperimentSession).toHaveBeenCalledWith(null, undefined, 0);
    });
    expect(mockNavigate).toHaveBeenCalledWith('/start');
  });

  it('returns to start instead of retrying once the quick test sequence is complete', async () => {
    const baseContext = mockedUseStory();
    mockedUseStory.mockReturnValue({
      ...baseContext,
      story: {
        ...(baseContext as any).story,
        benchmarkHistory: null,
      } as any,
      experimentSession: {
        participant_id: 'blind-00',
        session_id: 'session-4',
        mode: 'benchmark',
        started_at: '2026-04-04T00:40:00Z',
        selected_model: null,
        blind_mode: true,
        blind_code: 0,
        blind_session_index: 4,
        blind_total_sessions: 4,
        blind_completed_count: 4,
        blind_remaining_count: 0,
        blind_finished: true,
        quick_test_mode: true,
        quick_test_completed_runs: 4,
        condition: {
          id: 'baseline',
          name: 'Baseline',
          description: 'Baseline condition',
          active: true,
          assignment_count: 0,
          llm_config: {},
        },
      },
      startExperimentSession,
      clearExperimentSession,
    } as any);

    render(<StoryConclusion />);

    fireEvent.click(await screen.findByRole('button', { name: /Return to Start/i }));

    expect(startExperimentSession).not.toHaveBeenCalled();
    expect(clearExperimentSession).toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith('/');
  });

  it('holds on the conclusion page while benchmark history is still hydrating', async () => {
    const pendingPromise = new Promise(() => {});
    mockedAxios.get.mockImplementation((url: string) => {
      if (url.includes('/experiments/sessions/session-1') && !url.includes('/export')) {
        return pendingPromise as never;
      }
      return Promise.resolve({ data: {} }) as never;
    });

    const baseContext = mockedUseStory();
    mockedUseStory.mockReturnValue({
      ...baseContext,
      story: null,
      storyId: null,
      experimentMode: true,
      experimentSession: {
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
      },
    } as any);

    render(<StoryConclusion />);

    expect(await screen.findByText(/Preparing conclusion/i)).toBeInTheDocument();
    expect(screen.getByText(/completed story snapshot is still loading/i)).toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('uses local browser cache to replace the page with a single previous blind round', async () => {
    const blindHistory = {
      session: {
        session_id: 'session-1',
        participant_id: 'blind-03',
        mode: 'benchmark',
        started_at: '2026-04-04T00:00:00Z',
        selected_model: null,
        blind_mode: true,
        blind_code: 3,
        blind_invite_code: 'LY7H-H8W8',
        blind_session_index: 2,
        blind_total_sessions: 4,
        blind_completed_count: 1,
        blind_remaining_count: 3,
        blind_finished: false,
        condition: {
          id: 'baseline',
          name: 'Baseline',
          description: 'Baseline condition',
          active: true,
          assignment_count: 0,
          llm_config: {},
        },
      },
      dialogue_source: 'saved_dialogue',
      dialogue: [
        { id: 'd1', speaker: 'You', role: 'user', content: 'I feel stuck.' },
        { id: 'd2', speaker: 'Guide', role: 'assistant', content: 'We can take one concrete step at a time.' },
      ],
      turn_logs: [],
      feedback_logs: [],
      story_events: [],
      llm_call_logs: [],
      template_mode: false,
    };

    const previousDetail = {
      session: {
        ...blindHistory.session,
        session_id: 'session-0',
        blind_session_index: 1,
      },
      dialogue_source: 'saved_dialogue',
      dialogue: [
        { id: 'prior-1', speaker: 'You', role: 'user', content: 'First round input.' },
        { id: 'prior-2', speaker: 'Guide', role: 'assistant', content: 'First round response.' },
      ],
      feedback_logs: [
        {
          id: 'feedback-prior',
          session_id: 'session-0',
          feedback_type: 'benchmark_session_end',
          rating: 2,
          comment: 'Initial score.',
          form_version: 'benchmark_emotional_human_v1',
          created_at: '2026-04-04T00:05:00Z',
        },
      ],
      turn_logs: [],
      story_events: [],
      llm_call_logs: [],
      final_view_story: {
        id: 'story-0',
        title: 'Earlier Round',
      },
      template_mode: false,
    } as any;

    upsertLocalBenchmarkReviewDetail(previousDetail);

    mockedAxios.get.mockImplementation((url: string) => {
      if (url.includes('/blind-review')) {
        return Promise.reject(new Error(`Unexpected blind-review GET ${url}`)) as never;
      }
      if (url.includes('/experiments/sessions/session-1') && !url.includes('/export')) {
        return Promise.resolve({ data: blindHistory }) as never;
      }
      if (url.includes('/export')) {
        return Promise.resolve({ data: { schema_version: 'benchmark_result_v1', export_type: 'benchmark_result' } }) as never;
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`)) as never;
    });

    const baseContext = mockedUseStory();
    mockedUseStory.mockReturnValue({
      ...baseContext,
      story: {
        ...(baseContext as any).story,
        benchmarkHistory: null,
      } as any,
      experimentMode: true,
      experimentSession: blindHistory.session,
    } as any);

    render(<StoryConclusion />);

    expect(await screen.findByText(/Previous round ratings are available from this browser/i)).toBeInTheDocument();
    expect(screen.queryByText(/Cross-Round Re-Review/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Story Analysis/i)).not.toBeInTheDocument();
    expect(mockedAxios.get).not.toHaveBeenCalledWith(expect.stringContaining('/blind-review'));

    fireEvent.click(screen.getByRole('button', { name: /Previous Rating/i }));

    expect(screen.queryByText(/^Previous Round Rating$/i)).not.toBeInTheDocument();
    expect(loadHistoricalStory).toHaveBeenCalledWith(expect.objectContaining({
      benchmark_history: expect.objectContaining({
        session: expect.objectContaining({ session_id: 'session-0' }),
      }),
    }));
    expect(mockNavigate).toHaveBeenCalledWith('/conclusion');
    expect(JSON.parse(window.sessionStorage.getItem('emonest:previous-rating-return-target:v1') || '{}')).toEqual(
      expect.objectContaining({
        session: expect.objectContaining({ session_id: 'session-1' }),
      }),
    );
  });

  it('shows a dropdown when multiple previous ratings are cached and opens the selected round', async () => {
    const currentSession = {
      participant_id: 'blind-03',
      session_id: 'session-3',
      mode: 'benchmark',
      started_at: '2026-04-04T00:30:00Z',
      selected_model: null,
      blind_mode: true,
      blind_code: 3,
      blind_invite_code: 'LY7H-H8W8',
      blind_session_index: 3,
      blind_total_sessions: 4,
      blind_completed_count: 2,
      blind_remaining_count: 2,
      blind_finished: false,
      condition: {
        id: 'baseline',
        name: 'Baseline',
        description: 'Baseline condition',
        active: true,
        assignment_count: 0,
        llm_config: {},
      },
    };
    const previousOne = {
      session: {
        ...currentSession,
        session_id: 'session-1',
        blind_session_index: 1,
        started_at: '2026-04-04T00:00:00Z',
      },
      dialogue_source: 'saved_dialogue',
      dialogue: [{ id: 'p1', speaker: 'Guide', role: 'assistant', content: 'Oldest response.' }],
      feedback_logs: [{ id: 'f1', session_id: 'session-1', feedback_type: 'benchmark_session_end', rating: 2 }],
      turn_logs: [],
      story_events: [],
      llm_call_logs: [],
      final_view_story: { id: 'story-1', title: 'Oldest Round' },
      template_mode: false,
    } as any;
    const previousTwo = {
      session: {
        ...currentSession,
        session_id: 'session-2',
        blind_session_index: 2,
        started_at: '2026-04-04T00:15:00Z',
      },
      dialogue_source: 'saved_dialogue',
      dialogue: [{ id: 'p2', speaker: 'Guide', role: 'assistant', content: 'Second response.' }],
      feedback_logs: [{ id: 'f2', session_id: 'session-2', feedback_type: 'benchmark_session_end', rating: 5 }],
      turn_logs: [],
      story_events: [],
      llm_call_logs: [],
      final_view_story: { id: 'story-2', title: 'Second Round' },
      template_mode: false,
    } as any;
    upsertLocalBenchmarkReviewDetail(previousOne);
    upsertLocalBenchmarkReviewDetail(previousTwo);

    mockedAxios.get.mockImplementation((url: string) => {
      if (url.includes('/experiments/sessions/session-3') && !url.includes('/export')) {
        return Promise.resolve({
          data: {
            session: currentSession,
            dialogue_source: 'saved_dialogue',
            dialogue: [],
            turn_logs: [],
            feedback_logs: [],
            story_events: [],
            llm_call_logs: [],
            template_mode: false,
          },
        }) as never;
      }
      return Promise.resolve({ data: {} }) as never;
    });

    const baseContext = mockedUseStory();
    mockedUseStory.mockReturnValue({
      ...baseContext,
      story: {
        ...(baseContext as any).story,
        benchmarkHistory: null,
      } as any,
      experimentMode: true,
      experimentSession: currentSession,
    } as any);

    render(<StoryConclusion />);

    fireEvent.click(await screen.findByRole('button', { name: /Previous Rating/i }));
    expect(await screen.findByText(/Blind round 2\/4 \| score 5\/5 \| Second Round/i)).toBeInTheDocument();

    fireEvent.click(screen.getByText(/Blind round 1\/4 \| score 2\/5 \| Oldest Round/i));

    expect(loadHistoricalStory).toHaveBeenCalledWith(expect.objectContaining({
      benchmark_history: expect.objectContaining({
        session: expect.objectContaining({ session_id: 'session-1' }),
      }),
    }));
    expect(mockNavigate).toHaveBeenCalledWith('/conclusion');
  });

  it('returns from a previous rating page to the just-finished current round', async () => {
    const currentDetail = {
      session: {
        participant_id: 'blind-03',
        session_id: 'session-2',
        mode: 'benchmark',
        started_at: '2026-04-04T00:20:00Z',
        selected_model: null,
        blind_mode: true,
        blind_code: 3,
        blind_invite_code: 'LY7H-H8W8',
        blind_session_index: 2,
        blind_total_sessions: 4,
        blind_completed_count: 1,
        blind_remaining_count: 3,
        blind_finished: false,
        condition: {
          id: 'baseline',
          name: 'Baseline',
          description: 'Baseline condition',
          active: true,
          assignment_count: 0,
          llm_config: {},
        },
      },
      dialogue_source: 'saved_dialogue',
      dialogue: [{ id: 'current-d1', speaker: 'Guide', role: 'assistant', content: 'Current response.' }],
      feedback_logs: [],
      turn_logs: [],
      story_events: [],
      llm_call_logs: [],
      final_view_story: { id: 'story-2', title: 'Current Round' },
      template_mode: false,
    } as any;
    const previousDetail = {
      session: {
        ...currentDetail.session,
        session_id: 'session-1',
        blind_session_index: 1,
        started_at: '2026-04-04T00:00:00Z',
      },
      dialogue_source: 'saved_dialogue',
      dialogue: [{ id: 'previous-d1', speaker: 'Guide', role: 'assistant', content: 'Previous response.' }],
      feedback_logs: [{ id: 'previous-feedback', session_id: 'session-1', feedback_type: 'benchmark_session_end', rating: 2 }],
      turn_logs: [],
      story_events: [],
      llm_call_logs: [],
      final_view_story: { id: 'story-1', title: 'Previous Round' },
      template_mode: false,
    } as any;
    window.sessionStorage.setItem('emonest:previous-rating-return-target:v1', JSON.stringify(currentDetail));

    const previousStory = buildReplayStoryFromDetail(previousDetail);
    const baseContext = mockedUseStory();
    mockedUseStory.mockReturnValue({
      ...baseContext,
      story: {
        ...(baseContext as any).story,
        id: 'story-1',
        title: 'Previous Round',
        benchmarkHistory: previousDetail,
      } as any,
      experimentMode: true,
      experimentSession: currentDetail.session,
    } as any);

    render(<StoryConclusion />);

    expect(await screen.findByRole('button', { name: /Return to Current Round/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Start Next Test Story/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Begin a New Journey/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Mock Save session-1/i }));

    await waitFor(() => {
      const updatedPrevious = readLocalBenchmarkReviewHistory(previousDetail.session)
        .find(detail => detail.session.session_id === 'session-1');
      expect(getLatestRating(updatedPrevious)).toBe(4);
    });

    fireEvent.click(screen.getByRole('button', { name: /Return to Current Round/i }));

    expect(loadHistoricalStory).toHaveBeenCalledWith(expect.objectContaining({
      benchmark_history: expect.objectContaining({
        session: expect.objectContaining({ session_id: 'session-2' }),
      }),
    }));
    expect(loadHistoricalStory).not.toHaveBeenCalledWith(previousStory);
    expect(mockNavigate).toHaveBeenCalledWith('/conclusion');
    expect(window.sessionStorage.getItem('emonest:previous-rating-return-target:v1')).toBeNull();
    expect(window.sessionStorage.getItem('emonest:previous-rating-restored-session:v1')).toBe('session-2');
  });

  it('does not call the removed blind review endpoint when no local previous round exists', async () => {
    const blindHistory = {
      session: {
        session_id: 'session-1',
        participant_id: 'blind-03',
        mode: 'benchmark',
        started_at: '2026-04-04T00:00:00Z',
        selected_model: null,
        blind_mode: true,
        blind_code: 3,
        blind_invite_code: 'LY7H-H8W8',
        blind_session_index: 2,
        blind_total_sessions: 4,
        blind_completed_count: 1,
        blind_remaining_count: 3,
        blind_finished: false,
        condition: {
          id: 'baseline',
          name: 'Baseline',
          description: 'Baseline condition',
          active: true,
          assignment_count: 0,
          llm_config: {},
        },
      },
      dialogue_source: 'saved_dialogue',
      dialogue: [],
      turn_logs: [],
      feedback_logs: [],
      story_events: [],
      llm_call_logs: [],
      template_mode: false,
    };

    mockedAxios.get.mockImplementation((url: string) => {
      if (url.includes('/blind-review')) {
        return Promise.reject(new Error('blind review should not be called')) as never;
      }
      if (url.includes('/experiments/sessions/session-1') && !url.includes('/export')) {
        return Promise.resolve({ data: blindHistory }) as never;
      }
      return Promise.resolve({ data: {} }) as never;
    });

    const baseContext = mockedUseStory();
    mockedUseStory.mockReturnValue({
      ...baseContext,
      story: {
        ...(baseContext as any).story,
        benchmarkHistory: null,
      } as any,
      experimentMode: true,
      experimentSession: blindHistory.session,
    } as any);

    render(<StoryConclusion />);

    expect(await screen.findByText(/Previous round review will appear here/i)).toBeInTheDocument();
    expect(screen.queryByText(/Failed to load prior blind rounds/i)).not.toBeInTheDocument();
    expect(mockedAxios.get).not.toHaveBeenCalledWith(expect.stringContaining('/blind-review'));
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
