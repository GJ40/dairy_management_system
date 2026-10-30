import { useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useCustomerAuth } from '../../hooks/useCustomerAuth';
import ErrorAlert from '../../components/ErrorAlert';
import {
  Milk,
  Mail,
  Lock,
  Eye,
  EyeOff,
  Loader2,
  ArrowLeft,
  KeyRound,
} from 'lucide-react';

export function CustomerLogin() {
  const { login, isAuthenticated, isLoading } = useCustomerAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  const from = location.state?.from?.pathname || '/portal';

  if (!isLoading && isAuthenticated) {
    return <Navigate to={from} replace />;
  }

  const handleSubmit = async (event) => {
    event.preventDefault();
    setFormError(null);

    const trimmedEmail = email.trim();
    if (!trimmedEmail || !password) {
      setFormError('Enter your portal email and password.');
      return;
    }

    setIsSubmitting(true);
    try {
      await login(trimmedEmail, password);
      navigate(from, { replace: true });
    } catch (err) {
      setFormError(
        err?.message ||
          'Invalid email or password. Please check your credentials.'
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col justify-center bg-gradient-to-br from-emerald-950 via-slate-900 to-emerald-900 px-4 py-12 sm:px-6">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <Link
          to="/"
          className="mb-6 inline-flex items-center gap-2 text-xs font-medium text-emerald-300 transition hover:text-emerald-100"
        >
          <ArrowLeft className="h-4 w-4" /> Back to public homepage
        </Link>

        <div className="mb-2 flex items-center justify-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-500 font-bold text-slate-950 shadow-lg shadow-emerald-500/20">
            <Milk className="h-7 w-7" />
          </div>
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-white">
              Customer Portal
            </h1>
            <span className="block text-[11px] font-semibold uppercase tracking-widest text-emerald-400">
              Milk orders, bills & support
            </span>
          </div>
        </div>
        <p className="mt-2 text-center text-xs text-slate-300">
          Sign in with the email address your dairy registered for you.
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="rounded-2xl border border-slate-100 bg-white px-6 py-8 shadow-2xl sm:px-10">
          <form className="space-y-5" onSubmit={handleSubmit}>
            <ErrorAlert
              error={formError}
              onDismiss={() => setFormError(null)}
            />

            <div>
              <label
                htmlFor="customer-email"
                className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
              >
                Portal email
              </label>
              <div className="relative mt-1.5">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                  <Mail className="h-4 w-4" />
                </div>
                <input
                  id="customer-email"
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

            <div>
              <label
                htmlFor="customer-password"
                className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
              >
                Password
              </label>
              <div className="relative mt-1.5">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                  <Lock className="h-4 w-4" />
                </div>
                <input
                  id="customer-password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  disabled={isSubmitting}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="••••••••••••"
                  className="block w-full rounded-lg border border-slate-300 py-2.5 pl-9 pr-10 text-slate-900 transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500 sm:text-sm"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((value) => !value)}
                  className="absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400 transition hover:text-slate-600"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </button>
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
                  Signing in...
                </>
              ) : (
                'Sign in'
              )}
            </button>
          </form>

          <div className="mt-6 border-t border-slate-100 pt-5">
            <div className="flex items-start gap-3 rounded-lg border border-emerald-100 bg-emerald-50/70 p-3">
              <KeyRound className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700" />
              <div className="text-xs text-slate-600">
                <p className="font-semibold text-emerald-900">
                  First time here?
                </p>
                <p className="mt-0.5">
                  Use the activation link or token shared by the dairy to set
                  your password.
                </p>
                <Link
                  to="/portal/activate"
                  className="mt-1 inline-block font-semibold text-emerald-700 underline underline-offset-2 hover:text-emerald-900"
                >
                  Activate my account
                </Link>
              </div>
            </div>
            <p className="mt-3 text-center text-[11px] text-slate-400">
              Dairy staff?{' '}
              <Link to="/login" className="font-semibold text-slate-500 underline">
                Use the staff portal
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default CustomerLogin;
