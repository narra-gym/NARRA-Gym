import React from 'react';
import { Box, Typography, Fade } from '@mui/material';
import { keyframes } from '@emotion/react';

interface SpacetimeWarpProps {
  title?: string;
  summary?: string;
  message?: string; // fallback single line message
}

const warp = keyframes`
  0% {
    transform: scale(0.1) rotate(0deg);
    opacity: 0.5;
  }
  50% {
    transform: scale(1.5) rotate(180deg);
    opacity: 1;
  }
  100% {
    transform: scale(0.1) rotate(360deg);
    opacity: 0.5;
  }
`;

const stars = keyframes`
  0% {
    transform: translateY(0px);
  }
  100% {
    transform: translateY(-2000px);
  }
`;

const gradientShift = keyframes`
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
`;

const SpacetimeWarp: React.FC<SpacetimeWarpProps> = ({ title, summary, message }) => {
  return (
    <Box
      sx={{
        position: 'fixed',
        inset: 0,
        overflow: 'hidden',
        zIndex: 9999,
      }}
    >
      {/* Animated gradient backdrop */}
      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          background: 'linear-gradient(-45deg, #1e3c72, #2a5298, #1e3c72, #000)',
          backgroundSize: '400% 400%',
          animation: `${gradientShift} 12s ease infinite`,
          opacity: 0.6,
        }}
      />

      {/* Star field */}
      <Box
        sx={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '2000px',
          backgroundImage:
            'radial-gradient(ellipse at center, rgba(255,255,255,0.4) 0%, rgba(255,255,255,0) 70%), url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 100 100\'%3E%3Ccircle cx=\'50\' cy=\'50\' r=\'0.4\' fill=\'%23fff\' /%3E%3C/svg%3E")',
          backgroundRepeat: 'repeat',
          backgroundSize: '100px 100px',
          animation: `${stars} 14s linear infinite`,
          pointerEvents: 'none',
        }}
      />

      {/* Central warp ring */}
      <Box
        sx={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
        }}
      >
        <Box
          sx={{
            width: '120px',
            height: '120px',
            border: '2px solid #fff',
            borderRadius: '50%',
            animation: `${warp} 2.5s ease-in-out infinite`,
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
          }}
        >
          <Box
            sx={{
              width: '90px',
              height: '90px',
              backgroundColor: 'rgba(255, 255, 255, 0.15)',
              borderRadius: '50%',
              transform: 'rotate(45deg)',
            }}
          />
        </Box>

        {/* Story title & summary */}
        {title && (
          <Fade in timeout={800}>
            <Typography variant="h4" sx={{ color: '#fff', mt: 4, textAlign: 'center' }}>
              {title}
            </Typography>
          </Fade>
        )}
        {summary && (
          <Fade in timeout={1400}>
            <Typography variant="subtitle1" sx={{ color: '#ddd', mt: 2, px: 4, textAlign: 'center' }}>
              {summary}
            </Typography>
          </Fade>
        )}
        {!title && !summary && message && (
          <Typography variant="h5" sx={{ color: 'white', mt: 4 }}>
            {message}
          </Typography>
        )}
      </Box>
    </Box>
  );
};

export default SpacetimeWarp; 