import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCustomerAuth } from '../../hooks/useCustomerAuth';
import { getCustomerProfile } from '../../api/customerPortal';
import { formatCurrency, formatDateTime } from '../../utils/formatters';
import PageHeader from '../../components/PageHeader';
import LoadingSpinner from '../../components/LoadingSpinner';
import ErrorAlert from '../../components/ErrorAlert';
import {
  UserRound,
  Mail,
  Phone,
  MapPin,
  Droplets,
  LogOut,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';

export function CustomerProfile() {
  const { logout } = useCustomerAuth();
  const navigate = useNavigate();

  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  const load = useCallback(
    () =>
      getCustomerProfile()
        .then((response) => {
          setProfile(response);
          setError(null);
        })
        .catch((err) => {
          setError(err?.message || 'Failed to load your profile.');
        })
        .finally(() => {
          setLoading(false);
        }),
    []
  );

  useEffect(() => {
    load();
  }, [load, reloadKey]);

  const refresh = () => {
    setLoading(true);
    setError(null);
    setReloadKey((key) => key + 1);
  };

  const handleLogout = async () => {
    await logout();
    navigate('/portal/login', { replace: true });
  };

  const account = profile?.account;
  const customer = profile?.customer || account?.customer;

  return (
    <div>
      <PageHeader
        title="My Profile"
        subtitle="The contact details and rate your dairy has on file."
      >
        <button
          type="button"
          onClick={refresh}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </PageHeader>

      {loading ? (
        <LoadingSpinner message="Loading your profile…" />
      ) : error ? (
        <ErrorAlert message={error} onRetry={refresh} />
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-2">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50 text-emerald-700">
                <UserRound className="h-6 w-6" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-slate-900">
                  {customer?.name || 'Customer'}
                </h2>
                <p className="text-xs text-slate-500">Portal account holder</p>
              </div>
            </div>

            <dl className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <dt className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  <Mail className="h-3.5 w-3.5" /> Portal email
                </dt>
                <dd className="mt-1 break-words text-sm font-medium text-slate-800">
                  {account?.email || '—'}
                </dd>
              </div>
              <div>
                <dt className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  <Phone className="h-3.5 w-3.5" /> Phone
                </dt>
                <dd className="mt-1 text-sm font-medium text-slate-800">
                  {customer?.phone || '—'}
                </dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  <MapPin className="h-3.5 w-3.5" /> Delivery address
                </dt>
                <dd className="mt-1 text-sm font-medium text-slate-800">
                  {customer?.address || '—'}
                </dd>
              </div>
              <div>
                <dt className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  <Droplets className="h-3.5 w-3.5" /> Milk rate
                </dt>
                <dd className="mt-1 text-sm font-bold text-emerald-700">
                  {formatCurrency(customer?.rate_per_litre)}
                  <span className="font-semibold text-slate-400"> /L</span>
                </dd>
              </div>
              <div>
                <dt className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  Account status
                </dt>
                <dd className="mt-1 text-sm font-medium capitalize text-slate-800">
                  {account?.is_active ? 'Active' : 'Deactivated'}
                </dd>
              </div>
              <div>
                <dt className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  Activated
                </dt>
                <dd className="mt-1 text-sm text-slate-700">
                  {formatDateTime(account?.activated_at)}
                </dd>
              </div>
              <div>
                <dt className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  Last sign-in
                </dt>
                <dd className="mt-1 text-sm text-slate-700">
                  {formatDateTime(account?.last_login_at)}
                </dd>
              </div>
            </dl>

            <p className="mt-6 rounded-lg bg-slate-50 px-3 py-2 text-[11px] leading-relaxed text-slate-500">
              Name, phone, address and rate are maintained by dairy staff. Call
              the dairy if any detail needs correcting.
            </p>
          </section>

          <aside className="space-y-4">
            <div className="rounded-2xl border border-emerald-100 bg-emerald-50/60 p-5">
              <div className="flex items-center gap-2 text-emerald-800">
                <ShieldCheck className="h-4 w-4" />
                <h3 className="text-sm font-bold">Session security</h3>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-emerald-900">
                Your sign-in is protected by a short-lived access token and a
                secure refresh cookie. Signing out clears both on this device.
              </p>
              <button
                type="button"
                onClick={handleLogout}
                className="mt-4 inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-white transition hover:bg-slate-800"
              >
                <LogOut className="h-3.5 w-3.5" /> Sign out
              </button>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-5 text-xs text-slate-500">
              <p className="font-semibold text-slate-700">Need a change?</p>
              <p className="mt-1 leading-relaxed">
                Password changes and contact updates are handled by dairy staff
                in this release. Use the Support page to raise a request.
              </p>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}

export default CustomerProfile;
