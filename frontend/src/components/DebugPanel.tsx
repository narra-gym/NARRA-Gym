import React, { useState } from 'react';
import { Box, Button, Paper, Typography, Accordion, AccordionSummary, AccordionDetails, Chip, Stack } from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { Story, Character, Message } from '../types';

interface DebugPanelProps {
  story?: Story | null;
}

const DebugPanel: React.FC<DebugPanelProps> = ({ story }) => {
  const [isVisible, setIsVisible] = useState(false);

  if (!isVisible) {
    return (
      <Button 
        variant="outlined" 
        size="small" 
        sx={{ position: 'fixed', bottom: 10, right: 10, opacity: 0.7 }}
        onClick={() => setIsVisible(true)}
      >
        Debug
      </Button>
    );
  }

  if (!story) {
    return (
      <Paper sx={{ position: 'fixed', bottom: 10, right: 10, p: 2, maxWidth: 400, maxHeight: '80vh', overflow: 'auto', opacity: 0.9 }}>
        <Typography variant="h6">Debug Panel</Typography>
        <Typography>No story data available</Typography>
        <Button size="small" onClick={() => setIsVisible(false)}>Close</Button>
      </Paper>
    );
  }

  return (
    <Paper sx={{ position: 'fixed', bottom: 10, right: 10, p: 2, maxWidth: 400, maxHeight: '80vh', overflow: 'auto', opacity: 0.9, zIndex: 9999 }}>
      <Typography variant="h6">Debug Panel</Typography>
      <Button size="small" onClick={() => setIsVisible(false)}>Close</Button>
      {/* Basic pacing indicators */}
      <Stack direction="row" spacing={1} sx={{ mt: 1, mb: 1 }}>
        {typeof (story as any)?.dialogueCount === 'number' && (
          <Chip size="small" label={`Dialogue: ${(story as any).dialogueCount}`} />
        )}
        {typeof (story as any)?.conclusionCountdown === 'number' && (story as any).conclusionCountdown > 0 && (
          <Chip size="small" color="warning" label={`Countdown: ${(story as any).conclusionCountdown}`} />
        )}
      </Stack>
      
      <Accordion>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography>Characters ({story.characters.length})</Typography>
        </AccordionSummary>
        <AccordionDetails>
          {story.characters.map((char: Character) => (
            <Box key={char.id} sx={{ mb: 1, p: 1, border: '1px solid #eee' }}>
              <Typography variant="subtitle2">ID: {char.id}</Typography>
              <Typography variant="subtitle2">Name: {char.name}</Typography>
              <Typography variant="body2">Role: {char.role}</Typography>
            </Box>
          ))}
        </AccordionDetails>
      </Accordion>

      <Accordion>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography>Current Messages ({story.currentScene.messages.length})</Typography>
        </AccordionSummary>
        <AccordionDetails>
          {story.currentScene.messages.map((msg: Message, index: number) => (
            <Box key={msg.id || `msg-${index}`} sx={{ mb: 1, p: 1, border: '1px solid #eee' }}>
              <Typography variant="subtitle2">Message #{index+1}</Typography>
              <Typography variant="caption" display="block">ID: {msg.id}</Typography>
              <Typography variant="caption" display="block">Character ID: {msg.characterId || 'undefined'}</Typography>
              <Typography variant="caption" display="block">Type: {msg.type}</Typography>
              <Typography variant="body2">{msg.content.substring(0, 50)}...</Typography>
            </Box>
          ))}
        </AccordionDetails>
      </Accordion>

      <Accordion>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography>Summaries (every 3 turns)</Typography>
        </AccordionSummary>
        <AccordionDetails>
          {(story as any)?.dialogueSummaries && (story as any).dialogueSummaries.length > 0 ? (
            (story as any).dialogueSummaries.map((s: string, idx: number) => (
              <Box key={`sum-${idx}`} sx={{ mb: 1, p: 1, border: '1px solid #eee' }}>
                <Typography variant="subtitle2">Summary #{idx + 1}</Typography>
                <Typography variant="body2">{s}</Typography>
              </Box>
            ))
          ) : (
            <Typography variant="body2" color="text.secondary">No summaries yet</Typography>
          )}
        </AccordionDetails>
      </Accordion>
    </Paper>
  );
};

export default DebugPanel; 