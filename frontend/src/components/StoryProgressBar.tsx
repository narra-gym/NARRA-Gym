// import React, { useState, useEffect } from 'react';
// import { Box, LinearProgress, Typography, Paper } from '@mui/material';

// interface StoryProgressBarProps {
//   storyId: string;
//   onComplete?: () => void;
// }

// // 与 StoryContext 中保持一致，将来可提取到单独的 config 文件
// const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:11454';

// const StoryProgressBar: React.FC<StoryProgressBarProps> = ({ storyId, onComplete }) => {
//   const [progress, setProgress] = useState<number>(0);
//   const [currentStep, setCurrentStep] = useState<number>(0);
//   const [status, setStatus] = useState<string>('pending');
//   const [loading, setLoading] = useState<boolean>(true);

//   // 步骤描述
//   const stepDescriptions = [
//     'Preparing...',
//     'Creating story foundation...',
//     'Building story world...',
//     'Designing characters...',
//     'Outlining story structure...',
//     'Finalizing interactive elements...'
//   ];

//   useEffect(() => {
//     // 定期检查进度
//     const checkProgress = async () => {
//       try {
//         const response = await fetch(`${API_BASE_URL}/story/progress/${storyId}`);
//         if (!response.ok) {
//           throw new Error('Failed to fetch progress');
//         }
        
//         const data = await response.json();
//         setProgress(data.progress);
//         setCurrentStep(data.current_step);
//         setStatus(data.status);
//         setLoading(false);
        
//         // 如果生成完成，调用完成回调
//         if (data.progress === 100 && onComplete) {
//           onComplete();
//         }
//       } catch (error) {
//         console.error('Error fetching story progress:', error);
//         setLoading(false);
//       }
//     };

//     // 立即检查一次
//     checkProgress();
    
//     // 每2秒检查一次进度
//     const intervalId = setInterval(checkProgress, 2000);
    
//     // 清理定时器
//     return () => clearInterval(intervalId);
//   }, [storyId, onComplete]);

//   if (loading) {
//     return (
//       <Paper elevation={2} sx={{ p: 3, mb: 3, borderRadius: 2, background: 'rgba(255,255,255,0.8)', backdropFilter: 'blur(6px)' }}>
//         <Typography variant="h6" align="center" gutterBottom>
//         Ready to generate stories...
//         </Typography>
//         <LinearProgress sx={{
//           height: 10,
//           borderRadius: 5,
//           '& .MuiLinearProgress-bar': {
//             backgroundImage: 'linear-gradient(90deg, #6f7cff, #6bd3c0)'
//           }
//         }} />
//       </Paper>
//     );
//   }

//   return (
//     <Paper elevation={2} sx={{ p: 3, mb: 3, borderRadius: 2, background: 'rgba(255,255,255,0.8)', backdropFilter: 'blur(6px)' }}>
//       <Typography variant="h6" align="center" gutterBottom>
//         {currentStep > 0 && currentStep <= 5 
//           ? stepDescriptions[currentStep] 
//           : 'Generating story...'}
//       </Typography>
      
//       <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
//         <Box sx={{ width: '100%', mr: 1 }}>
//           <LinearProgress 
//             variant="determinate" 
//             value={progress} 
//             sx={{ 
//               height: 10, 
//               borderRadius: 5,
//               bgcolor: 'rgba(111,124,255,0.15)',
//               '& .MuiLinearProgress-bar': {
//                 backgroundImage: 'linear-gradient(90deg, #6f7cff, #6bd3c0)'
//               }
//             }}
//           />
//         </Box>
//         <Box sx={{ minWidth: 35 }}>
//           <Typography variant="body2" color="text.secondary">
//             {`${Math.round(progress)}%`}
//           </Typography>
//         </Box>
//       </Box>
      
//       <Box sx={{ mt: 2, display: 'flex', justifyContent: 'space-between' }}>
//         {[1, 2, 3, 4, 5].map((step) => (
//           <Box 
//             key={step} 
//             sx={{ 
//               display: 'flex', 
//               flexDirection: 'column', 
//               alignItems: 'center',
//               width: '20%'
//             }}
//           >
//             <Box 
//               sx={{ 
//                 width: 24, 
//                 height: 24, 
//                 borderRadius: '50%', 
//                 bgcolor: currentStep >= step ? 'primary.main' : 'grey.300',
//                 display: 'flex',
//                 justifyContent: 'center',
//                 alignItems: 'center',
//                 color: 'white',
//                 mb: 1,
//                 boxShadow: currentStep >= step ? '0 0 12px rgba(111,124,255,0.6)' : 'none'
//               }}
//             >
//               {step}
//             </Box>
//             <Typography 
//               variant="caption" 
//               align="center"
//               sx={{ 
//                 color: currentStep >= step ? 'text.primary' : 'text.secondary',
//                 fontWeight: currentStep === step ? 'bold' : 'normal',
//                 fontSize: '0.7rem'
//               }}
//             >
//               {['Foundation', 'World', 'Characters', 'Structure', 'Interactive'][step-1]}
//             </Typography>
//           </Box>
//         ))}
//       </Box>
//     </Paper>
//   );
// };

// export default StoryProgressBar; 



import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Box, Typography, Paper, Tooltip, Chip } from '@mui/material';
import CheckCircleRoundedIcon from '@mui/icons-material/CheckCircleRounded';
import AutoAwesomeRoundedIcon from '@mui/icons-material/AutoAwesomeRounded';
import { authorizedFetch } from '../utils/apiAccess';
import { API_BASE_URL } from '../utils/apiBaseUrl';

interface StoryProgressBarProps {
  storyId: string;
  onComplete?: () => void;
  compact?: boolean;              
}

const shimmer = `
@keyframes shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(200%); }
}
@keyframes gradientMove {
  0% { transform: translateX(0%); }
  100% { transform: translateX(-50%); }
}
@keyframes pulse {
  0% { box-shadow: 0 0 0px rgba(111,124,255,0.0); }
  50% { box-shadow: 0 0 18px rgba(111,124,255,0.55); }
  100% { box-shadow: 0 0 0px rgba(111,124,255,0.0); }
}
`;

// 线性插值，做“平滑进度”
function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

const StoryProgressBar: React.FC<StoryProgressBarProps> = ({ storyId, onComplete, compact }) => {
  const [serverProgress, setServerProgress] = useState<number>(0);  // 服务端真实进度
  const [progress, setProgress] = useState<number>(0);              // UI 平滑进度
  const [currentStep, setCurrentStep] = useState<number>(0);
  const [status, setStatus] = useState<string>('pending');          // pending | running | error | done
  const [loading, setLoading] = useState<boolean>(true);
  const completedOnce = useRef(false);

  const stepDescriptions = useMemo(
    () => [
      'Preparing...',
      'Creating story foundation...',
      'Building story world...',
      'Designing characters...',
      'Outlining story structure...',
      'Finalizing interactive elements...'
    ],
    []
  );

  // 轮询进度
  useEffect(() => {
    let cancelled = false;

    const checkProgress = async () => {
      try {
        const response = await authorizedFetch(`${API_BASE_URL}/story/progress/${storyId}`);
        if (!response.ok) throw new Error('Failed to fetch progress');
        const data = await response.json();

        if (cancelled) return;

        setServerProgress(Math.max(0, Math.min(100, data.progress ?? 0)));
        setCurrentStep(data.current_step ?? 0);
        setStatus(data.status ?? (data.progress >= 100 ? 'done' : 'running'));
        setLoading(false);

        if (data.progress >= 100 && !completedOnce.current) {
          completedOnce.current = true;
          onComplete?.();
        }
      } catch (err) {
        console.error('Error fetching story progress:', err);
        if (!cancelled) {
          setStatus('error');
          setLoading(false);
        }
      }
    };

    checkProgress();
    const intervalId = setInterval(checkProgress, 2000);
    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [storyId, onComplete]);
  
  useEffect(() => {
    let raf = 0;
    const animate = () => {
      setProgress((prev) => {
        // 状态为 error 时，停止动画
        if (status === 'error') return prev;
        const target = serverProgress;
        // 根据差距动态调整平滑系数：快靠近时更慢
        const t = target - prev > 10 ? 0.2 : 0.12;
        const next = lerp(prev, target, t);
        if (Math.abs(next - target) < 0.2) return target;
        return next;
      });
      raf = requestAnimationFrame(animate);
    };
    raf = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(raf);
  }, [serverProgress, status]);

  // 样式变量
  const barHeight = compact ? 14 : 24;
  const radius = compact ? 6 : 8;

  const StepPill: React.FC<{ i: number; label: string }> = ({ i, label }) => {
    const active = currentStep >= i;
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: 0, flex: 1 }}>
        <Box
          sx={{
            width: compact ? 22 : 26,
            height: compact ? 22 : 26,
            borderRadius: '999px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: active ? '#fff' : 'rgba(255,255,255,0.65)',
            fontSize: compact ? 12 : 13,
            fontWeight: 600,
            background: active
              ? 'linear-gradient(135deg, #6f7cff 0%, #6bd3c0 100%)'
              : 'rgba(255,255,255,0.12)',
            // border: '1px solid rgba(255,255,255,0.18)',
            transition: 'transform 200ms ease, box-shadow 200ms ease',
            ...(active && { animation: 'pulse 2s infinite' })
          }}
        >
          {active ? <CheckCircleRoundedIcon sx={{ fontSize: compact ? 16 : 18 }} /> : i}
        </Box>
        <Typography
          variant="caption"
          sx={{
            mt: 0.75,
            maxWidth: '100%',
            textAlign: 'center',
            color: active ? 'rgba(255,255,255,0.95)' : 'rgba(255,255,255,0.6)',
            fontWeight: currentStep === i ? 700 : 500,
            fontSize: compact ? '0.68rem' : '0.72rem',
            whiteSpace: 'nowrap',
            textOverflow: 'ellipsis',
            overflow: 'hidden'
          }}
        >
          {label}
        </Typography>
      </Box>
    );
  };

  const title =
    currentStep > 0 && currentStep <= 5
      ? stepDescriptions[currentStep]
      : status === 'done'
      ? 'Story ready!'
      : status === 'error'
      ? 'Something went wrong'
      : loading
      ? 'Ready to generate stories...'
      : 'Generating story...';

  return (
    <Paper
      elevation={2}
      sx={{
        p: compact ? 2 : 3,
        mb: 3,
        borderRadius: 3,
        background: 'linear-gradient(180deg, rgba(255,255,255,0.72), rgba(255,255,255,0.55))',
        backdropFilter: 'blur(10px)',
        border: '1px solid rgba(255,255,255,0.35)',
        overflow: 'hidden',
        position: 'relative'
      }}
    >
      {/* 注入关键帧 */}
      <style>{shimmer}</style>

      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: compact ? 1.25 : 1.75 }}>
        <Typography variant="h6" sx={{ fontSize: compact ? '1rem' : '1.1rem', fontWeight: 700 }}>
          {title}
        </Typography>
        {status === 'running' && <AutoAwesomeRoundedIcon sx={{ opacity: 0.7 }} />}
        {status === 'done' && (
          <Chip
            size="small"
            color="success"
            label="Completed"
            sx={{ ml: 'auto', fontWeight: 700, letterSpacing: 0.2 }}
          />
        )}
        {status === 'error' && (
          <Chip
            size="small"
            color="error"
            label="Error"
            sx={{ ml: 'auto', fontWeight: 700, letterSpacing: 0.2 }}
          />
        )}
      </Box>

      {/* 进度条容器（自定义轨道 + 扫光 + 渐变条） */}
      <Box sx={{ position: 'relative', width: '100%', mb: 1.25 }}>
        {/* 轨道 */}
        <Box
          sx={{
            height: barHeight,
            borderRadius: radius,
            background: 'linear-gradient(180deg, rgba(255,255,255,0.6) 0%, rgba(255,255,255,0.25) 100%)',
            border: 'none',
            // border: '1px solid rgba(111,124,255,0.25)'
            backdropFilter: 'blur(4px)', 
          }}
        />
        {/* 填充条 */}
        <Box
          // sx={{
          //   position: 'absolute',
          //   inset: 0,
          //   width: `${progress}%`,
          //   transition: 'width 220ms cubic-bezier(.2,.8,.2,1)',
          //   '&:after': {
          //     content: '""',
          //     display: 'block',
          //     height: '100%',
          //     borderRadius: radius,
          //     background:
          //       'linear-gradient(120deg, #6f7cff 0%, #6bd3c0 50%, #6f7cff 100%)',
          //     boxShadow: '0 2px 12px rgba(111,124,255,0.45)',
              
          //   }
          // }}
          sx={{
            position: 'absolute',
            inset: 0,
            width: `${progress}%`,
            transition: 'width 220ms cubic-bezier(.2,.8,.2,1)',
            overflow: 'hidden',        
            borderRadius: radius,     
            '&:after': {
              content: '""',
              display: 'block',
              height: '100%',
              width: '200%', // 比原寬一倍，才有移動空間
              borderRadius: radius,
              background: 'linear-gradient(120deg, #6f7cff, #6bd3c0, #6f7cff)',
              backgroundSize: '200% 100%',
              animation: 'gradientMove 3s linear infinite', // 👈 這裡讓漸層移動
              boxShadow: '0 2px 12px rgba(111,124,255,0.45)',
            }
          }}
        />
        {/* 扫光 */}
        {status !== 'error' && progress < 100 && (
          <Box
            sx={{
              position: 'absolute',
              inset: 0,
              overflow: 'hidden',
              borderRadius: radius,
              pointerEvents: 'none',
              '&::before': {
                content: '""',
                position: 'absolute',
                top: 0,
                left: 0,
                width: '35%',
                height: '100%',
                background:
                  'linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(255,255,255,.45) 50%, rgba(255,255,255,0) 100%)',
                transform: 'translateX(-100%)',
                animation: 'shimmer 2.2s infinite'
              }
            }}
          />
        )}
      </Box>

      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: compact ? 0.5 : 1 }}>
        <Typography variant="body2" color="text.secondary">
          {status === 'done' ? '100%' : `${Math.round(progress)}%`}
        </Typography>
        <Tooltip title="Smooth UI progress (syncs with server every 2s)">
          <Typography variant="caption" color="text.secondary">
            {status === 'running' ? 'Generating...' : status === 'done' ? 'Completed' : status === 'error' ? 'Error' : 'Pending'}
          </Typography>
        </Tooltip>
      </Box>

      {/* Step pills */}
      <Box
        sx={{
          mt: compact ? 1 : 1.5,
          display: 'grid',
          gridTemplateColumns: 'repeat(5, 1fr)',
          columnGap: compact ? 1 : 1.5,
          rowGap: 1
        }}
      >
        {['Foundation', 'World', 'Characters', 'Structure', 'Interactive'].map((label, idx) => (
          <StepPill key={label} i={idx + 1} label={label} />
        ))}
      </Box>
    </Paper>
  );
};

export default StoryProgressBar;
