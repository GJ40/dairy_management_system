import { Link } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';

/**
 * Live countdown for the temporary sign-in pause.
 *
 * The text is built from the values the API returned (which themselves come
 * from LOGIN_COOLDOWN_MINUTES / LOGIN_COOLDOWN_THRESHOLD in the backend .env),
 * so changing the configured pause needs no frontend change.
 */
export function CooldownNotice({
  remainingSeconds,
  clock,
  pauseMinutes = null,
  resetHref = null,
}) {
  const totalSeconds = pauseMinutes ? pauseMinutes * 60 : 0;
  const progress =
    totalSeconds > 0
      ? Math.min(100, Math.max(0, (remainingSeconds / totalSeconds) * 100))
      : 0;

  return (
    <div
      role="alert"
      aria-live="polite"
      className="my-4 overflow-hidden rounded-lg border border-amber-200 bg-amber-50"
    >
      <div className="flex items-start gap-3 p-4">
        <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs font-bold uppercase tracking-wider text-amber-800">
              Sign-in paused
            </p>
            <span
              className="font-mono text-lg font-bold tabular-nums text-amber-900"
              aria-label={`${remainingSeconds} seconds remaining`}
            >
              {clock}
            </span>
          </div>
          <p className="mt-1 text-sm font-medium leading-relaxed text-amber-900">
            {`Too many incorrect attempts${
              pauseMinutes ? ` (${pauseMinutes}-minute pause)` : ''
            }. Try again when the timer reaches zero.`}
          </p>
          <p className="mt-1 text-xs text-amber-700">
            The remaining time is enforced by the server. You can reset your
            password instead of waiting.
          </p>
          {resetHref && (
            <Link
              to={resetHref}
              className="mt-2 inline-block text-xs font-semibold text-amber-800 underline underline-offset-2 hover:text-amber-950"
            >
              Reset your password
            </Link>
          )}
        </div>
      </div>
      {totalSeconds > 0 && (
        <div className="h-1 w-full bg-amber-100">
          <div
            className="h-1 bg-amber-500 transition-all duration-1000 ease-linear"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}
    </div>
  );
}

export default CooldownNotice;
