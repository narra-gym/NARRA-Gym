import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Container,
  Divider,
  ListItemText,
  Menu,
  MenuItem,
  Paper,
  Snackbar,
  Stack,
  Typography,
} from '@mui/material';
import axios from 'axios';
import { API_BASE_URL, useStory } from '../contexts/StoryContext';
import MixedRichText from '../components/MixedRichText';
import FeedbackWidget from '../components/FeedbackWidget';
import BenchmarkEvaluationForm from '../components/BenchmarkEvaluationForm';
import {
  BenchmarkDialogueRecord,
  BenchmarkSessionDetail,
  Message,
} from '../types';
import {
  buildReplayStoryFromDetail,
  buildBenchmarkResultExportPayload,
  downloadJsonFile,
  getBenchmarkResultFilename,
  mergeAdjacentBenchmarkDialogueRecords,
} from '../utils/benchmarkHistory';
import {
  getBenchmarkRubricVersionLabel,
  isLegacyBenchmarkRubricFeedback,
} from '../utils/benchmarkEvaluation';
import {
  readLocalBenchmarkReviewHistory,
  upsertLocalBenchmarkReviewDetail,
} from '../utils/localBenchmarkReview';

const upsertFeedbackLogs = (
  feedbackLogs: Record<string, any>[],
  feedback: Record<string, any>,
) => {
  const nextLogs = feedbackLogs.filter(item => {
    if (feedback.id && item.id === feedback.id) {
      return false;
    }
    return !(
      item.session_id === feedback.session_id &&
      item.feedback_type === feedback.feedback_type
    );
  });
  return [...nextLogs, feedback];
};

const getLatestBenchmarkFeedbackLog = (feedbackLogs: Record<string, any>[] = []) => {
  const benchmarkLogs = feedbackLogs.filter(
    item => item.feedback_type === 'benchmark_session_end',
  );
  return benchmarkLogs[benchmarkLogs.length - 1] || null;
};

const PREVIOUS_RATING_RETURN_TARGET_KEY = 'emonest:previous-rating-return-target:v1';
const PREVIOUS_RATING_RESTORED_SESSION_KEY = 'emonest:previous-rating-restored-session:v1';

const getSessionStorage = (): Storage | null => {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    return window.sessionStorage || null;
  } catch (error) {
    return null;
  }
};

const readReturnBenchmarkDetail = (): BenchmarkSessionDetail | null => {
  const storage = getSessionStorage();
  if (!storage) {
    return null;
  }
  try {
    const raw = storage.getItem(PREVIOUS_RATING_RETURN_TARGET_KEY);
    return raw ? JSON.parse(raw) as BenchmarkSessionDetail : null;
  } catch (error) {
    storage.removeItem(PREVIOUS_RATING_RETURN_TARGET_KEY);
    return null;
  }
};

const writeReturnBenchmarkDetail = (detail: BenchmarkSessionDetail) => {
  const storage = getSessionStorage();
  if (!storage) {
    return;
  }
  try {
    storage.setItem(PREVIOUS_RATING_RETURN_TARGET_KEY, JSON.stringify(detail));
  } catch (error) {
    storage.removeItem(PREVIOUS_RATING_RETURN_TARGET_KEY);
  }
};

const clearReturnBenchmarkDetail = () => {
  getSessionStorage()?.removeItem(PREVIOUS_RATING_RETURN_TARGET_KEY);
};

const readRestoredCurrentSessionId = (): string | null => (
  getSessionStorage()?.getItem(PREVIOUS_RATING_RESTORED_SESSION_KEY) || null
);

const writeRestoredCurrentSessionId = (sessionId: string | null | undefined) => {
  const storage = getSessionStorage();
  if (!storage) {
    return;
  }
  if (sessionId) {
    storage.setItem(PREVIOUS_RATING_RESTORED_SESSION_KEY, sessionId);
    return;
  }
  storage.removeItem(PREVIOUS_RATING_RESTORED_SESSION_KEY);
};

const getBenchmarkDetailLabel = (detail: BenchmarkSessionDetail) => {
  const session = detail.session;
  const feedback = getLatestBenchmarkFeedbackLog(detail.feedback_logs || []);
  const scoreLabel = feedback?.rating !== undefined ? ` | score ${feedback.rating}/5` : '';
  const title = detail.final_view_story?.title || detail.story_snapshot?.title || session.session_id || 'Previous round';

  if (session.quick_test_mode) {
    return `Quick test slot ${session.blind_session_index || '?'}${session.blind_total_sessions ? `/${session.blind_total_sessions}` : ''}${scoreLabel} | ${title}`;
  }
  if (session.blind_mode) {
    return `Blind round ${session.blind_session_index || '?'}${session.blind_total_sessions ? `/${session.blind_total_sessions}` : ''}${scoreLabel} | ${title}`;
  }
  return `${title}${scoreLabel}`;
};

const StoryConclusion: React.FC = () => {
  const { story, experimentMode, experimentSession, startExperimentSession, clearExperimentSession, loadHistoricalStory } = useStory();
  const navigate = useNavigate();
  const [snackbarMsg, setSnackbarMsg] = useState<string | null>(null);
  const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>('success');
  const [historyFeedbackLogs, setHistoryFeedbackLogs] = useState<Record<string, any>[]>([]);
  const [resolvedBenchmarkHistory, setResolvedBenchmarkHistory] = useState<BenchmarkSessionDetail | null>(null);
  const [benchmarkHistoryLoading, setBenchmarkHistoryLoading] = useState(false);
  const [localReviewHistory, setLocalReviewHistory] = useState<BenchmarkSessionDetail[]>([]);
  const [previousRatingMenuAnchor, setPreviousRatingMenuAnchor] = useState<HTMLElement | null>(null);
  const [returnBenchmarkDetail, setReturnBenchmarkDetail] = useState<BenchmarkSessionDetail | null>(() => readReturnBenchmarkDetail());
  const [restoredCurrentSessionId, setRestoredCurrentSessionId] = useState<string | null>(() => readRestoredCurrentSessionId());
  const [startingNextQuickTest, setStartingNextQuickTest] = useState(false);

  const embeddedBenchmarkHistory = story?.benchmarkHistory || null;
  const benchmarkHistory = embeddedBenchmarkHistory || resolvedBenchmarkHistory;
  const benchmarkSnapshot = benchmarkHistory?.final_view_story || benchmarkHistory?.story_snapshot || null;
  const isBenchmarkConclusionView = experimentMode || Boolean(embeddedBenchmarkHistory);
  const isTemplateMode = Boolean(benchmarkHistory?.template_mode);
  const benchmarkSessionRecord = benchmarkHistory?.session || experimentSession || null;
  const benchmarkSessionId = benchmarkSessionRecord?.session_id || null;
  const isRestoredCurrentBenchmarkView = Boolean(
    embeddedBenchmarkHistory &&
    restoredCurrentSessionId &&
    benchmarkSessionId &&
    experimentSession?.session_id === benchmarkSessionId &&
    restoredCurrentSessionId === benchmarkSessionId,
  );
  const isHistoricalBenchmarkView = Boolean(embeddedBenchmarkHistory) && !isRestoredCurrentBenchmarkView;
  const isPreviousRatingReviewView = Boolean(
    isHistoricalBenchmarkView &&
    returnBenchmarkDetail?.session?.session_id &&
    benchmarkSessionId &&
    returnBenchmarkDetail.session.session_id !== benchmarkSessionId,
  );
  const isBlindBenchmarkSession = Boolean(benchmarkSessionRecord?.blind_mode);
  const isQuickTestSession = Boolean(benchmarkSessionRecord?.quick_test_mode);
  const isQuickTestComplete = Boolean(isQuickTestSession && benchmarkSessionRecord?.blind_finished);
  const canStartNextQuickTest = Boolean(isQuickTestSession && !isHistoricalBenchmarkView && !isQuickTestComplete);
  const benchmarkSessionStoryId = (benchmarkSessionRecord as any)?.story_id || undefined;
  const storyId = story?.id || benchmarkSnapshot?.id || benchmarkSessionStoryId || undefined;
  const storyUserId = story?.userId || benchmarkSnapshot?.user_id || benchmarkSnapshot?.userId || benchmarkSessionRecord?.participant_id || undefined;
  const storyTitle = story?.title || benchmarkSnapshot?.title || 'Untitled Story';
  const storyTheme = story?.theme || benchmarkSnapshot?.theme || benchmarkSnapshot?.cinematic_theme || 'your journey';
  const shouldHoldConclusion = benchmarkHistoryLoading || (
    experimentMode &&
    Boolean(experimentSession?.session_id) &&
    !story &&
    !benchmarkHistory
  );

  useEffect(() => {
    setHistoryFeedbackLogs(benchmarkHistory?.feedback_logs || []);
  }, [benchmarkHistory]);

  useEffect(() => {
    if (embeddedBenchmarkHistory || !experimentMode || !experimentSession?.session_id) {
      setResolvedBenchmarkHistory(null);
      setBenchmarkHistoryLoading(false);
      return;
    }

    let mounted = true;

    const fetchBenchmarkHistory = async () => {
      setBenchmarkHistoryLoading(true);
      try {
        const response = await axios.get(`${API_BASE_URL}/experiments/sessions/${experimentSession.session_id}`);
        if (mounted) {
          setResolvedBenchmarkHistory(response.data as BenchmarkSessionDetail);
        }
      } catch (error) {
        if (mounted) {
          setResolvedBenchmarkHistory(null);
        }
      } finally {
        if (mounted) {
          setBenchmarkHistoryLoading(false);
        }
      }
    };

    fetchBenchmarkHistory();

    return () => {
      mounted = false;
    };
  }, [embeddedBenchmarkHistory, experimentMode, experimentSession?.session_id]);

  useEffect(() => {
    if (story || benchmarkHistory || shouldHoldConclusion) {
      return;
    }
    navigate('/');
  }, [benchmarkHistory, navigate, shouldHoldConclusion, story]);

  const characterMap = useMemo(() => {
    const characters = story?.characters || [];
    return Object.fromEntries(characters.map(character => [character.id, character.name]));
  }, [story]);

  const mappedCurrentSceneDialogue = useMemo<BenchmarkDialogueRecord[]>(() => {
    if (!story) {
      return [];
    }
    return (story.currentScene.messages || []).map((message: Message, index: number) => {
      const speaker = message.characterId
        ? (characterMap[message.characterId] || (message.characterId === 'system' ? 'System' : message.characterId))
        : 'Unknown';
      const role = message.characterId === 'system'
        ? 'system'
        : story.characters.some(character => character.id === message.characterId && character.role === 'protagonist')
          ? 'user'
          : 'assistant';

      return {
        id: message.id || `scene-message-${index}`,
        speaker,
        role,
        character_id: message.characterId || null,
        content: message.content,
        timestamp: message.timestamp,
        message_type: message.type,
        source: 'current_scene',
      };
    });
  }, [story, characterMap]);

  const dialogueRecords = benchmarkHistory?.dialogue?.length ? benchmarkHistory.dialogue : mappedCurrentSceneDialogue;
  const displayDialogueRecords = useMemo(
    () => mergeAdjacentBenchmarkDialogueRecords(dialogueRecords),
    [dialogueRecords],
  );

  const existingBenchmarkFeedback = useMemo(() => {
    return getLatestBenchmarkFeedbackLog(historyFeedbackLogs);
  }, [historyFeedbackLogs]);

  const benchmarkExportPayload = useMemo(() => {
    if (!isBenchmarkConclusionView || !story) {
      return null;
    }

    return buildBenchmarkResultExportPayload({
      session: (benchmarkHistory?.session || experimentSession || null) as Record<string, any> | null,
      story: story as unknown as Record<string, any>,
      dialogueSource: benchmarkHistory?.dialogue_source || 'current_scene',
      dialogue: displayDialogueRecords,
      turnLogs: benchmarkHistory?.turn_logs || [],
      feedbackLogs: historyFeedbackLogs,
      templateMode: isTemplateMode,
    });
  }, [
    benchmarkHistory,
    displayDialogueRecords,
    experimentSession,
    historyFeedbackLogs,
    isBenchmarkConclusionView,
    isTemplateMode,
    story,
  ]);

  const currentBenchmarkDetailForCache = useMemo<BenchmarkSessionDetail | null>(() => {
    if (!isBenchmarkConclusionView || !benchmarkSessionRecord?.session_id) {
      return null;
    }

    const storyRecord = story ? story as unknown as Record<string, any> : null;
    const sessionRecord = {
      ...benchmarkSessionRecord,
      story_id: storyId || benchmarkSessionStoryId || benchmarkHistory?.session?.story_id || null,
    } as BenchmarkSessionDetail['session'];

    return {
      session: sessionRecord,
      dialogue_source: benchmarkHistory?.dialogue_source || 'current_scene',
      dialogue: dialogueRecords,
      story_snapshot: benchmarkHistory?.story_snapshot || benchmarkSnapshot || storyRecord,
      final_view_story: benchmarkHistory?.final_view_story || storyRecord || benchmarkSnapshot,
      turn_logs: benchmarkHistory?.turn_logs || [],
      feedback_logs: historyFeedbackLogs,
      participant_evaluation: benchmarkHistory?.participant_evaluation || existingBenchmarkFeedback || null,
      story_events: benchmarkHistory?.story_events || [],
      llm_call_logs: benchmarkHistory?.llm_call_logs || [],
      export_bundle: benchmarkHistory?.export_bundle || null,
      template_mode: isTemplateMode,
    };
  }, [
    benchmarkHistory,
    benchmarkSessionRecord,
    benchmarkSessionStoryId,
    benchmarkSnapshot,
    dialogueRecords,
    existingBenchmarkFeedback,
    historyFeedbackLogs,
    isBenchmarkConclusionView,
    isTemplateMode,
    story,
    storyId,
  ]);

  const refreshLocalReviewHistory = useCallback(() => {
    const history = readLocalBenchmarkReviewHistory(benchmarkSessionRecord as BenchmarkSessionDetail['session'] | null);
    setLocalReviewHistory(history);
    return history;
  }, [
    benchmarkSessionRecord,
  ]);

  useEffect(() => {
    refreshLocalReviewHistory();
    setPreviousRatingMenuAnchor(null);
  }, [refreshLocalReviewHistory]);

  useEffect(() => {
    if (!currentBenchmarkDetailForCache || !isBlindBenchmarkSession || isHistoricalBenchmarkView) {
      return;
    }
    setLocalReviewHistory(upsertLocalBenchmarkReviewDetail(currentBenchmarkDetailForCache));
  }, [currentBenchmarkDetailForCache, isBlindBenchmarkSession, isHistoricalBenchmarkView]);

  const previousBenchmarkDetails = useMemo(() => {
    if (!benchmarkSessionId) {
      return [];
    }
    return localReviewHistory.filter(detail => detail.session.session_id !== benchmarkSessionId);
  }, [benchmarkSessionId, localReviewHistory]);
  const hasPreviousBenchmarkDetails = previousBenchmarkDetails.length > 0;
  const canUsePreviousRating = Boolean(
    hasPreviousBenchmarkDetails &&
    isBlindBenchmarkSession &&
    !isHistoricalBenchmarkView &&
    !isPreviousRatingReviewView,
  );

  const renderDialogueRecord = (record: BenchmarkDialogueRecord, index: number) => {
    const isUser = record.role === 'user';
    const isSystem = record.role === 'system';
    const mode = /\*[^*]+\*/.test(record.content || '') ? 'rp_mixed' : 'plain';
    const borderColor = isUser
      ? 'rgba(232,168,152,0.28)'
      : isSystem
        ? 'rgba(122,168,196,0.25)'
        : 'rgba(125,184,162,0.22)';
    const background = isUser
      ? 'rgba(253,240,232,0.88)'
      : isSystem
        ? 'rgba(244,248,250,0.92)'
        : 'rgba(246,250,247,0.92)';

    return (
      <Box
        key={record.id || `dialogue-record-${index}`}
        sx={{
          p: 1.6,
          borderRadius: 2,
          background,
          border: `1px solid ${borderColor}`,
        }}
      >
        <Typography variant="caption" sx={{ display: 'block', mb: 0.55, fontWeight: 700, color: '#2c312d' }}>
          {record.speaker || 'Story'}
          {record.turn_index !== undefined ? ` | Turn ${record.turn_index}` : ''}
          {record.timestamp ? ` | ${record.timestamp}` : ''}
        </Typography>
        <MixedRichText
          content={record.content}
          mode={mode}
          dialogueColor={isUser ? '#5a4035' : '#2d433c'}
          narrationColor="#7f8a84"
          fontSize="1rem"
        />
      </Box>
    );
  };

  if (!story && shouldHoldConclusion) {
    return (
      <Box
        sx={{
          minHeight: '100vh',
          background:
            'radial-gradient(900px 600px at 10% 20%, rgba(125,184,162,0.14), transparent 50%),' +
            'radial-gradient(800px 500px at 88% 10%, rgba(232,168,152,0.12), transparent 50%),' +
            'radial-gradient(700px 450px at 50% 90%, rgba(176,168,216,0.10), transparent 50%),' +
            'linear-gradient(160deg, #faf8f5 0%, #f3ede5 100%)',
          py: 5,
        }}
      >
        <Container maxWidth="sm">
          <Paper
            elevation={0}
            sx={{
              p: { xs: 3, sm: 4 },
              borderRadius: 4,
              background: 'rgba(255, 252, 246, 0.82)',
              backdropFilter: 'blur(16px)',
              border: '1px solid rgba(125, 184, 162, 0.18)',
              boxShadow: '0 20px 60px rgba(60, 50, 44, 0.08)',
            }}
          >
            <Stack spacing={2}>
              <Typography variant="h5" sx={{ fontWeight: 700, color: '#3c322c' }}>
                Preparing conclusion...
              </Typography>
              <Alert severity="info">
                The completed story snapshot is still loading. The page stays here until conclusion data is ready.
              </Alert>
            </Stack>
          </Paper>
        </Container>
      </Box>
    );
  }

  const handleStartNewJourney = async () => {
    clearReturnBenchmarkDetail();
    writeRestoredCurrentSessionId(null);
    setReturnBenchmarkDetail(null);
    setRestoredCurrentSessionId(null);
    if (isQuickTestSession && !isHistoricalBenchmarkView) {
      if (isQuickTestComplete) {
        clearExperimentSession();
        navigate('/');
        return;
      }
      setStartingNextQuickTest(true);
      try {
        await startExperimentSession(null, undefined, 0);
        navigate('/start');
      } catch (error) {
        if (axios.isAxiosError(error) && error.response?.status === 409) {
          clearExperimentSession();
          navigate('/');
          return;
        }
        setSnackbarSeverity('error');
        setSnackbarMsg('Failed to start the next test story.');
      } finally {
        setStartingNextQuickTest(false);
      }
      return;
    }
    navigate('/');
  };

  const handleExportResultJson = async () => {
    if (benchmarkSessionId && !isTemplateMode) {
      try {
        const response = await axios.get(`${API_BASE_URL}/experiments/sessions/${benchmarkSessionId}/export`);
        downloadJsonFile(getBenchmarkResultFilename(storyTitle), response.data);
        setSnackbarSeverity('success');
        setSnackbarMsg('Benchmark result JSON exported.');
      } catch (error) {
        console.error(error);
        setSnackbarSeverity('error');
        setSnackbarMsg('Failed to export benchmark result JSON.');
      }
      return;
    }

    if (!benchmarkExportPayload) {
      setSnackbarSeverity('error');
      setSnackbarMsg('No benchmark result payload is available to export.');
      return;
    }
    downloadJsonFile(getBenchmarkResultFilename(storyTitle), benchmarkExportPayload);
    setSnackbarSeverity('success');
    setSnackbarMsg('Benchmark result JSON exported.');
  };

  const handleBenchmarkFeedbackSaved = (feedback: Record<string, any>) => {
    setHistoryFeedbackLogs(prev => {
      const nextFeedbackLogs = upsertFeedbackLogs(prev, feedback);
      if (currentBenchmarkDetailForCache) {
        setLocalReviewHistory(upsertLocalBenchmarkReviewDetail({
          ...currentBenchmarkDetailForCache,
          feedback_logs: nextFeedbackLogs,
          participant_evaluation: feedback,
        }));
      }
      return nextFeedbackLogs;
    });
  };

  const openBenchmarkDetailAsConclusion = (detail: BenchmarkSessionDetail) => {
    loadHistoricalStory(buildReplayStoryFromDetail(detail));
    navigate('/conclusion');
  };

  const handleLoadPreviousBenchmark = (detail: BenchmarkSessionDetail) => {
    setPreviousRatingMenuAnchor(null);
    if (currentBenchmarkDetailForCache) {
      setLocalReviewHistory(upsertLocalBenchmarkReviewDetail(currentBenchmarkDetailForCache));
      writeReturnBenchmarkDetail(currentBenchmarkDetailForCache);
      setReturnBenchmarkDetail(currentBenchmarkDetailForCache);
    }
    writeRestoredCurrentSessionId(null);
    setRestoredCurrentSessionId(null);
    openBenchmarkDetailAsConclusion(detail);
  };

  const handlePreviousRatingClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    if (previousBenchmarkDetails.length === 1) {
      handleLoadPreviousBenchmark(previousBenchmarkDetails[0]);
      return;
    }
    setPreviousRatingMenuAnchor(event.currentTarget);
  };

  const handleReturnToCurrentBenchmark = () => {
    if (!returnBenchmarkDetail) {
      setSnackbarSeverity('error');
      setSnackbarMsg('No current round is available to return to.');
      return;
    }
    const returnSessionId = returnBenchmarkDetail.session.session_id || null;
    writeRestoredCurrentSessionId(returnSessionId);
    setRestoredCurrentSessionId(returnSessionId);
    clearReturnBenchmarkDetail();
    setReturnBenchmarkDetail(null);
    openBenchmarkDetailAsConclusion(returnBenchmarkDetail);
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        background:
          'radial-gradient(900px 600px at 10% 20%, rgba(125,184,162,0.14), transparent 50%),' +
          'radial-gradient(800px 500px at 88% 10%, rgba(232,168,152,0.12), transparent 50%),' +
          'radial-gradient(700px 450px at 50% 90%, rgba(176,168,216,0.10), transparent 50%),' +
          'linear-gradient(160deg, #faf8f5 0%, #f3ede5 100%)',
        py: 5,
      }}
    >
      <Container maxWidth="md">
        <Paper
          elevation={0}
          sx={{
            p: { xs: 3, sm: 5 },
            borderRadius: 4,
            background: 'rgba(255, 252, 246, 0.82)',
            backdropFilter: 'blur(16px)',
            border: '1px solid rgba(125, 184, 162, 0.18)',
            boxShadow: '0 20px 60px rgba(60, 50, 44, 0.08)',
          }}
        >
          <Box sx={{ textAlign: 'center', mb: 2 }}>
            <Typography
              variant="h4"
              sx={{
                fontWeight: 700,
                background: 'linear-gradient(135deg, #5a9a82 0%, #9890c4 100%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                mb: 1,
              }}
            >
              Your Journey Has Concluded
            </Typography>
            <Typography variant="body1" color="text.secondary">
              {isTemplateMode
                ? 'Benchmark template replay loaded for fast QA.'
                : isHistoricalBenchmarkView
                  ? 'Historical benchmark session loaded for review.'
                  : 'Thank you for sharing your story with us.'}
            </Typography>
          </Box>

          <Divider sx={{ mb: 4, borderColor: 'rgba(125,184,162,0.2)' }} />

          {isBenchmarkConclusionView && (
            <Box sx={{ mb: 4 }}>
              <Typography variant="h5" color="secondary" sx={{ mb: 1.5 }}>
                Benchmark Session
              </Typography>
              <Alert severity="info" sx={{ mb: 2 }}>
                {isBlindBenchmarkSession
                  ? isQuickTestSession
                    ? `Quick test code: ${benchmarkSessionRecord?.blind_code ?? 0} | Hidden slot ${benchmarkSessionRecord?.blind_session_index || 1}/${benchmarkSessionRecord?.blind_total_sessions || 4} | Completed runs: ${benchmarkSessionRecord?.quick_test_completed_runs || 0}${benchmarkSessionRecord?.blind_finished ? ' | Sequence complete' : ''}${benchmarkSessionRecord?.condition?.name ? ` | Condition: ${benchmarkSessionRecord.condition.name}` : ''}`
                    : `Invite code: ${benchmarkSessionRecord?.blind_invite_code || benchmarkSessionRecord?.blind_code || 'unknown'} | Round ${benchmarkSessionRecord?.blind_session_index || 1}/${benchmarkSessionRecord?.blind_total_sessions || 4} | Completed: ${benchmarkSessionRecord?.blind_completed_count || 0} | Remaining: ${benchmarkSessionRecord?.blind_remaining_count || 0}${benchmarkSessionRecord?.condition?.name ? ` | Condition: ${benchmarkSessionRecord.condition.name}` : ''}`
                  : `Participant: ${benchmarkHistory?.session?.participant_id || experimentSession?.participant_id || storyUserId || 'unknown'} | Model: ${benchmarkHistory?.session?.selected_model || experimentSession?.selected_model || 'unknown'}${benchmarkHistory?.session?.condition?.name ? ` | Condition: ${benchmarkHistory.session.condition.name}` : ''}`}
              </Alert>
            </Box>
          )}

          {isBenchmarkConclusionView && (
            <Box sx={{ mb: 4 }}>
              <Typography variant="h5" gutterBottom sx={{ color: 'text.primary', fontWeight: 600 }}>
                Full Dialogue Record
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                The conclusion view now keeps the complete conversation history visible so benchmark review, scoring, and export all happen in one place.
              </Typography>
              <Paper
                elevation={0}
                sx={{
                  height: 520,
                  overflowY: 'auto',
                  borderRadius: 3,
                  background: 'rgba(255,252,246,0.78)',
                  backdropFilter: 'blur(14px)',
                  border: '1px solid rgba(125,184,162,0.15)',
                  boxShadow: '0 4px 24px rgba(60,50,44,0.06)',
                  p: { xs: 1.5, sm: 2 },
                }}
              >
                {displayDialogueRecords.length > 0 ? (
                  <Stack spacing={1.25}>
                    {displayDialogueRecords.map(renderDialogueRecord)}
                  </Stack>
                ) : (
                  <Alert severity="info">No dialogue record is available for this conclusion view.</Alert>
                )}
              </Paper>
            </Box>
          )}

          <Box sx={{ mb: 4 }}>
            <Typography variant="h5" gutterBottom sx={{ color: 'text.primary', fontWeight: 600 }}>
              Reflections
            </Typography>

            <Card
              sx={{
                mb: 3,
                background: 'linear-gradient(145deg, rgba(253,244,235,0.95) 0%, rgba(245,238,228,0.9) 100%)',
                border: '1px solid rgba(232, 168, 152, 0.28)',
                boxShadow: '0 4px 20px rgba(200, 136, 122, 0.10)',
              }}
            >
              <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
                <Typography variant="body1" paragraph sx={{ color: '#5a3e2e' }}>
                  Throughout this story, you embarked on a journey of self-discovery and emotional healing.
                  You faced challenges related to <em>{storyTheme.toLowerCase()}</em> and found new ways to approach
                  your situation.
                </Typography>
                <Typography variant="body1" sx={{ color: '#5a3e2e' }}>
                  Remember that growth often comes from our most difficult moments, and the strength
                  you showed in this story reflects the strength you have in real life.
                </Typography>
              </CardContent>
            </Card>
          </Box>

          <Box sx={{ mb: 4 }}>
            <Typography variant="h5" gutterBottom sx={{ color: 'text.primary', fontWeight: 600 }}>
              Taking This Forward
            </Typography>

            <Typography variant="body1" paragraph color="text.secondary">
              The emotions and insights from this story do not have to end here. Consider how the
              perspectives you gained might apply to your daily life.
            </Typography>

            <Box
              sx={{
                pl: 3,
                borderLeft: '4px solid',
                borderColor: 'rgba(125, 184, 162, 0.5)',
                py: 1.5,
                mb: 3,
                background: 'rgba(232,245,240,0.4)',
                borderRadius: '0 12px 12px 0',
              }}
            >
              <Typography variant="body1" sx={{ fontStyle: 'italic', color: '#4a6e60', lineHeight: 1.9 }}>
                "The next time you face a similar challenge, remember how you navigated through
                this story. The resilience and wisdom you showed are qualities you already possess."
              </Typography>
            </Box>

            <Typography variant="body1" color="text.secondary">
              We hope this experience has offered emotional comfort and practical insights that can
              support your wellbeing going forward.
            </Typography>
          </Box>

          <Box sx={{ mt: 5, mb: 2 }}>
            {isBenchmarkConclusionView ? (
              <Stack spacing={2.4}>
                <Box
                  sx={{
                    border: '1px solid rgba(84, 101, 92, 0.18)',
                    background: 'linear-gradient(180deg, rgba(252,250,244,0.98) 0%, rgba(245,248,244,0.96) 100%)',
                    boxShadow: '0 20px 48px rgba(43, 53, 47, 0.09)',
                    px: { xs: 2, sm: 3.5 },
                    py: { xs: 2, sm: 2.8 },
                  }}
                >
                  <Stack spacing={1.1}>
                    <Typography variant="body2" sx={{ color: 'rgba(55, 69, 61, 0.82)', lineHeight: 1.8 }}>
                      Read each prompt as an anchored rating item. Story items focus on the quality of the final narrative itself, while user-experience items focus on the experience of using the system.
                    </Typography>
                    <Typography variant="body2" sx={{ color: 'rgba(55, 69, 61, 0.82)', lineHeight: 1.8 }}>
                      Session record: story {storyTitle}, {isBlindBenchmarkSession ? (isQuickTestSession ? `quick test slot ${benchmarkSessionRecord?.blind_session_index || 1}/${benchmarkSessionRecord?.blind_total_sessions || 4}` : `blind round ${benchmarkSessionRecord?.blind_session_index || 1}/${benchmarkSessionRecord?.blind_total_sessions || 4}`) : `model ${benchmarkHistory?.session?.selected_model || experimentSession?.selected_model || 'n/a'}`}, dialogue record {displayDialogueRecords.length} blocks.
                    </Typography>
                    <Typography variant="body2" sx={{ color: 'rgba(55, 69, 61, 0.82)', lineHeight: 1.8 }}>
                      Saved benchmark responses remain visible below for comparison and re-evaluation.
                    </Typography>
                  </Stack>

                  {historyFeedbackLogs.length > 0 && (
                    <Box sx={{ mt: 2.2 }}>
                      <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1.1, color: '#26352d' }}>
                        Saved Benchmark Ratings
                      </Typography>
                      <Stack spacing={1}>
                        {historyFeedbackLogs.map(log => (
                          <Box key={log.id || `${log.feedback_type}-${log.created_at}`}>
                            <Typography variant="body2" sx={{ fontWeight: 700, color: '#2c3b33', lineHeight: 1.75 }}>
                              Overall story score: {log.rating ?? 'n/a'}/5
                            </Typography>
                            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25, lineHeight: 1.75 }}>
                              Rubric: {getBenchmarkRubricVersionLabel(log.form_version)}
                              {isLegacyBenchmarkRubricFeedback(log) ? ' | Needs re-evaluation with the current rubric' : ''}
                            </Typography>
                            {log.created_at && (
                              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25, lineHeight: 1.75 }}>
                                Saved at {log.created_at}
                              </Typography>
                            )}
                            {log.comment && (
                              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, lineHeight: 1.7 }}>
                                {log.comment}
                              </Typography>
                            )}
                          </Box>
                        ))}
                      </Stack>
                    </Box>
                  )}

                </Box>
                {isBlindBenchmarkSession && !isHistoricalBenchmarkView && !hasPreviousBenchmarkDetails && (
                  <Alert severity="info">
                    Previous round review will appear here after this browser has completed at least two hidden-slot stories.
                  </Alert>
                )}

                {canUsePreviousRating && (
                  <Alert severity="info">
                    Previous round ratings are available from this browser. Use the bottom Previous Rating button to replace this page with a prior round.
                  </Alert>
                )}

                <BenchmarkEvaluationForm
                  storyId={storyId}
                  userId={storyUserId}
                  sessionId={benchmarkHistory?.session?.session_id || experimentSession?.session_id || null}
                  participantId={benchmarkHistory?.session?.participant_id || experimentSession?.participant_id || null}
                  existingFeedback={existingBenchmarkFeedback}
                  templateMode={isTemplateMode}
                  onFeedbackSaved={handleBenchmarkFeedbackSaved}
                />
              </Stack>
            ) : (
              <FeedbackWidget
                storyId={storyId}
                userId={storyUserId}
                mode="inline"
                feedbackType="session_end"
              />
            )}
          </Box>

          <Box sx={{ textAlign: 'center', mt: 4, display: 'flex', justifyContent: 'center', gap: 2, flexWrap: 'wrap' }}>
            {isPreviousRatingReviewView ? (
              <Button
                variant="outlined"
                color="info"
                size="large"
                onClick={handleReturnToCurrentBenchmark}
                sx={{ borderRadius: 28, px: 3, py: 1.5 }}
              >
                Return to Current Round
              </Button>
            ) : canUsePreviousRating && (
              <>
                <Button
                  variant="outlined"
                  color="info"
                  size="large"
                  aria-controls={previousRatingMenuAnchor ? 'previous-rating-menu' : undefined}
                  aria-haspopup={previousBenchmarkDetails.length > 1 ? 'menu' : undefined}
                  onClick={handlePreviousRatingClick}
                  sx={{ borderRadius: 28, px: 3, py: 1.5 }}
                >
                  Previous Rating
                </Button>
                {previousBenchmarkDetails.length > 1 && (
                  <Menu
                    id="previous-rating-menu"
                    anchorEl={previousRatingMenuAnchor}
                    open={Boolean(previousRatingMenuAnchor)}
                    onClose={() => setPreviousRatingMenuAnchor(null)}
                  >
                    {previousBenchmarkDetails.map(detail => (
                      <MenuItem
                        key={detail.session.session_id}
                        onClick={() => handleLoadPreviousBenchmark(detail)}
                      >
                        <ListItemText
                          primary={getBenchmarkDetailLabel(detail)}
                          secondary={detail.session.completed_at || detail.session.started_at || detail.session.session_id}
                        />
                      </MenuItem>
                    ))}
                  </Menu>
                )}
              </>
            )}
            {isBenchmarkConclusionView && (
              <Button
                variant="outlined"
                color="secondary"
                size="large"
                onClick={handleExportResultJson}
                sx={{ borderRadius: 28, px: 3, py: 1.5 }}
              >
                Export Result JSON
              </Button>
            )}
            {!isPreviousRatingReviewView && (
              <Button
                variant="contained"
                color="primary"
                size="large"
                onClick={handleStartNewJourney}
                disabled={startingNextQuickTest}
                sx={{ borderRadius: 28, px: 4, py: 1.5 }}
              >
                {isQuickTestSession && !isHistoricalBenchmarkView
                  ? isQuickTestComplete
                    ? 'Return to Start'
                    : (startingNextQuickTest ? 'Starting Next Test Story...' : 'Start Next Test Story')
                  : canStartNextQuickTest
                  ? (startingNextQuickTest ? 'Starting Next Test Story...' : 'Start Next Test Story')
                  : 'Begin a New Journey'}
              </Button>
            )}
          </Box>
        </Paper>
      </Container>

      <Snackbar
        open={!!snackbarMsg}
        autoHideDuration={4000}
        onClose={() => setSnackbarMsg(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity={snackbarSeverity} onClose={() => setSnackbarMsg(null)} sx={{ width: '100%' }}>
          {snackbarMsg}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default StoryConclusion;
