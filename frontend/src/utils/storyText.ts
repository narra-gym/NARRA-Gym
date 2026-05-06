const BENCHMARK_STATE_KEYS = [
  'scene_shift',
  'act_advance',
  'ending_ready',
  'objective',
  'tension',
  'immediate_stakes',
  'latest_reveal',
  'relationship_shift',
  'emotional_beat',
  'location_status',
  'next_location',
];

const benchmarkStatePattern = new RegExp(
  `^\\s*(?:${BENCHMARK_STATE_KEYS.join('|')})\\s*:`,
  'im',
);

export const stripBenchmarkStateLeak = (content: string): string => {
  if (!content) {
    return '';
  }

  const match = benchmarkStatePattern.exec(content);
  if (!match) {
    return content.trim();
  }

  return content.slice(0, match.index).trim();
};
