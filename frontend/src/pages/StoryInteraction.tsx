import React, { useState, useEffect, useRef, useCallback, useMemo, useDeferredValue } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Container,
  Paper,
  Typography,
  TextField,
  Button,
  CircularProgress,
  Avatar,
  Stack,
  IconButton,
  Fade,
  Tabs,
  Tab,
  Snackbar,
  Alert,
  Chip
} from '@mui/material';
import SendIcon from '@mui/icons-material/Send';
import RoomIcon from '@mui/icons-material/Room';
import PeopleIcon from '@mui/icons-material/People';
import AutoAwesomeRoundedIcon from '@mui/icons-material/AutoAwesomeRounded';
import Groups2RoundedIcon from '@mui/icons-material/Groups2Rounded';
import RouteRoundedIcon from '@mui/icons-material/RouteRounded';
import FavoriteRoundedIcon from '@mui/icons-material/FavoriteRounded';
import { useStory } from '../contexts/StoryContext';
import { Message, Choice, Scene, Character, CastStatus } from '../types';
import DebugPanel from '../components/DebugPanel';
import InteractiveElement from '../components/InteractiveElement';
import SpacetimeWarp from '../components/SpacetimeWarp';
import FeedbackWidget from '../components/FeedbackWidget';
import MixedRichText from '../components/MixedRichText';
import TranscriptPane from '../components/TranscriptPane';
import { resolveAssetUrl } from '../utils/assetUrl';
import {
  getSceneTransitionDurationMs,
  shouldAutoInsertInteractiveElement,
  shouldBlockOnInteractiveElement,
} from '../utils/benchmarkMode';
import { dedupeTextList, toDisplayText } from '../utils/textLists';

// Extend the Scene interface to include location property
interface ExtendedScene extends Scene {
  location?: string;
  backgroundImage?: string;
}

// Dark neutral avatar palette picker for better aesthetics
const stringToDarkColor = (input: string): string => {
  const palette = ['#111827', '#1f2937', '#2d2a26', '#3a2f2b', '#374151'];
  let hash = 0;
  for (let i = 0; i < input.length; i++) hash = (hash + input.charCodeAt(i)) % 2147483647;
  return palette[hash % palette.length];
};

const chatAvatarSx = (name: string) => ({
  bgcolor: stringToDarkColor(name),
  width: 42,
  height: 42,
  borderRadius: '10px',
  boxShadow: '0 2px 8px rgba(0,0,0,0.25)',
  border: '1px solid rgba(255,255,255,0.08)',
  transition: 'transform 120ms ease, box-shadow 120ms ease',
  '&:hover': { transform: 'translateY(-1px)', boxShadow: '0 4px 12px rgba(0,0,0,0.3)' }
});

const asDisplayLine = (value: unknown): string | null => {
  const display = toDisplayText(value);
  return display || null;
};

const normalizeCharacterToken = (value?: string | null): string => (
  String(value || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '')
);

const normalizeLocationLabel = (value?: string | null): string => (
  String(value || '').replace(/\s+/g, ' ').trim()
);

const normalizeLocationToken = (value?: string | null): string => (
  normalizeLocationLabel(value).toLowerCase()
);

const appendUniqueLocation = (history: string[], nextLocation: string): string[] => {
  const normalizedNext = normalizeLocationLabel(nextLocation);
  if (!normalizedNext) {
    return history;
  }
  if (history.length > 0 && normalizeLocationToken(history[history.length - 1]) === normalizeLocationToken(normalizedNext)) {
    return history;
  }
  return [...history, normalizedNext];
};

const isTransitionSystemMessage = (message?: Message): boolean => {
  if (!message || message.type !== 'system' || typeof message.content !== 'string') {
    return false;
  }
  if (String(message.id || '').startsWith('transition-')) {
    return true;
  }
  const content = message.content.trim();
  return /^\[[^\]]+\]$/.test(content) && content.includes(' - ');
};

type CharacterIndex = {
  byExactId: Map<string, Character>;
  byNormalizedToken: Map<string, Character>;
  npcs: Character[];
  protagonist: Character | null;
};

const EMPTY_MESSAGES: Message[] = [];

const tabIconBadge = (icon: React.ReactNode, gradient: string, glow: string) => (
  <Box
    sx={{
      width: 28,
      height: 28,
      display: 'grid',
      placeItems: 'center',
      borderRadius: '10px',
      background: gradient,
      color: '#fff',
      boxShadow: `0 6px 16px ${glow}`,
      border: '1px solid rgba(255,255,255,0.22)',
      backdropFilter: 'blur(12px)',
      '& svg': {
        fontSize: '1rem',
      },
    }}
  >
    {icon}
  </Box>
);

const StoryInteraction: React.FC = () => {
  const [userMessage, setUserMessage] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [showTransition, setShowTransition] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [locationHistory, setLocationHistory] = useState<string[]>([]);
  const [tabValue, setTabValue] = useState(0);
  const [interactiveElementInChat, setInteractiveElementInChat] = useState<boolean>(false);
  const [blockedAfterMessageId, setBlockedAfterMessageId] = useState<string | null>(null);
  const proceededInteractiveIds = useRef<Set<string>>(new Set());
  const pendingTransitionCaptionRef = useRef<string | null>(null);
  
  const { 
    story, 
    loading, 
    error, 
    sendMessage, 
    selectChoice, 
    endStory,
    interactiveElement,
    fastForward,
    setFastForward,
    appendMessageToCurrentScene,
    experimentMode,
  } = useStory();
  const navigate = useNavigate();
  const [showIntro, setShowIntro] = useState<boolean>(true);
  const previousTransitionRef = useRef<string | null>(null);
  const previousLocationRef = useRef<string | null>(null);
  const pendingLocationRef = useRef<string | null>(null);
  const transitionTimerRef = useRef<number | null>(null);

  const insertingInteractiveRef = useRef(false);

  useEffect(() => {
    if (!interactiveElement) {
      setInteractiveElementInChat(false);
      insertingInteractiveRef.current = false;
      return;
    }

    if (!shouldAutoInsertInteractiveElement(story) || interactiveElementInChat || insertingInteractiveRef.current || !story) return;

    insertingInteractiveRef.current = true;

    const interactiveMessage = {
      id: `interactive-${Date.now()}`,
      characterId: 'system',
      content: interactiveElement.code,
      timestamp: new Date().toISOString(),
      type: 'interactive' as const
    };

    if (interactiveElement.prompt) {
      const promptMessage = {
        id: `interactive-prompt-${Date.now()}`,
        characterId: 'system',
        content: interactiveElement.prompt,
        timestamp: new Date().toISOString(),
        type: 'system' as const
      };
      appendMessageToCurrentScene(promptMessage);
    }

    setTimeout(() => {
      appendMessageToCurrentScene(interactiveMessage);
      setInteractiveElementInChat(true);
    }, 300);
  }, [interactiveElement, interactiveElementInChat, story, appendMessageToCurrentScene]);

  const characterIndex = useMemo<CharacterIndex>(() => {
    const byExactId = new Map<string, Character>();
    const byNormalizedToken = new Map<string, Character>();
    const npcs: Character[] = [];
    let protagonist: Character | null = null;

    (story?.characters || []).forEach(character => {
      byExactId.set(character.id, character);
      [character.id, character.name].forEach(value => {
        const token = normalizeCharacterToken(value);
        if (token && !byNormalizedToken.has(token)) {
          byNormalizedToken.set(token, character);
        }
      });
      if (character.role === 'protagonist' && !protagonist) {
        protagonist = character;
        byNormalizedToken.set('protagonist', character);
      }
      if (character.role === 'npc') {
        npcs.push(character);
      }
    });

    return { byExactId, byNormalizedToken, npcs, protagonist };
  }, [story?.characters]);

  const castStatusIndex = useMemo(() => {
    const map = new Map<string, CastStatus>();
    (story?.castStatuses || []).forEach(status => {
      [status.characterId, status.name].forEach(value => {
        const token = normalizeCharacterToken(value);
        if (token && !map.has(token)) {
          map.set(token, status);
        }
      });
    });
    return map;
  }, [story?.castStatuses]);

  const explicitInSceneCharacterIds = useMemo(() => {
    const ids = new Set<string>();
    if (characterIndex.protagonist?.id) {
      ids.add(characterIndex.protagonist.id);
    }
    (story?.castStatuses || []).forEach(status => {
      if (!status.inSceneNow) {
        return;
      }
      const normalizedCharacterId = normalizeCharacterToken(status.characterId);
      const normalizedName = normalizeCharacterToken(status.name);
      const matchedCharacter = (
        characterIndex.byExactId.get(status.characterId) ||
        characterIndex.byNormalizedToken.get(normalizedCharacterId) ||
        characterIndex.byNormalizedToken.get(normalizedName)
      );
      if (matchedCharacter && matchedCharacter.role !== 'system') {
        ids.add(matchedCharacter.id);
      }
    });
    return ids;
  }, [characterIndex, story?.castStatuses]);

  const inSceneNpcIds = useMemo(() => (
    Array.from(explicitInSceneCharacterIds).filter(characterId => (
      characterIndex.byExactId.get(characterId)?.role === 'npc'
    ))
  ), [characterIndex.byExactId, explicitInSceneCharacterIds]);

  const getCharacterById = useCallback((id?: string): Character => {
    // Handle undefined/null id
    if (!id) {
      console.warn('Character ID is undefined or null');
      return { id: 'unknown', name: 'Unknown', role: 'npc', description: '', personality: '' };
    }

    if (id === 'system') return { id: 'system', name: 'System', role: 'system', description: '', personality: '' };
    const normalizedId = normalizeCharacterToken(id);
    if ((normalizedId === 'npc' || normalizedId.startsWith('streamnpc')) && inSceneNpcIds.length === 1) {
      const inSceneNpc = characterIndex.byExactId.get(inSceneNpcIds[0]);
      if (inSceneNpc) return inSceneNpc;
    }

    const exactMatch = characterIndex.byExactId.get(id);
    if (exactMatch) return exactMatch;

    if (normalizedId === 'protagonist' && characterIndex.protagonist) {
      return characterIndex.protagonist;
    }

    const normalizedMatch = characterIndex.byNormalizedToken.get(normalizedId);
    if (normalizedMatch) return normalizedMatch;
    
    // First try to find by exact ID match
    const characterById = story?.characters.find(char => char.id === id);
    if (characterById) return characterById;
    
    // If ID is 'protagonist', find character with role 'protagonist'
    if (id === 'protagonist') {
      const protagonist = story?.characters.find(char => char.role === 'protagonist');
      if (protagonist) return protagonist;
    }
    
    // 尝试更灵活的匹配方式
    if (story?.characters) {
      // 1. 尝试不区分大小写的ID匹配
      const lowerCaseMatch = story.characters.find(
        char => char.id.toLowerCase() === id.toLowerCase()
      );
      if (lowerCaseMatch) return lowerCaseMatch;
      
      // 2. 尝试去掉下划线的匹配
      const noUnderscoreMatch = story.characters.find(
        char => char.id.replace('_', '') === id || id.replace('_', '') === char.id
      );
      if (noUnderscoreMatch) return noUnderscoreMatch;
      
      // 3. 尝试通过名称匹配（不区分大小写，去空格）
      const nameMatch = story.characters.find(
        char => char.name.toLowerCase().replace(/\s+/g, '') === id.toLowerCase() ||
               char.name.toLowerCase() === id.toLowerCase()
      );
      if (nameMatch) return nameMatch;
      
      // 4. 尝试部分ID匹配（如果ID是另一个ID的一部分）
      const partialIdMatch = story.characters.find(
        char => char.id.includes(id) || id.includes(char.id)
      );
      if (partialIdMatch) return partialIdMatch;
    }
    
    // For any other id pattern like 'npc1', try to find a matching NPC
    if (id.startsWith('npc') && /npc\d+/.test(id)) {
      const npcNumber = id.replace('npc', '');
      // Try to find npcs by index or by id
      const npcs = story?.characters.filter(char => char.role === 'npc');
      const npcIndex = parseInt(npcNumber, 10) - 1;
      if (npcs && npcs.length > npcIndex && npcIndex >= 0) {
        return npcs[npcIndex];
      }
    }
    
    // 添加调试信息
    console.warn(`Character not found with ID: ${id}`);
    if (story?.characters) {
      console.debug('Available characters:', story.characters.map(c => `${c.id} (${c.name})`).join(', '));
    }

    return { id: 'unknown', name: 'Unknown', role: 'npc', description: '', personality: '' };
  }, [characterIndex.byExactId, characterIndex.byNormalizedToken, characterIndex.protagonist, inSceneNpcIds, story?.characters]);

  // Auto-navigate to conclusion when backend ends the story
  const storyStatus = story?.status;
  const transitionDisplayMs = getSceneTransitionDurationMs(story);
  const triggerTransitionOverlay = useCallback((caption: string) => {
    if (!caption) return;
    setShowTransition(true);
    if (transitionTimerRef.current) {
      window.clearTimeout(transitionTimerRef.current);
    }
    transitionTimerRef.current = window.setTimeout(() => {
      setShowTransition(false);
      transitionTimerRef.current = null;
    }, transitionDisplayMs);
  }, [transitionDisplayMs]);

  useEffect(() => {
    if (storyStatus === 'completed') {
      if (transitionTimerRef.current) {
        window.clearTimeout(transitionTimerRef.current);
        transitionTimerRef.current = null;
      }
      pendingTransitionCaptionRef.current = null;
      setShowTransition(false);
      navigate('/conclusion');
    }
  }, [navigate, storyStatus]);

  useEffect(() => () => {
    if (transitionTimerRef.current) {
      window.clearTimeout(transitionTimerRef.current);
    }
  }, []);

  useEffect(() => {
    if (story?.currentScene.scene_transition_caption) {
      return;
    }
    pendingTransitionCaptionRef.current = null;
    if (transitionTimerRef.current) {
      window.clearTimeout(transitionTimerRef.current);
      transitionTimerRef.current = null;
    }
    setShowTransition(false);
  }, [story?.currentScene.scene_transition_caption]);

  useEffect(() => {
    previousTransitionRef.current = null;
    previousLocationRef.current = null;
    pendingLocationRef.current = null;
    pendingTransitionCaptionRef.current = null;
    setLocationHistory([]);
  }, [story?.id]);

  useEffect(() => {
    if (!loading && !story) {
      navigate('/');
      return;
    }
    
    if (story) {
      if (
        story.currentScene.scene_transition_caption &&
        story.currentScene.scene_transition_caption !== previousTransitionRef.current
      ) {
        if (blockedAfterMessageId) {
          pendingTransitionCaptionRef.current = story.currentScene.scene_transition_caption;
        } else {
          previousTransitionRef.current = story.currentScene.scene_transition_caption;
          triggerTransitionOverlay(story.currentScene.scene_transition_caption);
        }
      }
    }
  }, [story, loading, navigate, blockedAfterMessageId, triggerTransitionOverlay]);

  useEffect(() => {
    if (!story?.currentScene) {
      return;
    }

    const nextLocation = normalizeLocationLabel(
      (story.currentScene as ExtendedScene).location || String(story.currentScene.setting || ''),
    );
    if (!nextLocation) {
      return;
    }

    if (!previousLocationRef.current) {
      previousLocationRef.current = nextLocation;
      pendingLocationRef.current = null;
      setLocationHistory([nextLocation]);
      return;
    }

    if (normalizeLocationToken(previousLocationRef.current) === normalizeLocationToken(nextLocation)) {
      pendingLocationRef.current = null;
      return;
    }

    const transitionIsPending = Boolean(
      blockedAfterMessageId &&
      story.currentScene.scene_transition_caption &&
      story.currentScene.scene_transition_caption !== previousTransitionRef.current
    );
    if (transitionIsPending) {
      pendingLocationRef.current = nextLocation;
      return;
    }

    previousLocationRef.current = nextLocation;
    pendingLocationRef.current = null;
    setLocationHistory(prev => appendUniqueLocation(prev, nextLocation));
  }, [blockedAfterMessageId, story?.currentScene, story?.currentScene?.location, story?.currentScene?.scene_transition_caption]);

  useEffect(() => {
    if (!loading && story) {
        // Hide intro once first NPC message arrives or after timeout
        const hasMessages = story.currentScene.messages && story.currentScene.messages.length > 0;
        if (hasMessages) {
          setShowIntro(false);
        } else {
          const timer = setTimeout(() => setShowIntro(false), 2000);
          return () => clearTimeout(timer);
        }
    }
  }, [loading, story]);

  // Block dialogue after latest interactive element until user clicks Proceed
  useEffect(() => {
    if (!shouldBlockOnInteractiveElement(story)) {
      if (blockedAfterMessageId) {
        setBlockedAfterMessageId(null);
      }
      return;
    }
    const messages = story?.currentScene?.messages || [];
    const lastInteractive = [...messages].reverse().find(m => m.type === 'interactive');
    if (lastInteractive && lastInteractive.id) {
      const id = lastInteractive.id as string;
      if (!proceededInteractiveIds.current.has(id) && blockedAfterMessageId !== id) {
        setBlockedAfterMessageId(id);
      }
    }
  }, [story, story?.currentScene?.messages, blockedAfterMessageId]);

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!userMessage.trim() || isSending || isTyping || isInteractionBlocked) return;
    
    setIsSending(true);
    try {
      await sendMessage(userMessage);
      setUserMessage('');
    } catch (err) {
      setSendError('Failed to send message. Please try again.');
    } finally {
      setIsSending(false);
    }
  };

  const handleChoiceSelect = async (choiceId: string) => {
    if (isTyping || isSending || isInteractionBlocked) return;
    setIsSending(true);
    try {
      await selectChoice(choiceId);
    } catch (err) {
      setSendError('Failed to process choice. Please try again.');
    } finally {
      setIsSending(false);
    }
  };

  const handleProceedInteractive = (interactiveId: string) => {
    proceededInteractiveIds.current.add(interactiveId);
    setBlockedAfterMessageId(null);
    if (pendingLocationRef.current) {
      previousLocationRef.current = pendingLocationRef.current;
      setLocationHistory(prev => appendUniqueLocation(prev, pendingLocationRef.current as string));
      pendingLocationRef.current = null;
    }
    if (pendingTransitionCaptionRef.current) {
      const pendingCaption = pendingTransitionCaptionRef.current;
      pendingTransitionCaptionRef.current = null;
      previousTransitionRef.current = pendingCaption;
      triggerTransitionOverlay(pendingCaption);
    }
  };

  const handleEndStory = async () => {
    try {
      await endStory();
      // Navigation is handled by the useEffect that watches story.status
    } catch (err) {
      setSendError('Failed to end story. Please try again.');
    }
  };

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const storyMemory = story?.storyMemory;
  const storyProgress = story?.storyProgress;
  const sceneInfoPanel = story?.sceneInfoPanel;
  const storyState = story?.storyState;
  const interactiveHistory = story?.interactiveElementHistory || [];
  const isInteractionBlocked = Boolean(blockedAfterMessageId);
  const allMessages = useMemo(
    () => story?.currentScene.messages || EMPTY_MESSAGES,
    [story?.currentScene.messages]
  );
  const blockedIdx = blockedAfterMessageId ? allMessages.findIndex(m => m.id === blockedAfterMessageId) : -1;
  const visibleMessages = blockedIdx >= 0 ? allMessages.slice(0, blockedIdx + 1) : allMessages;
  const transcriptMessages = useDeferredValue(visibleMessages);
  const isTyping = visibleMessages.some(message => message.type === 'typing');
  const hasExplicitScenePresence = (story?.castStatuses || []).some(status => typeof status.inSceneNow === 'boolean');
  const scenePresenceMessages = useMemo(() => {
    const lastTransitionIndex = allMessages.reduce((latestIndex, message, index) => (
      isTransitionSystemMessage(message) ? index : latestIndex
    ), -1);
    return lastTransitionIndex >= 0 ? allMessages.slice(lastTransitionIndex + 1) : allMessages;
  }, [allMessages]);
  const activeCharacterIds = useMemo(() => {
    const ids = new Set<string>(explicitInSceneCharacterIds);
    const shouldUseMessageFallback = !hasExplicitScenePresence || scenePresenceMessages.some(message => {
      const token = normalizeCharacterToken(message.characterId || (message as any).character_id);
      return token === 'npc' || token.startsWith('streamnpc');
    });

    if (shouldUseMessageFallback) {
      scenePresenceMessages.forEach(message => {
        const rawCharacterId = message.characterId || (message as any).character_id;
        const resolvedCharacter = getCharacterById(rawCharacterId);
        if (resolvedCharacter.role !== 'system' && resolvedCharacter.id !== 'unknown') {
          ids.add(resolvedCharacter.id);
        }
      });
    }

    if (characterIndex.protagonist?.id) {
      ids.add(characterIndex.protagonist.id);
    }
    return ids;
  }, [characterIndex.protagonist, explicitInSceneCharacterIds, getCharacterById, hasExplicitScenePresence, scenePresenceMessages]);

  const getCharacterLastSeen = (characterId: string): string | null => {
    const messages = [...(story?.currentScene?.messages || [])].reverse();
    const lastMessage = messages.find(msg => {
      if (msg.type !== 'text') {
        return false;
      }
      return getCharacterById(msg.characterId || (msg as any).character_id).id === characterId;
    });
    return lastMessage?.content || null;
  };

  const renderInfoCard = (title: string, content?: React.ReactNode, accent: string = '#7db8a2') => {
    if (!content) return null;
    return (
      <Box
        sx={{
          p: 1.25,
          borderRadius: '14px',
          background: 'rgba(255,255,255,0.52)',
          border: `1px solid ${accent}33`,
          boxShadow: '0 8px 22px rgba(60,50,44,0.05)',
        }}
      >
        <Typography variant="caption" sx={{ display: 'block', color: accent, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', mb: 0.7 }}>
          {title}
        </Typography>
        {content}
      </Box>
    );
  };

  // Render scene information content
  const renderSceneInfo = () => {
    if (!story) return null;

    const primaryClues = sceneInfoPanel?.clueSummary?.length
      ? sceneInfoPanel.clueSummary
      : (storyMemory?.activeClues || []);

    const clueItems = dedupeTextList([
      ...primaryClues,
      ...(story.currentScene.hiddenElements?.foreshadowing ? [story.currentScene.hiddenElements.foreshadowing] : []),
    ].map(asDisplayLine).filter((item): item is string => Boolean(item))).slice(0, 4);

    return (
      <Stack spacing={1.15} sx={{ overflowY: 'auto', pr: 0.25 }}>
        {renderInfoCard(
          'Scene',
          <Stack spacing={0.7}>
            <Typography variant="body2">
              <strong>Location:</strong> {(story?.currentScene as ExtendedScene)?.location || locationHistory[locationHistory.length - 1] || 'Unknown'}
            </Typography>
            {storyProgress?.currentActTitle && (
              <Typography variant="body2">
                <strong>Act:</strong> {storyProgress.currentActTitle}
              </Typography>
            )}
            {storyProgress?.currentActPurpose && (
              <Typography variant="body2" sx={{ color: 'text.secondary', lineHeight: 1.55 }}>
                {storyProgress.currentActPurpose}
              </Typography>
            )}
            {sceneInfoPanel?.locationStatus && (
              <Typography variant="body2" sx={{ color: 'text.secondary', lineHeight: 1.55 }}>
                {sceneInfoPanel.locationStatus}
              </Typography>
            )}
            {story.currentScene.sceneDynamics?.narrativeAdvancement && (
              <Typography variant="body2" sx={{ color: 'text.secondary', lineHeight: 1.55 }}>
                {story.currentScene.sceneDynamics.narrativeAdvancement}
              </Typography>
            )}
          </Stack>,
          '#6f8fb0'
        )}
        {renderInfoCard(
          'Current Objective',
          <Typography variant="body2" sx={{ lineHeight: 1.55, color: '#3c322c' }}>
            {sceneInfoPanel?.objective || storyState?.currentObjective || storyMemory?.currentGoal || story.emotionalGoal || 'Keep moving toward the next emotional turning point.'}
          </Typography>
        )}
        {renderInfoCard(
          'Open Tensions',
          (sceneInfoPanel?.tensionSummary?.length || storyMemory?.openTensions?.length || sceneInfoPanel?.currentTension || story.currentScene.inciting_incident)
            ? (
              <Stack spacing={0.75}>
                {(sceneInfoPanel?.tensionSummary || storyMemory?.openTensions || [sceneInfoPanel?.currentTension || story.currentScene.inciting_incident || '']).filter(Boolean).slice(0, 3).map((item, idx) => (
                  <Typography key={`tension-${idx}`} variant="body2" sx={{ color: '#5a5048', lineHeight: 1.45 }}>
                    {item}
                  </Typography>
                ))}
              </Stack>
            )
            : null,
          '#b07b7b'
        )}
        {renderInfoCard(
          'Immediate Stakes',
          (sceneInfoPanel?.immediateStakes || storyState?.immediateStakes)
            ? (
              <Typography variant="body2" sx={{ color: '#5a5048', lineHeight: 1.5 }}>
                {sceneInfoPanel?.immediateStakes || storyState?.immediateStakes}
              </Typography>
            )
            : null,
          '#b08c5e'
        )}
        {renderInfoCard(
          'Clues To Remember',
          clueItems.length ? (
            <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
              {clueItems.map((clue, idx) => (
                <Box
                  key={`clue-${idx}`}
                  component="span"
                  sx={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    px: 1.05,
                    py: 0.72,
                    background: 'linear-gradient(180deg, rgba(229,236,250,0.92) 0%, rgba(210,221,242,0.88) 100%)',
                    color: '#425274',
                    border: '1px solid rgba(115,135,184,0.4)',
                    boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.76), 0 4px 12px rgba(85,104,146,0.08)',
                    maxWidth: '100%',
                    cursor: 'default',
                    userSelect: 'text',
                  }}
                >
                  <Typography
                    variant="body2"
                    sx={{
                      fontSize: '0.78rem',
                      lineHeight: 1.45,
                      color: 'inherit',
                      wordBreak: 'break-word',
                    }}
                  >
                    {clue}
                  </Typography>
                </Box>
              ))}
            </Stack>
          ) : null,
          '#7387b8'
        )}
        {renderInfoCard(
          'What Just Happened',
          (sceneInfoPanel?.recap || storyMemory?.whatJustHappened)
            ? (
              <Typography variant="body2" sx={{ color: '#5a5048', lineHeight: 1.55 }}>
                {sceneInfoPanel?.recap || storyMemory?.whatJustHappened}
              </Typography>
            )
            : null,
          '#7c9a90'
        )}
        {story?.currentScene.description && renderInfoCard(
          'What The Camera Sees',
          <Typography variant="body2" sx={{ fontStyle: 'italic', color: 'text.secondary', lineHeight: 1.65 }}>
            {story.currentScene.description}
          </Typography>,
          '#9d8566'
        )}
      </Stack>
    );
  };

  const [expandedCharId, setExpandedCharId] = useState<string | null>(null);

  const renderCharacters = () => {
    if (!story || !story.characters || story.characters.length === 0) {
      return (
        <Typography color="text.secondary">No characters in scene yet</Typography>
      );
    }

    const sorted = [...story.characters].sort((a, b) => {
      if (a.role === 'protagonist') return -1;
      if (b.role === 'protagonist') return 1;
      return 0;
    });

    return (
      <Box sx={{ height: '100%', minHeight: 0, overflowY: 'auto', scrollbarGutter: 'stable', pr: 0.5 }}>
        <Stack spacing={1.5}>
          {sorted.map(character => {
            const castStatus = (
              castStatusIndex.get(normalizeCharacterToken(character.id)) ||
              castStatusIndex.get(normalizeCharacterToken(character.name))
            );
            const isActive = typeof castStatus?.inSceneNow === 'boolean'
              ? castStatus.inSceneNow
              : activeCharacterIds.has(character.id);
            const isExpanded = expandedCharId === character.id;
            const roleBadge: Record<string, { label: string; color: string }> = {
              protagonist: { label: 'You', color: '#7db8a2' },
              npc: { label: 'NPC', color: '#a0a8b8' },
            };
            const badge = roleBadge[character.role] || roleBadge.npc;
            const imgSrc = character.imageUrl ? resolveAssetUrl(character.imageUrl) : undefined;

            return (
              <Box
                key={`char-${character.id}`}
                onClick={() => setExpandedCharId(isExpanded ? null : character.id)}
                sx={{
                  cursor: 'pointer',
                  borderRadius: '14px',
                  border: isExpanded
                    ? '1.5px solid rgba(125,184,162,0.45)'
                    : '1px solid rgba(125,184,162,0.15)',
                  background: isExpanded
                    ? 'rgba(232,245,240,0.55)'
                    : 'rgba(255,252,246,0.5)',
                  p: 1.5,
                  transition: 'all 0.2s ease',
                  opacity: isActive ? 1 : 0.7,
                  '&:hover': {
                    background: 'rgba(232,245,240,0.6)',
                    border: '1px solid rgba(125,184,162,0.35)',
                  },
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.2 }}>
                  {imgSrc ? (
                    <Avatar
                      src={imgSrc}
                      alt={character.name}
                      sx={{
                        width: 40,
                        height: 40,
                        borderRadius: '10px',
                        border: '1px solid rgba(125,184,162,0.2)',
                      }}
                    />
                  ) : (
                    <Avatar
                      sx={{
                        width: 40,
                        height: 40,
                        borderRadius: '10px',
                        bgcolor: stringToDarkColor(character.name),
                        fontSize: '0.95rem',
                        fontWeight: 600,
                      }}
                    >
                      {character.name.charAt(0)}
                    </Avatar>
                  )}

                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8 }}>
                      <Typography
                        variant="body2"
                        sx={{ fontWeight: 600, color: '#3c322c', lineHeight: 1.3 }}
                        noWrap
                      >
                        {character.name}
                      </Typography>
                      <Box
                        component="span"
                        sx={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          minHeight: 18,
                          px: 0.8,
                          borderRadius: '999px',
                          fontSize: '0.62rem',
                          fontWeight: 700,
                          letterSpacing: '0.04em',
                          bgcolor: `${badge.color}22`,
                          color: badge.color,
                          border: `1px solid ${badge.color}44`,
                          lineHeight: 1.2,
                          flexShrink: 0,
                        }}
                      >
                        {badge.label}
                      </Box>
                      {isActive && (
                        <Box
                          sx={{
                            width: 7,
                            height: 7,
                            borderRadius: '50%',
                            bgcolor: '#7db8a2',
                            boxShadow: '0 0 5px rgba(125,184,162,0.6)',
                            flexShrink: 0,
                          }}
                        />
                      )}
                    </Box>
                    {(castStatus?.currentStatus || character.personality) && (
                      <Typography
                        variant="caption"
                        sx={{ color: 'text.secondary', lineHeight: 1.3, display: 'block', mt: 0.2 }}
                        noWrap={!isExpanded}
                      >
                        {castStatus?.currentStatus || character.personality}
                      </Typography>
                    )}
                    <Typography variant="caption" sx={{ display: 'block', mt: 0.35, color: isActive ? '#5a7a6e' : '#9a928a' }}>
                      {isActive ? 'On screen now' : 'Off screen'}
                    </Typography>
                  </Box>

                  <Typography
                    sx={{ fontSize: '0.85rem', color: 'text.secondary', flexShrink: 0, transition: 'transform 0.2s', transform: isExpanded ? 'rotate(180deg)' : 'rotate(0)' }}
                  >
                    ▾
                  </Typography>
                </Box>

                {isExpanded && (
                  <Box sx={{ mt: 1.2, pl: 0.5, pr: 0.5 }}>
                    {character.description && (
                      <Typography variant="caption" sx={{ display: 'block', color: '#5a5048', mb: 0.6, lineHeight: 1.5 }}>
                        {character.description}
                      </Typography>
                    )}
                    {character.backstory && (
                      <Typography variant="caption" sx={{ display: 'block', color: 'text.secondary', fontStyle: 'italic', mb: 0.6, lineHeight: 1.5 }}>
                        {character.backstory}
                      </Typography>
                    )}
                    {(castStatus?.relationship || character.relationship) && (
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.4 }}>
                        <PeopleIcon sx={{ fontSize: 14, color: '#7db8a2' }} />
                        <Typography variant="caption" sx={{ color: '#5a7a6e', fontWeight: 500 }}>
                          {castStatus?.relationship || character.relationship}
                        </Typography>
                      </Box>
                    )}
                    {(castStatus?.lastSeen || getCharacterLastSeen(character.id)) && (
                      <Typography variant="caption" sx={{ display: 'block', color: '#857a71', mt: 0.75, lineHeight: 1.45 }}>
                        Last seen: {castStatus?.lastSeen || getCharacterLastSeen(character.id)}
                      </Typography>
                    )}
                  </Box>
                )}
              </Box>
            );
          })}
        </Stack>
      </Box>
    );
  };

  // Render location history content
  const renderLocationHistory = () => {
    return (
      <Stack spacing={1.15} sx={{ overflowY: 'auto', pr: 0.25 }}>
        {renderInfoCard(
          'Location Trail',
          locationHistory.length ? (
            <Stack spacing={0.85}>
              {locationHistory.map((location, index) => (
                <Box key={`loc-${index}`} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <RoomIcon color={index === locationHistory.length - 1 ? "primary" : "disabled"} sx={{ fontSize: 18 }} />
                  <Typography
                    variant="body2"
                    color={index === locationHistory.length - 1 ? "primary" : "text.secondary"}
                    fontWeight={index === locationHistory.length - 1 ? "bold" : "normal"}
                  >
                    {location}
                    {index === locationHistory.length - 1 && " (Current)"}
                  </Typography>
                </Box>
              ))}
            </Stack>
          ) : (
            <Typography color="text.secondary">No locations visited yet</Typography>
          ),
          '#7c9a90'
        )}
        {interactiveHistory.length > 0 && renderInfoCard(
          'Interactive Moments',
          <Stack spacing={0.8}>
            {interactiveHistory.slice(-3).map((item, index) => (
              <Box key={`interaction-history-${index}`}>
                <Typography variant="body2" sx={{ color: '#5a5048', lineHeight: 1.45 }}>
                  {item.summary}
                </Typography>
                {item.noveltyTags.length > 0 && (
                  <Typography variant="caption" sx={{ color: '#7c7a92' }}>
                    {item.noveltyTags.slice(0, 4).join(' • ')}
                  </Typography>
                )}
              </Box>
            ))}
          </Stack>,
          '#8b7ab0'
        )}
      </Stack>
    );
  };

  if (loading && !story) {
    return <SpacetimeWarp />;
  }

  if (error && !story) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', p: 3 }}>
        <Typography color="error" variant="h6">{error}</Typography>
      </Box>
    );
  }

  if (!story) return null;

  const renderMessage = (message: Message, index: number) => {
    const characterId = message.characterId || (message as any).character_id;
    const character = getCharacterById(characterId);
    const revealLike = /truth|proof|found|reveal|discovered|confess|secret/i.test(message.content || '');
    
    // 根据消息类型渲染不同的组件
    switch (message.type) {
      case 'system':
        // 系统消息
        if (message.content.startsWith('[') && message.content.endsWith(']')) {
          // 场景转换提示
          return (
            <Box sx={{ textAlign: 'center', my: 2 }}>
              <Box
                sx={{
                  display: 'inline-block',
                  minWidth: { xs: '72%', sm: '56%' },
                  maxWidth: '92%',
                  px: 2.25,
                  py: 1.1,
                  borderRadius: '18px',
                  background: 'rgba(246,250,247,0.96)',
                  border: '1px solid rgba(125,184,162,0.22)',
                  boxShadow: '0 10px 24px rgba(60,50,44,0.06)',
                }}
              >
                <Typography variant="caption" sx={{ display: 'block', mb: 0.3, color: '#7d9c92', fontWeight: 700, letterSpacing: '0.18em', textTransform: 'uppercase' }}>
                  Scene Shift
                </Typography>
                <Typography variant="body2" sx={{ color: '#7f8a84', fontStyle: 'italic', lineHeight: 1.6 }}>
                  {message.content.replace(/^\[|\]$/g, '')}
                </Typography>
              </Box>
            </Box>
          );
        } else {
          // 普通系统消息
          return (
            <Box sx={{ textAlign: 'center', my: 1.5, px: { xs: 1, sm: 4 } }}>
              <Box
                sx={{
                  display: 'inline-block',
                  maxWidth: '92%',
                  px: 2,
                  py: 1.1,
                  borderRadius: '16px',
                  background: revealLike ? 'rgba(233,225,198,0.72)' : 'rgba(255,255,255,0.45)',
                  border: revealLike ? '1px solid rgba(173,142,86,0.28)' : '1px solid rgba(125,184,162,0.18)',
                }}
              >
                <Typography variant="caption" sx={{ display: 'block', mb: 0.45, color: revealLike ? '#8b6a34' : '#6c8d84', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                  {revealLike ? 'Story Reveal' : 'Narration'}
                </Typography>
                <MixedRichText
                  content={message.content}
                  mode={message.renderMode}
                  dialogueColor={revealLike ? '#5f4a2d' : '#6f7b75'}
                  narrationColor="#8c9691"
                  fontSize="0.92rem"
                />
              </Box>
            </Box>
          );
        }
      
      case 'interactive':
        // 交互式元素
        return (
          <Box sx={{ my: 2, width: '100%' }}>
            {(() => {
              const prev = transcriptMessages[index - 1] as any;
              const showCaption = prev && prev.type === 'system' && typeof prev.content === 'string' && !(prev.content.startsWith('[') && prev.content.endsWith(']'));
              return showCaption ? (
                <Typography variant="body2" sx={{ mb: 1, color: '#3b3a36' }}>
                  {prev.content}
                </Typography>
              ) : null;
            })()}
            <InteractiveElement htmlCode={message.content} />
            {shouldBlockOnInteractiveElement(story) && (
              <Box sx={{ display: 'flex', justifyContent: 'center', mt: 1 }}>
                <Button
                  variant="contained"
                  size="small"
                  onClick={() => handleProceedInteractive((message.id as string) || `ie-${index}`)}
                  sx={{
                    borderRadius: '999px',
                    textTransform: 'none',
                    px: 3,
                    py: 0.5,
                    bgcolor: 'linear-gradient(135deg, #f2e8d8, #e8d9c5)',
                    color: '#0b1a1a',
                    boxShadow: '0 6px 16px rgba(94,84,62,0.25)',
                    '&:hover': { bgcolor: 'linear-gradient(135deg, #fff2e0, #f2e8d8)' }
                  }}
                >
                  Proceed
                </Button>
              </Box>
            )}
          </Box>
        );
        
      case 'choice':
        // 用户选择
        const isChoiceUser = character.role === 'protagonist';
        return (
          <Box 
            sx={{ 
              display: 'flex',
              flexDirection: isChoiceUser ? 'row-reverse' : 'row', 
              justifyContent: isChoiceUser ? 'flex-start' : 'flex-start',
              width: '100%',
              alignItems: 'flex-end',
              mb: 1.25
            }}
          >
            <Box sx={{ position: 'relative', display: 'inline-block', mr: isChoiceUser ? 0 : 1, ml: isChoiceUser ? 1 : 0,
              '&:hover .character-popup': { opacity: 1 }
            }}>
              <Avatar
                src={character.imageUrl ? resolveAssetUrl(character.imageUrl) : undefined}
                alt={character.name}
                imgProps={{
                  onError: (e: React.SyntheticEvent<HTMLImageElement>) => {
                    e.currentTarget.style.display = 'none';
                  }
                }}
                sx={chatAvatarSx(character.name)}
              >
                {character.name.charAt(0) || '?'}
              </Avatar>
              {character.imageUrl && (
                <Box className="character-popup"
                  sx={{
                    position: 'absolute',
                    bottom: '100%',
                    left: '50%',
                    transform: 'translateX(-50%)',
                    mb: 1,
                    opacity: 0,
                    pointerEvents: 'none',
                    transition: 'opacity 200ms ease',
                    zIndex: 1000,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center'
                  }}
                >
                  <img
                    src={resolveAssetUrl(character.imageUrl)}
                    alt={character.name}
                    onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
                    style={{
                      maxWidth: '80px',
                      maxHeight: '140px',
                      objectFit: 'contain',
                      borderRadius: '8px',
                      boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
                      border: '2px solid rgba(255,255,255,0.15)',
                      backgroundColor: '#ffffff'
                    }}
                  />
                  <Typography
                    variant="caption"
                    sx={{
                      mt: 0.5,
                      px: 1,
                      py: 0.25,
                      fontSize: '0.72rem',
                      borderRadius: 4,
                      color: '#f2f2f2',
                      backgroundColor: 'rgba(17,17,17,0.9)',
                      whiteSpace: 'nowrap'
                    }}
                  >
                    {character.name}
                  </Typography>
                </Box>
              )}
            </Box>
            <Box sx={{ position: 'relative', maxWidth: '80%', pt: 0.9 }}>
              <Typography
                variant="caption"
                sx={{
                  display: 'block',
                  mb: 0.45,
                  color: isChoiceUser ? '#a86c57' : '#5a7a6e',
                  fontWeight: 700,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  textAlign: isChoiceUser ? 'right' : 'left',
                }}
              >
                {isChoiceUser ? 'You' : character.name}
              </Typography>
              <Paper 
                elevation={0} 
                sx={{ 
                  py: 1.25, 
                  px: 2, 
                  borderRadius: isChoiceUser 
                    ? '1.2rem 1.2rem 0.4rem 1.2rem' 
                    : '1.2rem 1.2rem 1.2rem 0.4rem',
                  background: isChoiceUser
                    ? 'linear-gradient(135deg, #fdf0e8 0%, #f8e4d8 100%)'
                    : 'rgba(232,245,240,0.9)',
                  color: '#5a3e2e',
                  border: isChoiceUser
                    ? '1px solid rgba(232,168,152,0.3)'
                    : '1px solid rgba(125,184,162,0.25)',
                  boxShadow: isChoiceUser
                    ? '0 3px 12px rgba(200,136,122,0.12)'
                    : '0 3px 12px rgba(94,168,144,0.10)',
                }}
              >
                <MixedRichText
                  content={message.content}
                  mode={message.renderMode}
                  dialogueColor="#5a3e2e"
                  narrationColor="#c09b8a"
                />
              </Paper>
            </Box>
          </Box>
        );
        
      case 'text':
      default:
        const isUserMessage = character.role === 'protagonist';

        return (
          <Box 
            sx={{ 
              display: 'flex',
              flexDirection: isUserMessage ? 'row-reverse' : 'row', 
              justifyContent: isUserMessage ? 'flex-start' : 'flex-start',
              width: '100%',
              alignItems: 'flex-end',
              mb: 1.25
            }}
          >
            <Box sx={{ position: 'relative', display: 'inline-block', mr: isUserMessage ? 0 : 1, ml: isUserMessage ? 1 : 0,
              '&:hover .character-popup': { opacity: 1 }
            }}>
              <Avatar
                src={character.imageUrl ? resolveAssetUrl(character.imageUrl) : undefined}
                alt={character.name}
                imgProps={{
                  onError: (e: React.SyntheticEvent<HTMLImageElement>) => {
                    e.currentTarget.style.display = 'none';
                  }
                }}
                sx={chatAvatarSx(character.name)}
              >
                {character.name.charAt(0) || '?'}
              </Avatar>
              {character.imageUrl && (
                <Box className="character-popup"
                  sx={{
                    position: 'absolute',
                    bottom: '100%',
                    left: '50%',
                    transform: 'translateX(-50%)',
                    mb: 1,
                    opacity: 0,
                    pointerEvents: 'none',
                    transition: 'opacity 200ms ease',
                    zIndex: 1000,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center'
                  }}
                >
                  <img
                    src={resolveAssetUrl(character.imageUrl)}
                    alt={character.name}
                    onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
                    style={{
                      maxWidth: '80px',
                      maxHeight: '140px',
                      objectFit: 'contain',
                      borderRadius: '8px',
                      boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
                      border: '2px solid rgba(255,255,255,0.15)',
                      backgroundColor: '#ffffff'
                    }}
                  />
                  <Typography
                    variant="caption"
                    sx={{
                      mt: 0.5,
                      px: 1,
                      py: 0.25,
                      fontSize: '0.72rem',
                      borderRadius: 4,
                      color: '#f2f2f2',
                      backgroundColor: 'rgba(17,17,17,0.9)',
                      whiteSpace: 'nowrap'
                    }}
                  >
                    {character.name}
                  </Typography>
                </Box>
              )}
            </Box>
            <Box sx={{ position: 'relative', maxWidth: '80%', pt: 0.9 }}>
              <Typography
                variant="caption"
                sx={{
                  display: 'block',
                  mb: 0.45,
                  color: isUserMessage ? '#a86c57' : revealLike ? '#826535' : '#5a7a6e',
                  fontWeight: 700,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  textAlign: isUserMessage ? 'right' : 'left',
                }}
              >
                {isUserMessage ? 'You' : character.name}
              </Typography>
              <Paper
                elevation={0}
                sx={{
                  py: 1.25,
                  px: 2,
                  borderRadius: isUserMessage
                    ? '1.2rem 1.2rem 0.4rem 1.2rem'
                    : '1.2rem 1.2rem 1.2rem 0.4rem',
                  background: isUserMessage
                    ? 'linear-gradient(135deg, #fdf0e8 0%, #f8e4d8 100%)'
                    : revealLike
                      ? 'linear-gradient(135deg, rgba(244,237,214,0.94), rgba(238,226,190,0.9))'
                      : 'rgba(232,245,240,0.9)',
                  border: isUserMessage
                    ? '1px solid rgba(232,168,152,0.3)'
                    : revealLike
                      ? '1px solid rgba(173,142,86,0.34)'
                      : '1px solid rgba(125,184,162,0.25)',
                  boxShadow: isUserMessage
                    ? '0 3px 12px rgba(200,136,122,0.12)'
                    : revealLike
                      ? '0 10px 26px rgba(173,142,86,0.14)'
                      : '0 3px 12px rgba(94,168,144,0.10)',
                  position: 'relative',
                  overflow: 'hidden',
                  ...(revealLike ? { '&::before': { content: '""', position: 'absolute', left: 0, top: 0, bottom: 0, width: 4, background: 'linear-gradient(180deg, #c49a57 0%, #e5c889 100%)' } } : {}),
                }}
              >
                <MixedRichText
                  content={message.content}
                  mode={message.renderMode}
                  dialogueColor={isUserMessage ? '#5a4035' : '#264b42'}
                  narrationColor={isUserMessage ? '#b28f84' : '#7f8a84'}
                />
              </Paper>
            </Box>
          </Box>
        );
      case 'typing':
        // 正在输入占位 - 使用问号头像
        return (
          <Box 
            sx={{ 
              display: 'flex',
              flexDirection: 'row', 
              justifyContent: 'flex-start',
              width: '100%',
              alignItems: 'flex-end',
              mb: 2
            }}
          >
            <Avatar 
              sx={{ 
                mr: 1,
                bgcolor: '#1f2937',
                width: 42,
                height: 42,
                borderRadius: '10px',
                boxShadow: '0 2px 8px rgba(0,0,0,0.25)',
                border: '1px solid rgba(255,255,255,0.08)'
              }}
            >
              ?
            </Avatar>
            <Paper
              elevation={0}
              sx={{
                py: 1.25,
                px: 2,
                borderRadius: '1.2rem 1.2rem 1.2rem 0.4rem',
                background: 'rgba(232,245,240,0.7)',
                border: '1px solid rgba(125,184,162,0.2)',
                boxShadow: '0 3px 12px rgba(94,168,144,0.08)',
              }}
            >
              <Box sx={{ display: 'flex', gap: 0.7, alignItems: 'center', py: 0.35 }}>
                {[0, 1, 2].map(dot => (
                  <Box
                    key={`typing-dot-${dot}`}
                    sx={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      bgcolor: '#88b9aa',
                      opacity: 0.45,
                      animation: 'typingPulse 1.2s ease-in-out infinite',
                      animationDelay: `${dot * 0.18}s`,
                      '@keyframes typingPulse': {
                        '0%, 80%, 100%': { transform: 'translateY(0)', opacity: 0.35 },
                        '40%': { transform: 'translateY(-2px)', opacity: 1 },
                      },
                    }}
                  />
                ))}
              </Box>
            </Paper>
          </Box>
        );
    }
  };

  const renderChoices = (choices: Choice[] | undefined) => {
    if (!choices || choices.length === 0 || isTyping || isInteractionBlocked) return null;
    
    return (
      <Box sx={{ mb: 1.25 }}>
        <Stack spacing={0.8}>
          {choices.map(choice => (
            <Button
              key={choice.id}
              fullWidth
              variant="outlined"
              color="inherit"
              onClick={() => handleChoiceSelect(choice.id)}
              disabled={isTyping || isSending}
              sx={{
                justifyContent: 'flex-start',
                textAlign: 'left',
                p: 1.1,
                borderRadius: '1rem',
                textTransform: 'none',
                fontWeight: 500,
                fontSize: '0.9rem',
                lineHeight: 1.35,
                borderColor: 'rgba(125,184,162,0.35)',
                color: '#3c5a50',
                background: 'rgba(232,245,240,0.7)',
                boxShadow: '0 2px 10px rgba(94,168,144,0.08)',
                transition: 'all 0.22s ease',
                '&:hover': {
                  background: 'rgba(232,245,240,0.95)',
                  borderColor: 'rgba(125,184,162,0.65)',
                  boxShadow: '0 4px 16px rgba(94,168,144,0.16)',
                  transform: 'translateY(-1px)',
                },
              }}
            >
              {choice.text}
            </Button>
          ))}
        </Stack>
      </Box>
    );
  };

  // Build dynamic background image URL (fallback to default grey background if absent)
  const bgImageUrl = resolveAssetUrl(story?.currentScene?.backgroundImage);

  return (
    <Container maxWidth="xl" className="aurora-shimmer" sx={{ height: '100vh', py: 2, position: 'relative', backgroundImage: bgImageUrl ? `url('${bgImageUrl}')` : undefined, backgroundColor: bgImageUrl ? undefined : 'background.default', backgroundSize: 'cover', backgroundPosition: 'center', backgroundAttachment: 'fixed' }}>
      {showIntro && (
        <Box sx={{ position: 'absolute', inset: 0, bgcolor: 'background.default', zIndex: 2000, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
          <CircularProgress size={60} />
          <Typography variant="h6" sx={{ mt: 3 }}>Loading screenplay...</Typography>
        </Box>
      )}
      {showTransition && !isInteractionBlocked && story?.currentScene.scene_transition_caption && (
        <Fade in={showTransition}>
          <Box
            sx={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: 'rgba(0, 0, 0, 0.64)',
              zIndex: 1500,
              pointerEvents: 'none',
            }}
          >
            <Typography
              variant="h4"
              sx={{
                color: 'white',
                textAlign: 'center',
                fontWeight: 'bold',
                px: 4,
                py: 2,
                letterSpacing: '0.05em',
                textTransform: 'uppercase',
                fontFamily: '"Cormorant Garamond", "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Palatino, serif',
                textShadow: '2px 2px 4px rgba(0,0,0,0.5)',
                borderTop: '1px solid rgba(255,255,255,0.3)',
                borderBottom: '1px solid rgba(255,255,255,0.3)',
              }}
            >
              {story.currentScene.scene_transition_caption}
            </Typography>
          </Box>
        </Fade>
      )}
      
      <Paper
        elevation={0}
        sx={{
          p: 2,
          mb: 2,
          borderRadius: 3,
          background: 'rgba(255,252,246,0.82)',
          backdropFilter: 'blur(14px)',
          border: '1px solid rgba(125,184,162,0.18)',
          boxShadow: '0 4px 20px rgba(60,50,44,0.06)',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1.5, flexWrap: 'wrap' }}>
          <Typography variant="h5" sx={{ fontWeight: 700, color: '#3c322c' }}>
            {story?.title}
          </Typography>
        </Box>
      </Paper>
      
      <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, gap: 2, height: 'calc(100vh - 150px)', minWidth: 0 }}>
        {/* Left side - Dialogue history */}
        <Box sx={{ flex: { xs: '1', md: '7' }, minWidth: 0, height: { xs: '50%', md: '100%' } }}>
          <Paper
            elevation={0}
            sx={{
              height: '100%',
              width: '100%',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
              borderRadius: 3,
              background: 'rgba(255,252,246,0.78)',
              backdropFilter: 'blur(14px)',
              border: '1px solid rgba(125,184,162,0.15)',
              boxShadow: '0 4px 24px rgba(60,50,44,0.06)',
            }}
          >
            <TranscriptPane
              messages={transcriptMessages}
              renderMessage={renderMessage}
            />
          </Paper>
        </Box>
        
        {/* Right side - User options and plot info */}
        <Box sx={{ flex: { xs: '1', md: '5' }, minWidth: 0, height: { xs: '50%', md: '100%' }, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
          {/* Top section - User options and input */}
          <Paper
            elevation={0}
            sx={{
              p: 1.5,
              borderRadius: 3,
              mb: 1.25,
              flexShrink: 0,
              width: '100%',
              background: 'rgba(255,252,246,0.82)',
              backdropFilter: 'blur(14px)',
              border: '1px solid rgba(125,184,162,0.15)',
              boxShadow: '0 4px 20px rgba(60,50,44,0.05)',
            }}
          >
            {renderChoices(story?.currentScene.choices)}
            {Boolean(storyMemory?.whatJustHappened || story.dialogueSummaries?.length || story.conclusionCountdown) && (
              <Stack spacing={0.8} sx={{ mt: 0.3, mb: 0.95 }}>
                {storyMemory?.whatJustHappened && (
                  <Box sx={{ p: 1, borderRadius: '12px', background: 'rgba(255,255,255,0.46)', border: '1px solid rgba(125,184,162,0.18)' }}>
                    <Typography variant="caption" sx={{ display: 'block', color: '#6c8d84', fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase', mb: 0.35 }}>
                      What Just Happened
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.82rem', lineHeight: 1.45 }}>
                      {storyMemory.whatJustHappened}
                    </Typography>
                  </Box>
                )}
                {story.conclusionCountdown ? (
                  <Chip
                    label={`Ending pressure: ${story.conclusionCountdown} turn${story.conclusionCountdown > 1 ? 's' : ''} left`}
                    size="small"
                    sx={{
                      alignSelf: 'flex-start',
                      bgcolor: 'rgba(232,168,152,0.18)',
                      color: '#9f5d4a',
                      border: '1px solid rgba(232,168,152,0.32)',
                    }}
                  />
                ) : null}
              </Stack>
            )}
            {/* Fast-forward toggle */}
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.75 }}>
              <Typography variant="body2" sx={{ mr: 0.8, fontSize: '0.85rem' }}>Fast-forward</Typography>
              <Button
                size="small"
                variant={fastForward ? 'contained' : 'outlined'}
                color={fastForward ? 'secondary' : 'inherit'}
                onClick={() => setFastForward(!fastForward)}
                sx={{ borderRadius: 2, textTransform: 'none', minWidth: 46, px: 1.1, py: 0.35, fontSize: '0.78rem' }}
              >
                {fastForward ? 'On' : 'Off'}
              </Button>
            </Box>
            
            <form onSubmit={handleSendMessage}>
              <Stack direction="row" spacing={0.75}>
                <TextField
                  fullWidth
                  variant="outlined"
                  placeholder={
                    isInteractionBlocked
                      ? "Click Proceed on the interactive element to continue the scene..."
                      : isTyping
                        ? "Waiting for response..."
                        : "Type your message or choose an option..."
                  }
                  value={userMessage}
                  onChange={e => setUserMessage(e.target.value)}
                  disabled={isTyping || isSending || isInteractionBlocked}
                  sx={{
                    '& .MuiOutlinedInput-root': {
                      borderRadius: '1rem',
                      background: 'rgba(255,252,246,0.85)',
                      boxShadow: '0 2px 10px rgba(60,50,44,0.06)',
                    },
                    '& .MuiOutlinedInput-input': {
                      padding: '0.72rem 0.9rem',
                      color: '#3c322c',
                      fontSize: '0.9rem',
                    },
                    '& .MuiOutlinedInput-notchedOutline': {
                      borderColor: 'rgba(125,184,162,0.3)',
                    },
                    '&:hover .MuiOutlinedInput-notchedOutline': {
                      borderColor: 'rgba(125,184,162,0.55)',
                    },
                    '& .MuiOutlinedInput-root.Mui-focused .MuiOutlinedInput-notchedOutline': {
                      borderColor: '#7db8a2',
                      borderWidth: 1.5,
                    },
                    '& .MuiInputBase-input::placeholder': {
                      color: '#a89d96',
                      opacity: 1,
                    },
                  }}
                  autoComplete="off"
                />
                <IconButton 
                  type="submit" 
                  color="primary" 
                  aria-label="send message" 
                  disabled={!userMessage.trim() || isSending || isTyping || isInteractionBlocked}
                  sx={{ 
                    bgcolor: 'primary.main', 
                    color: 'white',
                    '&:hover': {
                      bgcolor: 'primary.dark'
                    },
                    width: 48,
                    height: 48,
                    borderRadius: '14px',
                    flexShrink: 0,
                  }}
                >
                  {isSending ? <CircularProgress size={20} color="inherit" /> : <SendIcon sx={{ fontSize: 20 }} />}
                </IconButton>
              </Stack>
            </form>
          </Paper>
          
          {/* Bottom section - Plot information with tabs */}
          <Paper
            elevation={0}
            sx={{
              flexGrow: 1,
              minHeight: 0,
              display: 'flex',
              flexDirection: 'column',
              width: '100%',
              borderRadius: 3,
              overflow: 'hidden',
              background: 'rgba(255,252,246,0.78)',
              backdropFilter: 'blur(14px)',
              border: '1px solid rgba(125,184,162,0.15)',
              boxShadow: '0 4px 24px rgba(60,50,44,0.06)',
            }}
          >
            <Box sx={{ borderBottom: '1px solid rgba(125,184,162,0.18)', bgcolor: 'rgba(232,245,240,0.35)', flexShrink: 0 }}>
              <Tabs
                value={tabValue}
                onChange={handleTabChange}
                variant="fullWidth"
                aria-label="story information tabs"
                textColor="inherit"
              >
                <Tab
                  icon={tabIconBadge(
                    <AutoAwesomeRoundedIcon />,
                    'linear-gradient(135deg, #a0b4d8 0%, #7db8a2 100%)',
                    'rgba(125,184,162,0.26)'
                  )}
                  label="Scene"
                  sx={{ color: '#5a7a6e', '&.Mui-selected': { color: '#3c5a50', fontWeight: 700 }, minWidth: 60 }}
                />
                <Tab
                  icon={tabIconBadge(
                    <Groups2RoundedIcon />,
                    'linear-gradient(135deg, #e8a898 0%, #d7a7c8 100%)',
                    'rgba(216,154,170,0.26)'
                  )}
                  label="Cast"
                  sx={{ color: '#5a7a6e', '&.Mui-selected': { color: '#3c5a50', fontWeight: 700 }, minWidth: 60 }}
                />
                <Tab
                  icon={tabIconBadge(
                    <RouteRoundedIcon />,
                    'linear-gradient(135deg, #7aa8c4 0%, #a0b4d8 100%)',
                    'rgba(122,168,196,0.26)'
                  )}
                  label="Journey"
                  sx={{ color: '#5a7a6e', '&.Mui-selected': { color: '#3c5a50', fontWeight: 700 }, minWidth: 60 }}
                />
                <Tab
                  icon={tabIconBadge(
                    <FavoriteRoundedIcon />,
                    'linear-gradient(135deg, #7db8a2 0%, #b0a8d8 100%)',
                    'rgba(176,168,216,0.26)'
                  )}
                  label="State"
                  sx={{ color: '#5a7a6e', '&.Mui-selected': { color: '#3c5a50', fontWeight: 700 }, minWidth: 60 }}
                />
              </Tabs>
            </Box>
            
            <Box sx={{ p: 2, flexGrow: 1, minHeight: 0, height: 0, minWidth: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
              {tabValue === 0 && renderSceneInfo()}
              {tabValue === 1 && renderCharacters()}
              {tabValue === 2 && renderLocationHistory()}
              {tabValue === 3 && (
                <Stack spacing={1.15} sx={{ overflowY: 'auto', pr: 0.25 }}>
                  {renderInfoCard(
                    'Current State',
                    <Typography variant="body2" sx={{ color: 'text.secondary', lineHeight: 1.55 }}>
                      {sceneInfoPanel?.recap || storyMemory?.whatJustHappened || 'The story state will become clearer as more turns accumulate.'}
                    </Typography>,
                    '#8b7ab0'
                  )}
                  {renderInfoCard(
                    'Latest Reveal',
                    (storyState?.latestReveal || storyMemory?.lastMajorTurningPoint)
                      ? (
                        <Typography variant="body2" sx={{ color: '#5a5048', lineHeight: 1.55 }}>
                          {storyState?.latestReveal || storyMemory?.lastMajorTurningPoint}
                        </Typography>
                      )
                      : null,
                    '#b08c5e'
                  )}
                  {renderInfoCard(
                    'Relationship Shift',
                    storyState?.relationshipShift
                      ? (
                        <Typography variant="body2" sx={{ color: '#5a5048', lineHeight: 1.55 }}>
                          {storyState.relationshipShift}
                        </Typography>
                      )
                      : null,
                    '#7c9a90'
                  )}
                </Stack>
              )}
            </Box>
          </Paper>
        </Box>
      </Box>
      
      <Box sx={{ display: 'flex', gap: 2, mt: 2 }}>
        <Button onClick={handleEndStory} color="error">End Story</Button>
      </Box>

      <Snackbar
        open={!!sendError}
        autoHideDuration={4000}
        onClose={() => setSendError(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity="error" onClose={() => setSendError(null)} sx={{ width: '100%' }}>
          {sendError}
        </Alert>
      </Snackbar>
      
      <DebugPanel story={story} />

      {/* Floating feedback button */}
      {!experimentMode && (
        <FeedbackWidget
          storyId={story?.id}
          userId={story?.userId}
          mode="floating"
          feedbackType="in_session"
        />
      )}
    </Container>
  );
};

export default StoryInteraction; 
