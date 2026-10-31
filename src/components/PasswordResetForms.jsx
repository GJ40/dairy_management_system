import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  CheckCircle2,
  Loader2,
  Lock,
  Mail,
  Milk,
  ShieldAlert,
} from 'lucide-react';
import ErrorAlert from './ErrorAlert';

const TOKEN_ERRORS = {
  INVALID_RESET_TOKEN: 'This link is not valid. Request a new one below.',
  RESET_TOKEN_EXPIRED: 'This link has expired. Request a new one below.',
  RESET_TOKEN_USED: 'This link has already been used. Request a new one below.',
};

function tokenErrorMessage(error) {
  return (
    TOKEN_ERRORS[error?.code] ||
    error?.message ||
    'This link cannot be used. Request a new one below.'
  );
}

function Shell({ title, eyebrow, backTo, backLabel, children }) {
  return (
    <div className="flex min-h-screen flex-col justify-center bg-gradient-to-br from-emerald-950 via-slate-900 to-emerald-900 px-4 py-12 sm:px-6">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <Link
          to={backTo}
          className="mb-6 inline-flex items-center gap-2 text-xs font-medium text-emerald-300 transition hover:text-emerald-100"
        >
          <ArrowLeft className="h-4 w-4" /> {backLabel}
        </Link>

        <div className="mb-2 flex items-center justify-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-500 font-bold text-slate-950 shadow-lg shadow-emerald-500/20">
            <Milk className="h-7 w-7" />
          </div>
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-white">
              {title}
            </h1>
            <span className="block text-[11px] font-semibold uppercase tracking-widest text-emerald-400">
              {eyebrow}
            </span>
          </div>
        </div>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="rounded-2xl border border-slate-100 bg-white px-6 py-8 shadow-2xl sm:px-10">
          {children}
        </div>
      </div>
    </div>
  );
}

export function PasswordResetRequest({ audience, onSubmit, loginPath }) {
  const [email, setEmail] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);
  const [sentMessage, setSentMessage] = useState(null);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setFormError(null);

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setFormError('Enter the email address registered with your dairy.');
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await onSubmit(trimmedEmail);
      setSentMessage(
        response?.message ||
          'If an account exists for that email, we have sent a password reset link.'
      );
    } catch (error) {
      setFormError(
        error?.message || 'Could not send the reset link. Please try again.'
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Shell
      title="Forgot password"
      eyebrow={`${audience} password reset`}
      backTo={loginPath}
      backLabel="Back to sign in"
    >
      {sentMessage ? (
        <div className="text-center">
          <Mail className="mx-auto mb-3 h-12 w-12 text-emerald-600" />
          <h2 className="text-lg font-bold text-slate-900">Check your inbox</h2>
          <p className="mt-2 text-sm leading-relaxed text-slate-600">
            {sentMessage}
          </p>
          <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
            The link is single-use and expires shortly after it is sent.
          </p>
          <Link
            to={loginPath}
            className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700"
          >
            Back to sign in
          </Link>
        </div>
      ) : (
        <form className="space-y-5" onSubmit={handleSubmit}>
          <ErrorAlert error={formError} onDismiss={() => setFormError(null)} />

          <p className="text-sm leading-relaxed text-slate-600">
            Enter the email address for your {audience.toLowerCase()} account and
            we will send you a secure link to set a new password.
          </p>

          <div>
            <label
              htmlFor="forgot-email"
              className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
            >
              Email address
            </label>
            <div className="relative mt-1.5">
              <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                <Mail className="h-4 w-4" />
              </div>
              <input
                id="forgot-email"
                name="email"
                type="email"
                autoComplete="email"
                required
                disabled={isSubmitting}
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
                className="block w-full rounded-lg border border-slate-300 py-2.5 pl-9 pr-3 text-slate-900 transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500 sm:text-sm"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Sending...
              </>
            ) : (
              'Send reset link'
            )}
          </button>
        </form>
      )}
    </Shell>
  );
}

export function PasswordResetConfirm({
  audience,
  validateToken,
  resetPassword,
  loginPath,
  forgotPath,
}) {
  const [searchParams] = useSearchParams();
  const token = (searchParams.get('token') || '').trim();

  const [status, setStatus] = useState(token ? 'checking' : 'invalid');
  const [invalidReason, setInvalidReason] = useState(
    'This page must be opened from the reset link we emailed you.'
  );
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);

  useEffect(() => {
    if (!token) return undefined;

    let isActive = true;
    validateToken(token)
      .then(() => {
        if (isActive) setStatus('ready');
      })
      .catch((error) => {
        if (!isActive) return;
        setInvalidReason(tokenErrorMessage(error));
        setStatus('invalid');
      });

    return () => {
      isActive = false;
    };
  }, [token, validateToken]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setFormError(null);

    if (password.length < 8) {
      setFormError('Your password must be at least 8 characters long.');
      return;
    }
    if (password !== confirmPassword) {
      setFormError('The two passwords do not match.');
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await resetPassword(token, password);
      setSuccessMessage(
        response?.message ||
          'Your password has been updated. Sign in with your new password.'
      );
      setPassword('');
      setConfirmPassword('');
      setStatus('success');
    } catch (error) {
      if (TOKEN_ERRORS[error?.code]) {
        setInvalidReason(tokenErrorMessage(error));
        setStatus('invalid');
        return;
      }
      setFormError(
        error?.message || 'Could not update your password. Please try again.'
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Shell
      title="Set a new password"
      eyebrow={`${audience} password reset`}
      backTo={loginPath}
      backLabel="Back to sign in"
    >
      {status === 'checking' && (
        <div className="flex flex-col items-center py-8 text-slate-600">
          <Loader2 className="mb-3 h-8 w-8 animate-spin text-emerald-600" />
          <p className="text-sm">Checking your reset link...</p>
        </div>
      )}

      {status === 'invalid' && (
        <div className="text-center">
          <ShieldAlert className="mx-auto mb-3 h-12 w-12 text-rose-500" />
          <h2 className="text-lg font-bold text-slate-900">Link not usable</h2>
          <p className="mt-2 text-sm leading-relaxed text-slate-600">
            {invalidReason}
          </p>
          <Link
            to={forgotPath}
            className="mt-6 inline-flex w-full items-center justify-center rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700"
          >
            Request a new link
          </Link>
          <Link
            to={loginPath}
            className="mt-3 inline-block text-xs font-semibold text-slate-500 underline hover:text-slate-700"
          >
            Return to sign in
          </Link>
        </div>
      )}

      {status === 'success' && (
        <div className="text-center">
          <CheckCircle2 className="mx-auto mb-3 h-12 w-12 text-emerald-600" />
          <h2 className="text-lg font-bold text-slate-900">Password updated</h2>
          <p className="mt-2 text-sm leading-relaxed text-slate-600">
            {successMessage}
          </p>
          <Link
            to={loginPath}
            className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700"
          >
            Go to sign in
          </Link>
        </div>
      )}

      {status === 'ready' && (
        <form className="space-y-5" onSubmit={handleSubmit}>
          <ErrorAlert error={formError} onDismiss={() => setFormError(null)} />

          <p className="text-sm leading-relaxed text-slate-600">
            Choose a new password for your {audience.toLowerCase()} account. This
            link works once, so the password is saved immediately.
          </p>

          <div>
            <label
              htmlFor="reset-password"
              className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
            >
              New password
            </label>
            <div className="relative mt-1.5">
              <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                <Lock className="h-4 w-4" />
              </div>
              <input
                id="reset-password"
                name="password"
                type="password"
                autoComplete="new-password"
                required
                disabled={isSubmitting}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="At least 8 characters"
                className="block w-full rounded-lg border border-slate-300 py-2.5 pl-9 pr-3 text-slate-900 transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500 sm:text-sm"
              />
            </div>
          </div>

          <div>
            <label
              htmlFor="reset-confirm"
              className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
            >
              Confirm new password
            </label>
            <div className="relative mt-1.5">
              <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                <Lock className="h-4 w-4" />
              </div>
              <input
                id="reset-confirm"
                name="confirmPassword"
                type="password"
                autoComplete="new-password"
                required
                disabled={isSubmitting}
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                placeholder="Repeat the password"
                className="block w-full rounded-lg border border-slate-300 py-2.5 pl-9 pr-3 text-slate-900 transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500 sm:text-sm"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Updating...
              </>
            ) : (
              'Update password'
            )}
          </button>
        </form>
      )}
    </Shell>
  );
}
