import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useCustomerAuth } from '../../hooks/useCustomerAuth';
import ErrorAlert from '../../components/ErrorAlert';
import {
  Milk,
  KeyRound,
  Lock,
  Loader2,
  ArrowLeft,
  CheckCircle2,
} from 'lucide-react';

export function CustomerActivate() {
  const { activate } = useCustomerAuth();
  const [searchParams] = useSearchParams();
  const [token, setToken] = useState(searchParams.get('token') || '');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);
  const [activatedEmail, setActivatedEmail] = useState(null);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setFormError(null);

    const trimmedToken = token.trim();
    if (!trimmedToken) {
      setFormError('Enter the activation token from your dairy.');
      return;
    }
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
      const response = await activate(trimmedToken, password);
      setActivatedEmail(response?.account?.email || null);
    } catch (err) {
      const messages = {
        INVALID_ACTIVATION_TOKEN: 'This activation token is not valid.',
        ACTIVATION_TOKEN_EXPIRED:
          'This activation token has expired. Ask the dairy to issue a new one.',
        ALREADY_ACTIVATED:
          'This account is already activated. Sign in with your password.',
        WEAK_PASSWORD: err?.message || 'Please choose a stronger password.',
      };
      setFormError(
        messages[err?.code] || err?.message || 'Could not activate the account.'
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col justify-center bg-gradient-to-br from-emerald-950 via-slate-900 to-emerald-900 px-4 py-12 sm:px-6">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <Link
          to="/portal/login"
          className="mb-6 inline-flex items-center gap-2 text-xs font-medium text-emerald-300 transition hover:text-emerald-100"
        >
          <ArrowLeft className="h-4 w-4" /> Back to sign in
        </Link>

        <div className="mb-2 flex items-center justify-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-500 font-bold text-slate-950 shadow-lg shadow-emerald-500/20">
            <Milk className="h-7 w-7" />
          </div>
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-white">
              Activate your account
            </h1>
            <span className="block text-[11px] font-semibold uppercase tracking-widest text-emerald-400">
              One-time activation token
            </span>
          </div>
        </div>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="rounded-2xl border border-slate-100 bg-white px-6 py-8 shadow-2xl sm:px-10">
          {activatedEmail ? (
            <div className="text-center">
              <CheckCircle2 className="mx-auto mb-3 h-12 w-12 text-emerald-600" />
              <h2 className="text-lg font-bold text-slate-900">
                Account activated
              </h2>
              <p className="mt-1 text-sm text-slate-600">
                {activatedEmail} is ready. Sign in with the password you just
                set.
              </p>
              <Link
                to="/portal/login"
                className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700"
              >
                Go to sign in
              </Link>
            </div>
          ) : (
            <form className="space-y-5" onSubmit={handleSubmit}>
              <ErrorAlert
                error={formError}
                onDismiss={() => setFormError(null)}
              />

              <div>
                <label
                  htmlFor="activation-token"
                  className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
                >
                  Activation token
                </label>
                <div className="relative mt-1.5">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                    <KeyRound className="h-4 w-4" />
                  </div>
                  <input
                    id="activation-token"
                    type="text"
                    required
                    disabled={isSubmitting}
                    value={token}
                    onChange={(event) => setToken(event.target.value)}
                    placeholder="Paste the token from your dairy"
                    className="block w-full rounded-lg border border-slate-300 py-2.5 pl-9 pr-3 font-mono text-sm text-slate-900 transition placeholder:font-sans placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
              </div>

              <div>
                <label
                  htmlFor="activation-password"
                  className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
                >
                  New password
                </label>
                <div className="relative mt-1.5">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                    <Lock className="h-4 w-4" />
                  </div>
                  <input
                    id="activation-password"
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
                  htmlFor="activation-confirm"
                  className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
                >
                  Confirm password
                </label>
                <div className="relative mt-1.5">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                    <Lock className="h-4 w-4" />
                  </div>
                  <input
                    id="activation-confirm"
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
                    Activating...
                  </>
                ) : (
                  'Activate account'
                )}
              </button>

              <p className="text-[11px] leading-relaxed text-slate-500">
                Activation tokens are single-use and expire. If yours no longer
                works, contact the dairy to have a new one issued.
              </p>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

export default CustomerActivate;
