import React, { useEffect, useRef, useState } from 'react';
import { Box, Paper, Typography, Button, Collapse, Stack, Fade, IconButton, Chip } from '@mui/material';
import WarningIcon from '@mui/icons-material/Warning';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import BlockIcon from '@mui/icons-material/Block';
import CloseIcon from '@mui/icons-material/Close';
import { useStory } from '../contexts/StoryContext';

interface InteractiveElementProps {
  htmlCode: string;
  height?: string | number;
  width?: string | number;
}

interface ConsoleMessage {
  type: 'log' | 'error' | 'warn' | 'info';
  content: string;
  timestamp: Date;
}

const DEFAULT_HEIGHT_PX = 560;
const MIN_HEIGHT_PX = 460;
const MAX_VIEWPORT_RATIO = 0.78;

const getInitialHeight = (height?: string | number): number => {
  if (typeof height === 'number' && Number.isFinite(height)) {
    return height;
  }
  if (typeof height === 'string') {
    const parsed = Number.parseInt(height, 10);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return DEFAULT_HEIGHT_PX;
};

const getMaxFrameHeight = (): number => {
  if (typeof window === 'undefined') {
    return 760;
  }
  return Math.max(560, Math.floor(window.innerHeight * MAX_VIEWPORT_RATIO));
};

const InteractiveElement: React.FC<InteractiveElementProps> = ({ 
  htmlCode, 
  height = DEFAULT_HEIGHT_PX, 
  width = '100%' 
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const { clearInteractiveElement } = useStory();
  const [error, setError] = useState<string | null>(null);
  const [showSource, setShowSource] = useState(false);
  const [showConsole, setShowConsole] = useState(false);
  const [consoleMessages, setConsoleMessages] = useState<ConsoleMessage[]>([]);
  // 新增状态：用户是否同意显示交互元素
  const [userConsent, setUserConsent] = useState<boolean | null>(null);
  const [dismissed, setDismissed] = useState<boolean>(false);
  const [frameHeightPx, setFrameHeightPx] = useState<number>(() => getInitialHeight(height));

  useEffect(() => {
    setFrameHeightPx(getInitialHeight(height));
  }, [height]);
  
  // 只有当用户同意后才初始化交互元素
  useEffect(() => {
    if (!containerRef.current || !htmlCode || userConsent !== true) return;
    const baseHeight = getInitialHeight(height);
    
    // Clear any previous content
    containerRef.current.innerHTML = '';
    setError(null);
    setConsoleMessages([]);
    
    try {
      // Create a sandboxed iframe for the interactive element with more permissions
      const iframe = document.createElement('iframe');
      iframe.style.width = '100%';
      iframe.style.height = `${baseHeight}px`;
      iframe.style.border = 'none';
      iframe.style.display = 'block';
      
      // 添加更多的权限，让交互式元素能够正常工作
      iframe.sandbox.add('allow-scripts');       // 允许执行脚本
      iframe.sandbox.add('allow-same-origin');   // 允许同源访问
      iframe.sandbox.add('allow-forms');         // 允许表单操作
      iframe.sandbox.add('allow-pointer-lock');  // 允许指针锁定
      iframe.sandbox.add('allow-popups');        // 允许弹窗
      iframe.sandbox.add('allow-modals');        // 允许模态框（alert、confirm、prompt等）
      
      // 设置允许全屏
      iframe.setAttribute('allowfullscreen', 'true');
      
      // Append the iframe to the container
      containerRef.current.appendChild(iframe);
      
      // Write the HTML code to the iframe
      const iframeDoc = iframe.contentDocument || iframe.contentWindow?.document;
      if (iframeDoc) {
        const applyMeasuredHeight = () => {
          try {
            const doc = iframe.contentDocument || iframe.contentWindow?.document;
            if (!doc?.body || !doc.documentElement) return;
            const measuredHeight = Math.max(
              doc.body.scrollHeight,
              doc.body.offsetHeight,
              doc.documentElement.scrollHeight,
              doc.documentElement.offsetHeight
            );
            if (!measuredHeight) return;
            const nextHeight = Math.min(
              Math.max(measuredHeight + 24, MIN_HEIGHT_PX, baseHeight),
              getMaxFrameHeight()
            );
            iframe.style.height = `${nextHeight}px`;
            setFrameHeightPx(prev => (prev === nextHeight ? prev : nextHeight));
          } catch (resizeError) {
            console.warn('Failed to measure interactive element height:', resizeError);
          }
        };

        // 注入控制台拦截代码
        const consoleInterceptScript = `
          <script>
            (function() {
              const originalConsole = {
                log: console.log,
                error: console.error,
                warn: console.warn,
                info: console.info
              };
              
              function interceptConsole(type) {
                return function() {
                  // 调用原始方法
                  originalConsole[type].apply(console, arguments);
                  
                  // 发送消息到父窗口
                  try {
                    const args = Array.from(arguments).map(arg => {
                      if (typeof arg === 'object') {
                        try {
                          return JSON.stringify(arg);
                        } catch (e) {
                          return String(arg);
                        }
                      }
                      return String(arg);
                    }).join(' ');
                    
                    window.parent.postMessage({
                      type: 'console',
                      method: type,
                      content: args
                    }, '*');
                  } catch (e) {
                    // 忽略发送消息时的错误
                  }
                };
              }
              
              // 替换控制台方法
              console.log = interceptConsole('log');
              console.error = interceptConsole('error');
              console.warn = interceptConsole('warn');
              console.info = interceptConsole('info');
            })();
          </script>
        `;
        
        // 添加控制台拦截代码到HTML
        let enhancedHtml = htmlCode;
        if (htmlCode.includes('<head>')) {
          enhancedHtml = htmlCode.replace('<head>', '<head>' + consoleInterceptScript);
        } else if (htmlCode.includes('<html>')) {
          enhancedHtml = htmlCode.replace('<html>', '<html><head>' + consoleInterceptScript + '</head>');
        } else {
          enhancedHtml = consoleInterceptScript + htmlCode;
        }
        
        iframeDoc.open();
        iframeDoc.write(enhancedHtml);
        iframeDoc.close();

        const loadHandler = () => applyMeasuredHeight();
        iframe.addEventListener('load', loadHandler);
        window.setTimeout(applyMeasuredHeight, 50);
        window.setTimeout(applyMeasuredHeight, 250);
        window.setTimeout(applyMeasuredHeight, 800);
        window.setTimeout(applyMeasuredHeight, 1500);

        let observer: MutationObserver | null = null;
        try {
          observer = new MutationObserver(() => applyMeasuredHeight());
          if (iframeDoc.body) {
            observer.observe(iframeDoc.body, {
              childList: true,
              subtree: true,
              attributes: true,
              characterData: true,
            });
          }
        } catch (observerError) {
          console.warn('Failed to observe interactive element mutations:', observerError);
        }
        
        // 添加错误监听
        const errorHandler = (e: ErrorEvent) => {
          console.error('Iframe script error:', e);
          setError('Interactive element encountered a script error');
          setConsoleMessages(prev => [...prev, {
            type: 'error',
            content: `Script error: ${e.message} at line ${e.lineno}, col ${e.colno}`,
            timestamp: new Date()
          }]);
        };
        iframe.contentWindow?.addEventListener('error', errorHandler);
        
        // 监听来自iframe的消息
        const messageHandler = (event: MessageEvent) => {
          if (event.data && event.data.type === 'console') {
            setConsoleMessages(prev => [...prev, {
              type: event.data.method,
              content: event.data.content,
              timestamp: new Date()
            }]);
          }
          window.setTimeout(applyMeasuredHeight, 0);
        };
        window.addEventListener('message', messageHandler);

        return () => {
          iframe.removeEventListener('load', loadHandler);
          iframe.contentWindow?.removeEventListener('error', errorHandler);
          window.removeEventListener('message', messageHandler);
          observer?.disconnect();
        };
      } else {
        throw new Error('Could not access iframe document');
      }
    } catch (error) {
      console.error('Error rendering interactive element:', error);
      setError('Failed to load interactive element securely');
    }
    
    // 清理函数
    return undefined;
  }, [htmlCode, userConsent, height]); // 添加userConsent作为依赖项
  
  // Consent prompt (English only)
  const renderConsentPrompt = () => {
    return (
      <Fade in={true}>
        <Box 
          sx={{ 
            width: '100%', 
            minHeight: `${frameHeightPx}px`,
            display: 'flex', 
            flexDirection: 'column',
            justifyContent: 'center',
            alignItems: 'center',
            p: 3,
            textAlign: 'center',
            backdropFilter: 'blur(10px)',
            backgroundColor: 'rgba(255,255,255,0.8)',
          }}
        >
          <WarningIcon color="warning" sx={{ fontSize: 60, mb: 2 }} />
          
          <Typography variant="h6" gutterBottom>
            Interactive Content
          </Typography>
          
          <Typography variant="body1" sx={{ mb: 3, maxWidth: '80%' }}>
            An interactive element needs your confirmation to display. It may include scripts and dynamic content.
          </Typography>
          
          <Stack direction="row" spacing={2}>
            <Button 
              variant="contained" 
              color="primary"
              startIcon={<CheckCircleIcon />}
              onClick={() => setUserConsent(true)}
            >
              Show Content
            </Button>
            
            <Button 
              variant="outlined"
              color="error"
              startIcon={<BlockIcon />}
              onClick={() => setUserConsent(false)}
            >
              Don't Show
            </Button>
          </Stack>
        </Box>
      </Fade>
    );
  };
  
  // Rejected view (English only)
  const renderRejectedView = () => {
    return (
      <Box 
        sx={{ 
          width: '100%', 
          minHeight: `${frameHeightPx}px`,
          display: 'flex', 
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          p: 3,
          textAlign: 'center',
        }}
      >
        <BlockIcon color="action" sx={{ fontSize: 60, mb: 2, opacity: 0.5 }} />
        
        <Typography variant="body1" sx={{ mb: 2, color: 'text.secondary' }}>
          You chose not to display interactive content
        </Typography>
        
        <Button 
          variant="text"
          onClick={() => setUserConsent(null)}
        >
          Choose Again
        </Button>
      </Box>
    );
  };
  
  // If dismissed by user, do not render
  if (dismissed) return null;
  
  // 如果出错，显示错误消息和一个查看源代码的选项
  if (error) {
    return (
      <Paper 
        elevation={3} 
        sx={{ 
          width, 
          minHeight: `${frameHeightPx}px`, 
          overflow: 'auto',
          borderRadius: 2,
          my: 2,
          p: 2
        }}
      >
        <Typography color="error" variant="body1" gutterBottom>
          {error}
        </Typography>
        
        <Box sx={{ mb: 2 }}>
          <Button 
            variant="outlined" 
            size="small" 
            onClick={() => setShowSource(!showSource)}
            sx={{ mr: 1 }}
          >
            {showSource ? 'Hide Source' : 'View Source'}
          </Button>
          
          <Button 
            variant="outlined" 
            size="small" 
            onClick={() => setShowConsole(!showConsole)}
          >
            {showConsole ? 'Hide Console' : 'View Console'}
          </Button>
        </Box>
        
        <Collapse in={showSource}>
          <Box 
            sx={{ 
              mt: 2, 
              p: 2, 
              bgcolor: '#f5f5f5', 
              borderRadius: 1,
              overflow: 'auto',
              maxHeight: '300px'
            }}
          >
            <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
              {htmlCode}
            </pre>
          </Box>
        </Collapse>
        
        <Collapse in={showConsole}>
          <Box 
            sx={{ 
              mt: 2, 
              p: 2, 
              bgcolor: '#000', 
              color: '#fff',
              borderRadius: 1,
              overflow: 'auto',
              maxHeight: '200px',
              fontFamily: 'monospace'
            }}
          >
            {consoleMessages.length === 0 ? (
              <Typography variant="body2" color="gray">No console output</Typography>
            ) : (
              consoleMessages.map((msg, idx) => (
                <Box key={idx} sx={{ 
                  mb: 0.5, 
                  color: msg.type === 'error' ? '#ff6b6b' : 
                         msg.type === 'warn' ? '#feca57' : 
                         msg.type === 'info' ? '#54a0ff' : '#fff'
                }}>
                  <span style={{ color: '#888', fontSize: '0.8em' }}>
                    {msg.timestamp.toLocaleTimeString()}: 
                  </span> {msg.content}
                </Box>
              ))
            )}
          </Box>
        </Collapse>

        {/* 尝试直接在div内渲染HTML (不执行脚本) */}
        <Typography variant="subtitle1" sx={{ mt: 2, mb: 1, fontWeight: 'bold' }}>
          Limited Preview (No Scripts):
        </Typography>
        <Box
          sx={{
            border: '1px solid #ddd',
            borderRadius: 1,
            p: 2,
            height: '60%',
            overflow: 'auto',
            bgcolor: '#fff'
          }}
          dangerouslySetInnerHTML={{ __html: htmlCode }}
        />
      </Paper>
    );
  }
  
  return (
    <Paper 
      elevation={3} 
      sx={{ 
        width, 
        minHeight: `${frameHeightPx + (showConsole && userConsent === true ? 220 : 0)}px`,
        overflow: 'hidden',
        borderRadius: '20px',
        my: 2,
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
        background: 'linear-gradient(180deg, rgba(255,252,246,0.96) 0%, rgba(247,242,234,0.94) 100%)',
        border: '1px solid rgba(125,184,162,0.18)',
        boxShadow: '0 18px 42px rgba(60,50,44,0.10)',
      }}
    >
      <Box
        sx={{
          px: 1.5,
          py: 1,
          borderBottom: '1px solid rgba(125,184,162,0.14)',
          background: 'linear-gradient(135deg, rgba(232,245,240,0.7), rgba(245,236,224,0.58))',
        }}
      >
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.35 }}>
          <Chip
            size="small"
            label="New Interaction"
            sx={{
              height: 22,
              bgcolor: 'rgba(125,184,162,0.18)',
              color: '#4f7669',
              fontWeight: 700,
              letterSpacing: '0.06em',
              border: '1px solid rgba(125,184,162,0.24)',
            }}
          />
          <Typography variant="caption" sx={{ color: '#8a7e74', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            Premium story artifact
          </Typography>
        </Stack>
        <Typography variant="caption" sx={{ color: '#5a7a6e', fontWeight: 700, letterSpacing: '0.09em', textTransform: 'uppercase' }}>
          Interactive Story Moment
        </Typography>
        <Typography variant="body2" sx={{ color: '#6f675f', mt: 0.25 }}>
          A tactile scene artifact generated for this story beat. Open it when you are ready to interact with the scene itself.
        </Typography>
      </Box>

      {/* Close button */}
      <IconButton
        size="small"
        sx={{ position: 'absolute', top: 10, right: 10, zIndex: 10, bgcolor: 'rgba(255,255,255,0.6)' }}
        onClick={() => {
          setDismissed(true);
          clearInteractiveElement();
        }}
        aria-label="Close interactive element"
      >
        <CloseIcon fontSize="small" />
      </IconButton>
      
      {/* 根据用户同意状态显示不同内容 */}
      {userConsent === null && renderConsentPrompt()}
      {userConsent === false && renderRejectedView()}
      
      <Box 
        ref={containerRef}
        sx={{ 
          width: '100%', 
          minHeight: `${frameHeightPx}px`,
          overflow: 'hidden',
          transition: 'min-height 0.3s ease',
          // 如果用户尚未同意，则隐藏内容
          display: userConsent === true ? 'block' : 'none'
        }}
      />
      
      {userConsent === true && (
        <>
          <Box sx={{ p: 1, borderTop: '1px solid #eee' }}>
            <Button 
              variant="text" 
              size="small" 
              onClick={() => setShowConsole(!showConsole)}
              sx={{ textTransform: 'none' }}
            >
              {showConsole ? 'Hide Console' : 'Show Console'}
            </Button>
          </Box>
          
          <Collapse in={showConsole}>
            <Box 
              sx={{ 
                p: 1,
                bgcolor: '#000', 
                color: '#fff',
                overflow: 'auto',
                height: '180px',
                fontFamily: 'monospace'
              }}
            >
              {consoleMessages.length === 0 ? (
                <Typography variant="body2" color="gray" sx={{ p: 1 }}>No console output</Typography>
              ) : (
                consoleMessages.map((msg, idx) => (
                  <Box key={idx} sx={{ 
                    mb: 0.5, 
                    px: 1,
                    color: msg.type === 'error' ? '#ff6b6b' : 
                           msg.type === 'warn' ? '#feca57' : 
                           msg.type === 'info' ? '#54a0ff' : '#fff'
                  }}>
                    <span style={{ color: '#888', fontSize: '0.8em' }}>
                      {msg.timestamp.toLocaleTimeString()}: 
                    </span> {msg.content}
                  </Box>
                ))
              )}
            </Box>
          </Collapse>
        </>
      )}
    </Paper>
  );
};

export default InteractiveElement; 