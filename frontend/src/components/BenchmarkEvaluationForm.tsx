import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Box, Button, Radio, RadioGroup, Stack, TextField, Typography } from '@mui/material';
import axios from 'axios';
import { API_BASE_URL, useStory } from '../contexts/StoryContext';
import { BenchmarkScores } from '../utils/benchmarkEvaluation';
import {
  BENCHMARK_EMOTIONAL_FORM_VERSION,
  BENCHMARK_SCORE_SECTIONS,
  BenchmarkScoreItem,
  buildBenchmarkEvaluationPayload,
  createEmptyBenchmarkScores,
  getBenchmarkScoresFromFeedback,
  isLegacyBenchmarkRubricFeedback,
} from '../utils/benchmarkEvaluation';

interface Props {
  storyId?: string;
  userId?: string;
  sessionId?: string | null;
  participantId?: string | null;
  existingFeedback?: Record<string, any> | null;
  templateMode?: boolean;
  onFeedbackSaved?: (feedback: Record<string, any>) => void;
}

const BenchmarkEvaluationForm: React.FC<Props> = ({
  storyId,
  userId,
  sessionId,
  participantId,
  existingFeedback,
  templateMode = false,
  onFeedbackSaved,
}) => {
  const { experimentSession } = useStory();
  const [scores, setScores] = useState<BenchmarkScores>(createEmptyBenchmarkScores());
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const legacyFeedbackLoaded = useMemo(
    () => isLegacyBenchmarkRubricFeedback(existingFeedback),
    [existingFeedback],
  );

  useEffect(() => {
    setScores(getBenchmarkScoresFromFeedback(existingFeedback));
    setComment(existingFeedback?.comment || '');
    setError(null);
  }, [existingFeedback]);

  useEffect(() => {
    setSuccessMessage(null);
  }, [storyId, sessionId]);

  const totalQuestionCount = useMemo(
    () => BENCHMARK_SCORE_SECTIONS.reduce((count, section) => count + section.items.length, 0),
    [],
  );

  const answeredQuestionCount = useMemo(
    () => Object.values(scores).filter(value => value > 0).length,
    [scores],
  );

  const canSubmit = useMemo(
    () => answeredQuestionCount === totalQuestionCount && !submitting,
    [answeredQuestionCount, totalQuestionCount, submitting],
  );

  const handleScoreChange = (key: keyof BenchmarkScores, value: number | null) => {
    setScores(prev => ({ ...prev, [key]: value || 0 }));
  };

  const handleSubmit = async () => {
    if (!canSubmit) {
      setError('Please complete every questionnaire item before submitting.');
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccessMessage(null);

    const payload = buildBenchmarkEvaluationPayload({
      storyId,
      userId,
      participantId: participantId || experimentSession?.participant_id || null,
      sessionId: sessionId || experimentSession?.session_id || null,
      scores,
      comment,
    });

    try {
      if (templateMode) {
        const localFeedback = {
          id: existingFeedback?.id || 'template-feedback-local',
          ...payload,
          created_at: new Date().toISOString(),
        };
        onFeedbackSaved?.(localFeedback);
        setSuccessMessage('Template feedback updated locally. No server data was changed.');
      } else {
        const response = await axios.post(`${API_BASE_URL}/feedback`, payload);
        const savedFeedback = response.data?.feedback || {
          id: response.data?.id,
          ...payload,
          created_at: new Date().toISOString(),
        };
        onFeedbackSaved?.(savedFeedback);
        setSuccessMessage(existingFeedback ? 'Benchmark feedback updated.' : 'Benchmark feedback submitted.');
      }
    } catch (err) {
      console.error(err);
      setError('Failed to submit benchmark evaluation. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const renderDescriptiveScale = (item: BenchmarkScoreItem) => (
    <RadioGroup
      name={`benchmark-${item.key}`}
      value={scores[item.key] ? String(scores[item.key]) : ''}
      onChange={event => handleScoreChange(item.key, Number(event.target.value))}
    >
      <Stack spacing={1}>
        {item.scaleOptions.map(option => {
          const selected = scores[item.key] === option.value;
          return (
            <Box
              key={`${item.key}-${option.value}`}
              component="label"
              sx={{
                display: 'block',
                p: 1.25,
                border: selected ? '1px solid rgba(59, 105, 88, 0.6)' : '1px solid rgba(118, 136, 125, 0.2)',
                background: selected ? 'rgba(232, 241, 236, 0.96)' : 'rgba(255,255,255,0.82)',
                cursor: 'pointer',
                transition: 'border-color 0.2s ease, background 0.2s ease',
                '&:hover': {
                  borderColor: 'rgba(59, 105, 88, 0.36)',
                  background: 'rgba(250, 251, 248, 0.96)',
                },
              }}
            >
              <Stack direction="row" spacing={1} alignItems="flex-start">
                <Radio
                  checked={selected}
                  value={String(option.value)}
                  sx={{
                    p: 0.1,
                    mt: 0.05,
                    color: 'rgba(59, 105, 88, 0.62)',
                    '&.Mui-checked': { color: 'rgb(59, 105, 88)' },
                  }}
                />
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#2b3b33' }}>
                    {option.title}
                  </Typography>
                  <Typography variant="body2" sx={{ mt: 0.25, color: 'rgba(58, 71, 64, 0.82)', lineHeight: 1.7 }}>
                    {option.description}
                  </Typography>
                </Box>
              </Stack>
            </Box>
          );
        })}
      </Stack>
    </RadioGroup>
  );

  const renderCompactScale = (item: BenchmarkScoreItem) => (
    <RadioGroup
      name={`benchmark-${item.key}`}
      value={scores[item.key] ? String(scores[item.key]) : ''}
      onChange={event => handleScoreChange(item.key, Number(event.target.value))}
    >
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: 'repeat(5, minmax(0, 1fr))', sm: 'repeat(5, 76px)' },
          justifyContent: 'flex-start',
          gap: 1.1,
        }}
      >
        {item.scaleOptions.map(option => {
          const selected = scores[item.key] === option.value;
          return (
            <Box
              key={`${item.key}-${option.value}`}
              component="label"
              sx={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 0.65,
                minHeight: 86,
                border: selected ? '1px solid rgba(59, 105, 88, 0.6)' : '1px solid rgba(118, 136, 125, 0.22)',
                background: selected ? 'rgba(232, 241, 236, 0.96)' : 'rgba(255,255,255,0.84)',
                cursor: 'pointer',
                transition: 'border-color 0.2s ease, background 0.2s ease, transform 0.2s ease',
                '&:hover': {
                  borderColor: 'rgba(59, 105, 88, 0.36)',
                  background: 'rgba(250, 251, 248, 0.96)',
                  transform: 'translateY(-1px)',
                },
              }}
            >
              <Radio
                checked={selected}
                value={String(option.value)}
                sx={{
                  p: 0,
                  color: 'rgba(59, 105, 88, 0.62)',
                  '&.Mui-checked': { color: 'rgb(59, 105, 88)' },
                }}
              />
              <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#2b3b33' }}>
                {option.title}
              </Typography>
            </Box>
          );
        })}
      </Box>
      {item.scaleHint && (
        <Typography variant="caption" sx={{ display: 'block', mt: 1.1, color: 'rgba(84, 98, 89, 0.76)', lineHeight: 1.6 }}>
          {item.scaleHint}
        </Typography>
      )}
    </RadioGroup>
  );

  const renderAnchoredScale = (item: BenchmarkScoreItem) => (
    <RadioGroup
      name={`benchmark-${item.key}`}
      value={scores[item.key] ? String(scores[item.key]) : ''}
      onChange={event => handleScoreChange(item.key, Number(event.target.value))}
    >
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: 'repeat(3, minmax(0, 1fr))' },
          gap: 1.15,
        }}
      >
        {item.scaleOptions.map(option => {
          const selected = scores[item.key] === option.value;
          return (
            <Box
              key={`${item.key}-${option.value}`}
              component="label"
              sx={{
                display: 'block',
                p: 1.25,
                border: selected ? '1px solid rgba(59, 105, 88, 0.6)' : '1px solid rgba(118, 136, 125, 0.22)',
                background: selected ? 'rgba(232, 241, 236, 0.96)' : 'rgba(255,255,255,0.84)',
                cursor: 'pointer',
                transition: 'border-color 0.2s ease, background 0.2s ease',
                '&:hover': {
                  borderColor: 'rgba(59, 105, 88, 0.36)',
                  background: 'rgba(250, 251, 248, 0.96)',
                },
              }}
            >
              <Stack direction="row" spacing={1} alignItems="flex-start">
                <Radio
                  checked={selected}
                  value={String(option.value)}
                  sx={{
                    p: 0.1,
                    mt: 0.05,
                    color: 'rgba(59, 105, 88, 0.62)',
                    '&.Mui-checked': { color: 'rgb(59, 105, 88)' },
                  }}
                />
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#2b3b33' }}>
                    {option.title}
                  </Typography>
                  <Typography variant="body2" sx={{ mt: 0.25, color: 'rgba(58, 71, 64, 0.82)', lineHeight: 1.65 }}>
                    {option.description}
                  </Typography>
                </Box>
              </Stack>
            </Box>
          );
        })}
      </Box>
    </RadioGroup>
  );

  const renderScale = (item: BenchmarkScoreItem) => {
    if (item.displayMode === 'compact') {
      return renderCompactScale(item);
    }
    if (item.displayMode === 'anchored') {
      return renderAnchoredScale(item);
    }
    return renderDescriptiveScale(item);
  };

  let questionNumber = 0;

  return (
    <Box
      sx={{
        mt: 2,
      }}
    >
      <Box
        sx={{
          px: { xs: 0, sm: 0 },
          py: { xs: 0, sm: 0 },
        }}
      >
        <Typography variant="overline" sx={{ letterSpacing: '0.16em', color: 'rgba(83, 98, 88, 0.82)', fontWeight: 700 }}>
          Benchmark Human Evaluation
        </Typography>
        <Typography variant="h5" sx={{ mt: 0.6, fontWeight: 700, color: '#26352d' }}>
          Post-Session Questionnaire
        </Typography>
        <Typography variant="body2" sx={{ mt: 1.1, maxWidth: 780, color: 'rgba(54, 68, 60, 0.82)', lineHeight: 1.8 }}>
          Please complete the questionnaire below based on the finished story session. Story quality items use question-specific anchored descriptions, while user-experience items use quicker response scales.
        </Typography>
        <Typography variant="body2" sx={{ mt: 1.15, color: 'rgba(54, 68, 60, 0.82)', lineHeight: 1.8 }}>
          Story quality items include tailored 1-5 anchor descriptions for each question. User-experience items use compact response scales. {answeredQuestionCount} of {totalQuestionCount} items completed. Rubric version: {BENCHMARK_EMOTIONAL_FORM_VERSION}.
        </Typography>
      </Box>

      <Box sx={{ px: { xs: 0, sm: 0 }, py: { xs: 2.25, sm: 3 } }}>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {successMessage && <Alert severity="success" sx={{ mb: 2 }}>{successMessage}</Alert>}
        {legacyFeedbackLoaded && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            This session has a benchmark rating from an older rubric version. The saved comment is preserved below, and all scores should be re-entered with the current questionnaire before saving.
          </Alert>
        )}
        {templateMode && (
          <Alert severity="info" sx={{ mb: 2 }}>
            This is a local benchmark template. Rating changes stay in the browser so you can review the questionnaire layout without changing server data.
          </Alert>
        )}

        <Stack spacing={3}>
          {BENCHMARK_SCORE_SECTIONS.map((section, sectionIndex) => (
            <Box
              key={section.id}
              sx={{
                pt: sectionIndex === 0 ? 0 : 1.6,
                borderTop: sectionIndex === 0 ? 'none' : '1px solid rgba(88, 107, 95, 0.12)',
              }}
            >
              <Box
                sx={{
                  px: { xs: 0, sm: 0 },
                  py: { xs: 0.8, sm: 1.1 },
                }}
              >
                <Typography variant="overline" sx={{ letterSpacing: '0.14em', color: 'rgba(76, 90, 80, 0.78)', fontWeight: 700 }}>
                  Section {sectionIndex + 1}
                </Typography>
                <Typography variant="h6" sx={{ mt: 0.3, fontWeight: 700, color: '#27362d' }}>
                  {section.title}
                </Typography>
                <Typography variant="body2" sx={{ mt: 0.55, color: 'rgba(55, 69, 61, 0.82)', lineHeight: 1.75 }}>
                  {section.description}
                </Typography>
              </Box>

              <Stack spacing={0}>
                {section.items.map((item, itemIndex) => {
                  questionNumber += 1;
                  return (
                    <Box
                      key={item.key}
                      sx={{
                        px: { xs: 0, sm: 0 },
                        py: { xs: 1.7, sm: 2.1 },
                        borderTop: itemIndex > 0 ? '1px solid rgba(88, 107, 95, 0.08)' : 'none',
                      }}
                    >
                      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.2, mb: 1.2 }}>
                        <Box
                          sx={{
                            minWidth: 34,
                            height: 34,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            color: '#32453b',
                            fontWeight: 700,
                            fontSize: 13,
                          }}
                        >
                          {questionNumber}
                        </Box>
                        <Box sx={{ minWidth: 0, flex: 1 }}>
                          <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#27362d', fontStyle: section.id === 'user_experience' ? 'italic' : 'normal' }}>
                            {item.label}
                          </Typography>
                          {item.helper && (
                            <Typography variant="body2" sx={{ mt: 0.45, color: 'rgba(61, 75, 67, 0.82)', lineHeight: 1.75 }}>
                              {item.helper}
                            </Typography>
                          )}
                          {item.scaleLabel && (
                            <Typography
                              variant="caption"
                              sx={{
                                display: 'block',
                                mt: item.helper ? 1 : 0.8,
                                letterSpacing: '0.08em',
                                textTransform: 'uppercase',
                                color: 'rgba(87, 102, 93, 0.74)',
                              }}
                            >
                              {item.scaleLabel}
                            </Typography>
                          )}
                        </Box>
                      </Box>

                      {renderScale(item)}
                    </Box>
                  );
                })}
              </Stack>
            </Box>
          ))}

          <Box sx={{ pt: 0.4 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#27362d' }}>
              Open-Ended Note
            </Typography>
            <Typography variant="body2" sx={{ mt: 0.45, mb: 1.5, color: 'rgba(61, 75, 67, 0.82)', lineHeight: 1.75 }}>
              Add any qualitative observations that would help interpret the ratings, such as strengths, weak points, or moments that shaped your judgement.
            </Typography>
            <TextField
              label="Optional Comment"
              value={comment}
              onChange={event => setComment(event.target.value)}
              placeholder="Describe the moments, qualities, or issues that most influenced your evaluation."
              multiline
              minRows={4}
              fullWidth
              helperText={`Saved with rubric version ${BENCHMARK_EMOTIONAL_FORM_VERSION}.`}
            />
          </Box>

          <Box
            sx={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: { xs: 'flex-start', sm: 'center' },
              flexDirection: { xs: 'column', sm: 'row' },
              gap: 1.5,
              pt: 0.6,
            }}
          >
            <Typography variant="body2" sx={{ color: 'rgba(61, 75, 67, 0.82)', lineHeight: 1.7 }}>
              Submission status: {answeredQuestionCount}/{totalQuestionCount} items completed.
            </Typography>
            <Button variant="contained" onClick={handleSubmit} disabled={!canSubmit}>
              {submitting ? 'Saving...' : existingFeedback ? 'Update Benchmark Feedback' : 'Save Benchmark Feedback'}
            </Button>
          </Box>
        </Stack>
      </Box>
    </Box>
  );
};

export default BenchmarkEvaluationForm;
