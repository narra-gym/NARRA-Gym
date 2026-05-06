import React, { createContext, useContext, useState, ReactNode, useEffect, useCallback, startTransition } from 'react';
import { Story, ExperimentSession, Message, Choice, Character, StoryMemory, StoryProgress, SceneInfoPanel, CastStatus, InteractiveElementHistoryItem, StoryStateMetadata } from '../types';
import axios from 'axios'; // Using axios for API calls
import {
  getEffectiveFastForward,
  shouldAutoInsertInteractiveElement,
  shouldPrefetchChoiceReflection,
} from '../utils/benchmarkMode';
import { authorizedFetch } from '../utils/apiAccess';
import { API_BASE_URL } from '../utils/apiBaseUrl';
import { mapRawMessageToMessage } from '../utils/storyMessages';
import { dedupeTextList, toDisplayText } from '../utils/textLists';

export { API_BASE_URL };
const EXPERIMENT_STORAGE_KEY = 'emonest-experiment-session';

interface StoryContextType {
  story: Story | null;
  storyId: string | null;
  clarifyingQuestions: string[] | null;
  questionsData: QuestionWithOptions[] | null;
  keywords: string[] | null;
  loading: boolean;
  error: string | null;
  userId: string;
  emotionalNeed: string;
  submitEmotionalNeed: (emotionalNeed: string) => Promise<void>;
  initiateStory: (emotionalNeed: string) => Promise<void>;
  submitAnswersAndCreateStory: (answers: Record<string, string>, storyKeywords?: string[], profileKeywords?: Record<string, string[]>, guidanceSentence?: string) => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  selectChoice: (choiceId: string) => Promise<void>;
  endStory: () => Promise<void>;
  storyGenerationProgress: number;
  currentGenerationStep: number;
  generationStatus: string;
  getStoryGenerationProgress: (id: string) => Promise<void>;
  storyReflection: any | null;
  interactiveElement: {
    code: string;
    elementType: string;
    prompt?: string;
  } | null;
  dialogueCount: number;
  pacingRecommendation: string | null;
  generateStoryReflection: (userInput: string) => Promise<any>;
  generateInteractiveElement: (
    elementType: string,
    description: string,
    contentDetails: string
  ) => Promise<any>;
  clearInteractiveElement: () => void;
  profileKeywords: Record<string, string[]> | null;
  fastForward: boolean;
  setFastForward: (value: boolean) => void;
  appendMessageToCurrentScene: (message: Message) => void;
  emotionHistory: Array<{ tone: string; index: number; timestamp: string }>;
  experimentSession: ExperimentSession | null;
  experimentMode: boolean;
  startExperimentSession: (
    selectedModel?: string | null,
    requestedConditionId?: string,
    blindCode?: number | string | null,
  ) => Promise<ExperimentSession>;
  clearExperimentSession: () => void;
  loadHistoricalStory: (rawStory: any) => void;
}

// Define the new question format type
export interface QuestionWithOptions {
  question: string;
  options: string[];
  allowsCustom: boolean;
  questionType?: 'single' | 'multiple'; // Add question type with optional property for backward compatibility
}

const StoryContext = createContext<StoryContextType | undefined>(undefined);

export const useStory = () => {
  const context = useContext(StoryContext);
  if (context === undefined) {
    throw new Error('useStory must be used within a StoryProvider');
  }
  return context;
};

interface StoryProviderProps {
  children: ReactNode;
}

const firstDisplayText = (...values: unknown[]): string => {
  for (const value of values) {
    const text = toDisplayText(value);
    if (text) return text;
  }
  return '';
};

const normalizeDisplayList = (raw: unknown, fallback?: string[]): string[] => (
  dedupeTextList(Array.isArray(raw) ? raw : (fallback || []))
);

const normalizeStoryMemory = (raw: any, fallback?: StoryMemory): StoryMemory => ({
  whatJustHappened: firstDisplayText(raw?.what_just_happened, raw?.whatJustHappened, fallback?.whatJustHappened),
  currentGoal: firstDisplayText(raw?.current_goal, raw?.currentGoal, fallback?.currentGoal),
  openTensions: normalizeDisplayList(raw?.open_tensions ?? raw?.openTensions, fallback?.openTensions),
  activeClues: normalizeDisplayList(raw?.active_clues ?? raw?.activeClues, fallback?.activeClues),
  lastMajorTurningPoint: firstDisplayText(raw?.last_major_turning_point, raw?.lastMajorTurningPoint, fallback?.lastMajorTurningPoint),
});

const normalizeStoryProgress = (raw: any, fallback?: StoryProgress): StoryProgress => ({
  currentActIndex: raw?.current_act_index ?? raw?.currentActIndex ?? fallback?.currentActIndex ?? 0,
  actCount: raw?.act_count ?? raw?.actCount ?? fallback?.actCount ?? 0,
  currentActTitle: firstDisplayText(raw?.current_act_title, raw?.currentActTitle, fallback?.currentActTitle),
  currentActPurpose: firstDisplayText(raw?.current_act_purpose, raw?.currentActPurpose, fallback?.currentActPurpose),
  sceneLocation: firstDisplayText(raw?.scene_location, raw?.sceneLocation, fallback?.sceneLocation),
});

const normalizeSceneInfoPanel = (raw: any, fallback?: SceneInfoPanel): SceneInfoPanel => ({
  recap: firstDisplayText(raw?.recap, fallback?.recap),
  sceneLocation: firstDisplayText(raw?.scene_location, raw?.sceneLocation, fallback?.sceneLocation),
  objective: firstDisplayText(raw?.objective, fallback?.objective),
  currentTension: firstDisplayText(raw?.current_tension, raw?.currentTension, fallback?.currentTension),
  immediateStakes: firstDisplayText(raw?.immediate_stakes, raw?.immediateStakes, fallback?.immediateStakes),
  locationStatus: firstDisplayText(raw?.location_status, raw?.locationStatus, fallback?.locationStatus),
  clueSummary: normalizeDisplayList(raw?.clue_summary ?? raw?.clueSummary, fallback?.clueSummary),
  tensionSummary: normalizeDisplayList(raw?.tension_summary ?? raw?.tensionSummary, fallback?.tensionSummary),
});

const normalizeStoryState = (raw: any, fallback?: StoryStateMetadata): StoryStateMetadata => ({
  currentObjective: firstDisplayText(raw?.current_objective, raw?.currentObjective, fallback?.currentObjective),
  currentTension: firstDisplayText(raw?.current_tension, raw?.currentTension, fallback?.currentTension),
  immediateStakes: firstDisplayText(raw?.immediate_stakes, raw?.immediateStakes, fallback?.immediateStakes),
  locationStatus: firstDisplayText(raw?.location_status, raw?.locationStatus, fallback?.locationStatus),
  relationshipShift: firstDisplayText(raw?.relationship_shift, raw?.relationshipShift, fallback?.relationshipShift),
  latestReveal: firstDisplayText(raw?.latest_reveal, raw?.latestReveal, fallback?.latestReveal),
  emotionalBeat: firstDisplayText(raw?.emotional_beat, raw?.emotionalBeat, fallback?.emotionalBeat),
});

const normalizeCastStatuses = (raw: any, fallback?: CastStatus[]): CastStatus[] => {
  if (!Array.isArray(raw)) return fallback || [];
  return raw.map((item: any) => ({
    characterId: firstDisplayText(item.character_id, item.characterId),
    name: firstDisplayText(item.name),
    role: firstDisplayText(item.role),
    relationship: firstDisplayText(item.relationship),
    currentStatus: firstDisplayText(item.current_status, item.currentStatus),
    lastSeen: firstDisplayText(item.last_seen, item.lastSeen),
    inSceneNow: typeof (item.in_scene_now ?? item.inSceneNow) === 'boolean'
      ? Boolean(item.in_scene_now ?? item.inSceneNow)
      : undefined,
  })).filter((item: CastStatus) => Boolean(item.characterId));
};

const normalizeInteractiveHistory = (raw: any, fallback?: InteractiveElementHistoryItem[]): InteractiveElementHistoryItem[] => {
  if (!Array.isArray(raw)) return fallback || [];
  return raw.map((item: any) => ({
    summary: firstDisplayText(item.summary),
    noveltyTags: normalizeDisplayList(item.novelty_tags ?? item.noveltyTags),
    similarityScore: typeof (item.similarity_score ?? item.similarityScore) === 'number' ? (item.similarity_score ?? item.similarityScore) : 0,
  }));
};

const normalizeHiddenElements = (raw: any, fallback?: Story['currentScene']['hiddenElements']) => ({
  easterEgg: firstDisplayText(raw?.easter_egg, raw?.easterEgg, fallback?.easterEgg),
  foreshadowing: firstDisplayText(raw?.foreshadowing, fallback?.foreshadowing),
});

const normalizeSceneElements = (raw: any, fallback?: Story['currentScene']['sceneElements']) => ({
  atmosphere: firstDisplayText(raw?.atmosphere, fallback?.atmosphere),
  visualDetails: normalizeDisplayList(raw?.visual_details ?? raw?.visualDetails, fallback?.visualDetails),
  symbolicMotifs: normalizeDisplayList(raw?.symbolic_motifs ?? raw?.symbolicMotifs, fallback?.symbolicMotifs),
});

const normalizeSceneDynamics = (raw: any, fallback?: Story['currentScene']['sceneDynamics']) => ({
  transitionRequired: raw?.transition_required ?? raw?.transitionRequired ?? fallback?.transitionRequired ?? false,
  newLocation: firstDisplayText(raw?.new_location, raw?.newLocation, fallback?.newLocation),
  timeProgression: firstDisplayText(raw?.time_progression, raw?.timeProgression, fallback?.timeProgression),
  narrativeAdvancement: firstDisplayText(raw?.narrative_advancement, raw?.narrativeAdvancement, fallback?.narrativeAdvancement),
  sceneTransitionCaption: firstDisplayText(raw?.scene_transition_caption, raw?.sceneTransitionCaption),
});

const mapCharacter = (char: any): Character => ({
  id: firstDisplayText(char.id),
  name: firstDisplayText(char.name),
  role: char.role === 'protagonist' ? 'protagonist' : char.role === 'system' ? 'system' : 'npc',
  description: firstDisplayText(char.visual_description, char.description, char.personality),
  personality: firstDisplayText(char.personality),
  backstory: firstDisplayText(char.backstory),
  relationship: firstDisplayText(char.relationship, char.relationship_to_protagonist),
  imageUrl: firstDisplayText(char.image_url, char.imageUrl) || undefined,
});

const mapMessage = mapRawMessageToMessage;

const mapChoice = (choice: any): Choice => ({
  id: firstDisplayText(choice.id),
  text: firstDisplayText(choice.text),
  emotionalImpact: firstDisplayText(choice.dramatic_impact, choice.emotionalImpact),
  nextSceneHint: firstDisplayText(choice.visual_representation, choice.next_scene_hint, choice.nextSceneHint) || undefined,
});

export const resolveSceneChoices = (rawScene: any, previousChoices?: Choice[]): Choice[] => {
  if (!rawScene) {
    return previousChoices || [];
  }

  if (!Array.isArray(rawScene.choices)) {
    return [];
  }

  return rawScene.choices.map(mapChoice);
};

const transformStoryPayload = (raw: any, fallbackUserId: string, previousStory?: Story | null): Story => {
  const rawCurrentScene = raw.current_scene || raw.currentScene;
  const mappedCharacters = (raw.characters || []).map(mapCharacter);
  const previousScene = previousStory?.currentScene;
  const mappedMessages = (rawCurrentScene?.messages || []).map(mapMessage).filter((message: Message | null): message is Message => Boolean(message));
  const mappedChoices = resolveSceneChoices(rawCurrentScene, previousScene?.choices);
  const previousStoryMemory = previousStory?.storyMemory;
  const previousStoryProgress = previousStory?.storyProgress;
  const previousSceneInfoPanel = previousStory?.sceneInfoPanel;
  const previousStoryState = previousStory?.storyState;

  return {
    id: firstDisplayText(raw.story_id, raw.id, previousStory?.id),
    userId: firstDisplayText(raw.user_id, previousStory?.userId, fallbackUserId),
    title: firstDisplayText(raw.title, previousStory?.title),
    theme: firstDisplayText(raw.theme, raw.cinematic_theme, previousStory?.theme),
    setting: raw.setting || previousStory?.setting || '',
    characters: mappedCharacters.length ? mappedCharacters : (previousStory?.characters || []),
    currentScene: {
      id: firstDisplayText(rawCurrentScene?.id, previousScene?.id, 'scene-1'),
      description: firstDisplayText(rawCurrentScene?.description, previousScene?.description),
      setting: firstDisplayText(rawCurrentScene?.location, rawCurrentScene?.setting) || raw.setting || previousScene?.setting || '',
      location: firstDisplayText(rawCurrentScene?.location, previousScene?.location),
      characters: mappedCharacters.length ? mappedCharacters.map((c: Character) => c.id) : (previousScene?.characters || []),
      messages: mappedMessages.length ? mappedMessages : (previousScene?.messages || []),
      choices: mappedChoices,
      emotionalTone: firstDisplayText(rawCurrentScene?.emotional_tone, rawCurrentScene?.mood, rawCurrentScene?.emotionalTone, previousScene?.emotionalTone),
      inciting_incident: firstDisplayText(rawCurrentScene?.inciting_incident, previousScene?.inciting_incident),
      mood: firstDisplayText(rawCurrentScene?.mood, rawCurrentScene?.emotional_tone, previousScene?.mood),
      scene_transition_caption: firstDisplayText(rawCurrentScene?.scene_transition_caption),
      backgroundImage: firstDisplayText(rawCurrentScene?.backgroundImage, rawCurrentScene?.background_image, previousScene?.backgroundImage) || undefined,
      hiddenElements: normalizeHiddenElements(rawCurrentScene?.hidden_elements || rawCurrentScene?.hiddenElements || {}, previousScene?.hiddenElements),
      sceneElements: normalizeSceneElements(rawCurrentScene?.scene_elements || rawCurrentScene?.sceneElements || {}, previousScene?.sceneElements),
      sceneDynamics: normalizeSceneDynamics(rawCurrentScene?.scene_dynamics || rawCurrentScene?.sceneDynamics || {}, previousScene?.sceneDynamics),
      storyState: normalizeStoryState(rawCurrentScene?.story_state || rawCurrentScene?.storyState || raw.story_state || raw.storyState, previousScene?.storyState || previousStoryState),
    },
    previousScenes: previousStory?.previousScenes || [],
    emotionalGoal: firstDisplayText(raw.emotional_goal, raw.emotional_undercurrent, previousStory?.emotionalGoal),
    status: raw.status || 'active',
    createdAt: raw.created_at || previousStory?.createdAt || new Date().toISOString(),
    updatedAt: raw.updated_at || previousStory?.updatedAt || new Date().toISOString(),
    dialogueSummaries: normalizeDisplayList(raw.dialogue_summaries ?? raw.dialogueSummaries, previousStory?.dialogueSummaries),
    dialogueCount: raw.dialogue_count ?? raw.dialogueCount ?? previousStory?.dialogueCount ?? 0,
    exchangeCount: raw.exchange_count ?? raw.exchangeCount ?? previousStory?.exchangeCount ?? 0,
    conclusionCountdown: raw.conclusion_countdown ?? raw.conclusionCountdown ?? previousStory?.conclusionCountdown ?? 0,
    storyMemory: normalizeStoryMemory(raw.story_memory || raw.storyMemory || {}, previousStoryMemory),
    storyProgress: normalizeStoryProgress(raw.story_progress || raw.storyProgress || {}, previousStoryProgress),
    sceneInfoPanel: normalizeSceneInfoPanel(raw.scene_info_panel || raw.sceneInfoPanel || {}, previousSceneInfoPanel),
    castStatuses: normalizeCastStatuses(raw.cast_statuses || raw.castStatuses, previousStory?.castStatuses),
    interactiveElementHistory: normalizeInteractiveHistory(raw.interactive_element_history || raw.interactiveElementHistory, previousStory?.interactiveElementHistory),
    storyMode: raw.story_mode || raw.storyMode || previousStory?.storyMode || 'default',
    benchmarkSpeedProfile: raw.benchmark_speed_profile ?? raw.benchmarkSpeedProfile ?? previousStory?.benchmarkSpeedProfile ?? false,
    generationMode: raw.generation_mode || raw.generationMode || previousStory?.generationMode || 'legacy_json',
    stateFreshness: raw.state_freshness || raw.stateFreshness || previousStory?.stateFreshness || 'stale',
    stateUpdatedAt: raw.state_updated_at || raw.stateUpdatedAt || previousStory?.stateUpdatedAt || null,
    pacingProfile: raw.pacing_profile || raw.pacingProfile || previousStory?.pacingProfile,
    storyState: normalizeStoryState(raw.story_state || raw.storyState, previousStoryState),
    benchmarkHistory: raw.benchmark_history || raw.benchmarkHistory || previousStory?.benchmarkHistory || null,
  };
};

const mergeStoryPayload = (previousStory: Story | null, raw: any, fallbackUserId: string): Story => {
  const nextStory = transformStoryPayload(raw, fallbackUserId, previousStory);
  if (!previousStory) return nextStory;
  return {
    ...previousStory,
    ...nextStory,
    previousScenes: previousStory.previousScenes,
    currentScene: {
      ...previousStory.currentScene,
      ...nextStory.currentScene,
      messages: nextStory.currentScene.messages,
      choices: nextStory.currentScene.choices,
    },
  };
};

export const StoryProvider: React.FC<StoryProviderProps> = ({ children }) => {
  const [story, setStory] = useState<Story | null>(null);
  const [storyId, setStoryId] = useState<string | null>(null);
  const [clarifyingQuestions, setClarifyingQuestions] = useState<string[] | null>(null);
  const [questionsData, setQuestionsData] = useState<QuestionWithOptions[] | null>(null);
  const [keywords, setKeywords] = useState<string[] | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [userId, setUserId] = useState<string>('user-1');
  const [emotionalNeed, setEmotionalNeed] = useState<string>('');
  const [storyGenerationProgress, setStoryGenerationProgress] = useState<number>(0);
  const [currentGenerationStep, setCurrentGenerationStep] = useState<number>(0);
  const [generationStatus, setGenerationStatus] = useState<string>('');
  const [storyReflection, setStoryReflection] = useState<any | null>(null);
  const [dialogueCount, setDialogueCount] = useState<number>(0);
  const [pacingRecommendation, setPacingRecommendation] = useState<string | null>(null);
  const [interactiveElement, setInteractiveElement] = useState<{
    code: string;
    elementType: string;
    prompt?: string;
  } | null>(null);
  const [fastForward, setFastForward] = useState<boolean>(false);

  const [profileKeywords, setProfileKeywords] = useState<Record<string, string[]> | null>(null);
  const [emotionHistory, setEmotionHistory] = useState<Array<{ tone: string; index: number; timestamp: string }>>([]);
  const [experimentSession, setExperimentSession] = useState<ExperimentSession | null>(null);

  const persistExperimentSession = useCallback((session: ExperimentSession | null) => {
    if (session) {
      window.localStorage.setItem(EXPERIMENT_STORAGE_KEY, JSON.stringify(session));
    } else {
      window.localStorage.removeItem(EXPERIMENT_STORAGE_KEY);
    }
  }, []);

  const applyExperimentSession = useCallback((session: ExperimentSession | null) => {
    setExperimentSession(session);
    if (session) {
      setUserId(session.participant_id);
      persistExperimentSession(session);
      return;
    }

    setUserId('user-1');
    persistExperimentSession(null);
  }, [persistExperimentSession]);

  useEffect(() => {
    let cancelled = false;
    const raw = window.localStorage.getItem(EXPERIMENT_STORAGE_KEY);
    if (!raw) return;

    let parsed: ExperimentSession;
    try {
      parsed = JSON.parse(raw) as ExperimentSession;
    } catch (error) {
      console.warn('Failed to parse persisted experiment session', error);
      window.localStorage.removeItem(EXPERIMENT_STORAGE_KEY);
      return;
    }

    if (!parsed.session_id) {
      applyExperimentSession(parsed);
      return;
    }

    const restorePersistedExperimentSession = async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/experiments/sessions/${parsed.session_id}`);
        const restoredSession = response.data?.session as ExperimentSession | undefined;
        if (cancelled) {
          return;
        }
        applyExperimentSession(restoredSession?.session_id ? restoredSession : parsed);
      } catch (error) {
        if (cancelled) {
          return;
        }

        if (axios.isAxiosError(error) && error.response?.status === 404) {
          console.info('Clearing stale persisted experiment session', parsed.session_id);
          applyExperimentSession(null);
          return;
        }

        console.warn('Failed to validate persisted experiment session', error);
        applyExperimentSession(parsed);
      }
    };

    void restorePersistedExperimentSession();

    return () => {
      cancelled = true;
    };
  }, [applyExperimentSession]);

  const getTypingText = useCallback(() => '...', []);

  const startExperimentSession = async (
    selectedModel?: string | null,
    requestedConditionId?: string,
    blindCode?: number | string | null,
  ): Promise<ExperimentSession> => {
    const response = await axios.post(`${API_BASE_URL}/experiments/session/start`, {
      requested_condition_id: requestedConditionId || null,
      selected_model: selectedModel || null,
      blind_code: blindCode ?? null,
      mode: 'benchmark',
    });
    const session = response.data as ExperimentSession;
    applyExperimentSession(session);
    return session;
  };

  const clearExperimentSession = () => {
    applyExperimentSession(null);
  };

  const loadHistoricalStory = (rawStory: any) => {
    const transformedStory = transformStoryPayload(rawStory, rawStory?.user_id || userId, null);
    setStory(transformedStory);
    setStoryId(transformedStory.id);
    setUserId(transformedStory.userId || rawStory?.user_id || userId);
    setDialogueCount(transformedStory.dialogueCount || 0);
    setStoryReflection(null);
    setInteractiveElement(null);
    setClarifyingQuestions(null);
    setQuestionsData(null);
    setKeywords(null);
    setProfileKeywords(null);
    setError(null);
  };

  const initiateStory = async (emotionalNeed: string): Promise<void> => {
    setLoading(true);
    setError(null);
    setEmotionalNeed(emotionalNeed);
    try {
      const response = await axios.post(`${API_BASE_URL}/story/initiate`, {
        emotional_need: emotionalNeed,
        user_id: experimentSession?.participant_id || userId,
        participant_id: experimentSession?.participant_id || null,
        session_id: experimentSession?.session_id || null,
        experiment_mode: Boolean(experimentSession),
      });
      const { story_id, questions, questions_data, keywords, profile_keywords } = response.data;
      setStoryId(story_id);
      setClarifyingQuestions(questions);
      setQuestionsData(questions_data || null);
      setKeywords(keywords || null);
      setProfileKeywords(profile_keywords || null);
    } catch (err) {
      setError('Failed to initiate story. Please check the backend and try again.');
      console.error(err);
      throw err; // Re-throw to be caught by the form
    } finally {
      setLoading(false);
    }
  };

  const submitEmotionalNeed = async (emotionalNeed: string) => {
    setEmotionalNeed(emotionalNeed);
    await initiateStory(emotionalNeed);
  };

  const generateStoryInSteps = async (
    answers: Record<string, string>,
    storyKeywords: string[],
    profileKeywordsObj: Record<string, string[]>,
    guidanceSentence: string
  ) => {
    setLoading(true);
    setError('');
    
    try {
      // 步骤1：基础框架
      const step1Response = await authorizedFetch(`${API_BASE_URL}/story/create/step1`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          story_id: storyId,
          emotional_need: emotionalNeed,
          user_id: experimentSession?.participant_id || userId,
          participant_id: experimentSession?.participant_id || null,
          session_id: experimentSession?.session_id || null,
          selected_keywords: storyKeywords,
          profile_keywords: profileKeywordsObj,
          guidance_sentence: guidanceSentence,
        }),
      });
      
      if (!step1Response.ok) {
        throw new Error('Failed to create story foundation');
      }
      
      const step1Data = await step1Response.json();
      setStoryGenerationProgress(step1Data.progress);
      setCurrentGenerationStep(1);
      
      // 步骤2：世界构建
      const step2Response = await authorizedFetch(`${API_BASE_URL}/story/create/step2`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          story_id: step1Data.story_id
        }),
      });
      
      if (!step2Response.ok) {
        throw new Error('Failed to create story setting');
      }
      
      const step2Data = await step2Response.json();
      setStoryGenerationProgress(step2Data.progress);
      setCurrentGenerationStep(2);
      
      // 步骤3：角色创建
      const step3Response = await authorizedFetch(`${API_BASE_URL}/story/create/step3`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          story_id: step1Data.story_id
        }),
      });
      
      if (!step3Response.ok) {
        throw new Error('Failed to create story characters');
      }
      
      const step3Data = await step3Response.json();
      setStoryGenerationProgress(step3Data.progress);
      setCurrentGenerationStep(3);
      
      // 步骤4：故事结构
      const step4Response = await authorizedFetch(`${API_BASE_URL}/story/create/step4`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          story_id: step1Data.story_id
        }),
      });
      
      if (!step4Response.ok) {
        throw new Error('Failed to create story structure');
      }
      
      const step4Data = await step4Response.json();
      setStoryGenerationProgress(step4Data.progress);
      setCurrentGenerationStep(4);
      
      // 步骤5：开场和互动元素
      const step5Response = await authorizedFetch(`${API_BASE_URL}/story/create/step5`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          story_id: step1Data.story_id
        }),
      });
      
      if (!step5Response.ok) {
        throw new Error('Failed to create story interactive elements');
      }
      
      const step5Data = await step5Response.json();
      setStoryGenerationProgress(step5Data.progress);
      setCurrentGenerationStep(5);
      
      // 完成故事生成
      const completeResponse = await authorizedFetch(`${API_BASE_URL}/story/complete/${step1Data.story_id}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      
      if (!completeResponse.ok) {
        throw new Error('Failed to complete story generation');
      }
      
      const storyData = await completeResponse.json();
      const transformedStory = transformStoryPayload(storyData, experimentSession?.participant_id || userId);

      setStory(transformedStory);
      setDialogueCount(transformedStory.dialogueCount || 0);
      setStoryId(transformedStory.id);
      setGenerationStatus('completed');
      
      return storyData;
    } catch (err) {
      console.error('Error generating story in steps:', err);
      setError(err instanceof Error ? err.message : 'Failed to generate story');
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const submitAnswersAndCreateStory = async (
    answers: Record<string, string>,
    storyKeywords: string[] = [],
    profileKeywordsObj: Record<string, string[]> = {},
    guidanceSentence: string = ""
  ) => {
    if (!storyId) {
      setError('No story ID available');
      return;
    }

    try {
      // 使用分步骤生成故事
      return await generateStoryInSteps(answers, storyKeywords, profileKeywordsObj, guidanceSentence);
    } catch (err) {
      console.error('Error submitting answers and creating story:', err);
      setError(err instanceof Error ? err.message : 'Failed to create story');
      throw err;
    }
  };

  const getStoryGenerationProgress = async (id: string) => {
    try {
      const response = await authorizedFetch(`${API_BASE_URL}/story/progress/${id}`);
      if (!response.ok) {
        throw new Error('Failed to fetch story progress');
      }
      
      const data = await response.json();
      setStoryGenerationProgress(data.progress);
      setCurrentGenerationStep(data.current_step);
      setGenerationStatus(data.status);
      
      return data;
    } catch (err) {
      console.error('Error fetching story progress:', err);
      return null;
    }
  };

  const updateEmotionHistoryFromStory = (raw: any, processedMessages: Message[]) => {
    const newTone: string = raw.current_scene?.emotional_tone || raw.current_scene?.emotionalTone || raw.current_scene?.mood || '';
    if (!newTone) return;
    setEmotionHistory(prev => {
      const last = prev[prev.length - 1];
      if (last?.tone === newTone) return prev;
      return [
        ...prev,
        { tone: newTone, index: processedMessages.length, timestamp: new Date().toISOString() },
      ];
    });
  };

  const streamTurn = async ({
    endpoint,
    requestBody,
    optimisticContent,
    optimisticType,
    errorMessage,
  }: {
    endpoint: string;
    requestBody: Record<string, any>;
    optimisticContent: string;
    optimisticType: 'text' | 'choice';
    errorMessage: string;
  }): Promise<void> => {
    if (!story) {
      setError('No active story.');
      return;
    }

    const protagonist = story.characters.find(c => c.role === 'protagonist');
    const typingPlaceholderId = `pending-${Math.random().toString(36).substring(2, 9)}`;
    const streamNpcId = `stream-npc-${Date.now()}`;

    const clearTypingPlaceholder = () => {
      startTransition(() => {
        setStory(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            currentScene: {
              ...prev.currentScene,
              messages: prev.currentScene.messages.filter(message => message.id !== typingPlaceholderId),
            },
          };
        });
      });
    };

    const upsertStreamingNpcMessage = (nextText: string) => {
      startTransition(() => {
        setStory(prev => {
          if (!prev) return prev;
          const filtered = prev.currentScene.messages.filter(message => message.id !== typingPlaceholderId);
          const nextMessage: Message = {
            id: streamNpcId,
            characterId: 'npc',
            content: nextText,
            timestamp: new Date().toISOString(),
            type: 'text',
            renderMode: /\*[^*]+\*/.test(nextText) ? 'rp_mixed' : 'plain',
          };
          const existingIndex = filtered.findIndex(message => message.id === streamNpcId);
          const nextMessages = existingIndex >= 0
            ? filtered.map(message => message.id === streamNpcId ? { ...message, ...nextMessage } : message)
            : [...filtered, nextMessage];
          return {
            ...prev,
            currentScene: {
              ...prev.currentScene,
              messages: nextMessages,
            },
          };
        });
      });
    };

    startTransition(() => {
      setStory(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          currentScene: {
            ...prev.currentScene,
            messages: [
              ...prev.currentScene.messages,
              {
                id: `temp-${Math.random().toString(36).substring(2, 9)}`,
                characterId: protagonist?.id || 'protagonist',
                content: optimisticContent,
                timestamp: new Date().toISOString(),
                type: optimisticType,
                renderMode: /\*[^*]+\*/.test(optimisticContent) ? 'rp_mixed' : 'plain',
              },
              {
                id: typingPlaceholderId,
                characterId: 'system',
                content: getTypingText(),
                timestamp: '',
                type: 'typing',
                renderMode: 'plain',
              },
            ],
          },
        };
      });
    });

    try {
      const response = await authorizedFetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok || !response.body) {
        throw new Error(`Stream request failed: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let sseBuffer = '';
      let streamText = '';
      let streamStarted = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        sseBuffer += decoder.decode(value, { stream: true });
        const lines = sseBuffer.split('\n');
        sseBuffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          let event: any;
          try {
            event = JSON.parse(line.slice(6));
          } catch {
            continue;
          }

          if (event.type === 'delta' && event.text) {
            streamStarted = true;
            streamText += event.text;
            upsertStreamingNpcMessage(streamText);
          } else if (event.type === 'done' && event.story) {
            const raw = event.story;
            const processedMessages = (raw.current_scene?.messages ?? []).map(mapMessage).filter((message: Message | null): message is Message => Boolean(message));
            updateEmotionHistoryFromStory(raw, processedMessages);

            startTransition(() => {
              setStory(prevStory => {
                const merged = mergeStoryPayload(prevStory, raw, experimentSession?.participant_id || userId);
                return {
                  ...merged,
                  currentScene: {
                    ...merged.currentScene,
                    messages: processedMessages,
                  },
                };
              });
            });

            if (raw.dialogue_count !== undefined) {
              setDialogueCount(raw.dialogue_count);
            }
          } else if (event.type === 'error') {
            throw new Error(event.message || 'Stream error from server');
          }
        }
      }

      if (!streamStarted) {
        clearTypingPlaceholder();
      }
    } catch (err) {
      clearTypingPlaceholder();
      setError(errorMessage);
      throw err;
    }
  };

  const sendMessage = async (content: string): Promise<void> => {
    if (!story) {
      setError('No active story.');
      return;
    }
    setError(null);

    await streamTurn({
      endpoint: '/messages/stream',
      requestBody: {
        story_id: story.id,
        user_id: story.userId,
        participant_id: experimentSession?.participant_id || null,
        session_id: experimentSession?.session_id || null,
        content,
        fast_forward: getEffectiveFastForward(story, fastForward),
      },
      optimisticContent: content,
      optimisticType: 'text',
      errorMessage: 'Failed to send message.',
    });
  };

  const selectChoice = async (choiceId: string): Promise<void> => {
    if (!story) {
      setError('Cannot select choice, no active story.');
      return;
    }
    setError(null);

    const selected = story.currentScene.choices?.find(c => c.id === choiceId);
    if (!selected) {
      setError('Invalid choice.');
      return;
    }

    let reflectionData = null;
    if (shouldPrefetchChoiceReflection(story)) {
      try {
        const reflectionResult = await generateStoryReflection(selected.text);
        if (reflectionResult?.success && reflectionResult?.reflection) {
          reflectionData = reflectionResult.reflection;
          console.log("Generated reflection for choice guidance:", reflectionData);

          if (reflectionResult.ui_element && reflectionResult.ui_element.needed && shouldAutoInsertInteractiveElement(story)) {
            try {
              console.log("UI element recommendation detected:", reflectionResult.ui_element);

              await generateInteractiveElement(
                reflectionResult.ui_element.element_type || "generic",
                reflectionResult.ui_element.description || "Interactive story element",
                reflectionResult.ui_element.purpose || "Generated based on story reflection"
              );
            } catch (interactiveError) {
              console.warn("Failed to generate interactive element:", interactiveError);
            }
          }
        }
      } catch (reflectionError) {
        console.warn("Failed to generate reflection for choice, continuing without it:", reflectionError);
      }
    }

    await streamTurn({
      endpoint: '/choices/stream',
      requestBody: {
        story_id: story.id,
        user_id: story.userId,
        participant_id: experimentSession?.participant_id || null,
        session_id: experimentSession?.session_id || null,
        choice_id: choiceId,
        reflection: reflectionData,
        fast_forward: getEffectiveFastForward(story, fastForward),
      },
      optimisticContent: selected.text,
      optimisticType: 'choice',
      errorMessage: 'Failed to process choice.',
    });
  };

  const endStory = async (): Promise<void> => {
    if (!story) {
        setError('No story to end.');
        return;
    }
    setError(null);
    try {
        await axios.post(`${API_BASE_URL}/stories/${story.id}/end`);
        const response = await axios.get(`${API_BASE_URL}/story/${story.id}`);
        const completedStory = mergeStoryPayload(
          story,
          response.data,
          experimentSession?.participant_id || userId,
        );
        setStory(completedStory);
        setStoryId(completedStory.id);
        setDialogueCount(completedStory.dialogueCount || 0);
    } catch (err) {
        setError('Failed to end story.');
        console.error(err);
        throw err;
    }
  };

  const generateStoryReflection = async (userInput: string): Promise<any> => {
    if (!story) {
      setError('Cannot generate reflection, no active story.');
      return null;
    }
    
    try {
      const response = await axios.post(`${API_BASE_URL}/story/${story.id}/reflection`, {
        user_input: userInput
      });
      
      const reflection = response.data;
      setStoryReflection(reflection);
      
      // Update dialogue count and pacing recommendation
      if (reflection.dialogue_count !== undefined) {
        setDialogueCount(reflection.dialogue_count);
        console.log(`Current dialogue count: ${reflection.dialogue_count}`);
      }
      
      if (reflection.pacing_recommendation) {
        setPacingRecommendation(reflection.pacing_recommendation);
        console.log(`Pacing recommendation: ${reflection.pacing_recommendation}`);
      }
      
      return reflection;
    } catch (err) {
      console.error('Failed to generate story reflection:', err);
      if (axios.isAxiosError(err) && err.response) {
        console.error('Error response:', err.response.status, err.response.data);
        console.error('Request data:', { story_id: story.id, user_input: userInput });
      }
      setError('Failed to analyze story progression.');
      return null;
    }
  };
  
  const generateInteractiveElement = async (
    elementType: string,
    description: string,
    contentDetails: string
  ): Promise<any> => {
    if (!story) {
      setError('Cannot generate interactive element, no active story.');
      return null;
    }
    
    try {
      console.log("Calling interactive element API with:", {
        element_type: elementType,
        element_description: description,
        content_details: contentDetails
      });
      
      // 修复API调用方式，与后端API匹配
      const response = await axios.post(
        `${API_BASE_URL}/story/${story.id}/interactive-element`, 
        {}, 
        {
          params: {
            element_type: elementType,
            element_description: description,
            content_details: contentDetails
          }
        }
      );
      
      const result = response.data;
      console.log("Interactive element API response:", result);
      
      if (result.success && result.code) {
        // 设置交互式元素状态，但不直接添加到对话中
        // 这将由页面组件监听变化处理
        setInteractiveElement({
          code: result.code,
          elementType: result.element_type || elementType,
          prompt: result.prompt || result.element_description || description || result.purpose || contentDetails
        });
        
        console.log("Generated interactive element:", elementType);
      }
      
      return result;
    } catch (err) {
      console.error('Failed to generate interactive element:', err);
      setError('Failed to create interactive element.');
      return null;
    }
  };
  
  const clearInteractiveElement = () => {
    setInteractiveElement(null);
  };

  const appendMessageToCurrentScene = (message: Message) => {
    const normalizedMessage: Message = {
      ...message,
      renderMode: message.renderMode || ((message.action || message.direction || /\*[^*]+\*/.test(message.content || '')) ? 'rp_mixed' : 'plain'),
    };
    setStory(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        currentScene: {
          ...prev.currentScene,
          messages: [...prev.currentScene.messages, normalizedMessage],
        },
      };
    });
  };

  const value = {
    story,
    storyId,
    clarifyingQuestions,
    questionsData,
    keywords,
    loading,
    error,
    userId,
    emotionalNeed,
    submitEmotionalNeed,
    initiateStory,
    submitAnswersAndCreateStory,
    sendMessage,
    selectChoice,
    endStory,
    storyGenerationProgress,
    currentGenerationStep,
    generationStatus,
    getStoryGenerationProgress,
    storyReflection,
    interactiveElement,
    dialogueCount,
    pacingRecommendation,
    generateStoryReflection,
    generateInteractiveElement,
    clearInteractiveElement,
    profileKeywords,
    fastForward,
    setFastForward,
    appendMessageToCurrentScene,
    emotionHistory,
    experimentSession,
    experimentMode: Boolean(experimentSession),
    startExperimentSession,
    clearExperimentSession,
    loadHistoricalStory,
  };

  return (
    <StoryContext.Provider value={value}>
      {children}
    </StoryContext.Provider>
  );
};
