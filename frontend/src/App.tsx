import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ThemeProvider, createTheme, CssBaseline } from '@mui/material';
import { StoryProvider } from './contexts/StoryContext';
import EmotionalNeedForm from './pages/EmotionalNeedForm';
import Home from './pages/Home';
import ClarifyingQuestionsForm from './pages/ClarifyingQuestionsForm';
import StoryInteraction from './pages/StoryInteraction';
import StoryConclusion from './pages/StoryConclusion';
import StoryPreview from './pages/StoryPreview';
import ProgressHarness from './debug/ProgressHarness'
import ExperimentMode from './pages/ExperimentMode';
import BenchmarkJudgePage from './pages/BenchmarkJudge';

// Apple-inspired healing theme — sage × peach × lavender with glassmorphism
const BODY_FONT =
  '"Manrope", "Avenir Next", "Segoe UI", "Helvetica Neue", Arial, sans-serif';
const DISPLAY_FONT =
  '"Cormorant Garamond", "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Palatino, serif';

const theme = createTheme({
  palette: {
    primary: {
      main: '#7db8a2',
      light: '#a8d4c4',
      dark: '#5a9a82',
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#e8a898',
      light: '#f0c4ba',
      dark: '#c8887a',
      contrastText: '#3c2a22',
    },
    background: {
      default: '#f9f7f4',
      paper: 'rgba(255, 252, 246, 0.72)',
    },
    text: {
      primary: '#1d1d1f',
      secondary: '#6e6e73',
    },
  },
  typography: {
    fontFamily: BODY_FONT,
    h1: {
      fontFamily: DISPLAY_FONT,
      fontWeight: 700,
      letterSpacing: '-0.03em',
      lineHeight: 1.08,
    },
    h2: {
      fontFamily: DISPLAY_FONT,
      fontWeight: 700,
      letterSpacing: '-0.028em',
      lineHeight: 1.12,
    },
    h3: {
      fontFamily: DISPLAY_FONT,
      fontWeight: 600,
      letterSpacing: '-0.02em',
      lineHeight: 1.18,
    },
    h4: {
      fontFamily: DISPLAY_FONT,
      fontWeight: 600,
      letterSpacing: '-0.018em',
      lineHeight: 1.22,
    },
    h5: {
      fontFamily: DISPLAY_FONT,
      fontWeight: 600,
      letterSpacing: '-0.012em',
      lineHeight: 1.28,
    },
    h6: {
      fontFamily: DISPLAY_FONT,
      fontWeight: 600,
      letterSpacing: '-0.01em',
      lineHeight: 1.35,
    },
    subtitle1: { fontWeight: 500, lineHeight: 1.5 },
    subtitle2: { fontWeight: 600, letterSpacing: '0.01em' },
    body1: { lineHeight: 1.68, letterSpacing: '0.002em' },
    body2: { lineHeight: 1.62, letterSpacing: '0.003em' },
    button: { fontWeight: 600, letterSpacing: '0.01em' },
    caption: { letterSpacing: '0.015em' },
  },
  shape: {
    borderRadius: 4,
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        '@import': 'url("https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&family=Manrope:wght@400;500;600;700;800&display=swap")',
        html: {
          WebkitFontSmoothing: 'antialiased',
          MozOsxFontSmoothing: 'grayscale',
        },
        'html, body, #root': {
          fontFamily: BODY_FONT,
        },
        body: {
          fontFamily: BODY_FONT,
        },
        'button, input, textarea, select': {
          fontFamily: 'inherit',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          fontFamily: BODY_FONT,
          textTransform: 'none',
          fontWeight: 600,
          borderRadius: 10,
          transition: 'all 0.22s cubic-bezier(.4,0,.2,1)',
          letterSpacing: '0.01em',
        },
        containedPrimary: {
          background: 'linear-gradient(135deg, #7db8a2 0%, #a0b4d8 100%)',
          boxShadow: '0 2px 8px rgba(94, 168, 144, 0.22)',
          '&:hover': {
            background: 'linear-gradient(135deg, #6aa992 0%, #8fa4cc 100%)',
            boxShadow: '0 4px 14px rgba(94, 168, 144, 0.30)',
            transform: 'translateY(-0.5px)',
          },
        },
        containedSecondary: {
          background: 'linear-gradient(135deg, #e8a898 0%, #f0c4ba 100%)',
          boxShadow: '0 2px 8px rgba(200, 136, 122, 0.20)',
          '&:hover': {
            background: 'linear-gradient(135deg, #d89888 0%, #e4b4aa 100%)',
            boxShadow: '0 4px 14px rgba(200, 136, 122, 0.28)',
            transform: 'translateY(-0.5px)',
          },
        },
        outlined: {
          borderRadius: 10,
          borderColor: 'rgba(0, 0, 0, 0.12)',
          '&:hover': {
            borderColor: 'rgba(0, 0, 0, 0.24)',
            backgroundColor: 'rgba(0, 0, 0, 0.02)',
          },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          boxShadow: '0 2px 20px rgba(0, 0, 0, 0.06), 0 0 0 1px rgba(255,255,255,0.15) inset',
          backdropFilter: 'saturate(180%) blur(20px)',
          borderRadius: 16,
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          boxShadow: '0 2px 16px rgba(0, 0, 0, 0.05)',
          backdropFilter: 'saturate(180%) blur(20px)',
          borderRadius: 16,
          border: '1px solid rgba(255,255,255,0.2)',
        },
      },
    },
    MuiTabs: {
      styleOverrides: {
        indicator: {
          height: 2.5,
          borderRadius: 2,
          background: 'linear-gradient(90deg, #7db8a2, #a0b4d8)',
        },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: { fontFamily: BODY_FONT, textTransform: 'none', fontWeight: 600, letterSpacing: '0.01em' },
      },
    },
    MuiAvatar: {
      styleOverrides: {
        root: { boxShadow: '0 2px 10px rgba(0, 0, 0, 0.08)' },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-root': { borderRadius: 10 },
          '& .MuiInputBase-root': { fontFamily: BODY_FONT },
          '& .MuiInputBase-input': { fontFamily: BODY_FONT },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontFamily: BODY_FONT, borderRadius: 20, fontWeight: 600, letterSpacing: '0.01em' },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: { borderRadius: 12, backdropFilter: 'saturate(180%) blur(20px)' },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: { borderRadius: 4, height: 4 },
      },
    },
  },
});

const App: React.FC = () => {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <StoryProvider>
        <Router>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/start" element={<EmotionalNeedForm />} />
            <Route path="/experiment" element={<ExperimentMode />} />
            <Route path="/experiment/judge" element={<BenchmarkJudgePage />} />
            <Route path="/clarify-questions" element={<ClarifyingQuestionsForm />} />
            <Route path="/story/preview" element={<StoryPreview />} />
            <Route path="/story/interaction" element={<StoryInteraction />} />
            <Route path="/conclusion" element={<StoryConclusion />} />
            <Route path="/debug/progress" element={<ProgressHarness />} />
          </Routes>
        </Router>

        
      </StoryProvider>
    </ThemeProvider>
  );
};


export default App;
