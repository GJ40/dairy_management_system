import apiClient from './client';

/**
 * Fetch executive dashboard summary including herd, production, stock, sales,
 * and financials (financials masked for Operator on backend).
 * @param {string} [date] - ISO date YYYY-MM-DD in Asia/Kolkata
 * @param {Object} [options] - Optional axios request options (e.g. { signal })
 * @returns {Promise<Object>}
 */
export async function getDashboardReport(date, options = {}) {
  const params = date ? { date } : {};
  return apiClient.get('/reports/dashboard', { ...options, params });
}

/**
 * Fetch production summary across a date range.
 * @param {string} from - YYYY-MM-DD
 * @param {string} to - YYYY-MM-DD
 * @returns {Promise<Object>}
 */
export async function getProductionReport(from, to) {
  return apiClient.get('/reports/production', { params: { from, to } });
}

/**
 * Fetch profit analysis (Revenue, Expenses, Net Profit) - Admin only.
 * @param {string} from - YYYY-MM-DD
 * @param {string} to - YYYY-MM-DD
 * @returns {Promise<Object>}
 */
export async function getProfitReport(from, to) {
  return apiClient.get('/reports/profit', { params: { from, to } });
}
