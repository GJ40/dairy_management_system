import { AlertCircle, RefreshCw, X } from 'lucide-react';

export function ErrorAlert({ error, message, onRetry, onDismiss }) {
  const displayError = error ?? message;
  if (!displayError) return null;

  const errorMessage =
    typeof displayError === 'string'
      ? displayError
      : displayError?.message || 'An unexpected error occurred. Please try again.';

  const errorCode =
    typeof displayError === 'object' ? displayError?.code : null;

  return (
    <div
      role="alert"
      className="p-4 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 flex items-start justify-between gap-3 my-4"
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
        <div>
          {errorCode && (
            <span className="text-xs uppercase font-bold tracking-wider text-rose-700 block mb-0.5">
              {errorCode}
            </span>
          )}
          <p className="text-sm font-medium leading-relaxed">{errorMessage}</p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-2 inline-flex items-center gap-1.5 text-xs font-semibold text-rose-700 hover:text-rose-900 underline underline-offset-2"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Try again
            </button>
          )}
        </div>
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="text-rose-500 hover:text-rose-700 p-1 rounded-md transition"
          aria-label="Dismiss error"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}

export default ErrorAlert;
