import React, { useEffect, useState } from 'react';
import { Box, Typography, Fade } from '@mui/material';

interface StoryIntroAnimationProps {
  title: string;
  onComplete: () => void;
}

const StoryIntroAnimation: React.FC<StoryIntroAnimationProps> = ({ title, onComplete }) => {
  const [animationPhase, setAnimationPhase] = useState(0);
  
  // Animation sequence timing
  useEffect(() => {
    // Phase 0: Initial stars appear
    const timer1 = setTimeout(() => setAnimationPhase(1), 1000);
    
    // Phase 1: Title appears
    const timer2 = setTimeout(() => setAnimationPhase(2), 3000);
    
    // Phase 2: Portal opens
    const timer3 = setTimeout(() => setAnimationPhase(3), 5000);
    
    // Phase 3: Wormhole effect
    const timer4 = setTimeout(() => setAnimationPhase(4), 7000);
    
    // Phase 4: Flash of light
    const timer5 = setTimeout(() => {
      setAnimationPhase(5);
      // Complete animation
      setTimeout(onComplete, 1000);
    }, 9000);
    
    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);
      clearTimeout(timer4);
      clearTimeout(timer5);
    };
  }, [onComplete]);

  return (
    <Box
      sx={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        bgcolor: 'black',
        zIndex: 2000,
        overflow: 'hidden',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        perspective: '1000px',
      }}
    >
      {/* Star field background */}
      <Box
        sx={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          opacity: animationPhase >= 0 ? 1 : 0,
          transition: 'opacity 1s ease-in',
          '&::before': {
            content: '""',
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'radial-gradient(circle at center, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 100%), url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'400\' height=\'400\' viewBox=\'0 0 800 800\'%3E%3Cg fill=\'none\' stroke=\'%23FFFFFF\' stroke-width=\'1\'%3E%3Ccircle r=\'1\' cx=\'100\' cy=\'100\'/%3E%3Ccircle r=\'1\' cx=\'200\' cy=\'150\'/%3E%3Ccircle r=\'1\' cx=\'300\' cy=\'300\'/%3E%3Ccircle r=\'1\' cx=\'400\' cy=\'400\'/%3E%3Ccircle r=\'1\' cx=\'500\' cy=\'200\'/%3E%3Ccircle r=\'1\' cx=\'600\' cy=\'100\'/%3E%3Ccircle r=\'1\' cx=\'700\' cy=\'300\'/%3E%3Ccircle r=\'1\' cx=\'50\' cy=\'350\'/%3E%3Ccircle r=\'1\' cx=\'150\' cy=\'450\'/%3E%3Ccircle r=\'1\' cx=\'250\' cy=\'250\'/%3E%3Ccircle r=\'1\' cx=\'350\' cy=\'150\'/%3E%3Ccircle r=\'1\' cx=\'450\' cy=\'350\'/%3E%3Ccircle r=\'1\' cx=\'550\' cy=\'450\'/%3E%3Ccircle r=\'1\' cx=\'650\' cy=\'250\'/%3E%3Ccircle r=\'1\' cx=\'750\' cy=\'150\'/%3E%3Ccircle r=\'1\' cx=\'125\' cy=\'175\'/%3E%3Ccircle r=\'1\' cx=\'225\' cy=\'275\'/%3E%3Ccircle r=\'1\' cx=\'325\' cy=\'375\'/%3E%3Ccircle r=\'1\' cx=\'425\' cy=\'475\'/%3E%3Ccircle r=\'1\' cx=\'525\' cy=\'175\'/%3E%3Ccircle r=\'1\' cx=\'625\' cy=\'275\'/%3E%3Ccircle r=\'1\' cx=\'725\' cy=\'375\'/%3E%3Ccircle r=\'1\' cx=\'75\' cy=\'425\'/%3E%3C/g%3E%3C/svg%3E")',
            backgroundSize: '200% 200%',
            animation: 'twinkle 8s linear infinite',
          },
        }}
      />

      {/* Portal/wormhole effect */}
      <Box
        sx={{
          position: 'absolute',
          width: '100vw',
          height: '100vh',
          background: animationPhase >= 2 ? 'radial-gradient(circle at center, rgba(75, 0, 130, 0.8) 0%, rgba(0, 0, 0, 0) 70%)' : 'none',
          transform: animationPhase >= 3 ? 'scale(1.5)' : 'scale(0)',
          opacity: animationPhase >= 2 ? 1 : 0,
          transition: 'transform 2s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 2s ease',
        }}
      />

      {/* Spinning vortex */}
      {animationPhase >= 2 && (
        <Box
          sx={{
            position: 'absolute',
            width: '100vw',
            height: '100vh',
            background: 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'100\' height=\'100\' viewBox=\'0 0 100 100\'%3E%3Cpath fill=\'none\' stroke=\'%23FFFFFF\' stroke-width=\'0.5\' d=\'M50,10 A40,40 0 0,1 90,50 A40,40 0 0,1 50,90 A40,40 0 0,1 10,50 A40,40 0 0,1 50,10 Z\'/%3E%3Cpath fill=\'none\' stroke=\'%23FFFFFF\' stroke-width=\'0.4\' d=\'M50,20 A30,30 0 0,1 80,50 A30,30 0 0,1 50,80 A30,30 0 0,1 20,50 A30,30 0 0,1 50,20 Z\'/%3E%3Cpath fill=\'none\' stroke=\'%23FFFFFF\' stroke-width=\'0.3\' d=\'M50,30 A20,20 0 0,1 70,50 A20,20 0 0,1 50,70 A20,20 0 0,1 30,50 A20,20 0 0,1 50,30 Z\'/%3E%3C/svg%3E") center center no-repeat',
            backgroundSize: animationPhase >= 3 ? '300% 300%' : '100% 100%',
            opacity: animationPhase >= 3 ? 0.8 : 0.4,
            animation: 'spin 4s linear infinite',
            transition: 'all 2s ease',
          }}
        />
      )}

      {/* Light streaks for wormhole effect */}
      {animationPhase >= 3 && (
        <Box
          sx={{
            position: 'absolute',
            width: '100vw',
            height: '100vh',
            background: 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'100\' height=\'100\' viewBox=\'0 0 100 100\'%3E%3Cline x1=\'0\' y1=\'50\' x2=\'100\' y2=\'50\' stroke=\'%23FFFFFF\' stroke-width=\'0.5\'/%3E%3Cline x1=\'50\' y1=\'0\' x2=\'50\' y2=\'100\' stroke=\'%23FFFFFF\' stroke-width=\'0.5\'/%3E%3Cline x1=\'0\' y1=\'0\' x2=\'100\' y2=\'100\' stroke=\'%23FFFFFF\' stroke-width=\'0.5\'/%3E%3Cline x1=\'0\' y1=\'100\' x2=\'100\' y2=\'0\' stroke=\'%23FFFFFF\' stroke-width=\'0.5\'/%3E%3C/svg%3E") center center no-repeat',
            backgroundSize: '200% 200%',
            opacity: 0.5,
            transform: `rotate(${animationPhase >= 4 ? 180 : 0}deg) scale(${animationPhase >= 4 ? 2 : 1})`,
            animation: 'streaks 3s linear infinite',
            transition: 'transform 2s ease',
          }}
        />
      )}

      {/* Flash of light at the end */}
      <Fade in={animationPhase >= 4} timeout={1000}>
        <Box
          sx={{
            position: 'absolute',
            width: '100vw',
            height: '100vh',
            background: 'white',
            opacity: animationPhase === 4 ? 0.9 : 0,
            transition: 'opacity 1s ease',
          }}
        />
      </Fade>

      {/* Story title */}
      <Typography
        variant="h2"
        component="h1"
        sx={{
          color: 'white',
          fontFamily: '"Cormorant Garamond", "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Palatino, serif',
          textAlign: 'center',
          position: 'relative',
          zIndex: 10,
          opacity: animationPhase >= 1 ? 1 : 0,
          transform: `scale(${animationPhase >= 3 ? 1.5 : 1}) translateZ(${animationPhase >= 3 ? 500 : 0}px)`,
          textShadow: '0 0 10px rgba(255,255,255,0.7)',
          transition: 'all 2s cubic-bezier(0.34, 1.56, 0.64, 1)',
          px: 3,
        }}
      >
        {title}
      </Typography>

      <style>
        {`
        @keyframes twinkle {
          0% { background-position: 0% 0%; }
          100% { background-position: 100% 100%; }
        }
        
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        
        @keyframes streaks {
          0% { transform: scale(1) rotate(0deg); }
          50% { transform: scale(1.5) rotate(180deg); }
          100% { transform: scale(1) rotate(360deg); }
        }
        `}
      </style>
    </Box>
  );
};

export default StoryIntroAnimation;