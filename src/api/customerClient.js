import axios from 'axios';

const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

// Customer sessions are completely separate from staff sessions: their own
// in-memory access token, their own httpOnly refresh cookie and their own
// refresh endpoint. A customer token is never attached to staff requests and
// vice versa.
let accessToken = null;
let authFailureHandler = null;

export function getCustomerAccessToken() {
  return accessToken;
}

export function setCustomerAccessToken(token) {
  accessToken = token || null;
}

export function setCustomerAuthFailureHandler(handler) {
  authFailureHandler = handler;
}

const CUSTOMER_AUTH_ENDPOINTS = [
  '/customer-auth/login',
  '/customer-auth/refresh',
  '/customer-auth/logout',
  '/customer-auth/activate',
  '/customer-auth/forgot-password',
  '/customer-auth/reset-password',
];

// Non-secret hint cookie set by POST /customer-auth/login, so a reload only
// attempts a refresh when a customer session actually exists.
const SESSION_HINT_COOKIE =
  import.meta.env.VITE_CUSTOMER_SESSION_HINT_COOKIE || 'dairy_customer_session';

export function hasCustomerSessionHint() {
  if (typeof document === 'undefined' || !document.cookie) return false;
  return document.cookie
    .split(';')
    .some((part) => part.trim() === `${SESSION_HINT_COOKIE}=1`);
}

function isCustomerAuthEndpoint(url = '') {
  return CUSTOMER_AUTH_ENDPOINTS.some((endpoint) => url.includes(endpoint));
}

export const customerClient = axios.create({
  baseURL,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

const refreshClient = axios.create({
  baseURL,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000,
});

function toPositiveInt(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? Math.ceil(parsed) : null;
}

function normalizeError(error) {
  const status = error.response?.status;
  const errorData = error.response?.data?.error || error.response?.data;

  // Same structured cooldown fields as the staff client, so the portal can
  // show the remaining pause after a 429.
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
  setCustomerAccessToken(null);
  if (authFailureHandler) {
    authFailureHandler();
    return;
  }
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('customer-auth:unauthorized'));
  }
}

let refreshPromise = null;

export function refreshCustomerSession() {
  if (!refreshPromise) {
    refreshPromise = refreshClient
      .post('/customer-auth/refresh')
      .then((response) => {
        const payload = response.data || {};
        const token = payload.access_token;
        if (!token) {
          throw new Error('Refresh response did not include an access token.');
        }
        setCustomerAccessToken(token);
        return {
          accessToken: token,
          account: payload.account || null,
          expiresIn: payload.expires_in,
        };
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

customerClient.interceptors.request.use(
  (config) => {
    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

customerClient.interceptors.response.use(
  (response) => {
    if (response.config.responseType === 'blob') {
      return response;
    }
    return response.data;
  },
  async (error) => {
    const originalRequest = error.config;
    const status = error.response?.status;

    if (
      status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      !isCustomerAuthEndpoint(originalRequest.url)
    ) {
      originalRequest._retry = true;
      try {
        const { accessToken: renewedToken } = await refreshCustomerSession();
        originalRequest.headers = originalRequest.headers || {};
        originalRequest.headers.Authorization = `Bearer ${renewedToken}`;
        return customerClient(originalRequest);
      } catch {
        handleAuthFailure();
        return Promise.reject(normalizeError(error));
      }
    }

    if (status === 401 && !isCustomerAuthEndpoint(originalRequest?.url)) {
      handleAuthFailure();
    }

    return Promise.reject(normalizeError(error));
  }
);

export default customerClient;
