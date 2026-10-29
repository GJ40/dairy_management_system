/**
 * Date, Currency, and Quantity formatters for Dairy Management System
 * Standardized to Asia/Kolkata timezone and INR currency.
 */

const TIMEZONE = 'Asia/Kolkata';

/**
 * Returns today's date string in YYYY-MM-DD format according to Asia/Kolkata timezone.
 * Avoids UTC offset bugs when users work in IST.
 */
export function getTodayKolkataDate() {
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
  return formatter.format(new Date());
}

/**
 * Format a date string or Date object to a readable date (e.g., "28 Oct 2026").
 * Safely handles "YYYY-MM-DD" strings without UTC timezone shift.
 */
export function formatDate(dateInput) {
  if (!dateInput) return '—';

  // If date-only string "YYYY-MM-DD", parse year, month, day directly
  if (typeof dateInput === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(dateInput)) {
    const [year, month, day] = dateInput.split('-').map(Number);
    const date = new Date(Date.UTC(year, month - 1, day, 12, 0, 0));
    return new Intl.DateTimeFormat('en-IN', {
      timeZone: TIMEZONE,
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    }).format(date);
  }

  const date = new Date(dateInput);
  if (isNaN(date.getTime())) return '—';

  return new Intl.DateTimeFormat('en-IN', {
    timeZone: TIMEZONE,
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(date);
}

/**
 * Format a date/timestamp to include time (e.g., "28 Oct 2026, 01:15 PM").
 */
export function formatDateTime(dateInput) {
  if (!dateInput) return '—';
  const date = new Date(dateInput);
  if (isNaN(date.getTime())) return '—';

  return new Intl.DateTimeFormat('en-IN', {
    timeZone: TIMEZONE,
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  }).format(date);
}

/**
 * Format a numeric amount to INR currency (₹).
 * Always outputs 2 decimal places. Does not recalculate backend values.
 */
export function formatCurrency(amount) {
  if (amount === null || amount === undefined || amount === '') return '₹0.00';
  const num = typeof amount === 'string' ? parseFloat(amount) : amount;
  if (isNaN(num)) return '₹0.00';

  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num);
}

/**
 * Format milk quantity in litres to two decimal places (e.g., "12.50 L").
 */
export function formatLitres(litres) {
  if (litres === null || litres === undefined || litres === '') return '0.00 L';
  const num = typeof litres === 'string' ? parseFloat(litres) : litres;
  if (isNaN(num)) return '0.00 L';

  return `${num.toFixed(2)} L`;
}
