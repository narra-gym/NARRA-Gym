import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Alert,
  Box, 
  TextField, 
  Typography, 
  Paper, 
  Container,
  CircularProgress
} from '@mui/material';
import axios from 'axios';
import JourneyButton from '../components/JourneyButton';
import ShaderBackground from '../components/ShaderBackground';
import { API_BASE_URL, useStory } from '../contexts/StoryContext';

const EmotionalNeedForm: React.FC = () => {
  const [emotionalNeed, setEmotionalNeed] = useState('');
  const [autoLaunchingTest, setAutoLaunchingTest] = useState(false);
  const [autoLaunchError, setAutoLaunchError] = useState<string | null>(null);
  const navigate = useNavigate();
  const autoLaunchAttemptedRef = useRef(false);
  const { initiateStory, loading, error, experimentMode, experimentSession, loadHistoricalStory } = useStory();
  const quickTestMode = Boolean(experimentSession?.blind_mode && experimentSession?.blind_code === 0);

  useEffect(() => {
    if (!quickTestMode || autoLaunchAttemptedRef.current) {
      return;
    }

    autoLaunchAttemptedRef.current = true;
    setAutoLaunchingTest(true);
    setAutoLaunchError(null);

    const launchQuickTestStory = async () => {
      try {
        const response = await axios.post(`${API_BASE_URL}/stories/quickstart`, {
          user_id: experimentSession?.participant_id || null,
          participant_id: experimentSession?.participant_id || null,
          session_id: experimentSession?.session_id,
        });
        loadHistoricalStory(response.data);
        navigate('/story/interaction');
      } catch (err) {
        autoLaunchAttemptedRef.current = false;
        console.error('Failed to auto-launch quick test story:', err);
        setAutoLaunchError('Failed to open the quick test story. Please try again.');
      } finally {
        setAutoLaunchingTest(false);
      }
    };

    launchQuickTestStory();
  }, [experimentSession?.participant_id, experimentSession?.session_id, loadHistoricalStory, navigate, quickTestMode]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!emotionalNeed.trim() || loading) return;
    
    try {
      await initiateStory(emotionalNeed);
      navigate('/clarify-questions'); // Navigate to the new questions form
    } catch (err) {
      console.error('Failed to initialize story:', err);
      // Error is handled globally in context, but you could add specific UI here if needed
    }
  };

  return (
    <Box sx={{ position: 'fixed', inset: 0, overflow: 'auto' }}>
      <Box sx={{ position: 'absolute', inset: 0, zIndex: 0 }}>
        <ShaderBackground />
        <Box sx={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.52)' }} />
      </Box>

      <Container maxWidth="sm" sx={{ pt: 12, pb: 6, position: 'relative', zIndex: 1 }}>
        <Paper
          elevation={0}
          sx={{
            p: { xs: 3, sm: 5 },
            borderRadius: '18px',
            background: 'linear-gradient(180deg, rgba(248, 243, 235, 0.92), rgba(242, 235, 226, 0.88))',
            backdropFilter: 'saturate(180%) blur(20px)',
            WebkitBackdropFilter: 'saturate(180%) blur(20px)',
            border: '1px solid var(--emo-glass-border)',
            boxShadow: '0 18px 42px rgba(32,24,20,0.16)',
          }}
        >
          <Typography variant="h4" component="h1" gutterBottom align="center"
            sx={{ color: 'var(--emo-ink)', fontWeight: 700, letterSpacing: '-0.01em', mb: 1.5 }}
          >
            Start Your Journey
          </Typography>

          <Typography variant="body1" paragraph align="center"
            sx={{ mb: 4, color: 'var(--emo-ink-soft)', lineHeight: 1.7, fontWeight: 500 }}
          >
            {quickTestMode
              ? 'Quick test mode is preparing a default benchmark world for you now.'
              : `Share what's on your mind, and we'll create a personalized interactive story
            to help you explore your emotions and discover new perspectives.`}
          </Typography>

          {experimentMode && (
            <Alert
              severity="info"
              sx={{
                mb: 3,
                backgroundColor: 'rgba(255, 249, 241, 0.92)',
                color: 'var(--emo-ink-soft)',
                border: '1px solid rgba(115, 85, 72, 0.16)',
                boxShadow: '0 8px 20px rgba(56, 38, 28, 0.08)',
                '& .MuiAlert-message': { color: 'var(--emo-ink-soft)', fontWeight: 500 },
                '& .MuiAlert-icon': { color: 'var(--emo-accent)' },
              }}
            >
              Benchmark tips: first-person prompts work best when they describe a concrete emotional situation, a specific relationship, and a real decision or tension.
              Examples: "My parents want me to stay in a stable job, but I want to quit and I feel guilty." "A close friend has been avoiding me and I can't decide whether to confront them or let it go." "I still replay my breakup every night and I can't tell whether I miss them or the version of myself I was back then."
            </Alert>
          )}

          {quickTestMode ? (
            <Box sx={{ py: 3, textAlign: 'center' }}>
              <CircularProgress />
              <Typography variant="body2" sx={{ mt: 2, color: 'var(--emo-ink-soft)', fontWeight: 600 }}>
                {autoLaunchingTest ? 'Preparing the default quick test story...' : 'Retrying the quick test story launch...'}
              </Typography>
              {(autoLaunchError || error) && (
                <Typography variant="body2" sx={{ mt: 2, color: '#a33b3b', fontWeight: 600 }}>
                  {autoLaunchError || error}
                </Typography>
              )}
            </Box>
          ) : (
            <form onSubmit={handleSubmit}>
              <TextField
                fullWidth
                placeholder="e.g., I'm feeling overwhelmed with work and struggling to find balance..."
                multiline rows={4}
                value={emotionalNeed}
                onChange={(e) => setEmotionalNeed(e.target.value)}
                variant="outlined" margin="normal" required
                sx={{
                  mb: 3,
                  '& .MuiInputBase-root': {
                    backgroundColor: 'rgba(255, 250, 245, 0.92)',
                    borderRadius: '10px',
                    color: 'var(--emo-ink)',
                  },
                  '& .MuiInputBase-input': {
                    color: 'var(--emo-ink)',
                    fontWeight: 500,
                  },
                  '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(115, 85, 72, 0.22)' },
                  '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(115, 85, 72, 0.38)' },
                  '& .MuiOutlinedInput-root.Mui-focused .MuiOutlinedInput-notchedOutline': {
                    borderColor: 'var(--emo-accent)',
                    borderWidth: 1,
                    boxShadow: '0 0 0 3px rgba(115, 85, 72, 0.14)',
                  },
                  '& .MuiInputBase-input::placeholder': { color: 'var(--emo-ink-muted)', opacity: 1 },
                }}
              />

              {error && (
                <Typography variant="body2" sx={{ mb: 2, color: '#a33b3b', fontWeight: 600 }}>{error}</Typography>
              )}

              <Box sx={{ display: 'flex', justifyContent: 'center' }}>
                <JourneyButton
                  type="submit"
                  label="Begin Your Journey"
                  disabled={!emotionalNeed.trim()}
                  loading={loading}
                />
              </Box>

              <Typography variant="body2" align="center"
                sx={{ mt: 3, color: 'var(--emo-ink-muted)', lineHeight: 1.7, fontWeight: 500 }}
              >
                Your story is personalized to what you share.
                The more you open up, the deeper the journey.
              </Typography>
            </form>
          )}
        </Paper>
      </Container>
    </Box>
  );
};

export default EmotionalNeedForm; 
