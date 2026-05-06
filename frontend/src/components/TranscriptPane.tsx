import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Box } from '@mui/material';
import { layout, prepare } from '@chenglou/pretext';
import { Message } from '../types';
import { parseMixedText } from '../utils/mixedText';

interface TranscriptPaneProps {
  messages: Message[];
  renderMessage: (message: Message, index: number) => React.ReactNode;
}

const PRETEXT_FONTS = {
  dialogue: '500 16px "Segoe UI"',
  narration: '400 italic 15px "Georgia"',
  system: '600 13px "Segoe UI"',
};

const preparedTextCache = new Map<string, any>();
const getPreparedText = (text: string, font: string) => {
  const key = `${font}::${text}`;
  if (!preparedTextCache.has(key)) {
    preparedTextCache.set(key, prepare(text, font, { whiteSpace: 'pre-wrap' }));
  }
  return preparedTextCache.get(key);
};

const fallbackTextHeight = (text: string, width: number, lineHeight: number) => {
  const approxCharsPerLine = Math.max(Math.floor(width / 11), 10);
  const lines = Math.max(
    1,
    text
      .split('\n')
      .reduce((count, line) => count + Math.max(1, Math.ceil(Math.max(line.length, 1) / approxCharsPerLine)), 0),
  );
  return lines * lineHeight;
};

const estimateMessageHeight = (message: Message, containerWidth: number): number => {
  const width = Math.max(containerWidth - 56, 220);
  const content = message.content || '';
  const mode = message.renderMode || ((message.action || message.direction || /\*[^*]+\*/.test(content)) ? 'rp_mixed' : 'plain');

  if (message.type === 'interactive') {
    return 388;
  }
  if (message.type === 'typing') {
    return 76;
  }

  const textWidth = message.type === 'system'
    ? width * 0.9
    : width * 0.72;
  const lineHeight = message.type === 'system' ? 20 : 28;
  const chromeHeight = message.type === 'system'
    ? 40
    : (message.type === 'choice' ? 76 : 88);

  try {
    const measuredText = mode === 'rp_mixed'
      ? parseMixedText(content).map(segment => segment.text).join('')
      : content;
    const textHeight = layout(
      getPreparedText(measuredText, message.type === 'system' ? PRETEXT_FONTS.system : PRETEXT_FONTS.dialogue),
      textWidth,
      lineHeight,
    ).height;
    return Math.max(textHeight + chromeHeight, message.type === 'system' ? 56 : 88);
  } catch {
    return fallbackTextHeight(content, textWidth, lineHeight) + chromeHeight;
  }
};

interface TranscriptItemProps {
  children: React.ReactNode;
  index: number;
  onMeasure: (index: number, height: number) => void;
  top: number;
}

const TranscriptItem: React.FC<TranscriptItemProps> = ({ children, index, onMeasure, top }) => {
  const itemRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = itemRef.current;
    if (!node) return;

    const emitHeight = () => {
      onMeasure(index, node.getBoundingClientRect().height);
    };

    emitHeight();
    const observer = new ResizeObserver(emitHeight);
    observer.observe(node);
    return () => observer.disconnect();
  }, [index, onMeasure, top]);

  return (
    <Box
      ref={itemRef}
      sx={{
        position: 'absolute',
        top,
        left: 0,
        right: 0,
      }}
    >
      {children}
    </Box>
  );
};

const TranscriptPane: React.FC<TranscriptPaneProps> = ({ messages, renderMessage }) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const stickToBottomRef = useRef(true);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewport, setViewport] = useState({ width: 720, height: 640 });
  const [measuredHeights, setMeasuredHeights] = useState<Record<number, number>>({});

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;

    const updateViewport = () => {
      setViewport({
        width: node.clientWidth,
        height: node.clientHeight,
      });
    };

    updateViewport();
    const observer = new ResizeObserver(updateViewport);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setMeasuredHeights({});
  }, [viewport.width]);

  const handleMeasure = useCallback((index: number, height: number) => {
    const roundedHeight = Math.ceil(height);
    setMeasuredHeights(prev => {
      if (prev[index] === roundedHeight) {
        return prev;
      }
      return { ...prev, [index]: roundedHeight };
    });
  }, []);

  const measurements = useMemo(() => {
    let offset = 0;
    return messages.map((message, index) => {
      const height = measuredHeights[index] ?? estimateMessageHeight(message, viewport.width);
      const item = {
        index,
        top: offset,
        height,
      };
      offset += height;
      return item;
    });
  }, [measuredHeights, messages, viewport.width]);

  const totalHeight = measurements.length
    ? measurements[measurements.length - 1].top + measurements[measurements.length - 1].height
    : 0;
  const lastMessageContent = messages[messages.length - 1]?.content;

  const overscan = 480;
  const visibleRange = useMemo(() => {
    const minTop = Math.max(scrollTop - overscan, 0);
    const maxBottom = scrollTop + viewport.height + overscan;
    let startIndex = 0;
    let endIndex = Math.max(measurements.length - 1, 0);

    for (let index = 0; index < measurements.length; index += 1) {
      const item = measurements[index];
      if (item.top + item.height >= minTop) {
        startIndex = index;
        break;
      }
    }

    for (let index = startIndex; index < measurements.length; index += 1) {
      const item = measurements[index];
      if (item.top > maxBottom) {
        endIndex = index;
        break;
      }
    }

    return { startIndex, endIndex };
  }, [measurements, scrollTop, viewport.height]);

  useEffect(() => {
    const node = containerRef.current;
    if (!node || !stickToBottomRef.current) return;
    node.scrollTop = node.scrollHeight;
  }, [messages.length, lastMessageContent]);

  return (
    <Box
      ref={containerRef}
      onScroll={(event) => {
        const node = event.currentTarget;
        setScrollTop(node.scrollTop);
        stickToBottomRef.current = node.scrollTop + node.clientHeight >= node.scrollHeight - 96;
      }}
      sx={{
        flexGrow: 1,
        overflowY: 'auto',
        p: { xs: 2, sm: 3 },
        position: 'relative',
      }}
    >
      <Box sx={{ height: totalHeight, position: 'relative' }}>
        {measurements
          .slice(visibleRange.startIndex, visibleRange.endIndex + 1)
          .map(item => (
            <TranscriptItem
              key={messages[item.index]?.id || `message-${item.index}`}
              index={item.index}
              onMeasure={handleMeasure}
              top={item.top}
            >
              {renderMessage(messages[item.index], item.index)}
            </TranscriptItem>
          ))}
      </Box>
    </Box>
  );
};

export default TranscriptPane;
