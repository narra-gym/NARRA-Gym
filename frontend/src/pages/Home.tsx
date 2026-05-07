import React from 'react';
import { Box, Button, Typography, Fade } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { keyframes } from '@emotion/react';
import ShaderBackground from '../components/ShaderBackground';

// Extra animations for nebula & hologrid
const nebulaShift = keyframes`
  0% { transform: scale(1) translate(-10%, -10%); opacity: 0.6; }
  50% { transform: scale(1.2) translate(10%, 10%); opacity: 0.8; }
  100% { transform: scale(1) translate(-10%, -10%); opacity: 0.6; }
`;

const holoRotate = keyframes`
  0% { transform: rotate(0deg); opacity: 0.15; }
  100% { transform: rotate(360deg); opacity: 0.15; }
`;

const Home: React.FC = () => {
  const navigate = useNavigate();

  return (
    <Box
      sx={{
        position: 'fixed',
        inset: 0,
        background: 'transparent',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#fff',
        overflow: 'hidden',
      }}
    >
      <ShaderBackground />
      {/* dark overlay 50% */}
      <Box sx={{ position: 'absolute', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 1 }} />
      {/* animated nebula layer */}
      <Box
        sx={{
          position: 'absolute',
          inset: '-20%',
          background:
            'radial-gradient(circle at 30% 30%, rgba(255,0,150,0.4), transparent 60%), radial-gradient(circle at 70% 70%, rgba(0,200,255,0.4), transparent 55%)',
          filter: 'blur(120px)',
          animation: `${nebulaShift} 6s ease-in-out infinite`,
        }}
      />

      {/* rotating holographic grid */}
      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px)',
          backgroundSize: '60px 60px',
          animation: `${holoRotate} 60s linear infinite`,
          pointerEvents: 'none',
        }}
      />

      {/* overlay stars */}
      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          backgroundImage:
            "radial-gradient(circle, rgba(255,255,255,0.6) 0.5px, rgba(255,255,255,0) 1px)",
          backgroundSize: '2px 2px',
          opacity: 0.4,
          pointerEvents: 'none',
        }}
      />

      {/* staged fade-in: no text at very start, white text */}
      <Fade in timeout={2200}>
        <Typography variant="h2" sx={{ fontWeight: 700, mb: 4, textShadow: '0 0 10px rgba(255,255,255,0.8)', zIndex: 2, color: '#fff' }}>
          NARRA-Gym
        </Typography>
      </Fade>

      <Fade in timeout={3200}>
        <Typography variant="h5" sx={{ maxWidth: 600, textAlign: 'center', mb: 6, px: 2, zIndex: 2, color: '#fff' }}>
        Co-creating adaptive narratives that fit your mood—now.
        </Typography>
      </Fade>

      <Fade in timeout={4200}>
        <Box sx={{ zIndex: 2, display: 'flex', flexDirection: 'column', gap: 2, alignItems: 'center' }}>
          <Button
            variant="outlined"
            onClick={() => navigate('/experiment')}
            sx={{
              color: '#fffaf5',
              borderColor: 'rgba(255,255,255,0.58)',
              backgroundColor: 'rgba(32, 24, 20, 0.18)',
              backdropFilter: 'blur(10px)',
              px: 3,
              fontWeight: 600,
              '&:hover': {
                borderColor: 'rgba(255,255,255,0.82)',
                backgroundColor: 'rgba(32, 24, 20, 0.28)',
              },
            }}
          >
            Benchmark Mode
          </Button>
        </Box>
      </Fade>
    </Box>
  );
};

export default Home; 
