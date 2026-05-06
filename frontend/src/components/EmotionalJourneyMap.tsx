import React, { useMemo } from 'react';
import { Box, Typography, Tooltip, Chip } from '@mui/material';

interface EmotionPoint {
  tone: string;
  index: number;
  timestamp: string;
}

/** Map an emotion to a 0-10 intensity score (higher = more intense / energised) */
function toneToIntensity(tone: string): number {
  const map: Record<string, number> = {
    peaceful: 3, calm: 3, serene: 2, tranquil: 2,
    healing: 3, warm: 3,
    hopeful: 5, optimistic: 5, curious: 5,
    joyful: 7, excited: 8,
    melancholic: 3, sad: 2, lonely: 2,
    conflicted: 6, tense: 7, anxious: 7,
    tense_confrontation: 8, angry: 9,
    mysterious: 5,
  };
  const key = tone.toLowerCase().replace(/[\s-]/g, '_');
  if (map[key] !== undefined) return map[key];
  for (const [k, v] of Object.entries(map)) {
    if (key.includes(k) || k.includes(key)) return v;
  }
  return 4;
}

function toneToColor(tone: string): string {
  const map: Record<string, string> = {
    peaceful: '#f5c842', calm: '#7db8a2', serene: '#e8a898', tranquil: '#7aa8c4',
    healing: '#7db8a2', warm: '#f5a623',
    hopeful: '#a27cc4', optimistic: '#e8a898', curious: '#a8d4c4',
    joyful: '#f5c842', excited: '#e888c0',
    melancholic: '#8fa8c8', sad: '#9aa8b8', lonely: '#7a6d9e',
    conflicted: '#b0a8d8', tense: '#8090a0', anxious: '#6878a8',
    tense_confrontation: '#5868a0', angry: '#c87870',
    mysterious: '#5848a0',
  };
  const key = tone.toLowerCase().replace(/[\s-]/g, '_');
  if (map[key]) return map[key];
  for (const [k, v] of Object.entries(map)) {
    if (key.includes(k) || k.includes(key)) return v;
  }
  return '#7db8a2';
}

function toneToIcon(tone: string): string {
  const map: Record<string, string> = {
    peaceful: '☀️', calm: '🌤️', serene: '🌅', tranquil: '🌊',
    healing: '🌿', warm: '🕯️',
    hopeful: '🌈', optimistic: '🌸', curious: '✨',
    joyful: '🌞', excited: '🎆',
    melancholic: '🌧️', sad: '🌫️', lonely: '🌙',
    conflicted: '🌦️', tense: '⛅', anxious: '🌩️',
    tense_confrontation: '⛈️', angry: '🌪️',
    mysterious: '🌌',
  };
  const key = tone.toLowerCase().replace(/[\s-]/g, '_');
  if (map[key]) return map[key];
  for (const [k, v] of Object.entries(map)) {
    if (key.includes(k) || k.includes(key)) return v;
  }
  return '🍃';
}

interface Props {
  history: EmotionPoint[];
  currentTurn?: number;
}

const SVG_H = 80;
const SVG_PADDING_X = 20;
const SVG_PADDING_Y = 12;

const EmotionalJourneyMap: React.FC<Props> = ({ history, currentTurn = 0 }) => {
  const points = useMemo(() => {
    if (history.length === 0) return [];
    return history.map((h, i) => ({
      ...h,
      intensity: toneToIntensity(h.tone),
      color: toneToColor(h.tone),
      icon: toneToIcon(h.tone),
      idx: i,
    }));
  }, [history]);

  // Summary chips: most frequent tones
  const topTones = useMemo(() => {
    const freq: Record<string, number> = {};
    history.forEach(h => { freq[h.tone] = (freq[h.tone] ?? 0) + 1; });
    return Object.entries(freq)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([tone]) => tone);
  }, [history]);

  if (points.length === 0) {
    return (
      <Box sx={{ textAlign: 'center', py: 3 }}>
        <Typography variant="caption" color="text.secondary">
          The journey hasn't begun yet — the emotional arc will appear here as the story unfolds
        </Typography>
      </Box>
    );
  }

  // Build SVG polyline
  const svgWidth = 340;
  const usableW = svgWidth - SVG_PADDING_X * 2;
  const usableH = SVG_H - SVG_PADDING_Y * 2;

  const toX = (i: number) =>
    SVG_PADDING_X + (points.length === 1 ? usableW / 2 : (i / (points.length - 1)) * usableW);
  const toY = (intensity: number) =>
    SVG_H - SVG_PADDING_Y - ((intensity / 10) * usableH);

  const polylinePoints = points.map((p, i) => `${toX(i)},${toY(p.intensity)}`).join(' ');

  // Gradient stops for the fill area
  const gradientId = 'emjGrad';

  return (
    <Box sx={{ width: '100%' }}>
      {/* Title */}
      <Typography
        variant="caption"
        sx={{
          display: 'block',
          mb: 0.5,
          fontWeight: 600,
          color: 'text.secondary',
          letterSpacing: '0.05em',
          textTransform: 'uppercase',
          fontSize: '0.65rem',
        }}
      >
        Emotional Journey Arc
      </Typography>

      {/* SVG Chart */}
      <Box
        sx={{
          width: '100%',
          borderRadius: 3,
          overflow: 'hidden',
          background: 'rgba(255,252,246,0.6)',
          backdropFilter: 'blur(8px)',
          border: '1px solid rgba(125,184,162,0.15)',
          p: 0.5,
        }}
      >
        <svg
          viewBox={`0 0 ${svgWidth} ${SVG_H}`}
          style={{ width: '100%', height: SVG_H, overflow: 'visible' }}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#7db8a2" stopOpacity="0.35" />
              <stop offset="100%" stopColor="#7db8a2" stopOpacity="0.02" />
            </linearGradient>
          </defs>

          {/* Horizontal guide lines */}
          {[2, 5, 8].map(level => (
            <line
              key={level}
              x1={SVG_PADDING_X}
              x2={svgWidth - SVG_PADDING_X}
              y1={toY(level)}
              y2={toY(level)}
              stroke="rgba(125,184,162,0.15)"
              strokeWidth="1"
              strokeDasharray="3 3"
            />
          ))}

          {/* Filled area under curve */}
          {points.length >= 2 && (
            <polygon
              points={`${toX(0)},${SVG_H - SVG_PADDING_Y} ${polylinePoints} ${toX(points.length - 1)},${SVG_H - SVG_PADDING_Y}`}
              fill={`url(#${gradientId})`}
            />
          )}

          {/* Polyline */}
          <polyline
            points={polylinePoints}
            fill="none"
            stroke="rgba(125,184,162,0.65)"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Data points */}
          {points.map((p, i) => (
            <Tooltip key={i} title={`${p.icon} ${p.tone} (Turn ${p.index})`} arrow>
              <g>
                {/* Glow ring */}
                <circle cx={toX(i)} cy={toY(p.intensity)} r={7} fill={p.color} fillOpacity={0.18} />
                {/* Main dot */}
                <circle
                  cx={toX(i)}
                  cy={toY(p.intensity)}
                  r={i === points.length - 1 ? 5 : 4}
                  fill={p.color}
                  stroke="white"
                  strokeWidth={i === points.length - 1 ? 2 : 1.5}
                  style={{ cursor: 'pointer' }}
                />
                {/* "You are here" pulse on last point */}
                {i === points.length - 1 && (
                  <circle
                    cx={toX(i)}
                    cy={toY(p.intensity)}
                    r={9}
                    fill="none"
                    stroke={p.color}
                    strokeWidth={1.5}
                    strokeOpacity={0.5}
                    style={{
                      animation: 'mapPulse 2s ease-in-out infinite',
                    }}
                  />
                )}
              </g>
            </Tooltip>
          ))}

          {/* Y-axis labels */}
          <text x={SVG_PADDING_X - 4} y={toY(8) + 4} textAnchor="end" fontSize={8} fill="rgba(100,90,85,0.5)">Hi</text>
          <text x={SVG_PADDING_X - 4} y={toY(5) + 4} textAnchor="end" fontSize={8} fill="rgba(100,90,85,0.5)">Mid</text>
          <text x={SVG_PADDING_X - 4} y={toY(2) + 4} textAnchor="end" fontSize={8} fill="rgba(100,90,85,0.5)">Lo</text>
        </svg>

        <style>{`
          @keyframes mapPulse {
            0%, 100% { r: 9; opacity: 0.5; }
            50%       { r: 13; opacity: 0; }
          }
        `}</style>
      </Box>

      {/* Current emotion label */}
      {points.length > 0 && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8, mt: 1 }}>
          <Box
            sx={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: points[points.length - 1].color,
              boxShadow: `0 0 6px ${points[points.length - 1].color}80`,
            }}
          />
          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 500 }}>
            Current mood: {points[points.length - 1].icon} {points[points.length - 1].tone}
          </Typography>
        </Box>
      )}

      {/* Dominant tone chips */}
      {topTones.length > 0 && (
        <Box sx={{ mt: 1.5 }}>
          <Typography
            variant="caption"
            sx={{ color: 'text.secondary', fontSize: '0.65rem', letterSpacing: '0.04em', textTransform: 'uppercase', fontWeight: 600 }}
          >
            Dominant Emotions
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
            {topTones.map(tone => (
              <Chip
                key={tone}
                label={`${toneToIcon(tone)} ${tone}`}
                size="small"
                sx={{
                  fontSize: '0.68rem',
                  height: 22,
                  background: `${toneToColor(tone)}20`,
                  color: toneToColor(tone),
                  border: `1px solid ${toneToColor(tone)}40`,
                  fontWeight: 600,
                }}
              />
            ))}
          </Box>
        </Box>
      )}
    </Box>
  );
};

export default EmotionalJourneyMap;
