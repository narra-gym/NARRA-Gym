import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Container,
  Divider,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import axios from 'axios';
import ShaderBackground from '../components/ShaderBackground';
import BenchmarkSessionHistoryDialog from '../components/BenchmarkSessionHistoryDialog';
import { API_BASE_URL, useStory } from '../contexts/StoryContext';
import { benchmarkTemplateDetail } from '../data/benchmarkTemplate';
import {
  BenchmarkModelOption,
  BenchmarkSessionDetail,
  BenchmarkSessionSummary,
  ExperimentConfig,
} from '../types';
import { buildReplayStoryFromDetail } from '../utils/benchmarkHistory';

const panelSx = {
  borderRadius: 4,
  background: 'rgba(255,248,240,0.9)',
  backdropFilter: 'blur(18px)',
  border: '1px solid rgba(255,255,255,0.42)',
  boxShadow: '0 24px 64px rgba(15,23,42,0.16)',
};

const headingColor = '#1f2937';
const bodyColor = 'rgba(31,41,55,0.82)';
const metaColor = 'rgba(51,65,85,0.82)';
const mutedColor = 'rgba(71,85,105,0.92)';

const ExperimentMode: React.FC = () => {
  const buildTimeBlindBenchmarkMode = process.env.REACT_APP_BENCHMARK_RANDOM_MODE === '1';
  const navigate = useNavigate();
  const { experimentSession, startExperimentSession, clearExperimentSession, loadHistoricalStory } = useStory();
  const [blindBenchmarkMode, setBlindBenchmarkMode] = useState(buildTimeBlindBenchmarkMode);
  const [models, setModels] = useState<BenchmarkModelOption[]>([]);
  const [sessions, setSessions] = useState<BenchmarkSessionSummary[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [blindAccessCode, setBlindAccessCode] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [loadingHistorySessionId, setLoadingHistorySessionId] = useState<string | null>(null);
  const [configLoading, setConfigLoading] = useState(true);
  const [modelsLoading, setModelsLoading] = useState(!blindBenchmarkMode);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [historySessionId, setHistorySessionId] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);

  useEffect(() => {
    let mounted = true;

    const fetchExperimentConfig = async () => {
      setConfigLoading(true);
      try {
        const response = await axios.get(`${API_BASE_URL}/experiments/config`);
        if (!mounted) {
          return;
        }
        const config = response.data as ExperimentConfig;
        setBlindBenchmarkMode(Boolean(config.blind_benchmark_mode_enabled));
      } catch (err) {
        console.error(err);
        if (mounted) {
          setBlindBenchmarkMode(buildTimeBlindBenchmarkMode);
        }
      } finally {
        if (mounted) {
          setConfigLoading(false);
        }
      }
    };

    fetchExperimentConfig();

    return () => {
      mounted = false;
    };
  }, [buildTimeBlindBenchmarkMode]);

  useEffect(() => {
    if (configLoading) {
      return;
    }

    let mounted = true;

    const fetchPageData = async () => {
      if (blindBenchmarkMode) {
        if (!mounted) {
          return;
        }
        setModels([]);
        setSessions([]);
        setModelsLoading(false);
        setHistoryLoading(false);

        if (experimentSession?.blind_mode) {
          if (experimentSession.quick_test_mode) {
            setBlindAccessCode('0');
          } else if (experimentSession.blind_invite_code) {
            setBlindAccessCode(experimentSession.blind_invite_code);
          } else if (experimentSession.blind_code !== undefined && experimentSession.blind_code !== null) {
            setBlindAccessCode(String(experimentSession.blind_code));
          }
        }
        return;
      }

      if (!blindBenchmarkMode) {
        setModelsLoading(true);
      }
      setHistoryLoading(true);
      try {
        const requests = [
          axios.get(`${API_BASE_URL}/experiments/sessions`, {
            params: { mode: 'benchmark', limit: 50 },
          }),
        ];
        if (!blindBenchmarkMode) {
          requests.unshift(axios.get(`${API_BASE_URL}/experiments/models`));
        }
        const responses = await Promise.all(requests);

        if (!mounted) {
          return;
        }

        const fetchedModels = !blindBenchmarkMode
          ? (responses[0].data as BenchmarkModelOption[])
          : [];
        const fetchedSessions = !blindBenchmarkMode
          ? (responses[1].data as BenchmarkSessionSummary[])
          : (responses[0].data as BenchmarkSessionSummary[]);
        setModels(fetchedModels);
        setSessions(fetchedSessions);

        if (experimentSession?.blind_mode) {
          if (experimentSession.quick_test_mode) {
            setBlindAccessCode('0');
          } else if (experimentSession.blind_invite_code) {
            setBlindAccessCode(experimentSession.blind_invite_code);
          } else if (experimentSession.blind_code !== undefined && experimentSession.blind_code !== null) {
            setBlindAccessCode(String(experimentSession.blind_code));
          }
        }
        if (!blindBenchmarkMode && experimentSession?.selected_model) {
          setSelectedModel(experimentSession.selected_model);
        }
      } catch (err) {
        console.error(err);
        if (mounted) {
          setError('Failed to load benchmark configuration or history. Please try again.');
        }
      } finally {
        if (mounted) {
          if (!blindBenchmarkMode) {
            setModelsLoading(false);
          }
          setHistoryLoading(false);
        }
      }
    };

    fetchPageData();

    return () => {
      mounted = false;
    };
  }, [blindBenchmarkMode, configLoading, experimentSession]);

  useEffect(() => {
    if (blindBenchmarkMode) {
      return;
    }
    if (!models.length) {
      return;
    }
    const availableModels = models.filter(model => model.available !== false);
    if (!availableModels.length) {
      setSelectedModel('');
      return;
    }
    if (!selectedModel || models.find(model => model.id === selectedModel)?.available === false) {
      setSelectedModel(availableModels[0].id);
    }
  }, [blindBenchmarkMode, models, selectedModel]);

  const activeModelLabel = useMemo(() => {
    if (blindBenchmarkMode) {
      return '';
    }
    const matchedModel = models.find(model => model.id === experimentSession?.selected_model);
    return matchedModel?.label || experimentSession?.selected_model || '';
  }, [blindBenchmarkMode, experimentSession, models]);

  const activeBlindCode = useMemo(() => {
    if (!experimentSession?.blind_mode) {
      return null;
    }
    return experimentSession.blind_code ?? null;
  }, [experimentSession]);

  const activeBlindInviteCode = useMemo(() => {
    if (!experimentSession?.blind_mode || experimentSession.quick_test_mode) {
      return null;
    }
    return experimentSession.blind_invite_code ?? null;
  }, [experimentSession]);

  const handleStart = async () => {
    if (blindBenchmarkMode) {
      const normalizedBlindAccessCode = blindAccessCode.trim().toUpperCase();
      if (!normalizedBlindAccessCode) {
        setError('Please enter your invite code. Use 0 for quick test.');
        return;
      }
    } else {
      if (!selectedModel) {
        setError('Please choose a benchmark model before starting.');
        return;
      }
      const selectedModelOption = models.find(model => model.id === selectedModel);
      if (selectedModelOption?.available === false) {
        setError(selectedModelOption.availability_reason || 'This benchmark model is not configured yet.');
        return;
      }
    }

    setLoading(true);
    setError(null);
    try {
      if (blindBenchmarkMode) {
        await startExperimentSession(null, undefined, blindAccessCode.trim().toUpperCase());
      } else {
        await startExperimentSession(selectedModel);
      }
      navigate('/start');
    } catch (err) {
      console.error(err);
      if (axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string') {
        setError(err.response.data.detail);
      } else {
        setError('Failed to start benchmark session. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  const openHistory = (sessionId: string) => {
    setHistorySessionId(sessionId);
    setHistoryOpen(true);
  };

  const handleLoadHistory = async (sessionId: string) => {
    setLoadingHistorySessionId(sessionId);
    setError(null);
    try {
      const response = await axios.get(`${API_BASE_URL}/experiments/sessions/${sessionId}`);
      const detail = response.data as BenchmarkSessionDetail;
      loadHistoricalStory(buildReplayStoryFromDetail(detail));
      navigate('/conclusion');
    } catch (err) {
      console.error(err);
      setError('Failed to load the historical benchmark conclusion view. Please try again.');
    } finally {
      setLoadingHistorySessionId(null);
    }
  };

  const handleLoadTemplate = () => {
    loadHistoricalStory(buildReplayStoryFromDetail(benchmarkTemplateDetail));
    navigate('/conclusion');
  };

  return (
    <Box sx={{ position: 'fixed', inset: 0, overflow: 'auto' }}>
      <Box sx={{ position: 'absolute', inset: 0, zIndex: 0 }}>
        <ShaderBackground />
        <Box sx={{ position: 'absolute', inset: 0, backgroundColor: 'rgba(0,0,0,0.58)' }} />
      </Box>

      <Container maxWidth="lg" sx={{ mt: 10, mb: 8, position: 'relative', zIndex: 1 }}>
        <Stack spacing={3}>
          <Paper
            sx={{
              p: { xs: 3, sm: 5 },
              ...panelSx,
            }}
          >
            <Typography variant="h4" align="center" sx={{ color: headingColor, fontWeight: 700, mb: 1 }}>
              NARRA-Gym Benchmark Mode
            </Typography>
            <Typography align="center" sx={{ color: bodyColor, mb: 3, lineHeight: 1.8 }}>
              {blindBenchmarkMode
                ? 'Enter your invite code to start or resume a blind benchmark run. Enter 0 for a quick test lane that auto-loads a default world and rotates through hidden model slots.'
                : 'Choose a single model for the full benchmark run. You can also load prior benchmark data below and inspect the saved dialogue history turn by turn.'}
            </Typography>

            {experimentSession && (
              <Alert severity="info" sx={{ mb: 3 }}>
                {experimentSession.blind_mode
                  ? experimentSession.quick_test_mode
                    ? `Quick test code: ${activeBlindCode ?? 0} | Hidden slot ${experimentSession.blind_session_index || 1}/${experimentSession.blind_total_sessions || 4} | Completed runs: ${experimentSession.quick_test_completed_runs || 0}${experimentSession.blind_finished ? ' | Sequence complete' : ''}${experimentSession.condition?.name ? ` | Condition: ${experimentSession.condition.name}` : ''}`
                    : `Active invite code: ${activeBlindInviteCode ?? activeBlindCode ?? 'unknown'} | Round ${experimentSession.blind_session_index || 1}/${experimentSession.blind_total_sessions || 4} | Completed: ${experimentSession.blind_completed_count || 0} | Remaining: ${experimentSession.blind_remaining_count || 0}${experimentSession.condition?.name ? ` | Condition: ${experimentSession.condition.name}` : ''}`
                  : `Active participant: ${experimentSession.participant_id} | Model: ${activeModelLabel} | Condition: ${experimentSession.condition.name}`}
              </Alert>
            )}

            {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}

            {blindBenchmarkMode ? (
              <Box sx={{ mb: 4 }}>
                <Typography variant="h6" sx={{ color: headingColor, fontWeight: 600, mb: 1.5 }}>
                  Invite Code
                </Typography>
                <TextField
                  label="Invite Code"
                  value={blindAccessCode}
                  onChange={(event) => setBlindAccessCode(event.target.value.toUpperCase())}
                  fullWidth
                  helperText="Enter your issued invite code for formal blind runs. Enter 0 for a quick test world that skips straight to a default endgame-ready story."
                />
              </Box>
            ) : (
              <>
                <Typography variant="h6" sx={{ color: headingColor, fontWeight: 600, mb: 1.5 }}>
                  Select Model
                </Typography>

                {modelsLoading ? (
                  <Box sx={{ display: 'flex', justifyContent: 'center', py: 5 }}>
                    <CircularProgress />
                  </Box>
                ) : (
                  <Stack spacing={1.5} sx={{ mb: 4 }}>
                    {models.map(model => {
                      const active = selectedModel === model.id;
                      const disabled = model.available === false;
                      return (
                        <Paper
                          key={model.id}
                          onClick={() => !disabled && setSelectedModel(model.id)}
                          sx={{
                            p: 2,
                            borderRadius: 3,
                            cursor: disabled ? 'not-allowed' : 'pointer',
                            border: active
                              ? '2px solid rgba(96,139,119,0.95)'
                              : '1px solid rgba(148,163,184,0.28)',
                            background: disabled
                              ? 'rgba(226,232,240,0.5)'
                              : active
                                ? 'rgba(224,240,233,0.96)'
                                : 'rgba(255,255,255,0.78)',
                            color: disabled ? 'rgba(100,116,139,0.95)' : active ? '#21483f' : headingColor,
                            opacity: disabled ? 0.72 : 1,
                            transition: 'all 0.2s ease',
                            '&:hover': {
                              transform: disabled ? 'none' : 'translateY(-1px)',
                              borderColor: disabled ? 'rgba(148,163,184,0.28)' : 'rgba(96,139,119,0.55)',
                              background: disabled
                                ? 'rgba(226,232,240,0.5)'
                                : active
                                  ? 'rgba(224,240,233,0.98)'
                                  : 'rgba(255,255,255,0.9)',
                            },
                          }}
                        >
                          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                            {model.label}
                          </Typography>
                          <Typography variant="body2" sx={{ opacity: 0.88, mt: 0.5 }}>
                            {model.description || model.id}
                          </Typography>
                          <Typography variant="caption" sx={{ display: 'block', mt: 0.75, color: mutedColor }}>
                            Provider: {model.provider || 'default'}
                          </Typography>
                          {disabled && (
                            <Alert severity="warning" sx={{ mt: 1.25 }}>
                              {model.availability_reason || 'This model is not configured in the current environment.'}
                            </Alert>
                          )}
                        </Paper>
                      );
                    })}
                  </Stack>
                )}
              </>
            )}

            <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center', flexWrap: 'wrap' }}>
              <Button
                variant="contained"
                onClick={handleStart}
                disabled={
                  configLoading ||
                  loading ||
                  (!blindBenchmarkMode && (modelsLoading || !selectedModel || models.every(model => model.available === false))) ||
                  (blindBenchmarkMode && !blindAccessCode.trim())
                }
              >
                {loading ? (
                  <CircularProgress size={22} color="inherit" />
                ) : experimentSession ? (
                  blindBenchmarkMode ? 'Resume Blind Benchmark Session' : 'Restart Benchmark Session'
                ) : (
                  blindBenchmarkMode ? 'Start Blind Benchmark Session' : 'Start Benchmark Session'
                )}
              </Button>
              <Button variant="outlined" onClick={handleLoadTemplate} disabled={loading}>
                Load Benchmark Template
              </Button>
              <Button variant="outlined" onClick={() => navigate('/experiment/judge')} disabled={loading}>
                LLM Judge
              </Button>
              {experimentSession && (
                <Button variant="outlined" onClick={clearExperimentSession} disabled={loading}>
                  Clear Session
                </Button>
              )}
              <Button variant="text" onClick={() => navigate('/')}>
                Back Home
              </Button>
            </Box>
          </Paper>

          <Paper
            sx={{
              p: { xs: 3, sm: 4 },
              ...panelSx,
            }}
          >
            <Typography variant="h5" sx={{ color: headingColor, fontWeight: 700, mb: 1 }}>
              Historical Benchmark Data
            </Typography>
            <Typography sx={{ color: bodyColor, mb: 3, lineHeight: 1.8 }}>
              {blindBenchmarkMode
                ? 'Blind benchmark mode keeps the entry page focused on invite-code access. Recent round ratings are cached in this browser and can be reopened from the conclusion page.'
                : 'Load any completed run directly into the final conclusion screen, or inspect the raw saved data in a dialog before exporting it.'}
            </Typography>

            {blindBenchmarkMode ? (
              <Alert severity="info">
                Global benchmark history is intentionally hidden in blind mode so invite-code participants only see their own rounds after they finish them.
              </Alert>
            ) : historyLoading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                <CircularProgress />
              </Box>
            ) : sessions.length === 0 ? (
              <Alert severity="info">No benchmark history has been recorded yet.</Alert>
            ) : (
              <Stack spacing={1.5}>
                {sessions.map((session, index) => (
                  <React.Fragment key={session.session_id || session.id}>
                    <Box
                      sx={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        gap: 2,
                        flexWrap: 'wrap',
                        alignItems: 'center',
                      }}
                    >
                      <Box>
                        <Typography sx={{ color: headingColor, fontWeight: 700 }}>
                          {session.blind_mode
                            ? session.quick_test_mode
                              ? 'Quick Test Code 0'
                              : `Invite ${session.blind_invite_code || session.blind_code || 'unknown'}`
                            : session.participant_id}
                        </Typography>
                        <Typography variant="body2" sx={{ color: metaColor }}>
                          {session.blind_mode
                            ? session.quick_test_mode
                  ? `${session.started_at} | Hidden slot ${session.blind_session_index || 1}/${session.blind_total_sessions || 4} | Completed runs: ${session.quick_test_completed_runs || 0}${session.blind_finished ? ' | Sequence complete' : ''} | Condition: ${session.condition?.name || 'n/a'}`
                              : `${session.started_at} | Round ${session.blind_session_index || 1}/${session.blind_total_sessions || 4} | Condition: ${session.condition?.name || 'n/a'}`
                            : `${session.started_at} | Model: ${session.selected_model} | Condition: ${session.condition?.name}`}
                        </Typography>
                        <Typography variant="body2" sx={{ color: mutedColor }}>
                          Status: {session.status || 'unknown'} | Turns: {session.turn_count || 0} | Feedback: {session.feedback_count || 0}
                        </Typography>
                      </Box>

                      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                        <Button
                          variant="outlined"
                          onClick={() => handleLoadHistory(session.session_id || session.id || '')}
                          disabled={loadingHistorySessionId === (session.session_id || session.id || '')}
                        >
                          {loadingHistorySessionId === (session.session_id || session.id || '') ? 'Loading...' : 'Load History'}
                        </Button>
                        <Button variant="text" onClick={() => openHistory(session.session_id || session.id || '')}>
                          Inspect Data
                        </Button>
                      </Box>
                    </Box>
                    {index < sessions.length - 1 && <Divider sx={{ borderColor: 'rgba(148,163,184,0.24)' }} />}
                  </React.Fragment>
                ))}
              </Stack>
            )}
          </Paper>
        </Stack>
      </Container>

      <BenchmarkSessionHistoryDialog
        open={historyOpen}
        sessionId={historySessionId}
        onClose={() => setHistoryOpen(false)}
      />
    </Box>
  );
};

export default ExperimentMode;
