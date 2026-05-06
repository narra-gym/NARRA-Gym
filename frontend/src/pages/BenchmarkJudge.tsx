import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Divider,
  LinearProgress,
  Paper,
  Rating,
  Stack,
  Typography,
} from '@mui/material';
import axios from 'axios';
import ShaderBackground from '../components/ShaderBackground';
import { API_BASE_URL } from '../contexts/StoryContext';
import {
  BenchmarkJudgeInputSummary,
  BenchmarkJudgePayload,
  BenchmarkJudgeResponse,
  BenchmarkModelOption,
} from '../types';
import {
  buildBenchmarkJudgeInputSummary,
  normalizeBenchmarkJudgePayload,
} from '../utils/benchmarkJudge';

const scoreItems: Array<{ key: keyof BenchmarkJudgeResponse['judge_scores']; label: string; helper: string }> = [
  {
    key: 'overall_rating',
    label: 'Overall Rating',
    helper: 'High-level placeholder score for the full session.',
  },
  {
    key: 'emotional_alignment',
    label: 'Emotional Alignment',
    helper: 'How well the model output fits the user context and emotional need.',
  },
  {
    key: 'narrative_coherence',
    label: 'Narrative Coherence',
    helper: 'Whether the story flow stays understandable and internally consistent.',
  },
  {
    key: 'supportiveness',
    label: 'Supportiveness',
    helper: 'Whether the generated tone feels helpfully supportive rather than flat or generic.',
  },
];

const percentageLabel = (value: number): string => `${(value * 100).toFixed(1)}%`;

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

const BenchmarkJudgePage: React.FC = () => {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [models, setModels] = useState<BenchmarkModelOption[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [selectedModel, setSelectedModel] = useState('');
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);
  const [payload, setPayload] = useState<BenchmarkJudgePayload | null>(null);
  const [previewSummary, setPreviewSummary] = useState<BenchmarkJudgeInputSummary | null>(null);
  const [result, setResult] = useState<BenchmarkJudgeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let mounted = true;

    const fetchModels = async () => {
      setModelsLoading(true);
      try {
        const response = await axios.get(`${API_BASE_URL}/experiments/models`);
        if (!mounted) {
          return;
        }
        const fetchedModels = response.data as BenchmarkModelOption[];
        setModels(fetchedModels);
        setSelectedModel(current => current || fetchedModels[0]?.id || '');
      } catch (fetchError) {
        console.error(fetchError);
        if (mounted) {
          setError('Failed to load judge models.');
        }
      } finally {
        if (mounted) {
          setModelsLoading(false);
        }
      }
    };

    fetchModels();

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
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
  }, [models, selectedModel]);

  const activeModelLabel = useMemo(() => {
    const matched = models.find(model => model.id === selectedModel);
    return matched?.label || selectedModel || 'No model selected';
  }, [models, selectedModel]);

  const canRunJudge = Boolean(payload && selectedModel && !modelsLoading && !submitting);

  const handleOpenFilePicker = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';

    if (!file) {
      return;
    }

    setError(null);
    setResult(null);

    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      const normalized = normalizeBenchmarkJudgePayload(parsed);
      setSelectedFileName(file.name);
      setPayload(normalized);
      setPreviewSummary(buildBenchmarkJudgeInputSummary(normalized));
    } catch (parseError) {
      console.error(parseError);
      setSelectedFileName(file.name);
      setPayload(null);
      setPreviewSummary(null);
      setError(
        parseError instanceof Error
          ? `Failed to parse benchmark JSON: ${parseError.message}`
          : 'Failed to parse benchmark JSON.',
      );
    }
  };

  const handleRunJudge = async () => {
    if (!payload || !selectedModel) {
      setError('Upload a benchmark JSON and choose a judge model first.');
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const response = await axios.post(`${API_BASE_URL}/experiments/judge`, {
        selected_model: selectedModel,
        benchmark_payload: payload,
      });
      setResult(response.data as BenchmarkJudgeResponse);
    } catch (judgeError: any) {
      console.error(judgeError);
      setResult(null);
      setError(
        judgeError?.response?.data?.detail ||
        'Failed to run the benchmark judge. Please try again.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  const currentSummary = result?.input_summary || previewSummary;

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
              Benchmark LLM Judge
            </Typography>
            <Typography align="center" sx={{ color: bodyColor, mb: 3, lineHeight: 1.8 }}>
              Upload an existing benchmark JSON, choose a judge model, and run a placeholder
              LLM-as-a-judge pass plus a deterministic Slop Score analysis.
            </Typography>

            {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}

            <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center', flexWrap: 'wrap', mb: 2 }}>
              <Button variant="contained" onClick={handleOpenFilePicker}>
                {selectedFileName ? 'Replace JSON File' : 'Upload Benchmark JSON'}
              </Button>
              <Button variant="outlined" onClick={handleRunJudge} disabled={!canRunJudge}>
                {submitting ? <CircularProgress size={22} color="inherit" /> : 'Run Judge'}
              </Button>
              <Button variant="text" onClick={() => navigate('/experiment')}>
                Back To Benchmark
              </Button>
            </Box>

            <input
              ref={fileInputRef}
              type="file"
              accept=".json,application/json"
              data-testid="benchmark-judge-file-input"
              hidden
              onChange={handleFileChange}
            />

            <Typography align="center" sx={{ color: metaColor }}>
              Supported inputs: conclusion export JSON, session detail JSON, or export bundle JSON.
            </Typography>
          </Paper>

          <Paper
            sx={{
              p: { xs: 3, sm: 4 },
              ...panelSx,
            }}
          >
            <Typography variant="h5" sx={{ color: headingColor, fontWeight: 700, mb: 1 }}>
              Judge Model
            </Typography>
            <Typography sx={{ color: bodyColor, mb: 3, lineHeight: 1.8 }}>
              Reuses the existing benchmark model list so we can keep the new flow lightweight.
            </Typography>

            {modelsLoading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
                <CircularProgress />
              </Box>
            ) : (
              <Stack spacing={1.5}>
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
                        border: active ? '2px solid rgba(96,139,119,0.95)' : '1px solid rgba(148,163,184,0.28)',
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
          </Paper>

          <Paper
            sx={{
              p: { xs: 3, sm: 4 },
              ...panelSx,
            }}
          >
            <Typography variant="h5" sx={{ color: headingColor, fontWeight: 700, mb: 1 }}>
              Uploaded Benchmark Summary
            </Typography>
            <Typography sx={{ color: bodyColor, mb: 3, lineHeight: 1.8 }}>
              Local parsing happens in the browser first so you can confirm the JSON shape before
              spending a judge call.
            </Typography>

            {currentSummary ? (
              <Stack spacing={2}>
                <Typography sx={{ color: headingColor, fontWeight: 700 }}>
                  {selectedFileName || 'Uploaded JSON'}
                </Typography>
                <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                  <Chip size="small" label={`Judge model: ${activeModelLabel}`} />
                  <Chip size="small" label={`Dialogue: ${currentSummary.dialogue_count}`} />
                  <Chip size="small" label={`Model output: ${currentSummary.output_message_count}`} />
                  <Chip size="small" label={`Turns: ${currentSummary.turn_log_count}`} />
                  <Chip size="small" label={`LLM calls: ${currentSummary.llm_call_count}`} />
                  <Chip size="small" label={`Source: ${currentSummary.content_source}`} />
                </Stack>
                <Typography variant="body2" sx={{ color: metaColor }}>
                  Session: {currentSummary.session_id || 'unknown'} | Participant:{' '}
                  {currentSummary.participant_id || 'unknown'} | Story:{' '}
                  {currentSummary.story_title || currentSummary.story_id || 'unknown'}
                </Typography>
                <Typography variant="body2" sx={{ color: mutedColor }}>
                  Total output tokens used for stats: {currentSummary.total_output_tokens}
                </Typography>
              </Stack>
            ) : (
              <Alert severity="info">Upload a benchmark JSON file to preview the parsed session.</Alert>
            )}
          </Paper>

          {result && (
            <Paper
              sx={{
                p: { xs: 3, sm: 4 },
                ...panelSx,
              }}
            >
              <Typography variant="h5" sx={{ color: headingColor, fontWeight: 700, mb: 1 }}>
                Judge Result
              </Typography>
              <Typography sx={{ color: bodyColor, mb: 3, lineHeight: 1.8 }}>
                Placeholder rubric scores from the selected judge model, plus a deterministic Slop Score.
              </Typography>

              <Stack spacing={3}>
                <Stack spacing={2}>
                  {scoreItems.map(item => (
                    <Box key={item.key}>
                      <Typography sx={{ color: headingColor, fontWeight: 700, mb: 0.5 }}>
                        {item.label}
                      </Typography>
                      <Typography variant="body2" sx={{ color: metaColor, mb: 1 }}>
                        {item.helper}
                      </Typography>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                        <Rating value={result.judge_scores[item.key]} readOnly />
                        <Typography sx={{ color: headingColor, fontWeight: 700 }}>
                          {result.judge_scores[item.key]}/5
                        </Typography>
                      </Box>
                    </Box>
                  ))}
                </Stack>

                <Divider sx={{ borderColor: 'rgba(148,163,184,0.24)' }} />

                <Box>
                  <Typography sx={{ color: headingColor, fontWeight: 700, mb: 1 }}>
                    Judge Summary
                  </Typography>
                  <Typography sx={{ color: bodyColor, lineHeight: 1.8, mb: 2 }}>
                    {result.judge_summary.summary}
                  </Typography>

                  <Stack spacing={2}>
                    <Box>
                      <Typography sx={{ color: headingColor, fontWeight: 700, mb: 1 }}>
                        Strengths
                      </Typography>
                      <Stack spacing={1}>
                        {result.judge_summary.strengths.map((item, index) => (
                          <Typography key={`${item}-${index}`} sx={{ color: metaColor }}>
                            {index + 1}. {item}
                          </Typography>
                        ))}
                      </Stack>
                    </Box>

                    <Box>
                      <Typography sx={{ color: headingColor, fontWeight: 700, mb: 1 }}>
                        Issues
                      </Typography>
                      <Stack spacing={1}>
                        {result.judge_summary.issues.map((item, index) => (
                          <Typography key={`${item}-${index}`} sx={{ color: metaColor }}>
                            {index + 1}. {item}
                          </Typography>
                        ))}
                      </Stack>
                    </Box>
                  </Stack>
                </Box>

                <Divider sx={{ borderColor: 'rgba(148,163,184,0.24)' }} />

                <Box>
                  <Typography sx={{ color: headingColor, fontWeight: 700, mb: 1 }}>
                    Slop Score
                  </Typography>
                  <Typography sx={{ color: bodyColor, mb: 2, lineHeight: 1.8 }}>
                    Higher means more repetitive, more stock-phrase-heavy, or more obviously pattern-driven.
                  </Typography>

                  <Box sx={{ mb: 2 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.75 }}>
                      <Typography sx={{ color: headingColor, fontWeight: 700 }}>
                        {result.slop_stats.slop_score.toFixed(2)} / 100
                      </Typography>
                      <Typography sx={{ color: metaColor }}>
                        {result.slop_stats.total_output_messages} output messages
                      </Typography>
                    </Box>
                    <LinearProgress
                      variant="determinate"
                      value={Math.min(100, Math.max(0, result.slop_stats.slop_score))}
                    />
                    <Typography variant="body2" sx={{ color: mutedColor, mt: 1 }}>
                      {result.slop_stats.interpretation}
                    </Typography>
                  </Box>

                  <Stack spacing={1}>
                    <Typography sx={{ color: metaColor }}>
                      GPT-ism hit rate: {percentageLabel(result.slop_stats.gptism_hit_rate)}
                    </Typography>
                    <Typography sx={{ color: metaColor }}>
                      Repeated bigram ratio: {percentageLabel(result.slop_stats.repeated_bigram_ratio)}
                    </Typography>
                    <Typography sx={{ color: metaColor }}>
                      Repeated trigram ratio: {percentageLabel(result.slop_stats.repeated_trigram_ratio)}
                    </Typography>
                    <Typography sx={{ color: metaColor }}>
                      High-frequency term ratio: {percentageLabel(result.slop_stats.high_frequency_term_ratio)}
                    </Typography>
                    <Typography sx={{ color: metaColor }}>
                      Repeated sentence-prefix ratio: {percentageLabel(result.slop_stats.repeated_sentence_prefix_ratio)}
                    </Typography>
                  </Stack>

                  {result.slop_stats.top_repeated_terms.length > 0 && (
                    <Box sx={{ mt: 2 }}>
                      <Typography sx={{ color: headingColor, fontWeight: 700, mb: 1 }}>
                        Top repeated terms
                      </Typography>
                      <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                        {result.slop_stats.top_repeated_terms.map(item => (
                          <Chip
                            key={`${item.term}-${item.count}`}
                            size="small"
                            label={`${item.term} x${item.count}`}
                          />
                        ))}
                      </Stack>
                    </Box>
                  )}
                </Box>
              </Stack>
            </Paper>
          )}
        </Stack>
      </Container>
    </Box>
  );
};

export default BenchmarkJudgePage;
