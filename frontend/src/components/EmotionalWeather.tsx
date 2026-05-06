import React, { useMemo } from 'react';
import { Box, Typography, Tooltip } from '@mui/material';

interface WeatherState {
  icon: string;
  label: string;
  color: string;
  bg: string;
  glow: string;
  description: string;
}

const WEATHER_MAP: Record<string, WeatherState> = {
  // ── Calm family ──
  peaceful:    { icon: '☀️', label: 'Clear',       color: '#f5a623', bg: 'rgba(255,218,120,0.18)', glow: 'rgba(245,166,35,0.25)', description: 'A calm and warm atmosphere' },
  calm:        { icon: '🌤️', label: 'Fair',        color: '#7db8a2', bg: 'rgba(125,184,162,0.18)', glow: 'rgba(125,184,162,0.25)', description: 'Peaceful and serene' },
  serene:      { icon: '🌅', label: 'Sunrise',     color: '#e8a898', bg: 'rgba(232,168,152,0.18)', glow: 'rgba(232,168,152,0.3)',  description: 'A gentle glow' },
  tranquil:    { icon: '🌊', label: 'Still Sea',   color: '#7aa8c4', bg: 'rgba(122,168,196,0.18)', glow: 'rgba(122,168,196,0.25)', description: 'Calm as a quiet ocean' },
  // ── Hopeful family ──
  hopeful:     { icon: '🌈', label: 'Rainbow',     color: '#a27cc4', bg: 'rgba(162,124,196,0.18)', glow: 'rgba(162,124,196,0.3)',  description: 'Filled with hope' },
  optimistic:  { icon: '🌸', label: 'Blossom',     color: '#e8a898', bg: 'rgba(232,168,152,0.18)', glow: 'rgba(232,168,152,0.3)',  description: 'Bright anticipation' },
  healing:     { icon: '🌿', label: 'Healing',     color: '#7db8a2', bg: 'rgba(125,184,162,0.18)', glow: 'rgba(125,184,162,0.3)',  description: 'A gentle moment of recovery' },
  warm:        { icon: '🕯️', label: 'Candlelight', color: '#f5a623', bg: 'rgba(255,218,120,0.18)', glow: 'rgba(245,166,35,0.3)',  description: 'Warm companionship' },
  // ── Sad family ──
  melancholic: { icon: '🌧️', label: 'Light Rain',  color: '#8fa8c8', bg: 'rgba(143,168,200,0.18)', glow: 'rgba(143,168,200,0.25)', description: 'A touch of wistfulness' },
  sad:         { icon: '🌫️', label: 'Mist',        color: '#9aa8b8', bg: 'rgba(154,168,184,0.18)', glow: 'rgba(154,168,184,0.25)', description: 'Wrapped in a gentle haze' },
  lonely:      { icon: '🌙', label: 'Moonlit',     color: '#7a6d9e', bg: 'rgba(122,109,158,0.18)', glow: 'rgba(122,109,158,0.3)',  description: 'Quiet solitude' },
  // ── Tense family ──
  tense:       { icon: '⛅', label: 'Overcast',    color: '#8090a0', bg: 'rgba(128,144,160,0.18)', glow: 'rgba(128,144,160,0.25)', description: 'A slightly tense atmosphere' },
  anxious:     { icon: '🌩️', label: 'Thunder',     color: '#6878a8', bg: 'rgba(104,120,168,0.18)', glow: 'rgba(104,120,168,0.3)',  description: 'Restless unease' },
  tense_confrontation: { icon: '⛈️', label: 'Storm', color: '#5868a0', bg: 'rgba(88,104,160,0.18)', glow: 'rgba(88,104,160,0.35)', description: 'A tense standoff' },
  // ── Intense family ──
  angry:       { icon: '🌪️', label: 'Tempest',     color: '#c87870', bg: 'rgba(200,120,112,0.18)', glow: 'rgba(200,120,112,0.35)', description: 'Intense emotions swirling' },
  conflicted:  { icon: '🌦️', label: 'Mixed',       color: '#b0a8d8', bg: 'rgba(176,168,216,0.18)', glow: 'rgba(176,168,216,0.3)',  description: 'Inner conflict and ambivalence' },
  // ── Mysterious family ──
  mysterious:  { icon: '🌌', label: 'Starry',      color: '#5848a0', bg: 'rgba(88,72,160,0.18)',   glow: 'rgba(88,72,160,0.35)',   description: 'Deep and enigmatic' },
  curious:     { icon: '✨', label: 'Shimmer',     color: '#a8d4c4', bg: 'rgba(168,212,196,0.18)', glow: 'rgba(168,212,196,0.3)',  description: 'Full of curiosity' },
  // ── Joyful family ──
  joyful:      { icon: '🌞', label: 'Sunny',       color: '#f5a623', bg: 'rgba(255,230,100,0.22)', glow: 'rgba(245,166,35,0.35)', description: 'Bright and joyful' },
  excited:     { icon: '🎆', label: 'Fireworks',   color: '#e888c0', bg: 'rgba(232,136,192,0.18)', glow: 'rgba(232,136,192,0.3)',  description: 'Thrilling excitement' },
};

const DEFAULT_WEATHER: WeatherState = {
  icon: '🍃',
  label: 'Breeze',
  color: '#7db8a2',
  bg: 'rgba(125,184,162,0.15)',
  glow: 'rgba(125,184,162,0.2)',
  description: 'The story unfolds',
};

function resolveWeather(tone: string): WeatherState {
  if (!tone) return DEFAULT_WEATHER;
  const key = tone.toLowerCase().replace(/[\s-]/g, '_');
  if (WEATHER_MAP[key]) return WEATHER_MAP[key];
  // Fuzzy match: check if any keyword exists in the tone string
  for (const [k, v] of Object.entries(WEATHER_MAP)) {
    if (key.includes(k) || k.includes(key)) return v;
  }
  return DEFAULT_WEATHER;
}

interface Props {
  emotionalTone?: string;
}

const EmotionalWeather: React.FC<Props> = ({ emotionalTone }) => {
  const weather = useMemo(() => resolveWeather(emotionalTone ?? ''), [emotionalTone]);

  return (
    <Tooltip title={weather.description} arrow placement="bottom">
      <Box
        sx={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 0.8,
          px: 1.5,
          py: 0.5,
          borderRadius: '20px',
          background: weather.bg,
          border: `1px solid ${weather.color}30`,
          boxShadow: `0 2px 12px ${weather.glow}`,
          transition: 'all 0.6s cubic-bezier(0.34, 1.56, 0.64, 1)',
          cursor: 'default',
          userSelect: 'none',
          backdropFilter: 'blur(8px)',
        }}
      >
        <Box
          component="span"
          sx={{
            fontSize: '1.1rem',
            lineHeight: 1,
            filter: 'drop-shadow(0 1px 3px rgba(0,0,0,0.15))',
            animation: 'weatherFloat 3s ease-in-out infinite',
            '@keyframes weatherFloat': {
              '0%, 100%': { transform: 'translateY(0px)' },
              '50%': { transform: 'translateY(-2px)' },
            },
          }}
        >
          {weather.icon}
        </Box>
        <Typography
          variant="caption"
          sx={{
            fontWeight: 600,
            color: weather.color,
            fontSize: '0.72rem',
            letterSpacing: '0.04em',
            whiteSpace: 'nowrap',
          }}
        >
          {weather.label}
        </Typography>
      </Box>
    </Tooltip>
  );
};

export default EmotionalWeather;
