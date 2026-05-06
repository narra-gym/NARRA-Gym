import { stripBenchmarkStateLeak } from './storyText';

describe('stripBenchmarkStateLeak', () => {
  it('removes benchmark state dumps after visible dialogue', () => {
    expect(stripBenchmarkStateLeak(
      '*She tightens her grip on the letter.*\n\n"We still have time."\nscene_shift: no\nact_advance: yes\nobjective: Leave now.',
    )).toBe('*She tightens her grip on the letter.*\n\n"We still have time."');
  });

  it('keeps normal story text untouched', () => {
    expect(stripBenchmarkStateLeak('"We should go before the rain gets worse."')).toBe('"We should go before the rain gets worse."');
  });
});
