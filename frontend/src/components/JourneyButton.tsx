import React from 'react';
import { Box, CircularProgress } from '@mui/material';
import { keyframes } from '@emotion/react';

const flowerSpinForward = keyframes`
  from { transform: rotate(var(--journey-flower-start, 0deg)); }
  to { transform: rotate(calc(var(--journey-flower-start, 0deg) + 360deg)); }
`;

const flowerSpinBackward = keyframes`
  from { transform: rotate(var(--journey-flower-start, 0deg)); }
  to { transform: rotate(calc(var(--journey-flower-start, 0deg) - 360deg)); }
`;

const orbitPerimeter = keyframes`
  0%   { top: 0; left: 0; }
  12%  { top: 0; left: calc(100% - 6px); }
  42%  { top: calc(100% - 6px); left: calc(100% - 6px); }
  67%  { top: calc(100% - 6px); left: 0; }
  100% { top: 0; left: 0; }
`;

const flowerLayouts = [
  { className: 'journey-flower-1', top: '-12px', left: '-13px', rotate: '5deg', animation: flowerSpinForward, duration: '15s', delay: '0s' },
  { className: 'journey-flower-2', bottom: '-5px', left: '8px', rotate: '35deg', animation: flowerSpinBackward, duration: '13s', delay: '1s' },
  { className: 'journey-flower-3', bottom: '-15px', rotate: '0deg', animation: flowerSpinForward, duration: '16s', delay: '1s' },
  { className: 'journey-flower-4', top: '-14px', rotate: '15deg', animation: flowerSpinForward, duration: '17s', delay: '1s' },
  { className: 'journey-flower-5', right: '11px', top: '-3px', rotate: '25deg', animation: flowerSpinBackward, duration: '20s', delay: '1s' },
  { className: 'journey-flower-6', right: '-15px', bottom: '-15px', rotate: '30deg', animation: flowerSpinForward, duration: '15s', delay: '1s' },
] as const;

type JourneyButtonProps = {
  label: string;
  onClick?: React.MouseEventHandler<HTMLButtonElement>;
  type?: 'button' | 'submit' | 'reset';
  disabled?: boolean;
  loading?: boolean;
};

const JourneyButton: React.FC<JourneyButtonProps> = ({
  label,
  onClick,
  type = 'button',
  disabled = false,
  loading = false,
}) => {
  const isDisabled = disabled || loading;

  return (
    <Box
      component="button"
      type={type}
      onClick={onClick}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      sx={{
        position: 'relative',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: '12.6rem',
        minWidth: '12.6rem',
        height: '4.1rem',
        p: 0,
        border: 0,
        outline: 0,
        background: 'transparent',
        cursor: isDisabled ? 'not-allowed' : 'pointer',
        appearance: 'none',
        WebkitAppearance: 'none',
        font: 'inherit',
        '& .journey-wrapper': {
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minWidth: '12rem',
          height: '2.95rem',
          background: 'transparent',
        },
        '& .journey-label': {
          position: 'relative',
          zIndex: 2,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '2.3rem',
          px: '0.95rem',
          borderRadius: '12px',
          background: 'linear-gradient(180deg, rgba(255, 252, 248, 0.96), rgba(249, 240, 232, 0.93))',
          border: '1px solid rgba(115, 85, 72, 0.18)',
          boxShadow: '0 10px 22px rgba(56, 38, 28, 0.16)',
          backdropFilter: 'blur(6px)',
          WebkitBackdropFilter: 'blur(6px)',
          color: 'var(--emo-ink)',
          fontWeight: 700,
          fontSize: '1.06rem',
          lineHeight: 1,
          letterSpacing: '0.02em',
          whiteSpace: 'nowrap',
          transition: 'background 220ms ease, box-shadow 220ms ease, border-color 220ms ease, color 220ms ease',
          visibility: loading ? 'hidden' : 'visible',
        },
        '& .journey-spinner': {
          position: 'absolute',
          inset: 0,
          zIndex: 3,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        },
        '& .journey-orbit-dot': {
          position: 'absolute',
          top: 0,
          left: 0,
          zIndex: 1,
          width: '6px',
          height: '6px',
          borderRadius: '999px',
          backgroundColor: 'rgba(115, 85, 72, 0.95)',
          boxShadow: '0 0 10px rgba(115, 85, 72, 0.35)',
          pointerEvents: 'none',
          animation: `${orbitPerimeter} 5.6s linear infinite`,
        },
        '& .journey-flower': {
          position: 'absolute',
          zIndex: 0,
          display: 'grid',
          gridTemplateColumns: '1.2em 1.2em',
          transition: 'grid-template-columns 0.8s ease',
        },
        '& .journey-petal': {
          width: '1em',
          height: '1em',
          borderRadius: '40% 70% / 7% 90%',
          background: 'linear-gradient(145deg, #ffffff, #f0c8be)',
          border: '0.5px solid rgba(232, 168, 152, 0.7)',
          transition: 'width 0.8s ease, height 0.8s ease, background 220ms ease, border-color 220ms ease',
        },
        '& .journey-petal-two': { transform: 'rotate(90deg)' },
        '& .journey-petal-three': { transform: 'rotate(270deg)' },
        '& .journey-petal-four': { transform: 'rotate(180deg)' },
        '&:hover .journey-label': {
          background: 'linear-gradient(180deg, rgba(255, 254, 251, 0.98), rgba(252, 243, 236, 0.95))',
          borderColor: 'rgba(115, 85, 72, 0.26)',
          boxShadow: '0 12px 26px rgba(56, 38, 28, 0.2)',
        },
        '&:hover .journey-flower': {
          gridTemplateColumns: '1.8em 1.8em',
        },
        '&:hover .journey-petal': {
          width: '1.8em',
          height: '1.8em',
          background: 'linear-gradient(145deg, #fff5f2, #e8a898)',
          borderColor: 'rgba(232, 168, 152, 0.95)',
        },
        '&:hover .journey-flower-1': {
          animation: `${flowerLayouts[0].animation} ${flowerLayouts[0].duration} linear ${flowerLayouts[0].delay} infinite`,
        },
        '&:hover .journey-flower-2': {
          animation: `${flowerLayouts[1].animation} ${flowerLayouts[1].duration} linear ${flowerLayouts[1].delay} infinite`,
        },
        '&:hover .journey-flower-3': {
          animation: `${flowerLayouts[2].animation} ${flowerLayouts[2].duration} linear ${flowerLayouts[2].delay} infinite`,
        },
        '&:hover .journey-flower-4': {
          animation: `${flowerLayouts[3].animation} ${flowerLayouts[3].duration} linear ${flowerLayouts[3].delay} infinite`,
        },
        '&:hover .journey-flower-5': {
          animation: `${flowerLayouts[4].animation} ${flowerLayouts[4].duration} linear ${flowerLayouts[4].delay} infinite`,
        },
        '&:hover .journey-flower-6': {
          animation: `${flowerLayouts[5].animation} ${flowerLayouts[5].duration} linear ${flowerLayouts[5].delay} infinite`,
        },
        '&:focus-visible .journey-label': {
          boxShadow: '0 0 0 3px rgba(255,255,255,0.22), 0 0 0 6px rgba(115, 85, 72, 0.26), 0 12px 26px rgba(56, 38, 28, 0.18)',
        },
        '&:disabled .journey-label': {
          color: 'rgba(63, 48, 41, 0.58)',
          background: 'rgba(255, 250, 245, 0.8)',
          boxShadow: '0 6px 14px rgba(56, 38, 28, 0.08)',
        },
      }}
    >
      <Box component="span" className="journey-wrapper">
        <Box component="span" className="journey-label">
          {label}
        </Box>
        <Box component="span" className="journey-orbit-dot" />
        {loading && (
          <Box component="span" className="journey-spinner">
            <CircularProgress size={22} sx={{ color: 'var(--emo-accent-strong)' }} />
          </Box>
        )}
        {flowerLayouts.map((flower) => (
          <Box
            key={flower.className}
            component="span"
            className={`journey-flower ${flower.className}`}
            sx={{
              ...('top' in flower ? { top: flower.top } : {}),
              ...('bottom' in flower ? { bottom: flower.bottom } : {}),
              ...('left' in flower ? { left: flower.left } : {}),
              ...('right' in flower ? { right: flower.right } : {}),
              '--journey-flower-start': flower.rotate,
              transform: `rotate(${flower.rotate})`,
            }}
          >
            <Box component="span" className="journey-petal journey-petal-one" />
            <Box component="span" className="journey-petal journey-petal-two" />
            <Box component="span" className="journey-petal journey-petal-three" />
            <Box component="span" className="journey-petal journey-petal-four" />
          </Box>
        ))}
      </Box>
    </Box>
  );
};

export default JourneyButton;
