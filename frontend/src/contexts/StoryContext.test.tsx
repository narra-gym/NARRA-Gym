import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import { StoryProvider, useStory } from './StoryContext';

jest.mock('axios');

const mockedAxios = axios as jest.Mocked<typeof axios>;
const EXPERIMENT_STORAGE_KEY = 'emonest-experiment-session';

const baselineCondition = {
  id: 'baseline',
  name: 'Baseline',
  description: 'Baseline condition',
  active: true,
  assignment_count: 0,
  llm_config: {},
};

const persistedBlindSession = {
  participant_id: 'blind-01',
  session_id: 'session-stale',
  mode: 'benchmark',
  started_at: '2026-04-24T00:00:00Z',
  selected_model: null,
  blind_mode: true,
  blind_code: 1,
  blind_invite_code: 'JUMF-TVDL',
  blind_session_index: 2,
  blind_total_sessions: 4,
  blind_completed_count: 1,
  blind_remaining_count: 3,
  blind_finished: false,
  condition: baselineCondition,
};

const StoryProbe = () => {
  const { experimentSession, userId } = useStory();

  return (
    <div>
      <div data-testid="user-id">{userId}</div>
      <div data-testid="session-state">
        {experimentSession ? JSON.stringify(experimentSession) : 'none'}
      </div>
    </div>
  );
};

describe('StoryProvider persisted experiment session hydration', () => {
  beforeEach(() => {
    mockedAxios.get.mockReset();
    mockedAxios.isAxiosError = jest.fn((error: unknown) => Boolean((error as { isAxiosError?: boolean })?.isAxiosError));
    window.localStorage.clear();
  });

  it('clears a persisted experiment session when the backend no longer has it', async () => {
    window.localStorage.setItem(EXPERIMENT_STORAGE_KEY, JSON.stringify(persistedBlindSession));
    mockedAxios.get.mockRejectedValue({
      isAxiosError: true,
      response: { status: 404 },
    });

    render(
      <StoryProvider>
        <StoryProbe />
      </StoryProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('session-state')).toHaveTextContent('none');
    });

    expect(screen.getByTestId('user-id')).toHaveTextContent('user-1');
    expect(window.localStorage.getItem(EXPERIMENT_STORAGE_KEY)).toBeNull();
    expect(mockedAxios.get).toHaveBeenCalledWith(expect.stringContaining('/experiments/sessions/session-stale'));
  });

  it('refreshes the persisted experiment session with the backend copy when it still exists', async () => {
    window.localStorage.setItem(EXPERIMENT_STORAGE_KEY, JSON.stringify(persistedBlindSession));
    mockedAxios.get.mockResolvedValue({
      data: {
        session: {
          ...persistedBlindSession,
          blind_session_index: 1,
          blind_completed_count: 0,
          blind_remaining_count: 4,
        },
      },
    });

    render(
      <StoryProvider>
        <StoryProbe />
      </StoryProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('session-state')).toHaveTextContent('"blind_completed_count":0');
    });

    expect(screen.getByTestId('session-state')).toHaveTextContent('"blind_session_index":1');
    expect(screen.getByTestId('user-id')).toHaveTextContent('blind-01');
    expect(JSON.parse(window.localStorage.getItem(EXPERIMENT_STORAGE_KEY) || '{}')).toMatchObject({
      blind_session_index: 1,
      blind_completed_count: 0,
      blind_remaining_count: 4,
    });
  });
});
