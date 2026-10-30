import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'react-toastify';
import { useAuth } from '../../hooks/useAuth';
import {
  getCustomerQueries,
  getCustomerQuery,
  addCustomerQueryMessage,
  updateCustomerQueryStatus,
  assignCustomerQuery,
} from '../../api/customerQueries';
import { getUsers } from '../../api/users';
import { formatDateTime } from '../../utils/formatters';
import PageHeader from '../../components/PageHeader';
import EmptyState from '../../components/EmptyState';
import LoadingSpinner from '../../components/LoadingSpinner';
import ErrorAlert from '../../components/ErrorAlert';
import {
  MessagesSquare,
  Search,
  RefreshCw,
  X,
  Send,
  Lock,
  UserRound,
  ShieldCheck,
  Clock,
  ChevronRight,
} from 'lucide-react';

const STATUSES = ['open', 'in_progress', 'answered', 'closed'];
const CATEGORIES = ['billing', 'order', 'delivery', 'account', 'other'];

const STATUS_CONFIG = {
  open: { label: 'Open', color: 'bg-amber-100 text-amber-800' },
  in_progress: { label: 'In progress', color: 'bg-sky-100 text-sky-800' },
  answered: { label: 'Answered', color: 'bg-emerald-100 text-emerald-800' },
  closed: { label: 'Closed', color: 'bg-slate-100 text-slate-600' },
};

const OPERATOR_TRANSITIONS = {
  open: ['in_progress'],
  in_progress: ['open', 'answered'],
  answered: [],
  closed: [],
};

const ADMIN_TRANSITIONS = {
  open: ['in_progress', 'closed'],
  in_progress: ['open', 'answered', 'closed'],
  answered: ['closed'],
  closed: ['open'],
};

function StatusBadge({ status }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.open;
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${config.color}`}>
      {config.label}
    </span>
  );
}

function allowedTransitions(status, isAdmin) {
  return (isAdmin ? ADMIN_TRANSITIONS : OPERATOR_TRANSITIONS)[status] || [];
}

export default function CustomerQueries() {
  const { user, isAdmin } = useAuth();
  const userId = user?.id;

  const [queries, setQueries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [assignedTo, setAssignedTo] = useState('');
  const [search, setSearch] = useState('');

  const [staff, setStaff] = useState([]);
  const [detailId, setDetailId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);

  const [reply, setReply] = useState('');
  const [internal, setInternal] = useState(false);
  const [sending, setSending] = useState(false);

  const [statusTarget, setStatusTarget] = useState('');
  const [statusLoading, setStatusLoading] = useState(false);
  const [assignTarget, setAssignTarget] = useState('');
  const [assignLoading, setAssignLoading] = useState(false);

  // State is only updated from promise callbacks so the effect below does not
  // call setState synchronously (react-hooks/set-state-in-effect).
  const fetchQueries = useCallback(() => {
    const params = { page: 1, page_size: 100 };
    if (statusFilter !== 'all') params.status = statusFilter;
    if (categoryFilter !== 'all') params.category = categoryFilter;
    if (assignedTo === 'me') params.assigned_to = userId;
    else if (assignedTo) params.assigned_to = Number(assignedTo);
    return getCustomerQueries(params)
      .then((response) => {
        setQueries(response?.items || []);
        setError(null);
      })
      .catch((err) => {
        setError(err?.message || 'Failed to load support queries.');
      })
      .finally(() => {
        setLoading(false);
      });
  }, [statusFilter, categoryFilter, assignedTo, userId]);

  // User-triggered refetch: resets loading/error outside the effect body.
  const refreshQueries = () => {
    setLoading(true);
    setError(null);
    fetchQueries();
  };

  useEffect(() => {
    fetchQueries();
  }, [fetchQueries]);

  useEffect(() => {
    if (!isAdmin) return;
    getUsers({ page: 1, page_size: 100, is_active: true })
      .then((response) => setStaff(response?.items || []))
      .catch(() => setStaff([]));
  }, [isAdmin]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return queries;
    return queries.filter((row) => {
      const customer = row.customer?.name || '';
      return (
        row.query_no?.toLowerCase().includes(query) ||
        row.subject?.toLowerCase().includes(query) ||
        customer.toLowerCase().includes(query) ||
        (row.account_email || '').toLowerCase().includes(query)
      );
    });
  }, [queries, search]);

  const loadDetail = useCallback(async (queryId) => {
    setDetailLoading(true);
    setDetailError(null);
    try {
      const response = await getCustomerQuery(queryId);
      const row = response?.query || null;
      setDetail(row);
      setStatusTarget('');
      setAssignTarget(row?.assigned_to?.id ? String(row.assigned_to.id) : '');
      setReply('');
      setInternal(false);
    } catch (err) {
      setDetailError(err?.message || 'Failed to load this query.');
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const openDetail = (row) => {
    setDetailId(row.id);
    setDetail(row);
    loadDetail(row.id);
  };

  const closeDetail = () => {
    setDetailId(null);
    setDetail(null);
    setDetailError(null);
    setReply('');
    setInternal(false);
  };

  const refreshAll = async () => {
    await fetchQueries();
    if (detailId) loadDetail(detailId);
  };

  const sendReply = async (event) => {
    event.preventDefault();
    const body = reply.trim();
    if (!body) {
      toast.error('Enter a message first.');
      return;
    }
    setSending(true);
    try {
      await addCustomerQueryMessage(detailId, { message: body, is_internal: internal });
      toast.success(internal ? 'Internal note added.' : 'Reply sent.');
      setReply('');
      setInternal(false);
      await refreshAll();
    } catch (err) {
      toast.error(err?.message || 'Could not add the message.');
    } finally {
      setSending(false);
    }
  };

  const changeStatus = async () => {
    if (!statusTarget) return;
    setStatusLoading(true);
    try {
      await updateCustomerQueryStatus(detailId, statusTarget);
      toast.success('Query status updated.');
      setStatusTarget('');
      await refreshAll();
    } catch (err) {
      toast.error(err?.message || 'Could not change the query status.');
    } finally {
      setStatusLoading(false);
    }
  };

  const saveAssignment = async () => {
    setAssignLoading(true);
    try {
      await assignCustomerQuery(detailId, assignTarget ? Number(assignTarget) : null);
      toast.success('Query assignment updated.');
      await refreshAll();
    } catch (err) {
      toast.error(err?.message || 'Could not update the assignment.');
    } finally {
      setAssignLoading(false);
    }
  };

  const transitions = detail ? allowedTransitions(detail.status, isAdmin) : [];

  return (
    <div>
      <PageHeader
        title="Support Queries"
        subtitle="Reply to customer tickets, add internal notes, and manage status and assignment."
      >
        <button
          type="button"
          onClick={refreshQueries}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </PageHeader>

      <div className="mb-5 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => {
            setLoading(true);
            setStatusFilter('all');
          }}
          className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
            statusFilter === 'all'
              ? 'bg-emerald-600 text-white shadow-sm'
              : 'border border-slate-200 bg-white text-slate-600 hover:border-emerald-300'
          }`}
        >
          All
        </button>
        {STATUSES.map((status) => (
          <button
            key={status}
            type="button"
            onClick={() => {
              setLoading(true);
              setStatusFilter(status);
            }}
            className={`rounded-full px-3 py-1.5 text-xs font-semibold capitalize transition ${
              statusFilter === status
                ? 'bg-emerald-600 text-white shadow-sm'
                : 'border border-slate-200 bg-white text-slate-600 hover:border-emerald-300'
            }`}
          >
            {status.replace('_', ' ')}
          </button>
        ))}
      </div>

      <div className="mb-5 flex flex-col gap-3 lg:flex-row">
        <select
          value={categoryFilter}
          onChange={(event) => {
            setLoading(true);
            setCategoryFilter(event.target.value);
          }}
          aria-label="Filter by category"
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
        >
          <option value="all">All categories</option>
          {CATEGORIES.map((category) => (
            <option key={category} value={category}>
              {category}
            </option>
          ))}
        </select>

        {isAdmin ? (
          <select
            value={assignedTo}
            onChange={(event) => {
              setLoading(true);
              setAssignedTo(event.target.value);
            }}
            aria-label="Filter by assignee"
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
          >
            <option value="">All assignees</option>
            <option value="me">Assigned to me</option>
            {staff.map((member) => (
              <option key={member.id} value={member.id}>
                {member.full_name}
              </option>
            ))}
          </select>
        ) : (
          <button
            type="button"
            onClick={() => {
              setLoading(true);
              setAssignedTo(assignedTo === 'me' ? '' : 'me');
            }}
            className={`rounded-lg border px-3 py-2 text-sm font-medium transition ${
              assignedTo === 'me'
                ? 'border-emerald-300 bg-emerald-50 text-emerald-700'
                : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
            }`}
          >
            Assigned to me
          </button>
        )}

        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search ticket no., subject, customer or email…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
          />
        </div>
      </div>

      {loading ? (
        <LoadingSpinner message="Loading support queries…" />
      ) : error ? (
        <ErrorAlert message={error} onRetry={refreshQueries} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={MessagesSquare}
          title="No support queries found"
          description="Customer queries raised from the portal will appear here."
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  {['Ticket', 'Subject', 'Customer', 'Category', 'Status', 'Assignee', 'Updated', ''].map(
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
                {filtered.map((row) => (
                  <tr
                    key={row.id}
                    onClick={() => openDetail(row)}
                    className="cursor-pointer transition-colors hover:bg-slate-50"
                  >
                    <td className="px-4 py-3 font-mono text-xs font-bold text-emerald-700">
                      {row.query_no}
                    </td>
                    <td className="max-w-[240px] px-4 py-3">
                      <p className="truncate font-medium text-slate-800">{row.subject}</p>
                      <p className="text-xs text-slate-500">{row.account_email || '—'}</p>
                    </td>
                    <td className="px-4 py-3 text-slate-700">
                      {row.customer?.name || `Customer #${row.customer?.id ?? '—'}`}
                    </td>
                    <td className="px-4 py-3 capitalize text-slate-600">{row.category}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={row.status} />
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {row.assigned_to?.full_name || 'Unassigned'}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-500">
                      {formatDateTime(row.updated_at)}
                    </td>
                    <td className="px-4 py-3 text-slate-400">
                      <ChevronRight className="h-4 w-4" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {detailId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="query-thread-title"
            className="flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
          >
            <div className="flex items-start justify-between border-b border-slate-100 p-5 sm:p-6">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 id="query-thread-title" className="font-mono text-sm font-bold text-slate-900">
                    {detail?.query_no || 'Ticket'}
                  </h2>
                  {detail && <StatusBadge status={detail.status} />}
                  {detail && (
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold capitalize text-slate-600">
                      {detail.category}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-sm font-semibold text-slate-800">{detail?.subject}</p>
                <p className="text-xs text-slate-500">
                  {detail?.customer?.name} · {detail?.account_email || 'no portal email'} ·{' '}
                  {detail?.customer?.phone || 'no phone'}
                </p>
              </div>
              <button
                type="button"
                onClick={closeDetail}
                className="rounded-lg p-1.5 transition hover:bg-slate-100"
                aria-label="Close query"
              >
                <X className="h-5 w-5 text-slate-500" />
              </button>
            </div>

            <div className="overflow-y-auto p-5 sm:p-6">
              {detailLoading ? (
                <LoadingSpinner message="Loading conversation…" />
              ) : detailError ? (
                <ErrorAlert message={detailError} onRetry={() => loadDetail(detailId)} />
              ) : detail ? (
                <>
                  <div className="mb-5 space-y-3">
                    {(detail.messages || []).map((message) => {
                      const staffMessage = message.sender_type === 'staff';
                      const systemMessage = message.sender_type === 'system';
                      return (
                        <div
                          key={message.id}
                          className={`rounded-xl border p-3 text-sm ${
                            message.is_internal
                              ? 'border-amber-200 bg-amber-50'
                              : systemMessage
                                ? 'border-slate-200 bg-slate-50'
                                : staffMessage
                                  ? 'border-emerald-200 bg-emerald-50'
                                  : 'border-slate-200 bg-white'
                          }`}
                        >
                          <div className="mb-1 flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                            <span>
                              {systemMessage
                                ? 'System'
                                : staffMessage
                                  ? 'Staff'
                                  : 'Customer'}
                            </span>
                            {message.is_internal && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-amber-200 px-1.5 py-0.5 text-amber-900">
                                <Lock className="h-3 w-3" /> Internal
                              </span>
                            )}
                            <span className="font-normal normal-case text-slate-400">
                              {formatDateTime(message.created_at)}
                            </span>
                          </div>
                          <p className="whitespace-pre-wrap text-slate-700">{message.body}</p>
                        </div>
                      );
                    })}
                  </div>

                  <form onSubmit={sendReply} className="rounded-xl border border-slate-200 p-3">
                    <textarea
                      rows={3}
                      maxLength={5000}
                      value={reply}
                      onChange={(event) => setReply(event.target.value)}
                      placeholder="Write a reply to the customer or an internal note…"
                      className="w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
                    />
                    <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                      <label className="flex items-center gap-2 text-xs font-medium text-slate-600">
                        <input
                          type="checkbox"
                          checked={internal}
                          onChange={(event) => setInternal(event.target.checked)}
                          className="h-4 w-4 rounded text-amber-600"
                        />
                        Internal note (hidden from customer)
                      </label>
                      <button
                        type="submit"
                        disabled={sending}
                        className={`inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold text-white transition disabled:opacity-60 ${
                          internal
                            ? 'bg-amber-500 hover:bg-amber-600'
                            : 'bg-emerald-600 hover:bg-emerald-700'
                        }`}
                      >
                        <Send className="h-4 w-4" /> {sending ? 'Sending…' : internal ? 'Add note' : 'Send reply'}
                      </button>
                    </div>
                  </form>

                  <div className="mt-5 grid gap-4 border-t border-slate-100 pt-4 sm:grid-cols-2">
                    <div>
                      <p className="mb-1 flex items-center gap-1 text-xs font-bold uppercase tracking-wide text-slate-500">
                        <Clock className="h-3.5 w-3.5" /> Status
                      </p>
                      <div className="flex gap-2">
                        <select
                          value={statusTarget}
                          onChange={(event) => setStatusTarget(event.target.value)}
                          disabled={transitions.length === 0}
                          className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400 disabled:bg-slate-50 disabled:text-slate-400"
                        >
                          <option value="">
                            {transitions.length === 0 ? 'No transitions available' : 'Change status…'}
                          </option>
                          {transitions.map((status) => (
                            <option key={status} value={status}>
                              {status.replace('_', ' ')}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          onClick={changeStatus}
                          disabled={!statusTarget || statusLoading}
                          className="rounded-lg bg-slate-800 px-3 py-2 text-sm font-semibold text-white transition hover:bg-slate-900 disabled:opacity-50"
                        >
                          {statusLoading ? 'Saving…' : 'Update'}
                        </button>
                      </div>
                    </div>

                    {isAdmin ? (
                      <div>
                        <p className="mb-1 flex items-center gap-1 text-xs font-bold uppercase tracking-wide text-slate-500">
                          <ShieldCheck className="h-3.5 w-3.5" /> Assignment
                        </p>
                        <div className="flex gap-2">
                          <select
                            value={assignTarget}
                            onChange={(event) => setAssignTarget(event.target.value)}
                            className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
                          >
                            <option value="">Unassigned</option>
                            {staff.map((member) => (
                              <option key={member.id} value={member.id}>
                                {member.full_name} ({member.role})
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            onClick={saveAssignment}
                            disabled={assignLoading}
                            className="rounded-lg bg-amber-500 px-3 py-2 text-sm font-semibold text-white transition hover:bg-amber-600 disabled:opacity-60"
                          >
                            {assignLoading ? 'Saving…' : 'Assign'}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div>
                        <p className="mb-1 flex items-center gap-1 text-xs font-bold uppercase tracking-wide text-slate-500">
                          <UserRound className="h-3.5 w-3.5" /> Assignment
                        </p>
                        <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
                          {detail.assigned_to?.full_name || 'Unassigned'}
                          <span className="ml-1 text-xs text-slate-400">
                            (admin-managed)
                          </span>
                        </p>
                      </div>
                    )}
                  </div>
                </>
              ) : null}
            </div>

            <div className="flex justify-end border-t border-slate-100 bg-slate-50 p-4 sm:px-6">
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
    </div>
  );
}
