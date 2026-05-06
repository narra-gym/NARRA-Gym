import React from 'react';
import { Box } from '@mui/material';
import { parseMixedText } from '../utils/mixedText';

interface MixedRichTextProps {
  content: string;
  mode?: 'plain' | 'rp_mixed';
  dialogueColor?: string;
  narrationColor?: string;
  fontSize?: string | number;
}

const MixedRichText: React.FC<MixedRichTextProps> = ({
  content,
  mode = 'plain',
  dialogueColor = '#2d5a4a',
  narrationColor = '#7f8a84',
  fontSize = '1rem',
}) => {
  if (!content) {
    return null;
  }

  if (mode !== 'rp_mixed') {
    return (
      <Box
        component="div"
        sx={{
          color: dialogueColor,
          whiteSpace: 'pre-wrap',
          lineHeight: 1.7,
          fontSize,
        }}
      >
        {content}
      </Box>
    );
  }

  const segments = parseMixedText(content);
  return (
    <Box
      component="div"
      sx={{
        whiteSpace: 'pre-wrap',
        lineHeight: 1.66,
        fontSize,
      }}
    >
      {segments.map((segment, index) => (
        <Box
          key={`${segment.kind}-${index}`}
          component="span"
          sx={{
            color: segment.kind === 'narration' ? narrationColor : dialogueColor,
            fontStyle: segment.kind === 'narration' ? 'italic' : 'normal',
            fontWeight: segment.kind === 'narration' ? 400 : 500,
          }}
        >
          {segment.text}
        </Box>
      ))}
    </Box>
  );
};

export default MixedRichText;
