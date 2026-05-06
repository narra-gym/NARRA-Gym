// src/debug/ProgressHarness.tsx
import React from 'react';
import { Box, Paper, Slider, Button, Stack, Typography } from '@mui/material';
import StoryProgressBar from '../components/StoryProgressBar';

// 用一个“测试版 fetch 覆盖”来把 serverProgress 喂给组件
function installLocalProgressFeed(getServerProgress: () => {progress:number,current_step:number,status:string}) {
  const orig = window.fetch;
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString();
    if (url.includes('/story/progress/')) {
      const { progress, current_step, status } = getServerProgress();
      return new Response(JSON.stringify({ progress, current_step, status }), {
        status: 200, headers: { 'Content-Type': 'application/json' }
      });
    }
    return orig(input as any, init);
  };
}

export default function ProgressHarness() {
  const [serverP, setServerP] = React.useState(0);
  const [step, setStep] = React.useState(0);
  const [status, setStatus] = React.useState<'pending'|'running'|'error'|'done'>('pending');
  const [compact, setCompact] = React.useState(false);
  const storyId = 'debug-001';

  // 安装一次 fetch mock，把当前滑块值暴露给 StoryProgressBar 的轮询
  React.useEffect(() => {
    installLocalProgressFeed(() => ({ progress: serverP, current_step: step, status }));
  }, [serverP, step, status]);

  const bump = (d:number)=> setServerP(p=> Math.max(0, Math.min(100, p+d)));

  return (
    <Box sx={{ p: 6, minHeight: '100vh', bgcolor: '#f6f7fb' }}>
      <Paper sx={{ p: 3, maxWidth: 820, mx: 'auto' }}>
        <Typography variant="h6" fontWeight={700} mb={2}>StoryProgressBar — Debug Harness</Typography>

        <StoryProgressBar
          storyId={storyId}
          compact={compact}
          onComplete={() => console.log('[Harness] onComplete fired')}
        />

        <Stack direction="row" spacing={2} alignItems="center" mt={2}>
          <Typography variant="body2" sx={{ width: 120 }}>Server Progress</Typography>
          <Slider min={0} max={100} value={serverP} onChange={(_,v)=> setServerP(v as number)}
                  valueLabelDisplay="auto" sx={{ flex: 1 }} />
          <Button variant="outlined" onClick={()=> bump(+5)}>+5%</Button>
          <Button variant="outlined" onClick={()=> bump(+20)}>+20%</Button>
          <Button variant="outlined" onClick={()=> setServerP(100)}>100%</Button>
        </Stack>

        <Stack direction="row" spacing={2} alignItems="center" mt={2}>
          <Typography variant="body2" sx={{ width: 120 }}>Step</Typography>
          <Slider min={0} max={5} step={1} value={step} onChange={(_,v)=> setStep(v as number)}
                  valueLabelDisplay="auto" sx={{ flex: 1 }} />
          <Button onClick={()=> setStep(s=> Math.min(5, s+1))}>Next Step</Button>
          <Button onClick={()=> setStep(s=> Math.max(0, s-1))}>Prev Step</Button>
        </Stack>

        <Stack direction="row" spacing={1} mt={2}>
          <Button variant={status==='pending'?'contained':'outlined'} onClick={()=> setStatus('pending')}>pending</Button>
          <Button variant={status==='running'?'contained':'outlined'} onClick={()=> setStatus('running')}>running</Button>
          <Button variant={status==='error'?'contained':'outlined'} color="error" onClick={()=> setStatus('error')}>error</Button>
          <Button variant={status==='done'?'contained':'outlined'} color="success" onClick={()=> setStatus('done')}>done</Button>
          <Button onClick={()=> setCompact(c=>!c)}>{compact ? 'Full' : 'Compact'}</Button>
        </Stack>
      </Paper>
    </Box>
  );
}