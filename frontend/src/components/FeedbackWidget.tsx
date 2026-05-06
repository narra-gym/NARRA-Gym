import React, { useState } from 'react';
import {
  Box,
  Typography,
  Button,
  TextField,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Fab,
  Zoom,
} from '@mui/material';
import StarIcon from '@mui/icons-material/Star';
import StarBorderIcon from '@mui/icons-material/StarBorder';
import CloseIcon from '@mui/icons-material/Close';
import FavoriteIcon from '@mui/icons-material/Favorite';
import axios from 'axios';
import { API_BASE_URL, useStory } from '../contexts/StoryContext';

const FEELING_TAGS = [
  { label: '🌿 Healing', value: 'healed' },
  { label: '💫 Understood', value: 'understood' },
  { label: '☀️ Hopeful', value: 'hopeful' },
  { label: '🌊 Calming', value: 'calmed' },
  { label: '🌸 Warm', value: 'warm' },
  { label: '✨ Insightful', value: 'learned' },
  { label: '🤔 Thought-provoking', value: 'reflective' },
  { label: '🎭 Immersive', value: 'immersed' },
];

const STAR_LABELS = ['', 'Disappointing', 'It was okay', 'Pretty good', 'Loved it', 'Truly healing'];

interface Props {
  storyId?: string;
  userId?: string;
  /** 'floating' = bottom-right FAB, 'inline' = embedded form */
  mode?: 'floating' | 'inline';
  feedbackType?: string;
  onSubmitted?: () => void;
}

const FeedbackWidget: React.FC<Props> = ({
  storyId,
  userId,
  mode = 'floating',
  feedbackType = 'general',
  onSubmitted,
}) => {
  const { experimentSession } = useStory();
  const [open, setOpen] = useState(false);
  const [rating, setRating] = useState(0);
  const [hoverRating, setHoverRating] = useState(0);
  const [selectedFeelings, setSelectedFeelings] = useState<string[]>([]);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const activeRating = hoverRating || rating;

  const toggleFeeling = (value: string) => {
    setSelectedFeelings(prev =>
      prev.includes(value) ? prev.filter(f => f !== value) : [...prev, value]
    );
  };

  const handleSubmit = async () => {
    if (rating === 0) return;
    setSubmitting(true);
    try {
      await axios.post(`${API_BASE_URL}/feedback`, {
        story_id: storyId,
        user_id: userId,
        participant_id: experimentSession?.participant_id || null,
        session_id: experimentSession?.session_id || null,
        rating,
        feelings: selectedFeelings,
        comment: comment.trim() || null,
        feedback_type: feedbackType,
      });
      setSubmitted(true);
      setTimeout(() => {
        setOpen(false);
        // Reset after dialog closes
        setTimeout(() => {
          setSubmitted(false);
          setRating(0);
          setSelectedFeelings([]);
          setComment('');
        }, 300);
        onSubmitted?.();
      }, 2000);
    } catch {
      // silent fail — feedback should never block the user
    } finally {
      setSubmitting(false);
    }
  };

  const handleClose = () => {
    if (!submitting) setOpen(false);
  };

  // ── Success screen ───────────────────────────────────────────────────────
  const successScreen = (
    <Box sx={{ textAlign: 'center', py: mode === 'inline' ? 2 : 3 }}>
      <Box
        component="span"
        sx={{
          fontSize: '2.8rem',
          display: 'block',
          mb: 1,
          animation: 'feedbackBounce 0.6s cubic-bezier(0.34,1.56,0.64,1)',
          '@keyframes feedbackBounce': {
            '0%': { transform: 'scale(0)' },
            '100%': { transform: 'scale(1)' },
          },
        }}
      >
        🌿
      </Box>
      <Typography variant="h6" sx={{ fontWeight: 700, color: '#3c322c', mb: 0.5 }}>
        Thank you for your feedback!
      </Typography>
      <Typography variant="body2" color="text.secondary">
        Your voice makes every story more healing
      </Typography>
    </Box>
  );

  // ── Form content ─────────────────────────────────────────────────────────
  const formContent = (
    <Box>
      {/* Star rating */}
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', mb: 2.5 }}>
        <Box sx={{ display: 'flex', gap: 0.5 }}>
          {[1, 2, 3, 4, 5].map(star => (
            <IconButton
              key={star}
              disableRipple
              onMouseEnter={() => setHoverRating(star)}
              onMouseLeave={() => setHoverRating(0)}
              onClick={() => setRating(star)}
              sx={{
                p: 0.4,
                transition: 'transform 0.18s cubic-bezier(0.34,1.56,0.64,1)',
                transform: activeRating >= star ? 'scale(1.22)' : 'scale(1)',
              }}
            >
              {activeRating >= star ? (
                <StarIcon sx={{ fontSize: 34, color: '#f5c842', filter: 'drop-shadow(0 2px 6px rgba(245,200,66,0.5))' }} />
              ) : (
                <StarBorderIcon sx={{ fontSize: 34, color: 'rgba(140,120,100,0.28)' }} />
              )}
            </IconButton>
          ))}
        </Box>
        <Typography
          variant="caption"
          sx={{
            mt: 0.5,
            color: rating > 0 ? '#7db8a2' : 'text.disabled',
            fontWeight: 600,
            minHeight: '1.2em',
            transition: 'color 0.2s',
          }}
        >
          {rating > 0 ? STAR_LABELS[rating] : 'Tap a star to rate'}
        </Typography>
      </Box>

      {/* Feeling chips */}
      <Typography
        variant="caption"
        sx={{
          display: 'block',
          mb: 1,
          textAlign: 'center',
          color: 'text.secondary',
          letterSpacing: '0.03em',
        }}
      >
        This experience made you feel… <span style={{ opacity: 0.6 }}>(select multiple)</span>
      </Typography>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.7, justifyContent: 'center', mb: 2.5 }}>
        {FEELING_TAGS.map(f => {
          const active = selectedFeelings.includes(f.value);
          return (
            <Chip
              key={f.value}
              label={f.label}
              onClick={() => toggleFeeling(f.value)}
              size="small"
              sx={{
                borderRadius: '16px',
                fontWeight: active ? 700 : 500,
                fontSize: '0.75rem',
                cursor: 'pointer',
                transition: 'all 0.2s',
                background: active
                  ? 'linear-gradient(135deg, #7db8a2 0%, #b0a8d8 100%)'
                  : 'transparent',
                color: active ? '#fff' : 'text.secondary',
                border: active ? 'none' : '1px solid rgba(125,184,162,0.35)',
                boxShadow: active ? '0 3px 12px rgba(125,184,162,0.35)' : 'none',
                transform: active ? 'scale(1.05)' : 'scale(1)',
                '&:hover': {
                  borderColor: 'rgba(125,184,162,0.7)',
                  background: active
                    ? 'linear-gradient(135deg, #5a9a82 0%, #9890c4 100%)'
                    : 'rgba(125,184,162,0.08)',
                },
              }}
            />
          );
        })}
      </Box>

      {/* Comment */}
      <TextField
        multiline
        rows={2}
        fullWidth
        placeholder="Anything else you'd like to share? (optional)"
        value={comment}
        onChange={e => setComment(e.target.value)}
        size="small"
        inputProps={{ maxLength: 200 }}
        sx={{
          '& .MuiOutlinedInput-root': {
            borderRadius: 3,
            fontSize: '0.85rem',
            background: 'rgba(255,252,246,0.7)',
          },
        }}
        helperText={comment.length > 0 ? `${comment.length}/200` : undefined}
        FormHelperTextProps={{ sx: { textAlign: 'right', mr: 0 } }}
      />
    </Box>
  );

  // ── Inline mode ──────────────────────────────────────────────────────────
  if (mode === 'inline') {
    return (
      <Box
        sx={{
          p: 3,
          borderRadius: 4,
          background: 'rgba(125,184,162,0.07)',
          border: '1px solid rgba(125,184,162,0.18)',
          backdropFilter: 'blur(8px)',
        }}
      >
        {submitted ? (
          successScreen
        ) : (
          <>
            <Typography
              variant="h6"
              sx={{ fontWeight: 700, color: '#3c322c', mb: 0.4, textAlign: 'center' }}
            >
              💬 How was the journey?
            </Typography>
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ mb: 2.5, textAlign: 'center', fontSize: '0.82rem' }}
            >
              Share how you feel — help us craft a better healing experience
            </Typography>
            {formContent}
            <Button
              variant="contained"
              color="primary"
              fullWidth
              onClick={handleSubmit}
              disabled={rating === 0 || submitting}
              sx={{ mt: 2.5, borderRadius: 20, py: 1.3, fontWeight: 700 }}
            >
              {submitting ? 'Submitting…' : 'Submit Feedback'}
            </Button>
          </>
        )}
      </Box>
    );
  }

  // ── Floating mode ────────────────────────────────────────────────────────
  return (
    <>
      <Zoom in>
        <Fab
          size="small"
          onClick={() => setOpen(true)}
          title="Share your feelings"
          sx={{
            position: 'fixed',
            bottom: 28,
            right: 28,
            width: 48,
            height: 48,
            background: 'linear-gradient(135deg, #7db8a2, #b0a8d8)',
            color: '#fff',
            boxShadow: '0 4px 20px rgba(125,184,162,0.45)',
            zIndex: 1200,
            transition: 'all 0.25s',
            '&:hover': {
              background: 'linear-gradient(135deg, #5a9a82, #9890c4)',
              transform: 'scale(1.12)',
              boxShadow: '0 6px 24px rgba(125,184,162,0.55)',
            },
          }}
        >
          <FavoriteIcon sx={{ fontSize: 20 }} />
        </Fab>
      </Zoom>

      <Dialog
        open={open}
        onClose={handleClose}
        maxWidth="xs"
        fullWidth
        TransitionProps={{ timeout: 300 }}
        PaperProps={{
          sx: {
            borderRadius: 5,
            background: 'rgba(255,252,246,0.96)',
            backdropFilter: 'blur(20px)',
            boxShadow: '0 32px 80px rgba(60,50,44,0.18)',
          },
        }}
      >
        <DialogTitle sx={{ pb: 0, pt: 3, textAlign: 'center', position: 'relative' }}>
          {!submitted && (
            <IconButton
              onClick={handleClose}
              size="small"
              sx={{
                position: 'absolute',
                right: 12,
                top: 12,
                color: 'text.secondary',
                '&:hover': { color: 'text.primary' },
              }}
            >
              <CloseIcon fontSize="small" />
            </IconButton>
          )}
          <Typography variant="h6" sx={{ fontWeight: 700, color: '#3c322c' }}>
            💬 Share Your Feelings
          </Typography>
          {!submitted && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.3, fontSize: '0.8rem' }}>
              Your feedback helps us do better
            </Typography>
          )}
        </DialogTitle>

        <DialogContent sx={{ pt: 2.5, pb: submitted ? 3 : 1 }}>
          {submitted ? successScreen : formContent}
        </DialogContent>

        {!submitted && (
          <DialogActions sx={{ px: 3, pb: 3, gap: 1 }}>
            <Button
              onClick={handleClose}
              disabled={submitting}
              sx={{ borderRadius: 20, color: 'text.secondary', flex: 1 }}
            >
              Maybe Later
            </Button>
            <Button
              variant="contained"
              color="primary"
              onClick={handleSubmit}
              disabled={rating === 0 || submitting}
              sx={{ borderRadius: 20, px: 3, flex: 2, fontWeight: 700, py: 1.1 }}
            >
              {submitting ? 'Submitting…' : 'Submit Feedback'}
            </Button>
          </DialogActions>
        )}
      </Dialog>
    </>
  );
};

export default FeedbackWidget;
