import apiClient from './client';

/**
 * Authenticate with email & password
 * @param {string} email
 * @param {string} password
 * @returns {Promise<{ token: string, user: Object }>}
 */
export async function loginApi(email, password) {
  return apiClient.post('/auth/login', { email, password });
}

/**
 * Retrieve authenticated user profile based on active Bearer token
 * @returns {Promise<{ user: Object }>}
 */
export async function getMeApi() {
  return apiClient.get('/auth/me');
}
