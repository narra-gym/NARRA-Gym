import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import BenchmarkSessionHistoryDialog from './BenchmarkSessionHistoryDialog';
import { useStory } from '../contexts/StoryContext';
import { downloadJsonFile } from '../utils/benchmarkHistory';

jest.mock('axios');

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

const mockedAxios = axios as jest.Mocked<typeof axios>;
const mockedUseStory = useStory as jest.MockedFunction<typeof useStory>;
const mockedDownloadJsonFile = downloadJsonFile as jest.MockedFunction<typeof downloadJsonFile>;

describe('BenchmarkSessionHistoryDialog', () => {
  beforeEach(() => {
    mockNavigate.mockReset();
    mockedAxios.get.mockReset();
    mockedDownloadJsonFile.mockReset();
    mockedUseStory.mockReturnValue({
      loadHistoricalStory: jest.fn(),
    } as any);
  });

  it('hides blind session model labels and exports through the backend export endpoint', async () => {
    mockedAxios.get.mockImplementation((url: string) => {
      if (url.endsWith('/experiments/sessions/session-3')) {
        return Promise.resolve({
          data: {
            session: {
              session_id: 'session-3',
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
            dialogue_source: 'turn_logs',
            dialogue: [
              { id: 'd1', speaker: 'You', role: 'user', content: 'I feel stuck.' },
            ],
            turn_logs: [],
            feedback_logs: [],
          },
        });
      }
      if (url.endsWith('/experiments/sessions/session-3/export')) {
        return Promise.resolve({
          data: {
            schema_version: 'benchmark_result_v1',
            export_type: 'benchmark_result',
            session: {
              session_id: 'session-3',
              selected_model: 'openai/gpt-5.4',
            },
          },
        });
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`));
    });

    render(<BenchmarkSessionHistoryDialog open sessionId="session-3" onClose={jest.fn()} />);

    expect(await screen.findByText(/Invite code: LY7H-H8W8/i)).toBeInTheDocument();
    expect(screen.queryByText(/Model:/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Export Result JSON/i }));

    await waitFor(() => {
      expect(mockedAxios.get).toHaveBeenCalledWith('http://localhost:11454/experiments/sessions/session-3/export');
      expect(mockedDownloadJsonFile).toHaveBeenCalledWith(
        'session-3_benchmark_result.json',
        expect.objectContaining({
          schema_version: 'benchmark_result_v1',
          export_type: 'benchmark_result',
        }),
      );
    });
  });
});
