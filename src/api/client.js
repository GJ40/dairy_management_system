import axios from 'axios';

// Storage keys
export const TOKEN_STORAGE_KEY = 'dairy_auth_token';
export const USER_STORAGE_KEY = 'dairy_auth_user';

const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export const apiClient = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

// Attach Authorization Bearer token to every request if available
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem(TOKEN_STORAGE_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor for consistent error normalization and 401 handling
apiClient.interceptors.response.use(
  (response) => {
    // If requesting a binary blob (e.g. PDF), return the full response or data with headers
    if (response.config.responseType === 'blob') {
      return response;
    }
    return response.data;
  },
  (error) => {
    const status = error.response?.status;
    const errorData = error.response?.data?.error || error.response?.data;

    const normalizedError = {
      status,
      code: errorData?.code || 'UNKNOWN_ERROR',
      message:
        errorData?.message ||
        error.message ||
        'An unexpected server error occurred.',
      details: errorData?.details || null,
      raw: error,
    };

    // Auto-clear invalid session on 401 Unauthorized (unless already on /login)
    if (status === 401) {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      localStorage.removeItem(USER_STORAGE_KEY);
      if (
        typeof window !== 'undefined' &&
        !window.location.pathname.startsWith('/login')
      ) {
        window.dispatchEvent(new Event('auth:unauthorized'));
      }
    }

    return Promise.reject(normalizedError);
  }
);

export default apiClient;
