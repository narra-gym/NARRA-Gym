const LOCAL_API_BASE_URL = 'http://localhost:11454';
const PROXIED_API_BASE_PATH = '/api';

const trimTrailingSlash = (value: string) => value.replace(/\/+$/, '');

const resolveRuntimeApiBaseUrl = () => {
  if (typeof window === 'undefined') {
    return LOCAL_API_BASE_URL;
  }

  const hostname = window.location.hostname;
  if (!hostname || hostname === 'localhost' || hostname === '127.0.0.1') {
    return LOCAL_API_BASE_URL;
  }

  return `${window.location.origin}${PROXIED_API_BASE_PATH}`;
};

export const API_BASE_URL = trimTrailingSlash(
  process.env.REACT_APP_API_BASE_URL || resolveRuntimeApiBaseUrl()
);
