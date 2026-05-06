import { BenchmarkSessionDetail, BenchmarkSessionSummary } from '../types';

const STORAGE_PREFIX = 'emonest:benchmark-review-history:v2:';
const LEGACY_STORAGE_PREFIXES = ['emonest:benchmark-review-history:v1:'];
const MAX_CACHED_SESSIONS = 8;

interface LocalBenchmarkReviewCache {
  version: 1;
  updatedAt: string;
  sessions: BenchmarkSessionDetail[];
}

const getStorage = (): Storage | null => {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    return window.localStorage || null;
  } catch (error) {
    return null;
  }
};

const normalizeKeyPart = (value: unknown): string => (
  String(value ?? 'unknown')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'unknown'
);

export const getBenchmarkReviewCacheKey = (
  session?: Partial<BenchmarkSessionSummary> | null,
): string | null => {
  if (!session?.participant_id) {
    return null;
  }

  const mode = session.quick_test_mode ? 'quick' : session.blind_mode ? 'blind' : 'benchmark';
  const bucket = session.blind_invite_code
    || (session.blind_code !== null && session.blind_code !== undefined ? `code-${session.blind_code}` : null)
    || session.condition?.id
    || session.selected_model
    || 'default';

  return [
    STORAGE_PREFIX,
    normalizeKeyPart(mode),
    ':',
    normalizeKeyPart(session.participant_id),
    ':',
    normalizeKeyPart(bucket),
  ].join('');
};

const getSessionTimestamp = (detail: BenchmarkSessionDetail): number => {
  const raw = detail.session.completed_at || detail.session.started_at || '';
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? parsed : 0;
};

const sortSessions = (sessions: BenchmarkSessionDetail[]): BenchmarkSessionDetail[] => (
  [...sessions].sort((a, b) => {
    const aIndex = a.session.blind_session_index ?? -1;
    const bIndex = b.session.blind_session_index ?? -1;
    if (aIndex !== bIndex) {
      return bIndex - aIndex;
    }
    return getSessionTimestamp(b) - getSessionTimestamp(a);
  })
);

export const readLocalBenchmarkReviewHistory = (
  session?: Partial<BenchmarkSessionSummary> | null,
): BenchmarkSessionDetail[] => {
  const storage = getStorage();
  const key = getBenchmarkReviewCacheKey(session);
  if (!storage || !key) {
    return [];
  }

  try {
    LEGACY_STORAGE_PREFIXES.forEach(prefix => {
      Object.keys(storage)
        .filter(storageKey => storageKey.startsWith(prefix))
        .forEach(storageKey => storage.removeItem(storageKey));
    });
    const raw = storage.getItem(key);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as LocalBenchmarkReviewCache;
    return sortSessions(Array.isArray(parsed.sessions) ? parsed.sessions : []);
  } catch (error) {
    storage.removeItem(key);
    return [];
  }
};

const writeLocalBenchmarkReviewHistory = (
  session: Partial<BenchmarkSessionSummary> | null | undefined,
  sessions: BenchmarkSessionDetail[],
): BenchmarkSessionDetail[] => {
  const storage = getStorage();
  const key = getBenchmarkReviewCacheKey(session);
  const sortedSessions = sortSessions(sessions).slice(0, MAX_CACHED_SESSIONS);
  if (!storage || !key) {
    return sortedSessions;
  }

  const payload: LocalBenchmarkReviewCache = {
    version: 1,
    updatedAt: new Date().toISOString(),
    sessions: sortedSessions,
  };

  try {
    storage.setItem(key, JSON.stringify(payload));
  } catch (error) {
    const trimmed = sortedSessions.slice(0, Math.max(1, Math.floor(MAX_CACHED_SESSIONS / 2)));
    try {
      storage.setItem(key, JSON.stringify({ ...payload, sessions: trimmed }));
      return trimmed;
    } catch (retryError) {
      return sortedSessions;
    }
  }

  return sortedSessions;
};

export const upsertLocalBenchmarkReviewDetail = (
  detail: BenchmarkSessionDetail,
): BenchmarkSessionDetail[] => {
  const sessionId = detail.session.session_id;
  if (!sessionId) {
    return readLocalBenchmarkReviewHistory(detail.session);
  }

  const current = readLocalBenchmarkReviewHistory(detail.session);
  const next = [
    detail,
    ...current.filter(item => item.session.session_id !== sessionId),
  ];
  return writeLocalBenchmarkReviewHistory(detail.session, next);
};
