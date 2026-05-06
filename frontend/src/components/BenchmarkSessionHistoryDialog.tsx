import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  Divider,
  Stack,
  Typography,
} from '@mui/material';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../contexts/StoryContext';
import { useStory } from '../contexts/StoryContext';
import { BenchmarkSessionDetail } from '../types';
import {
  buildReplayStoryFromDetail,
  downloadJsonFile,
  getBenchmarkResultFilename,
  mergeAdjacentBenchmarkDialogueRecords,
} from '../utils/benchmarkHistory';

interface Props {
  open: boolean;
  sessionId: string | null;
  onClose: () => void;
}

const BenchmarkSessionHistoryDialog: React.FC<Props> = ({ open, sessionId, onClose }) => {
  const navigate = useNavigate();
  const { loadHistoricalStory } = useStory();
  const [detail, setDetail] = useState<BenchmarkSessionDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const displayDialogue = mergeAdjacentBenchmarkDialogueRecords(detail?.dialogue || []);

  const handleOpenFinalView = () => {
    if (!detail) {
      return;
    }
    loadHistoricalStory(buildReplayStoryFromDetail(detail));
    onClose();
    navigate('/conclusion');
  };

  const handleExportJson = async () => {
    if (!detail) {
      return;
    }
    setExporting(true);
    try {
      const response = await axios.get(`${API_BASE_URL}/experiments/sessions/${detail.session.session_id}/export`);
      downloadJsonFile(
        getBenchmarkResultFilename(
          detail.final_view_story?.title || detail.story_snapshot?.title || detail.session.session_id,
        ),
        response.data,
      );
    } catch (err) {
      console.error(err);
      setError('Failed to export benchmark result JSON for this session.');
    } finally {
      setExporting(false);
    }
  };

  useEffect(() => {
    if (!open || !sessionId) {
      setDetail(null);
      setLoading(false);
      setError(null);
      return;
    }

    let mounted = true;

    const fetchDetail = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await axios.get(`${API_BASE_URL}/experiments/sessions/${sessionId}`);
        if (mounted) {
          setDetail(response.data as BenchmarkSessionDetail);
        }
      } catch (err) {
        console.error(err);
        if (mounted) {
          setError('Failed to load benchmark history for this session.');
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };

    fetchDetail();

    return () => {
      mounted = false;
    };
  }, [open, sessionId]);

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>
        Benchmark History
      </DialogTitle>
      <DialogContent dividers>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
            <CircularProgress />
          </Box>
        ) : error ? (
          <Alert severity="error">{error}</Alert>
        ) : detail ? (
          <Stack spacing={2}>
            <Box>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                Session Overview
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {detail.session.blind_mode
                  ? detail.session.quick_test_mode
            ? `Quick test code: ${detail.session.blind_code ?? 0} | Hidden slot ${detail.session.blind_session_index || 1}/${detail.session.blind_total_sessions || 4} | Completed runs: ${detail.session.quick_test_completed_runs || 0}${detail.session.blind_finished ? ' | Sequence complete' : ''} | Condition: ${detail.session.condition?.name}`
                    : `Invite code: ${detail.session.blind_invite_code || detail.session.blind_code || 'unknown'} | Round ${detail.session.blind_session_index || 1}/${detail.session.blind_total_sessions || 4} | Condition: ${detail.session.condition?.name}`
                  : `Participant: ${detail.session.participant_id} | Model: ${detail.session.selected_model} | Condition: ${detail.session.condition?.name}`}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Started: {detail.session.started_at} {detail.session.completed_at ? `| Completed: ${detail.session.completed_at}` : ''}
              </Typography>
              <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: 'wrap' }}>
                <Chip size="small" label={`Dialogue source: ${detail.dialogue_source}`} />
                <Chip size="small" label={`Turns: ${detail.turn_logs.length}`} />
                <Chip size="small" label={`Feedback: ${detail.feedback_logs.length}`} />
              </Stack>
              <Box sx={{ mt: 1.5, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                <Button variant="contained" onClick={handleOpenFinalView}>
                  Open Conclusion View
                </Button>
                <Button variant="outlined" onClick={handleExportJson} disabled={exporting}>
                  {exporting ? 'Exporting...' : 'Export Result JSON'}
                </Button>
              </Box>
              {!detail.final_view_story && detail.turn_logs.length > 0 && (
                <Alert severity="info" sx={{ mt: 1.5 }}>
                  This older session does not have a persisted final scene snapshot, so the view below is reconstructed from turn logs. New completed sessions will preserve the ending state for direct replay.
                </Alert>
              )}
            </Box>

            {detail.feedback_logs.length > 0 && (
              <Box>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                  Saved Ratings
                </Typography>
                <Stack spacing={1}>
                  {detail.feedback_logs.map(log => (
                    <Box
                      key={log.id}
                      sx={{
                        p: 1.5,
                        borderRadius: 2,
                        background: 'rgba(125,184,162,0.08)',
                        border: '1px solid rgba(125,184,162,0.18)',
                      }}
                    >
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>
                        {log.feedback_type || 'feedback'} | rating {log.rating}
                      </Typography>
                      {log.comment && (
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                          {log.comment}
                        </Typography>
                      )}
                    </Box>
                  ))}
                </Stack>
              </Box>
            )}

            <Divider />

            <Box>
              <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>
                Dialogue Record
              </Typography>
              <Stack spacing={1.25} sx={{ maxHeight: 460, overflowY: 'auto', pr: 0.5 }}>
                {displayDialogue.map(record => (
                  <Box
                    key={record.id}
                    sx={{
                      p: 1.5,
                      borderRadius: 2,
                      background: record.role === 'user'
                        ? 'rgba(232,168,152,0.10)'
                        : record.role === 'system'
                          ? 'rgba(111,143,176,0.10)'
                          : 'rgba(125,184,162,0.10)',
                      border: '1px solid rgba(60,50,44,0.10)',
                    }}
                  >
                    <Typography variant="caption" sx={{ fontWeight: 700, display: 'block', mb: 0.4 }}>
                      {record.speaker}
                      {record.turn_index !== undefined ? ` | Turn ${record.turn_index}` : ''}
                      {record.timestamp ? ` | ${record.timestamp}` : ''}
                    </Typography>
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>
                      {record.content}
                    </Typography>
                  </Box>
                ))}
                {displayDialogue.length === 0 && (
                  <Alert severity="info">No persisted dialogue was found for this session.</Alert>
                )}
              </Stack>
            </Box>
          </Stack>
        ) : (
          <Alert severity="info">Select a historical benchmark session to inspect its data.</Alert>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default BenchmarkSessionHistoryDialog;
