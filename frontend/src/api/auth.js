import apiClient from './client';

/**
 * Authenticate with email & password.
 * The response carries a short-lived access token in the body; the long-lived
 * refresh token is set by the API as an httpOnly cookie.
 * @param {string} email
 * @param {string} password
 * @returns {Promise<{ access_token: string, token_type: string, expires_in: number, user: Object }>}
 */
export async function loginApi(email, password) {
  return apiClient.post('/auth/login', { email, password });
}

/**
 * Exchange the httpOnly refresh cookie for a fresh access token.
 * Prefer `refreshSession` from ./client, which de-duplicates concurrent calls.
 * @returns {Promise<{ access_token: string, token_type: string, expires_in: number, user: Object }>}
 */
export async function refreshApi() {
  return apiClient.post('/auth/refresh');
}

/**
 * Clear the refresh cookie server-side.
 * @returns {Promise<{ message: string }>}
 */
export async function logoutApi() {
  return apiClient.post('/auth/logout');
}

/**
 * Retrieve authenticated user profile based on the active access token
 * @returns {Promise<{ user: Object }>}
 */
export async function getMeApi() {
  return apiClient.get('/auth/me');
}

/**
 * Ask the API to email a single-use password reset link. The response is the
 * same whether or not the address belongs to an account.
 * @param {string} email
 * @returns {Promise<{ message: string }>}
 */
export async function forgotPasswordApi(email) {
  return apiClient.post('/auth/forgot-password', { email });
}

/**
 * Check a reset link before showing the form. A dead link rejects with
 * INVALID_RESET_TOKEN, RESET_TOKEN_EXPIRED or RESET_TOKEN_USED.
 * @param {string} token
 * @returns {Promise<{ valid: boolean }>}
 */
export async function validateResetTokenApi(token) {
  return apiClient.get('/auth/reset-password/validate', {
    params: { token },
  });
}

/**
 * Consume the reset token and store the new password.
 * @param {string} token
 * @param {string} password
 * @returns {Promise<{ message: string }>}
 */
export async function resetPasswordApi(token, password) {
  return apiClient.post('/auth/reset-password', { token, password });
}
