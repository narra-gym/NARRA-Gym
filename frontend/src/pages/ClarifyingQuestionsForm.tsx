import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  TextField,
  Button,
  Typography,
  Paper,
  Container,
  CircularProgress,
  Alert,
  Stack,
  Divider,
  LinearProgress,
  Radio,
  RadioGroup,
  FormControlLabel,
  FormControl,
  Checkbox,
  FormGroup,
} from '@mui/material';
import { useStory, QuestionWithOptions } from '../contexts/StoryContext';
import StoryProgressBar from '../components/StoryProgressBar';
import ShaderBackground from '../components/ShaderBackground';

const ClarifyingQuestionsForm: React.FC = () => {
  const navigate = useNavigate();
  const { 
    clarifyingQuestions, 
    questionsData,
    keywords, 
    submitAnswersAndCreateStory, 
    loading, 
    error, 
    storyId,
    profileKeywords,
  } = useStory();
  
  const [answers, setAnswers] = useState<Record<string, string | string[]>>({});
  const [selectedKeywords, setSelectedKeywords] = useState<string[]>([]);
  const [customKeywords, setCustomKeywords] = useState<string>('');
  const [customKeywordError, setCustomKeywordError] = useState<string>('');
  const [showKeywordStep, setShowKeywordStep] = useState(false);
  const [showProgressBar, setShowProgressBar] = useState(false);
  const [storyGenerated, setStoryGenerated] = useState(false);
  const [customAnswers, setCustomAnswers] = useState<Record<string, string>>({});
  const [useCustomAnswer, setUseCustomAnswer] = useState<Record<string, boolean>>({});
  const [showProfileKeywordStep, setShowProfileKeywordStep] = useState(false);
  const [selectedProfileKeywords, setSelectedProfileKeywords] = useState<Record<string, string[]>>({ social_inclination: [], interests: [], personality: [] });
  const [customProfileKeywords, setCustomProfileKeywords] = useState<Record<string, string>>({ social_inclination: '', interests: '', personality: '' });
  const [finalProfileKeywords, setFinalProfileKeywords] = useState<Record<string, string[]>>({ social_inclination: [], interests: [], personality: [] });
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState<number>(0);
  const [, setCanSubmitKeywords] = useState<boolean>(false);
  const [guidanceSentence, setGuidanceSentence] = useState<string>("");

  // Friendly remarks to make the profiling more engaging
  const questionRemarks: Record<number, string> = {
    2: "Let me get to know you a little better.", // Before question 3 (0-based index)
    4: "Great, we're halfway there!",              // Before question 5
    7: "Just a few more questions...",            // Before question 8
    9: "This is the final question – thank you!"  // Before question 10
  };

  const handleSkipAllQuestions = () => {
    // Skip the entire clarifying questions flow and jump to story keyword selection
    setShowProfileKeywordStep(false);
    setShowKeywordStep(true);
    setCanSubmitKeywords(false);
    setTimeout(() => setCanSubmitKeywords(true), 500);
  };

  useEffect(() => {
    if (!loading && (!clarifyingQuestions || !storyId)) {
      navigate('/');
    }
  }, [clarifyingQuestions, storyId, navigate, loading]);

  const handleAnswerChange = (question: string, value: string) => {
    setAnswers(prev => ({ ...prev, [question]: value }));
    // When selecting a predefined option, disable custom answer mode
    setUseCustomAnswer(prev => ({ ...prev, [question]: false }));
  };
  
  // Handle multiple choice answer change
  const handleMultipleAnswerChange = (question: string, value: string, checked: boolean) => {
    setAnswers(prev => {
      const currentAnswers = Array.isArray(prev[question]) ? prev[question] as string[] : [];
      
      if (checked) {
        // Add the value if it's checked and not already in the array
        return { ...prev, [question]: [...currentAnswers, value] };
      } else {
        // Remove the value if it's unchecked
        return { ...prev, [question]: currentAnswers.filter(item => item !== value) };
      }
    });
    
    // When selecting predefined options, disable custom answer mode
    setUseCustomAnswer(prev => ({ ...prev, [question]: false }));
  };
  
  const handleCustomAnswerChange = (question: string, value: string) => {
    setCustomAnswers(prev => ({ ...prev, [question]: value }));
    // When typing a custom answer, enable custom answer mode
    if (value.trim()) {
      setUseCustomAnswer(prev => ({ ...prev, [question]: true }));
    }
  };
  
  const handleToggleCustomAnswer = (question: string, enabled: boolean) => {
    setUseCustomAnswer(prev => ({ ...prev, [question]: enabled }));
  };
  
  const handleNext = () => {
    if (clarifyingQuestions) {
      // Save the current question's answer before moving on
      const currentQuestion = getCurrentQuestion();
      if (currentQuestion) {
        const questionText = currentQuestion.question;
        
        if (useCustomAnswer[questionText]) {
          // If using custom answer, store as string
          const customAnswer = customAnswers[questionText] || '';
          setAnswers(prev => ({ ...prev, [questionText]: customAnswer }));
        } else if (currentQuestion.questionType === 'multiple') {
          // For multiple choice, we've already stored the array in answers state
          // Make sure it's initialized
          if (!answers[questionText]) {
            setAnswers(prev => ({ ...prev, [questionText]: [] }));
          }
        }
        // For single choice, we've already stored the string answer
      }
      
      // If on the last question, show keyword selection step instead of submitting
      if (currentQuestionIndex === clarifyingQuestions.length - 1) {
        setShowProfileKeywordStep(true);
        // Reset submission flag when entering keyword step
        setCanSubmitKeywords(false);
        
        // Enable submission after a short delay to prevent auto-submission
        setTimeout(() => {
          setCanSubmitKeywords(true);
        }, 500);
      } else {
        // Otherwise just advance to the next question
        setCurrentQuestionIndex((prev: number) => prev + 1);
      }
    }
  };

  const handleBack = () => {
    if (showKeywordStep) {
      setShowKeywordStep(false);
      setShowProfileKeywordStep(true);
    } else if (showProfileKeywordStep) {
      setShowProfileKeywordStep(false);
    } else if (currentQuestionIndex > 0) {
      setCurrentQuestionIndex((prev: number) => prev - 1);
    } else {
      navigate('/start');
    }
  };

  const toggleKeyword = (keyword: string) => {
    setSelectedKeywords(prev => {
      if (prev.includes(keyword)) {
        return prev.filter(k => k !== keyword);
      }
      return [...prev, keyword];
    });
  };

  const handleCustomKeywordsChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setCustomKeywords(value);
    
    // Clear previous errors
    setCustomKeywordError('');
    
    // Basic format validation
    if (value.trim() !== '') {
      // Check for allowed characters
      const keywordRegex = /^[a-zA-Z0-9\s,]+$/;
      if (!keywordRegex.test(value)) {
        setCustomKeywordError('Keywords should only contain letters, numbers, spaces, and commas');
        return;
      }
      
      // Check for empty keywords between commas
      const keywordsList = value.split(',');
      if (keywordsList.some(kw => kw.trim() === '')) {
        setCustomKeywordError('Please avoid empty keywords or consecutive commas');
      }
      
      // Check for keywords that are too long
      if (keywordsList.some(kw => kw.trim().length > 20)) {
        setCustomKeywordError('Each keyword should be 20 characters or less');
      }
    }
  };

  const getFormattedKeywords = (): string[] => {
    const predefinedSelected = [...selectedKeywords];
    
    if (customKeywords.trim()) {
      // Process custom keywords - split by comma and trim each one
      const customKeywordsList = customKeywords
        .split(',')
        .map(kw => kw.trim())
        .filter(kw => kw !== ''); // Remove empty items
      
      // Manual deduplication without using Set
      const allKeywords = [...predefinedSelected];
      customKeywordsList.forEach(keyword => {
        if (!allKeywords.includes(keyword)) {
          allKeywords.push(keyword);
        }
      });
      
      return allKeywords;
    }
    
    return predefinedSelected;
  };
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!showKeywordStep) {
      return; // Should not be called from question pages
    }
    
    // Check for custom keyword errors before submitting
    if (customKeywordError) {
      return;
    }
    
    try {
      // Get combined keywords (selected + custom)
      const allKeywords = getFormattedKeywords();
      
      // Convert any string[] answers to comma-separated strings for API compatibility
      const formattedAnswers: Record<string, string> = {};
      Object.entries(answers).forEach(([key, value]) => {
        if (Array.isArray(value)) {
          formattedAnswers[key] = value.join(', ');
        } else {
          formattedAnswers[key] = value;
        }
      });
      
      // 显示进度条
      setShowProgressBar(true);
      
      await submitAnswersAndCreateStory(formattedAnswers, allKeywords, finalProfileKeywords, guidanceSentence.trim());
      setStoryGenerated(true);
      
      // 生成完成后导航到预览页面
      navigate('/story/preview');
    } catch (err) {
      console.error("Failed to submit answers and create story", err);
      setShowProgressBar(false);
    }
  };

  const handleStoryGenerationComplete = () => {
    if (storyGenerated) {
      navigate('/story/preview');
    }
  };

  // Helper function to get the current question data
  const getCurrentQuestion = (): QuestionWithOptions | null => {
    if (!questionsData || questionsData.length === 0 || showKeywordStep) {
      return null;
    }
    return questionsData[currentQuestionIndex];
  };

  // Fallback to old question format if questionsData is not available
  const getCurrentQuestionText = (): string => {
    if (showKeywordStep) return "";
    
    if (questionsData && questionsData.length > 0) {
      return questionsData[currentQuestionIndex].question;
    }
    
    if (clarifyingQuestions && clarifyingQuestions.length > 0) {
      return clarifyingQuestions[currentQuestionIndex];
    }
    
    return "";
  };

  const aggregateProfileKeywords = (): Record<string,string[]> => {
    const output: Record<string,string[]> = {} as any;
    (['social_inclination','interests','personality'] as const).forEach(topic=>{
      const selected = selectedProfileKeywords[topic] || [];
      const customs = customProfileKeywords[topic]
        .split(',')
        .map(s=>s.trim())
        .filter(Boolean);
      const unique = Array.from(new Set([...selected, ...customs]));
      output[topic] = unique;
    });
    return output;
  };

  const handleProfileKeywordNext = () => {
    const aggregated = aggregateProfileKeywords();
    setFinalProfileKeywords(aggregated);
    setShowProfileKeywordStep(false);
    setShowKeywordStep(true);
  };

  // Determine if story can be submitted
  const canSubmitStory = showKeywordStep && (
    (selectedKeywords.length > 0 || (customKeywords.trim() !== '' && !customKeywordError))
  );

  // Check if multiple-choice answer includes an option
  const isOptionChecked = (question: string, option: string): boolean => {
    const answer = answers[question];
    return Array.isArray(answer) ? answer.includes(option) : false;
  };

  if (!clarifyingQuestions) {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <CircularProgress />
        <Typography sx={{ mt: 2, color: 'text.secondary' }}>Generating personalized questions for you...</Typography>
      </Box>
    );
  }

  const currentQuestion = getCurrentQuestionText();
  const currentQuestionData = getCurrentQuestion();
  const progress = (showKeywordStep || showProfileKeywordStep)
    ? 100
    : ((currentQuestionIndex + 1) / clarifyingQuestions.length) * 100;

  /* ── Shared inline-sx tokens (Apple-style glassmorphism) ── */
  const readableText = {
    strong: 'var(--emo-ink)',
    primary: 'var(--emo-ink-soft)',
    secondary: 'var(--emo-ink-muted)',
    accent: 'var(--emo-accent)',
    accentStrong: 'var(--emo-accent-strong)',
  };

  const glassCard = {
    background: 'linear-gradient(180deg, rgba(248, 243, 235, 0.92), rgba(242, 235, 226, 0.88))',
    backdropFilter: 'saturate(180%) blur(20px)',
    WebkitBackdropFilter: 'saturate(180%) blur(20px)',
    border: '1px solid var(--emo-glass-border)',
    boxShadow: '0 18px 42px rgba(32, 24, 20, 0.16)',
    borderRadius: '18px',
  };

  const controlColor = {
    color: readableText.secondary,
    '&.Mui-checked': { color: readableText.accentStrong },
  };

  const inputSx = {
    '& .MuiOutlinedInput-root': {
      borderRadius: '10px',
      backgroundColor: 'rgba(255, 250, 245, 0.92)',
      color: readableText.strong,
    },
    '& .MuiInputBase-input': { color: readableText.strong, fontWeight: 500 },
    '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(115, 85, 72, 0.22)' },
    '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(115, 85, 72, 0.38)' },
    '& .MuiOutlinedInput-root.Mui-focused .MuiOutlinedInput-notchedOutline': {
      borderColor: readableText.accent,
      boxShadow: '0 0 0 3px rgba(115, 85, 72, 0.14)',
    },
    '& .MuiInputLabel-root': { color: readableText.secondary },
    '& .MuiInputLabel-root.Mui-focused': { color: readableText.primary },
    '& .MuiInputBase-input::placeholder': { color: readableText.secondary, opacity: 1 },
  };

  const optionRowSx = {
    mb: 0.5,
    ml: 0,
    borderRadius: '10px',
    px: 1.25,
    py: 0.45,
    '&:hover': { bgcolor: 'rgba(115, 85, 72, 0.08)' },
  };

  const pillBtn = (selected: boolean) => ({
    textTransform: 'none' as const,
    borderRadius: '20px',
    px: 2,
    py: 0.75,
    fontSize: '0.875rem',
    fontWeight: 500,
    letterSpacing: '0.01em',
    transition: 'all 0.2s ease',
    border: '1px solid',
    borderColor: selected ? 'rgba(115, 85, 72, 0.35)' : 'rgba(115, 85, 72, 0.18)',
    bgcolor: selected ? 'rgba(115, 85, 72, 0.12)' : 'rgba(255, 255, 255, 0.38)',
    color: selected ? readableText.accentStrong : readableText.primary,
    backdropFilter: 'blur(8px)',
    '&:hover': {
      bgcolor: selected ? 'rgba(115, 85, 72, 0.18)' : 'rgba(255, 255, 255, 0.58)',
      borderColor: 'rgba(115, 85, 72, 0.3)',
    },
  });

  const actionBtn = {
    borderRadius: '10px',
    px: 3.5,
    py: 1.2,
    fontWeight: 600,
    fontSize: '0.95rem',
    bgcolor: readableText.accent,
    color: '#fffaf5',
    border: '1px solid rgba(95, 70, 58, 0.24)',
    backdropFilter: 'blur(12px)',
    boxShadow: '0 10px 24px rgba(56, 38, 28, 0.18)',
    '&:hover': {
      bgcolor: readableText.accentStrong,
      boxShadow: '0 14px 28px rgba(56, 38, 28, 0.22)',
    },
    '&.Mui-disabled': {
      color: 'rgba(255, 250, 245, 0.76)',
      bgcolor: 'rgba(115, 85, 72, 0.38)',
      borderColor: 'rgba(95, 70, 58, 0.12)',
      boxShadow: 'none',
    },
  };

  return (
    <Box sx={{ position: 'fixed', inset: 0, overflow: 'auto' }}>
      <Box sx={{ position: 'absolute', inset: 0, zIndex: 0 }}>
        <ShaderBackground />
        <Box sx={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.52)' }} />
      </Box>

      <Container maxWidth="sm" sx={{ pt: 10, pb: 8, position: 'relative', zIndex: 1 }}>
        {showProgressBar ? (
          <StoryProgressBar
            storyId={storyId || ''}
            onComplete={handleStoryGenerationComplete}
          />
        ) : (
        <Paper elevation={0} sx={{ p: { xs: 3, sm: 4.5 }, overflowY: 'auto', maxHeight: '82vh', ...glassCard }}>

          {/* ── Progress indicator ── */}
          <Box sx={{ mb: 4 }}>
            <Typography variant="body2" align="center" sx={{ color: readableText.secondary, fontSize: '0.8rem', fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase', mb: 1.5 }}>
              {showKeywordStep
                ? 'Story Keywords'
                : showProfileKeywordStep
                ? 'About You'
                : `Question ${currentQuestionIndex + 1} of ${clarifyingQuestions.length}`}
            </Typography>
            <LinearProgress
              variant="determinate"
              value={progress}
              sx={{
                height: 3,
                borderRadius: '2px',
                bgcolor: 'rgba(115, 85, 72, 0.12)',
                '& .MuiLinearProgress-bar': {
                  background: 'linear-gradient(90deg, rgba(115, 85, 72, 0.5), rgba(95, 70, 58, 0.92))',
                  borderRadius: '2px',
                },
              }}
            />
          </Box>

          {/* ── Title / question ── */}
          {showProfileKeywordStep ? (
            <Typography variant="h5" component="h1" align="center" sx={{ color: readableText.strong, minHeight: 80, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700 }}>
              Select keywords that describe you
            </Typography>
          ) : showKeywordStep ? (
            <Typography variant="h5" component="h1" align="center" sx={{ color: readableText.strong, minHeight: 80, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700 }}>
              Select keywords for your story
            </Typography>
          ) : (
            <>
              {questionRemarks[currentQuestionIndex] && (
                <Typography variant="body2" align="center" sx={{ color: readableText.secondary, mb: 1, fontWeight: 600 }}>
                  {questionRemarks[currentQuestionIndex]}
                </Typography>
              )}
              <Typography variant="h5" component="h1" align="center" sx={{ color: readableText.strong, minHeight: 80, display: 'flex', alignItems: 'center', justifyContent: 'center', px: 1, fontWeight: 700 }}>
                {currentQuestion}
              </Typography>
            </>
          )}

          {/* ── Form body ── */}
          <form onSubmit={handleSubmit}>

            {/* Question options */}
            {(!showKeywordStep && !showProfileKeywordStep) && (
              <Stack spacing={3} sx={{ mt: 3 }}>
                {currentQuestionData ? (
                  <Box>
                    <FormControl component="fieldset" fullWidth>
                      {(!currentQuestionData.questionType || currentQuestionData.questionType === 'single') ? (
                        <RadioGroup
                          value={useCustomAnswer[currentQuestion] ? "custom" : (
                            Array.isArray(answers[currentQuestion]) ? "" : (answers[currentQuestion] || "")
                          )}
                          onChange={(e) => {
                            const value = e.target.value;
                            if (value === "custom") { handleToggleCustomAnswer(currentQuestion, true); }
                            else { handleAnswerChange(currentQuestion, value); }
                          }}
                        >
                          {currentQuestionData.options.map((option, idx) => (
                            <FormControlLabel
                              key={`opt-${currentQuestionIndex}-${idx}`}
                              value={option}
                              control={<Radio sx={controlColor} />}
                              label={<Typography sx={{ color: readableText.primary, fontSize: '0.95rem', fontWeight: 500 }}>{option}</Typography>}
                              sx={optionRowSx}
                            />
                          ))}
                          <FormControlLabel
                            value="custom"
                            control={<Radio sx={controlColor} />}
                            label={<Typography sx={{ color: readableText.secondary, fontSize: '0.95rem', fontWeight: 500 }}>Other (specify below)</Typography>}
                            sx={optionRowSx}
                          />
                        </RadioGroup>
                      ) : (
                        <FormGroup>
                          {currentQuestionData.options.map((option, idx) => (
                            <FormControlLabel
                              key={`opt-${currentQuestionIndex}-${idx}`}
                              control={
                                <Checkbox sx={controlColor}
                                  checked={isOptionChecked(currentQuestion, option)}
                                  onChange={(e) => handleMultipleAnswerChange(currentQuestion, option, e.target.checked)}
                                />
                              }
                              label={<Typography sx={{ color: readableText.primary, fontSize: '0.95rem', fontWeight: 500 }}>{option}</Typography>}
                              sx={optionRowSx}
                            />
                          ))}
                          <FormControlLabel
                            control={
                              <Checkbox sx={controlColor}
                                checked={!!useCustomAnswer[currentQuestion]}
                                onChange={(e) => handleToggleCustomAnswer(currentQuestion, e.target.checked)}
                              />
                            }
                            label={<Typography sx={{ color: readableText.secondary, fontSize: '0.95rem', fontWeight: 500 }}>Other (specify below)</Typography>}
                            sx={optionRowSx}
                          />
                        </FormGroup>
                      )}
                    </FormControl>

                    {useCustomAnswer[currentQuestion] && (
                      <TextField
                        fullWidth placeholder="Type your custom answer here..." multiline rows={2}
                        value={customAnswers[currentQuestion] || ''}
                        onChange={(e) => handleCustomAnswerChange(currentQuestion, e.target.value)}
                        variant="outlined" sx={{ mt: 2, ...inputSx }}
                      />
                    )}
                  </Box>
                ) : (
                  <TextField fullWidth placeholder="You can leave this blank if you wish..." multiline rows={4}
                    value={Array.isArray(answers[currentQuestion]) ? (answers[currentQuestion] as string[]).join(', ') : (answers[currentQuestion] as string) || ''}
                    onChange={(e) => handleAnswerChange(currentQuestion, e.target.value)}
                    variant="outlined" autoFocus sx={inputSx}
                  />
                )}
              </Stack>
            )}

            {/* Profile keywords */}
            {showProfileKeywordStep && profileKeywords && (
              <Box sx={{ mt: 3 }}>
                {(['social_inclination', 'interests', 'personality'] as const).map((topic) => (
                  <Box key={topic} sx={{ mb: 4 }}>
                    <Typography variant="subtitle1" align="center" gutterBottom sx={{ color: readableText.secondary, textTransform: 'capitalize', fontSize: '0.85rem', letterSpacing: '0.04em', fontWeight: 600 }}>
                      {topic.replace('_', ' ')}
                    </Typography>
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, justifyContent: 'center' }}>
                      {profileKeywords[topic]?.map((kw) => (
                        <Button key={`profile-${topic}-${kw}`}
                          variant="text"
                          onClick={() => {
                            setSelectedProfileKeywords(prev => {
                              const list = prev[topic] || [];
                              return { ...prev, [topic]: list.includes(kw) ? list.filter(x => x !== kw) : [...list, kw] };
                            });
                          }}
                          sx={pillBtn(selectedProfileKeywords[topic]?.includes(kw))}
                        >{kw}</Button>
                      ))}
                    </Box>
                    <TextField fullWidth label="Custom keywords (comma separated)" value={customProfileKeywords[topic]}
                      onChange={(e) => setCustomProfileKeywords(prev => ({ ...prev, [topic]: e.target.value }))}
                      sx={{ mt: 2, ...inputSx }} size="small"
                    />
                  </Box>
                ))}
              </Box>
            )}

            {/* Story keywords */}
            {showKeywordStep && (
              <Box sx={{ mt: 3 }}>
                <Typography variant="body2" align="center" sx={{ mb: 3, color: readableText.secondary, lineHeight: 1.6, fontWeight: 500 }}>
                  These keywords will become central elements in your story — locations, characters, or themes.
                </Typography>

                {keywords && keywords.length > 0 ? (
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, justifyContent: 'center' }}>
                    {keywords.map((kw) => (
                      <Button key={`story-${kw}`} variant="text" onClick={() => toggleKeyword(kw)}
                        sx={pillBtn(selectedKeywords.includes(kw))}
                      >{kw}</Button>
                    ))}
                  </Box>
                ) : (
                  <Alert severity="warning" sx={{ mb: 3, bgcolor: 'rgba(255, 243, 219, 0.92)', color: '#6a4c1d', border: '1px solid rgba(181, 135, 52, 0.22)', '& .MuiAlert-message': { color: '#6a4c1d', fontWeight: 500 }, '& .MuiAlert-icon': { color: '#b17f2c' } }}>
                    We couldn't find suggested keywords. Please add your own below.
                  </Alert>
                )}

                <Divider sx={{ my: 4, borderColor: 'rgba(115, 85, 72, 0.14)' }} />

                <Typography variant="subtitle1" align="center" gutterBottom sx={{ color: readableText.strong, fontWeight: 700 }}>
                  Optional story guidance
                </Typography>
                <TextField fullWidth placeholder="e.g., The story should begin in a crumbling lighthouse at dusk."
                  value={guidanceSentence} onChange={(e) => setGuidanceSentence(e.target.value)}
                  multiline rows={2} sx={{ mt: 1.5, mb: 3, ...inputSx }}
                />

                <Typography variant="subtitle1" align="center" gutterBottom sx={{ color: readableText.strong, fontWeight: 700 }}>
                  Or add your own keywords
                </Typography>
                <TextField fullWidth placeholder="e.g., beach, mountain, dragon, wizard"
                  value={customKeywords} onChange={handleCustomKeywordsChange}
                  error={!!customKeywordError}
                  helperText={customKeywordError || "Separate keywords with commas"}
                  sx={{ mt: 1.5, ...inputSx, '& .MuiFormHelperText-root': { color: readableText.secondary, fontWeight: 500 } }}
                />
                {customKeywords && !customKeywordError && (
                  <Typography variant="body2" sx={{ mt: 1, color: readableText.secondary, fontWeight: 500 }}>
                    {customKeywords.split(',').map(kw => kw.trim()).filter(kw => kw !== '').length} custom keyword(s) added
                  </Typography>
                )}

                {(selectedKeywords.length > 0 || (customKeywords && !customKeywordError)) && (
                  <Box sx={{ mt: 3, p: 2, borderRadius: '12px', bgcolor: 'rgba(255, 255, 255, 0.52)', border: '1px solid rgba(115, 85, 72, 0.14)' }}>
                    <Typography variant="body2" gutterBottom sx={{ color: readableText.secondary, fontSize: '0.8rem', fontWeight: 600 }}>
                      Your story keywords:
                    </Typography>
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75 }}>
                      {getFormattedKeywords().map((keyword, index) => (
                        <Box key={index} sx={{ bgcolor: 'rgba(115, 85, 72, 0.12)', color: readableText.accentStrong, px: 1.5, py: 0.4, borderRadius: '6px', fontSize: '0.85rem', fontWeight: 600 }}>
                          {keyword}
                        </Box>
                      ))}
                    </Box>
                  </Box>
                )}
              </Box>
            )}

            {error && (
              <Alert severity="error" sx={{ mt: 3, mb: 2, bgcolor: 'rgba(255, 235, 235, 0.94)', color: '#8a2f2f', border: '1px solid rgba(180, 72, 72, 0.2)', '& .MuiAlert-message': { color: '#8a2f2f', fontWeight: 500 }, '& .MuiAlert-icon': { color: '#b44848' } }}>
                {error}
              </Alert>
            )}

            {/* ── Footer actions ── */}
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 5 }}>
              <Button variant="text" onClick={handleBack} disabled={loading}
                sx={{ color: readableText.primary, fontWeight: 500, '&:hover': { color: readableText.accentStrong, bgcolor: 'transparent' } }}
              >Back</Button>

              {(!showKeywordStep && !showProfileKeywordStep) && (
                <Button variant="text" onClick={handleSkipAllQuestions} disabled={loading}
                  sx={{ color: readableText.secondary, fontSize: '0.85rem', fontWeight: 500, '&:hover': { color: readableText.primary, bgcolor: 'transparent' } }}
                >Skip all</Button>
              )}

              {showKeywordStep ? (
                <Button type="submit" variant="contained" size="large" disabled={loading || !canSubmitStory} sx={actionBtn}>
                  {loading ? <CircularProgress size={20} sx={{ color: '#fffaf5' }} /> : 'Create My Story'}
                </Button>
              ) : showProfileKeywordStep ? (
                <Button variant="contained" onClick={handleProfileKeywordNext} size="large" sx={actionBtn}>
                  Continue
                </Button>
              ) : (
                <Button variant="contained" onClick={handleNext} size="large" sx={actionBtn}
                  disabled={useCustomAnswer[currentQuestion] && (!customAnswers[currentQuestion] || !customAnswers[currentQuestion].trim())}
                >Next</Button>
              )}
            </Box>
          </form>
        </Paper>
        )}
      </Container>
    </Box>
  );
};

export default ClarifyingQuestionsForm; 
