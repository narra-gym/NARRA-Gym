import { API_BASE_URL } from './apiBaseUrl';

const ABSOLUTE_URL_PATTERN = /^(?:https?:)?\/\//i;

export const resolveAssetUrl = (path?: string) => {
  if (!path) return undefined;
  if (ABSOLUTE_URL_PATTERN.test(path) || path.startsWith('data:') || path.startsWith('blob:')) {
    return path;
  }

  const normalizedBase = API_BASE_URL.replace(/\/+$/, '');
  const normalizedPath = path.replace(/^\/+/, '');

  return normalizedBase ? `${normalizedBase}/${normalizedPath}` : `/${normalizedPath}`;
};
