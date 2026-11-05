import axios from 'axios';

const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

// Access token lives only in memory: it never touches localStorage, so an XSS
// payload cannot read it back out of storage. The refresh token is held by the
// browser in an httpOnly cookie that this code can neither read nor forge.
let accessToken = null;
let authFailureHandler = null;

export function getAccessToken() {
  return accessToken;
}

export function setAccessToken(token) {
  accessToken = token || null;
}

export function setAuthFailureHandler(handler) {
  authFailureHandler = handler;
}

const AUTH_ENDPOINTS = [
  '/auth/login',
  '/auth/refresh',
  '/auth/logout',
  '/auth/forgot-password',
  '/auth/reset-password',
];

// Set by the API on login and cleared on logout. It holds no secret — it only
// tells the app whether it is worth asking for a fresh access token, so a
// first-time visitor does not trigger a guaranteed 401 on every page load.
const SESSION_HINT_COOKIE =
  import.meta.env.VITE_SESSION_HINT_COOKIE || 'dairy_session';

export function hasSessionHint() {
  if (typeof document === 'undefined' || !document.cookie) return false;
  return document.cookie
    .split(';')
    .some((part) => part.trim() === `${SESSION_HINT_COOKIE}=1`);
}

function isAuthEndpoint(url = '') {
  return AUTH_ENDPOINTS.some((endpoint) => url.includes(endpoint));
}

export const apiClient = axios.create({
  baseURL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

// Separate instance for refreshes so the interceptors below cannot recurse.
const refreshClient = axios.create({
  baseURL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 15000,
});

function toPositiveInt(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? Math.ceil(parsed) : null;
}

function normalizeError(error) {
  const status = error.response?.status;
  const errorData = error.response?.data?.error || error.response?.data;

  // A 429 carries the remaining pause both as structured fields and as the
  // standard Retry-After header, so the form can run a countdown without
  // parsing the message text.
  const retryAfter = toPositiveInt(
    errorData?.retry_after_seconds ?? error.response?.headers?.['retry-after']
  );

  return {
    status,
    code: errorData?.code || 'UNKNOWN_ERROR',
    message:
      errorData?.message ||
      error.message ||
      'An unexpected server error occurred.',
    details: errorData?.details || null,
    retryAfterSeconds: retryAfter,
    cooldownMinutes: toPositiveInt(errorData?.cooldown_minutes),
    raw: error,
  };
}

function handleAuthFailure() {
  setAccessToken(null);
  if (authFailureHandler) {
    authFailureHandler();
    return;
  }
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('auth:unauthorized'));
  }
}

// Single-flight refresh: concurrent 401s share one POST /auth/refresh call.
let refreshPromise = null;

export function refreshSession() {
  if (!refreshPromise) {
    refreshPromise = refreshClient
      .post('/auth/refresh')
      .then((response) => {
        const payload = response.data || {};
        const token = payload.access_token;
        if (!token) {
          throw new Error('Refresh response did not include an access token.');
        }
        setAccessToken(token);
        return {
          accessToken: token,
          user: payload.user || null,
          expiresIn: payload.expires_in,
        };
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

// Attach the in-memory access token to every outgoing request.
apiClient.interceptors.request.use(
  (config) => {
    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

apiClient.interceptors.response.use(
  (response) => {
    // If requesting a binary blob (e.g. PDF), return the full response or data with headers
    if (response.config.responseType === 'blob') {
      return response;
    }
    return response.data;
  },
  async (error) => {
    const originalRequest = error.config;
    const status = error.response?.status;

    // A 401 means the 30-minute access token expired: mint a new one from the
    // refresh cookie and replay the original request transparently.
    if (
      status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      !isAuthEndpoint(originalRequest.url)
    ) {
      originalRequest._retry = true;
      try {
        const { accessToken: renewedToken } = await refreshSession();
        originalRequest.headers = originalRequest.headers || {};
        originalRequest.headers.Authorization = `Bearer ${renewedToken}`;
        return apiClient(originalRequest);
      } catch {
        handleAuthFailure();
        return Promise.reject(normalizeError(error));
      }
    }

    // Reaching here means the session is genuinely over: the replayed request
    // failed again, or there was nothing left to refresh with.
    if (status === 401 && !isAuthEndpoint(originalRequest?.url)) {
      handleAuthFailure();
    }

    return Promise.reject(normalizeError(error));
  }
);

export default apiClient;
