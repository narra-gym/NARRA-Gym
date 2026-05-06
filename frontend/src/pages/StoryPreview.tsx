import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Typography,
  Paper,
  Container,
  CircularProgress,
  Stack,
  Fade,
} from '@mui/material';
import { useStory } from '../contexts/StoryContext';
import SpacetimeWarp from '../components/SpacetimeWarp';
import ShaderBackground from '../components/ShaderBackground';
import { resolveAssetUrl } from '../utils/assetUrl';

const dossierFrameSx = {
  position: 'relative',
  overflow: 'hidden',
  p: { xs: 3, md: 5 },
  borderRadius: 0,
  background: 'linear-gradient(180deg, rgba(242,233,210,0.98) 0%, rgba(226,212,182,0.96) 100%)',
  border: '1px solid rgba(79,55,31,0.78)',
  boxShadow: '0 0 0 2px rgba(112,83,47,0.18) inset, 0 24px 54px rgba(11,8,6,0.34)',
  backdropFilter: 'blur(6px)',
  '&::before': {
    content: '""',
    position: 'absolute',
    inset: 10,
    border: '1px solid rgba(115,84,48,0.22)',
    pointerEvents: 'none',
  },
} as const;

const archivalPanelSx = {
  position: 'relative',
  borderRadius: 0,
  p: { xs: 2, md: 2.5 },
  background: 'linear-gradient(180deg, rgba(249,244,231,0.96) 0%, rgba(236,225,198,0.92) 100%)',
  border: '1px solid rgba(103,75,45,0.45)',
  boxShadow: 'inset 0 1px 0 rgba(255,247,227,0.82), 0 10px 24px rgba(64,47,28,0.08)',
} as const;

const characterDossierSx = {
  ...archivalPanelSx,
  flex: 1,
  minWidth: 0,
  display: 'flex',
  flexDirection: 'column',
  gap: 1.4,
} as const;

const portraitFrameSx = {
  alignSelf: 'center',
  width: '100%',
  maxWidth: 260,
  px: 1.4,
  py: 1.6,
  borderRadius: 0,
  background: 'linear-gradient(180deg, rgba(84,62,39,0.08) 0%, rgba(84,62,39,0.02) 100%)',
  border: '1px solid rgba(103,75,45,0.35)',
  boxShadow: 'inset 0 0 0 1px rgba(255,249,236,0.62)',
} as const;

const StoryPreview: React.FC = () => {
  const navigate = useNavigate();
  const { story, loading } = useStory();
  const [starting, setStarting] = React.useState(false);

  // Add an effect to redirect if no story is available
  React.useEffect(() => {
    if (!loading && !story) {
      navigate('/');
    }
  }, [story, loading, navigate]);

  const handleBeginStory = () => {
    // Trigger fade-out animation, then navigate
    setStarting(true);
    // Delay navigation slightly longer than Fade timeout
    setTimeout(() => {
      navigate('/story/interaction');
    }, 600);
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <CircularProgress />
        <Typography sx={{ mt: 2, color: 'text.secondary' }}>Crafting your personalized story...</Typography>
      </Box>
    );
  }

  if (!story) {
    return null; // Will be redirected by the useEffect
  }

  const protagonist = story.characters.find(c => c.role === 'protagonist');
  const npcs = story.characters.filter(c => c.role === 'npc');
  const firstScene = story.currentScene;
  // Build immersive blurb
  const immersiveLines: string[] = [];
  if (protagonist) immersiveLines.push(`You are ${protagonist.name}.`);
  if (typeof story.setting === 'string') {
    immersiveLines.push(`Current location: ${story.setting}.`);
  } else {
    if (story.setting.primary_location) immersiveLines.push(`Current location: ${story.setting.primary_location}.`);
    if (story.setting.atmosphere) immersiveLines.push(`It feels ${story.setting.atmosphere.toLowerCase()}.`);
  }
  if ((firstScene as any).inciting_incident) immersiveLines.push((firstScene as any).inciting_incident);

  const introText = immersiveLines.join(' ');

  return (
    <Fade in={!starting} timeout={500}>
      <Box sx={{ position: 'relative' }}>
        <Box sx={{ position: 'fixed', inset: 0 }}>
          <ShaderBackground />
          <Box sx={{ position: 'absolute', inset: 0, background: 'linear-gradient(180deg, rgba(19,12,7,0.54) 0%, rgba(34,24,17,0.66) 100%)' }} />
        </Box>
        <Container maxWidth="lg" sx={{ mt: 6, mb: 6, position: 'relative', zIndex: 1 }}>
          <Paper elevation={3} sx={dossierFrameSx}>
            <Typography
              variant="overline"
              component="p"
              align="center"
              sx={{ display: 'block', color: '#7b5836', letterSpacing: '0.22em', fontWeight: 700, mb: 1.25 }}
            >
              Emotional Story Dossier
            </Typography>
            <Typography
              variant="h3"
              component="h1"
              align="center"
              gutterBottom
              sx={{ fontWeight: 700, color: '#2d2015', textTransform: 'uppercase', letterSpacing: '0.04em' }}
            >
              {story.title}
            </Typography>
            <Box sx={{ width: 120, height: 2, mx: 'auto', mb: 3, background: 'linear-gradient(90deg, rgba(101,72,43,0) 0%, rgba(101,72,43,0.72) 50%, rgba(101,72,43,0) 100%)' }} />

            <Stack spacing={2.2}>
              <Box sx={archivalPanelSx}>
                <Typography variant="overline" sx={{ display: 'block', color: '#7b5836', letterSpacing: '0.18em', fontWeight: 700, mb: 1 }}>
                  Story Premise
                </Typography>
                <Typography variant="body1" sx={{ color: '#3d2c1c', lineHeight: 1.8 }}>
                  {introText}
                </Typography>
              </Box>

              <Box sx={archivalPanelSx}>
                <Typography variant="overline" sx={{ display: 'block', color: '#7b5836', letterSpacing: '0.18em', fontWeight: 700, mb: 1 }}>
                  Your Role
                </Typography>
                <Typography variant="body1" sx={{ color: '#3d2c1c', lineHeight: 1.8 }}>
                  {protagonist?.description || 'An unfolding identity.'}
                </Typography>
              </Box>
            </Stack>

            <Box sx={{ mt: 5 }}>
              <Typography variant="h5" gutterBottom sx={{ color: '#2f2116', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Cast Ledger
              </Typography>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={3} alignItems="stretch">
                {protagonist && (
                  <Box sx={characterDossierSx}>
                    {protagonist.imageUrl && (
                      <Box sx={portraitFrameSx}>
                        <Box sx={{ display: 'flex', justifyContent: 'center' }}>
                          <img
                            src={resolveAssetUrl(protagonist.imageUrl)}
                            alt={protagonist.name}
                            style={{
                              maxWidth: '100%',
                              maxHeight: 360,
                              objectFit: 'contain'
                            }}
                          />
                        </Box>
                      </Box>
                    )}
                    <Box>
                      <Typography variant="overline" sx={{ display: 'block', color: '#866446', letterSpacing: '0.16em', fontWeight: 700 }}>
                        Primary Perspective
                      </Typography>
                      <Typography variant="h6" sx={{ color: '#2d2015', mt: 0.4 }}>
                        {protagonist.name} (You)
                      </Typography>
                    </Box>
                    <Typography variant="body2" sx={{ color: '#57402c', lineHeight: 1.75 }}>
                      {protagonist.description}
                    </Typography>
                  </Box>
                )}

                {npcs.map(npc => (
                  <Box sx={characterDossierSx} key={npc.id}>
                    {npc.imageUrl && (
                      <Box sx={portraitFrameSx}>
                        <Box sx={{ display: 'flex', justifyContent: 'center' }}>
                          <img
                            src={resolveAssetUrl(npc.imageUrl)}
                            alt={npc.name}
                            style={{
                              maxWidth: '100%',
                              maxHeight: 360,
                              objectFit: 'contain'
                            }}
                          />
                        </Box>
                      </Box>
                    )}
                    <Box>
                      <Typography variant="overline" sx={{ display: 'block', color: '#866446', letterSpacing: '0.16em', fontWeight: 700 }}>
                        Supporting Character
                      </Typography>
                      <Typography variant="h6" sx={{ color: '#2d2015', mt: 0.4 }}>
                        {npc.name}
                      </Typography>
                      <Typography variant="body2" sx={{ color: '#7a5c3e', mt: 0.45, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                        {npc.relationship || 'A key figure'}
                      </Typography>
                    </Box>
                    <Typography variant="body2" sx={{ color: '#57402c', lineHeight: 1.75 }}>
                      {npc.description}
                    </Typography>
                  </Box>
                ))}
              </Stack>
            </Box>

            <Box sx={{ mt: 6, textAlign: 'center' }}>
            <Button
              variant="contained"
              color="inherit"
              size="large"
              onClick={handleBeginStory}
              sx={{
                borderRadius: 0,
                border: '1px solid rgba(244,232,210,0.28)',
                px: 6,
                py: 1.5,
                fontSize: '1rem',
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                background: 'linear-gradient(180deg, #5b3f27 0%, #2f2015 100%)',
                color: '#f4ead2',
                boxShadow: '0 10px 24px rgba(18,12,8,0.28)',
                '&:hover': {
                  background: 'linear-gradient(180deg, #704d2f 0%, #3b2718 100%)',
                  boxShadow: '0 12px 28px rgba(18,12,8,0.34)',
                }
              }}
            >
              Begin Your Story
            </Button>
            </Box>
          </Paper>
          {starting && (
            <SpacetimeWarp title={story.title} summary={introText} />
          )}
        </Container>
      </Box>
    </Fade>
  );
};

export default StoryPreview; 
