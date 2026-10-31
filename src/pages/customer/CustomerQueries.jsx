import { useCallback, useEffect, useState } from 'react';
import { toast } from 'react-toastify';
import {
  addMyQueryMessage,
  createMyQuery,
  getMyQueries,
  getMyQuery,
} from '../../api/customerPortal';
import { formatDateTime } from '../../utils/formatters';
import PageHeader from '../../components/PageHeader';
import LoadingSpinner from '../../components/LoadingSpinner';
import ErrorAlert from '../../components/ErrorAlert';
import EmptyState from '../../components/EmptyState';
import {
  MessagesSquare,
  Plus,
  X,
  Loader2,
  Send,
  RefreshCw,
  Lock,
} from 'lucide-react';

const CATEGORIES = ['billing', 'order', 'delivery', 'account', 'other'];
const STATUSES = ['open', 'in_progress', 'answered', 'closed'];

const STATUS_BADGE = {
  open: 'bg-amber-100 text-amber-800',
  in_progress: 'bg-sky-100 text-sky-800',
  answered: 'bg-emerald-100 text-emerald-800',
  closed: 'bg-slate-100 text-slate-600',
};

export function CustomerQueries() {
  const [queries, setQueries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [reloadKey, setReloadKey] = useState(0);

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    category: 'billing',
    subject: '',
    message: '',
  });
  const [formLoading, setFormLoading] = useState(false);

  const [detailId, setDetailId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const [reply, setReply] = useState('');
  const [sending, setSending] = useState(false);

  const loadQueries = useCallback(
    () =>
      getMyQueries({
        page: 1,
        page_size: 100,
        status: statusFilter === 'all' ? undefined : statusFilter,
      })
        .then((response) => {
          setQueries(response?.items || []);
          setError(null);
        })
        .catch((err) => {
          setError(err?.message || 'Failed to load your support queries.');
        })
        .finally(() => {
          setLoading(false);
        }),
    [statusFilter]
  );

  useEffect(() => {
    loadQueries();
  }, [loadQueries, reloadKey]);

  const reload = () => {
    setLoading(true);
    setError(null);
    setReloadKey((key) => key + 1);
  };

  const submitQuery = async (event) => {
    event.preventDefault();
    if (!form.subject.trim()) {
      toast.error('Add a short subject.');
      return;
    }
    if (form.message.trim().length < 1) {
      toast.error('Describe your question.');
      return;
    }

    setFormLoading(true);
    try {
      const response = await createMyQuery({
        category: form.category,
        subject: form.subject.trim(),
        message: form.message.trim(),
      });
      toast.success('Query sent to the dairy.');
      setShowForm(false);
      setForm({ category: 'billing', subject: '', message: '' });
      reload();
      if (response?.query?.id) {
        openDetail(response.query);
      }
    } catch (err) {
      toast.error(err?.message || 'Could not submit the query.');
    } finally {
      setFormLoading(false);
    }
  };

  const loadDetail = useCallback(async (queryId) => {
    setDetailLoading(true);
    setDetailError(null);
    try {
      const response = await getMyQuery(queryId);
      setDetail(response?.query || null);
    } catch (err) {
      setDetailError(err?.message || 'Failed to load this query.');
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const openDetail = (query) => {
    setDetailId(query.id);
    setDetail(query);
    setReply('');
    loadDetail(query.id);
  };

  const closeDetail = () => {
    setDetailId(null);
    setDetail(null);
    setDetailError(null);
    setReply('');
  };

  const sendReply = async (event) => {
    event.preventDefault();
    const body = reply.trim();
    if (!body) {
      toast.error('Write a message first.');
      return;
    }
    setSending(true);
    try {
      await addMyQueryMessage(detailId, body);
      setReply('');
      toast.success('Message sent.');
      await loadDetail(detailId);
      reload();
    } catch (err) {
      toast.error(err?.message || 'Could not send the message.');
    } finally {
      setSending(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Support"
        subtitle="Ask the dairy about a bill, an order or your account."
      >
        <div className="flex gap-2">
          <button
            type="button"
            onClick={reload}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            type="button"
            onClick={() => {
              setForm({ category: 'billing', subject: '', message: '' });
              setShowForm(true);
            }}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700"
          >
            <Plus className="h-4 w-4" /> New query
          </button>
        </div>
      </PageHeader>

      {showForm && (
        <form
          onSubmit={submitQuery}
          className="mb-6 rounded-2xl border border-emerald-100 bg-white p-5 shadow-sm"
        >
          <div className="mb-4 flex items-start justify-between">
            <div>
              <h2 className="text-sm font-bold text-slate-900">Raise a query</h2>
              <p className="text-xs text-slate-500">
                The dairy team replies in this thread — no email needed.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              aria-label="Cancel new query"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label
                htmlFor="query-category"
                className="block text-xs font-semibold uppercase tracking-wider text-slate-600"
              >
                Category
              </label>
              <select
                id="query-category"
                value={form.category}
                disabled={formLoading}
                onChange={(event) =>
                  setForm({ ...form, category: event.target.value })
                }
                className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm capitalize focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500"
              >
                {CATEGORIES.map((category) => (
                  <option key={category} value={category}>
                    {category}
                  </option>
                ))}
              </select>
            </div>
            <div className="sm:col-span-2">
              <label
                htmlFor="query-subject"
                className="block text-xs font-semibold uppercase tracking-wider text-slate-600"
              >
                Subject
              </label>
              <input
                id="query-subject"
                type="text"
                required
                maxLength={200}
                disabled={formLoading}
                value={form.subject}
                onChange={(event) =>
                  setForm({ ...form, subject: event.target.value })
                }
                placeholder="e.g. Question about my October invoice"
                className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500"
              />
            </div>
          </div>

          <div className="mt-4">
            <label
              htmlFor="query-message"
              className="block text-xs font-semibold uppercase tracking-wider text-slate-600"
            >
              Message
            </label>
            <textarea
              id="query-message"
              rows={4}
              required
              maxLength={2000}
              disabled={formLoading}
              value={form.message}
              onChange={(event) =>
                setForm({ ...form, message: event.target.value })
              }
              placeholder="Tell us what you need help with…"
              className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500"
            />
          </div>

          <div className="mt-4 flex justify-end border-t border-slate-100 pt-4">
            <button
              type="submit"
              disabled={formLoading}
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-60"
            >
              {formLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Sending…
                </>
              ) : (
                'Send query'
              )}
            </button>
          </div>
        </form>
      )}

      <div className="mb-5 flex flex-wrap gap-2">
        {['all', ...STATUSES].map((status) => (
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

      {loading ? (
        <LoadingSpinner message="Loading your queries…" />
      ) : error ? (
        <ErrorAlert message={error} onRetry={reload} />
      ) : queries.length === 0 ? (
        <EmptyState
          icon={MessagesSquare}
          title="No support queries"
          description="Questions you raise with the dairy will appear here with replies."
        />
      ) : (
        <div className="divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          {queries.map((query) => (
            <button
              key={query.id}
              type="button"
              onClick={() => openDetail(query)}
              className="flex w-full flex-wrap items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-slate-50"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-slate-800">
                  {query.subject}
                </p>
                <p className="mt-0.5 text-xs text-slate-500">
                  <span className="font-mono">{query.query_no}</span> ·{' '}
                  <span className="capitalize">{query.category}</span> · updated{' '}
                  {formatDateTime(query.last_message_at || query.updated_at)}
                </p>
              </div>
              <span
                className={`rounded-full px-2 py-0.5 text-[11px] font-semibold capitalize ${
                  STATUS_BADGE[query.status] || 'bg-slate-100 text-slate-600'
                }`}
              >
                {query.status.replace('_', ' ')}
              </span>
            </button>
          ))}
        </div>
      )}

      {detailId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="customer-query-title"
            className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
          >
            <div className="flex items-start justify-between border-b border-slate-100 p-5">
              <div className="min-w-0">
                <h2
                  id="customer-query-title"
                  className="truncate text-base font-bold text-slate-900"
                >
                  {detail?.subject || 'Query'}
                </h2>
                <p className="mt-1 text-xs text-slate-500">
                  <span className="font-mono">{detail?.query_no}</span>
                  {detail && (
                    <>
                      {' '}
                      ·{' '}
                      <span className="capitalize">{detail.category}</span> ·{' '}
                      <span className="capitalize">
                        {detail.status.replace('_', ' ')}
                      </span>
                    </>
                  )}
                </p>
              </div>
              <button
                type="button"
                onClick={closeDetail}
                className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                aria-label="Close"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5">
              {detailLoading ? (
                <LoadingSpinner message="Loading conversation…" size="sm" />
              ) : detailError ? (
                <ErrorAlert message={detailError} />
              ) : (
                <div className="space-y-3">
                  {(detail?.messages || []).map((message) => {
                    const fromCustomer = message.sender_type === 'customer';
                    return (
                      <div
                        key={message.id}
                        className={`flex ${fromCustomer ? 'justify-end' : 'justify-start'}`}
                      >
                        <div
                          className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${
                            fromCustomer
                              ? 'bg-emerald-600 text-white'
                              : 'bg-slate-100 text-slate-800'
                          }`}
                        >
                          <p className="whitespace-pre-wrap break-words">
                            {message.body}
                          </p>
                          <p
                            className={`mt-1 text-[10px] ${
                              fromCustomer ? 'text-emerald-100' : 'text-slate-500'
                            }`}
                          >
                            {fromCustomer ? 'You' : 'Dairy team'} ·{' '}
                            {formatDateTime(message.created_at)}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="border-t border-slate-100 bg-slate-50 p-4">
              {detail?.status === 'closed' ? (
                <p className="flex items-center gap-2 text-xs font-medium text-slate-500">
                  <Lock className="h-3.5 w-3.5" /> This query is closed. Raise a
                  new query if you need more help.
                </p>
              ) : (
                <form onSubmit={sendReply} className="flex items-end gap-2">
                  <textarea
                    rows={2}
                    value={reply}
                    maxLength={2000}
                    disabled={sending}
                    onChange={(event) => setReply(event.target.value)}
                    placeholder="Write a reply…"
                    className="min-h-[44px] flex-1 resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500"
                  />
                  <button
                    type="submit"
                    disabled={sending}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2.5 text-xs font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-60"
                  >
                    {sending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Send className="h-4 w-4" />
                    )}
                    Send
                  </button>
                </form>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default CustomerQueries;
