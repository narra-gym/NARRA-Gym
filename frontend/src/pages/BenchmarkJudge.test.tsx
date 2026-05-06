import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import BenchmarkJudgePage from './BenchmarkJudge';

jest.mock('axios');
jest.mock('../components/ShaderBackground', () => () => <div data-testid="shader-background" />);

const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('BenchmarkJudgePage', () => {
  let consoleErrorSpy: jest.SpyInstance;

  beforeEach(() => {
    mockedAxios.get.mockReset();
    mockedAxios.post.mockReset();
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it('uploads a valid benchmark json and renders judge results', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: [
        {
          id: 'doubao/seed-2.0-pro',
          label: 'Doubao Seed 2.0 Pro (Official)',
          description: 'Judge model',
          provider: 'doubao',
          available: false,
          availability_reason: 'Doubao is unavailable in this environment.',
        },
        {
          id: 'openai/gpt-5.4',
          label: 'OpenAI GPT-5.4',
          description: 'Judge model',
          provider: 'openrouter',
          available: true,
        },
      ],
    });
    mockedAxios.post.mockResolvedValueOnce({
      data: {
        input_summary: {
          session_id: 'session-1',
          story_id: 'story-1',
          participant_id: 'participant-1',
          selected_model: 'openai/gpt-5.4',
          dialogue_count: 2,
          output_message_count: 1,
          turn_log_count: 0,
          llm_call_count: 0,
          feedback_count: 0,
          content_source: 'current_scene',
          story_title: 'Late Night',
          total_output_tokens: 12,
        },
        judge_scores: {
          overall_rating: 4,
          emotional_alignment: 5,
          narrative_coherence: 4,
          supportiveness: 5,
        },
        judge_summary: {
          summary: 'Strong supportive pacing with decent coherence.',
          strengths: ['Strong tone match', 'Clear progression'],
          issues: ['Could use more specificity'],
        },
        slop_stats: {
          slop_score: 31.5,
          interpretation: 'Moderate slop.',
          total_output_messages: 1,
          total_output_tokens: 12,
          gptism_hit_rate: 0.01,
          repeated_bigram_ratio: 0.02,
          repeated_trigram_ratio: 0.01,
          high_frequency_term_ratio: 0.25,
          repeated_sentence_prefix_ratio: 0.1,
          top_repeated_terms: [{ term: 'steady', count: 2 }],
          gptism_hits: { 'soft-gentle': 1 },
        },
      },
    });

    render(
      <MemoryRouter>
        <BenchmarkJudgePage />
      </MemoryRouter>,
    );

    await screen.findByText('OpenAI GPT-5.4');
    expect(screen.getByText('Doubao is unavailable in this environment.')).toBeInTheDocument();

    const file = new File(
      [
        JSON.stringify({
          session: {
            session_id: 'session-1',
            participant_id: 'participant-1',
            selected_model: 'openai/gpt-5.4',
          },
          story: {
            id: 'story-1',
            title: 'Late Night',
          },
          dialogue_source: 'current_scene',
          dialogue: [
            { id: 'd1', speaker: 'User', role: 'user', content: 'I feel stuck.' },
            { id: 'd2', speaker: 'Guide', role: 'assistant', content: 'We can move one concrete step at a time.' },
          ],
          turn_logs: [],
          feedback_logs: [],
          llm_call_logs: [],
        }),
      ],
      'benchmark.json',
      { type: 'application/json' },
    );
    Object.defineProperty(file, 'text', {
      value: () => Promise.resolve(JSON.stringify({
        session: {
          session_id: 'session-1',
          participant_id: 'participant-1',
          selected_model: 'openai/gpt-5.4',
        },
        story: {
          id: 'story-1',
          title: 'Late Night',
        },
        dialogue_source: 'current_scene',
        dialogue: [
          { id: 'd1', speaker: 'User', role: 'user', content: 'I feel stuck.' },
          { id: 'd2', speaker: 'Guide', role: 'assistant', content: 'We can move one concrete step at a time.' },
        ],
        turn_logs: [],
        feedback_logs: [],
        llm_call_logs: [],
      })),
    });

    fireEvent.change(screen.getByTestId('benchmark-judge-file-input'), {
      target: { files: [file] },
    });

    await screen.findByText(/Session: session-1/i);
    expect(screen.getByText(/Story: Late Night/i)).toBeInTheDocument();
    expect(screen.getByText(/Judge model: OpenAI GPT-5\.4/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /run judge/i }));

    await screen.findByText(/Strong supportive pacing with decent coherence\./i);
    expect(screen.getByText(/31.50 \/ 100/i)).toBeInTheDocument();
    expect(mockedAxios.post).toHaveBeenCalledWith(
      expect.stringContaining('/experiments/judge'),
      expect.objectContaining({
        selected_model: 'openai/gpt-5.4',
      }),
    );
  });

  it('shows an error for invalid benchmark json', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: [{ id: 'openai/gpt-5.4', label: 'OpenAI GPT-5.4', provider: 'openrouter', available: true }],
    });

    render(
      <MemoryRouter>
        <BenchmarkJudgePage />
      </MemoryRouter>,
    );

    await screen.findByText('OpenAI GPT-5.4');

    const invalidFile = new File(['{bad-json'], 'broken.json', { type: 'application/json' });
    Object.defineProperty(invalidFile, 'text', {
      value: () => Promise.resolve('{bad-json'),
    });
    fireEvent.change(screen.getByTestId('benchmark-judge-file-input'), {
      target: { files: [invalidFile] },
    });

    await waitFor(() => {
      expect(screen.getByText(/Failed to parse benchmark JSON/i)).toBeInTheDocument();
    });
    expect(mockedAxios.post).not.toHaveBeenCalled();
  });
});
