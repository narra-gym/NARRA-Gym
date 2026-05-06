import axios from 'axios';
import { API_BASE_URL } from './apiBaseUrl';

const FRONTEND_ACCESS_HEADER = 'X-Storygame-Access';
const FRONTEND_ACCESS_BOOTSTRAP_URL = `${API_BASE_URL}/access/session`;

let frontendAccessToken: string | null = null;
let frontendAccessTokenPromise: Promise<string> | null = null;
let axiosInterceptorInstalled = false;

const shouldAttachFrontendAccess = (url?: string | null): boolean => {
  if (!url || url === FRONTEND_ACCESS_BOOTSTRAP_URL) {
    return false;
  }
  return url.startsWith(API_BASE_URL);
};

const requestFrontendAccessToken = async (): Promise<string> => {
  const response = await fetch(FRONTEND_ACCESS_BOOTSTRAP_URL, {
    method: 'GET',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to bootstrap frontend access session (${response.status})`);
  }

  const payload = await response.json();
  if (!payload?.csrf_token || typeof payload.csrf_token !== 'string') {
    throw new Error('Frontend access bootstrap did not return a valid CSRF token');
  }

  return payload.csrf_token;
};

export const ensureFrontendAccessToken = async (): Promise<string> => {
  if (frontendAccessToken) {
    return frontendAccessToken;
  }

  if (!frontendAccessTokenPromise) {
    frontendAccessTokenPromise = requestFrontendAccessToken()
      .then((token) => {
        frontendAccessToken = token;
        return token;
      })
      .catch((error) => {
        frontendAccessTokenPromise = null;
        throw error;
      });
  }

  return frontendAccessTokenPromise;
};

export const authorizedFetch = async (
  input: RequestInfo | URL,
  init: RequestInit = {}
): Promise<Response> => {
  const token = await ensureFrontendAccessToken();
  const inheritedHeaders =
    init.headers || (input instanceof Request ? input.headers : undefined);
  const headers = new Headers(inheritedHeaders);
  headers.set(FRONTEND_ACCESS_HEADER, token);

  return fetch(input, {
    ...init,
    credentials: 'include',
    headers,
  });
};

export const resetFrontendAccessForTests = (): void => {
  frontendAccessToken = null;
  frontendAccessTokenPromise = null;
};

if (!axiosInterceptorInstalled && (axios as any)?.interceptors?.request) {
  axios.interceptors.request.use(async (config) => {
    if (!shouldAttachFrontendAccess(config.url)) {
      return config;
    }

    const token = await ensureFrontendAccessToken();
    const headers = config.headers || {};
    (headers as any)[FRONTEND_ACCESS_HEADER] = token;
    config.headers = headers;
    config.withCredentials = true;
    return config;
  });
  axiosInterceptorInstalled = true;
}
