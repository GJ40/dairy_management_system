import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'react-toastify';
import {
  getPortalAccounts,
  getPortalAccount,
  provisionPortalAccount,
  reactivatePortalAccount,
  deactivatePortalAccount,
  resetPortalAccountActivation,
} from '../../api/portalAccounts';
import { getCustomers } from '../../api/customers';
import { formatDateTime } from '../../utils/formatters';
import PageHeader from '../../components/PageHeader';
import EmptyState from '../../components/EmptyState';
import LoadingSpinner from '../../components/LoadingSpinner';
import ErrorAlert from '../../components/ErrorAlert';
import {
  KeyRound,
  Search,
  RefreshCw,
  X,
  Plus,
  Copy,
  CheckCircle2,
  Clock,
  Ban,
  RotateCcw,
  Mail,
  UserRound,
  ShieldCheck,
} from 'lucide-react';

const FETCH_PAGE_SIZE = 100;

async function fetchAllCustomers() {
  const byId = new Map();
  let page = 1;
  let total = Infinity;
  while (byId.size < total && page <= 100) {
    const response = await getCustomers({ page, page_size: FETCH_PAGE_SIZE });
    const items = response?.items || [];
    items.forEach((customer) => byId.set(customer.id, customer));
    const responseTotal = Number(response?.total);
    total = Number.isFinite(responseTotal) ? responseTotal : byId.size;
    if (items.length === 0) break;
    page += 1;
  }
  return Array.from(byId.values());
}

function accountState(account) {
  if (!account.is_active) {
    return { label: 'Deactivated', color: 'bg-slate-100 text-slate-600', icon: Ban };
  }
  if (!account.activated_at) {
    return { label: 'Pending activation', color: 'bg-amber-100 text-amber-800', icon: Clock };
  }
  return { label: 'Active', color: 'bg-emerald-100 text-emerald-800', icon: CheckCircle2 };
}

function ActivationPanel({ activation, onClose }) {
  if (!activation) return null;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(activation.token);
      toast.success('Activation token copied.');
    } catch {
      toast.error('Could not copy automatically. Select the token and copy it manually.');
    }
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs">
      <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl">
        <div className="flex items-start justify-between border-b border-slate-100 p-5">
          <div>
            <h2 className="font-bold text-slate-900">Activation token issued</h2>
            <p className="mt-1 text-xs text-slate-500">
              Share this one-time token with the customer. It expires{' '}
              {formatDateTime(activation.expires_at)}.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 hover:bg-slate-100"
            aria-label="Close activation token"
          >
            <X className="h-5 w-5 text-slate-500" />
          </button>
        </div>
        <div className="space-y-3 p-5">
          <div className="break-all rounded-xl border border-slate-200 bg-slate-50 p-3 font-mono text-sm text-slate-800">
            {activation.token}
          </div>
          <button
            type="button"
            onClick={copy}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
          >
            <Copy className="h-4 w-4" /> Copy token
          </button>
          <p className="text-xs text-slate-500">
            The customer activates the account at{' '}
            <span className="font-mono text-slate-700">
              {`${window.location.origin}/portal/activate`}
            </span>{' '}
            by pasting this token and choosing a password. Share it privately —
            it works once.
          </p>
        </div>
        <div className="flex justify-end border-t border-slate-100 p-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

export default function PortalAccounts() {
  const [accounts, setAccounts] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [activeFilter, setActiveFilter] = useState('all');

  const [showProvision, setShowProvision] = useState(false);
  const [provisionForm, setProvisionForm] = useState({ customer_id: '', email: '' });
  const [provisionLoading, setProvisionLoading] = useState(false);
  const [activation, setActivation] = useState(null);

  const [detailId, setDetailId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);

  const [deactivateTarget, setDeactivateTarget] = useState(null);
  const [deactivateReason, setDeactivateReason] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  // State is only updated from promise callbacks so the effect below does not
  // call setState synchronously (react-hooks/set-state-in-effect).
  const fetchAccounts = useCallback(() => {
    const params = { page: 1, page_size: 100 };
    if (activeFilter === 'active') params.is_active = true;
    if (activeFilter === 'inactive') params.is_active = false;
    return getPortalAccounts(params)
      .then((response) => {
        setAccounts(response?.items || []);
        setError(null);
      })
      .catch((err) => {
        setError(err?.message || 'Failed to load portal accounts.');
      })
      .finally(() => {
        setLoading(false);
      });
  }, [activeFilter]);

  // User-triggered refetch: resets loading/error outside the effect body.
  const refreshAccounts = () => {
    setLoading(true);
    setError(null);
    fetchAccounts();
  };

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  useEffect(() => {
    fetchAllCustomers()
      .then(setCustomers)
      .catch(() => setCustomers([]));
  }, []);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return accounts.filter((account) => {
      if (activeFilter === 'active' && !(account.is_active && account.activated_at)) {
        return false;
      }
      if (activeFilter === 'pending' && !(account.is_active && !account.activated_at)) {
        return false;
      }
      if (activeFilter === 'inactive' && account.is_active) {
        return false;
      }
      if (!query) return true;
      const name = account.customer?.name || '';
      return (
        account.email?.toLowerCase().includes(query) ||
        name.toLowerCase().includes(query) ||
        account.customer?.phone?.toLowerCase().includes(query)
      );
    });
  }, [accounts, search, activeFilter]);

  const availableCustomers = useMemo(() => {
    const used = new Set(accounts.map((account) => account.customer_id));
    return customers.filter((customer) => !used.has(customer.id) && customer.is_active);
  }, [accounts, customers]);

  const activeCount = accounts.filter(
    (account) => account.is_active && account.activated_at
  ).length;
  const pendingCount = accounts.filter(
    (account) => account.is_active && !account.activated_at
  ).length;
  const inactiveCount = accounts.filter((account) => !account.is_active).length;

  const refreshAll = async () => {
    await fetchAccounts();
    if (detailId) loadDetail(detailId);
  };

  const loadDetail = useCallback(async (accountId) => {
    setDetailLoading(true);
    setDetailError(null);
    try {
      const response = await getPortalAccount(accountId);
      setDetail(
        response?.account
          ? { ...response.account, events: response.events || [] }
          : null
      );
    } catch (err) {
      setDetailError(err?.message || 'Failed to load this account.');
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const openDetail = (account) => {
    setDetailId(account.id);
    setDetail(null);
    loadDetail(account.id);
  };

  const closeDetail = () => {
    setDetailId(null);
    setDetail(null);
    setDetailError(null);
  };

  const openDeactivate = (account) => {
    setDeactivateTarget(account);
    setDeactivateReason('');
  };

  const closeDeactivate = () => {
    if (actionLoading) return;
    setDeactivateTarget(null);
    setDeactivateReason('');
  };

  const provision = async (event) => {
    event.preventDefault();
    if (!provisionForm.customer_id) {
      toast.error('Select a customer.');
      return;
    }
    setProvisionLoading(true);
    try {
      const response = await provisionPortalAccount({
        customer_id: Number(provisionForm.customer_id),
        email: provisionForm.email.trim(),
      });
      setShowProvision(false);
      setProvisionForm({ customer_id: '', email: '' });
      setActivation(response?.activation || null);
      toast.success('Portal account provisioned.');
      await fetchAccounts();
    } catch (err) {
      toast.error(err?.message || 'Could not provision this account.');
    } finally {
      setProvisionLoading(false);
    }
  };

  const runLifecycle = async (type, account) => {
    setActionLoading(true);
    try {
      if (type === 'reactivate') {
        const response = await reactivatePortalAccount(account.id);
        setActivation(response?.activation || null);
        toast.success('Account reactivated with a fresh activation token.');
      }
      if (type === 'reset') {
        const response = await resetPortalAccountActivation(account.id);
        setActivation(response?.activation || null);
        toast.success('Activation token reissued.');
      }
      await refreshAll();
    } catch (err) {
      toast.error(err?.message || 'Could not update this account.');
    } finally {
      setActionLoading(false);
    }
  };

  const deactivate = async () => {
    if (!deactivateTarget) return;
    const reason = deactivateReason.trim();
    if (reason.length < 3) {
      toast.error('Enter a reason of at least 3 characters.');
      return;
    }
    setActionLoading(true);
    try {
      await deactivatePortalAccount(deactivateTarget.id, reason);
      toast.success('Portal account deactivated.');
      setDeactivateTarget(null);
      setDeactivateReason('');
      await refreshAll();
    } catch (err) {
      toast.error(err?.message || 'Could not deactivate this account.');
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Portal Accounts"
        subtitle="Provision customer portal access and manage activation, deactivation and reset."
        badge="Admin Only"
      >
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={refreshAccounts}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            type="button"
            onClick={() => {
              setProvisionForm({ customer_id: '', email: '' });
              setShowProvision(true);
            }}
            className="inline-flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-amber-600"
          >
            <Plus className="h-4 w-4" /> Provision Account
          </button>
        </div>
      </PageHeader>

      <div className="mb-5 flex flex-wrap gap-2">
        {[
          { key: 'all', label: `All (${accounts.length})` },
          { key: 'active', label: `Active (${activeCount})` },
          { key: 'pending', label: `Pending (${pendingCount})` },
          { key: 'inactive', label: `Deactivated (${inactiveCount})` },
        ].map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => {
              setLoading(true);
              setActiveFilter(key);
            }}
            className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
              activeFilter === key
                ? 'bg-amber-500 text-white shadow-sm'
                : 'border border-slate-200 bg-white text-slate-600 hover:border-amber-300'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="relative mb-5">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input
          type="text"
          placeholder="Search by customer name, phone or portal email…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
        />
      </div>

      {loading ? (
        <LoadingSpinner message="Loading portal accounts…" />
      ) : error ? (
        <ErrorAlert message={error} onRetry={refreshAccounts} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={KeyRound}
          title="No portal accounts found"
          description="Provision portal access for a customer to get started."
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  {['Customer', 'Portal email', 'Status', 'Activated', 'Last login', ''].map(
                    (heading) => (
                      <th
                        key={heading}
                        className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-slate-500"
                      >
                        {heading}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filtered.map((account) => {
                  const state = accountState(account);
                  const StateIcon = state.icon;
                  return (
                    <tr key={account.id} className="transition-colors hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <p className="font-medium text-slate-800">
                          {account.customer?.name || `Customer #${account.customer_id}`}
                        </p>
                        <p className="text-xs text-slate-500">
                          {account.customer?.phone || 'No phone'}
                        </p>
                      </td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center gap-1.5 text-xs text-slate-600">
                          <Mail className="h-3.5 w-3.5 text-slate-400" /> {account.email}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${state.color}`}
                        >
                          <StateIcon className="h-3 w-3" /> {state.label}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-500">
                        {account.activated_at ? formatDateTime(account.activated_at) : '—'}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-500">
                        {account.last_login_at ? formatDateTime(account.last_login_at) : '—'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          onClick={() => openDetail(account)}
                          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-50"
                        >
                          Manage
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {showProvision && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-2xl bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-100 p-5">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-100">
                  <KeyRound className="h-5 w-5 text-amber-700" />
                </div>
                <div>
                  <h2 className="font-bold text-slate-900">Provision Portal Account</h2>
                  <p className="text-xs text-slate-500">Issue a single-use activation token</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowProvision(false)}
                className="rounded-lg p-1.5 hover:bg-slate-100"
                aria-label="Close provisioning form"
              >
                <X className="h-5 w-5 text-slate-500" />
              </button>
            </div>
            <form onSubmit={provision} className="space-y-4 p-5">
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-700">
                  Customer <span className="text-rose-500">*</span>
                </label>
                <select
                  required
                  value={provisionForm.customer_id}
                  onChange={(event) => {
                    setProvisionForm((current) => ({
                      ...current,
                      customer_id: event.target.value,
                    }));
                  }}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
                >
                  <option value="">Select a customer…</option>
                  {availableCustomers.map((customer) => (
                    <option key={customer.id} value={customer.id}>
                      {customer.name} {customer.phone ? `· ${customer.phone}` : ''}
                    </option>
                  ))}
                </select>
                {availableCustomers.length === 0 && (
                  <p className="mt-1 text-xs text-slate-500">
                    Every active customer already has a portal account.
                  </p>
                )}
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-700">
                  Portal email <span className="text-rose-500">*</span>
                </label>
                <input
                  required
                  type="email"
                  maxLength={150}
                  placeholder="customer@example.com"
                  value={provisionForm.email}
                  onChange={(event) =>
                    setProvisionForm((current) => ({ ...current, email: event.target.value }))
                  }
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
                />
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowProvision(false)}
                  disabled={provisionLoading}
                  className="rounded-lg bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-200 disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={provisionLoading}
                  className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-amber-600 disabled:opacity-60"
                >
                  {provisionLoading ? 'Provisioning…' : 'Provision Account'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {detailId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs">
          <div className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
            <div className="flex items-start justify-between border-b border-slate-100 p-5">
              <div>
                <h2 className="text-lg font-bold text-slate-900">
                  {detail?.customer?.name || 'Portal account'}
                </h2>
                <p className="text-xs text-slate-500">{detail?.email || '—'}</p>
                {detail && (
                  <div className="mt-2">
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${accountState(detail).color}`}
                    >
                      {accountState(detail).label}
                    </span>
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={closeDetail}
                className="rounded-lg p-1.5 hover:bg-slate-100"
                aria-label="Close account detail"
              >
                <X className="h-5 w-5 text-slate-500" />
              </button>
            </div>

            <div className="overflow-y-auto p-5">
              {detailLoading ? (
                <LoadingSpinner message="Loading account…" />
              ) : detailError ? (
                <ErrorAlert message={detailError} onRetry={() => loadDetail(detailId)} />
              ) : detail ? (
                <>
                  <div className="mb-5 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
                      <p className="mb-1 text-xs font-bold uppercase tracking-wide text-slate-500">
                        Customer
                      </p>
                      <p className="flex items-center gap-1.5 font-semibold text-slate-800">
                        <UserRound className="h-3.5 w-3.5 text-slate-400" />
                        {detail.customer?.name || '—'}
                      </p>
                      <p className="text-xs text-slate-500">{detail.customer?.phone || 'No phone'}</p>
                      <p className="text-xs text-slate-500">{detail.customer?.address || 'No address'}</p>
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
                      <p className="mb-1 text-xs font-bold uppercase tracking-wide text-slate-500">
                        Access
                      </p>
                      <p className="text-slate-700">
                        Activated: {detail.activated_at ? formatDateTime(detail.activated_at) : 'Not yet'}
                      </p>
                      <p className="text-slate-700">
                        Last login: {detail.last_login_at ? formatDateTime(detail.last_login_at) : 'Never'}
                      </p>
                    </div>
                  </div>

                  <div className="mb-5 flex flex-wrap gap-2">
                    {detail.is_active && !detail.activated_at && (
                      <button
                        type="button"
                        onClick={() => runLifecycle('reset', detail)}
                        disabled={actionLoading}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-60"
                      >
                        <RotateCcw className="h-4 w-4" /> Reissue activation token
                      </button>
                    )}
                    {detail.is_active ? (
                      <button
                        type="button"
                        onClick={() => openDeactivate(detail)}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-semibold text-rose-700 transition hover:bg-rose-100"
                      >
                        <Ban className="h-4 w-4" /> Deactivate
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => runLifecycle('reactivate', detail)}
                        disabled={actionLoading}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-60"
                      >
                        <ShieldCheck className="h-4 w-4" /> Reactivate
                      </button>
                    )}
                  </div>

                  <h3 className="mb-2 text-sm font-bold text-slate-800">Audit events</h3>
                  {detail.events?.length ? (
                    <ol className="space-y-2">
                      {detail.events.map((event) => (
                        <li
                          key={event.id}
                          className="rounded-lg border border-slate-100 bg-slate-50 p-3 text-sm"
                        >
                          <p className="font-medium capitalize text-slate-700">
                            {event.action.replace('_', ' ')}
                          </p>
                          {event.note && <p className="text-xs text-slate-500">{event.note}</p>}
                          <p className="text-[11px] text-slate-400">
                            {formatDateTime(event.created_at)}
                          </p>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="text-sm text-slate-500">No audit events recorded.</p>
                  )}
                </>
              ) : null}
            </div>

            <div className="flex justify-end border-t border-slate-100 bg-slate-50 p-4">
              <button
                type="button"
                onClick={closeDetail}
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {deactivateTarget && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-2xl bg-white shadow-2xl">
            <div className="flex items-start justify-between border-b border-slate-100 p-5">
              <div>
                <h2 className="font-bold text-slate-900">Deactivate portal account</h2>
                <p className="mt-1 text-xs text-slate-500">
                  {deactivateTarget.customer?.name} · {deactivateTarget.email}
                </p>
              </div>
              <button
                type="button"
                onClick={closeDeactivate}
                className="rounded-lg p-1.5 hover:bg-slate-100"
                aria-label="Close deactivation form"
              >
                <X className="h-5 w-5 text-slate-500" />
              </button>
            </div>
            <div className="space-y-3 p-5">
              <label className="block text-xs font-semibold text-slate-700">
                Reason <span className="text-rose-500">*</span>
              </label>
              <textarea
                rows={3}
                maxLength={500}
                value={deactivateReason}
                onChange={(event) => setDeactivateReason(event.target.value)}
                placeholder="Why is portal access being withdrawn?"
                className="w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-rose-400"
              />
              <p className="text-xs text-slate-500">
                The customer will be signed out and cannot log in again until reactivated.
              </p>
            </div>
            <div className="flex justify-end gap-3 border-t border-slate-100 p-4">
              <button
                type="button"
                onClick={closeDeactivate}
                disabled={actionLoading}
                className="rounded-lg bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-200 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={deactivate}
                disabled={actionLoading}
                className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-rose-700 disabled:opacity-60"
              >
                {actionLoading ? 'Deactivating…' : 'Deactivate account'}
              </button>
            </div>
          </div>
        </div>
      )}

      <ActivationPanel activation={activation} onClose={() => setActivation(null)} />
    </div>
  );
}
