import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'react-toastify';
import { useAuth } from '../../hooks/useAuth';
import {
  getCustomerOrders,
  getCustomerOrder,
  approveCustomerOrder,
  rejectCustomerOrder,
  fulfilCustomerOrder,
  cancelCustomerOrder,
} from '../../api/customerOrders';
import { getStock } from '../../api/stock';
import {
  getTodayKolkataDate,
  formatDate,
  formatDateTime,
  formatCurrency,
  formatLitres,
} from '../../utils/formatters';
import PageHeader from '../../components/PageHeader';
import EmptyState from '../../components/EmptyState';
import LoadingSpinner from '../../components/LoadingSpinner';
import ErrorAlert from '../../components/ErrorAlert';
import ConfirmModal from '../../components/ConfirmModal';
import {
  ClipboardList,
  Search,
  X,
  RefreshCw,
  Calendar,
  CheckCircle2,
  XCircle,
  Clock,
  Truck,
  Ban,
  AlertTriangle,
  Droplets,
  User,
  Mail,
} from 'lucide-react';

const STATUS_FILTERS = [
  'all',
  'submitted',
  'approved',
  'rejected',
  'cancelled',
  'fulfilled',
];

const STATUS_CONFIG = {
  submitted: { label: 'Submitted', color: 'bg-amber-100 text-amber-800', icon: Clock },
  approved: { label: 'Approved', color: 'bg-sky-100 text-sky-800', icon: CheckCircle2 },
  rejected: { label: 'Rejected', color: 'bg-rose-100 text-rose-800', icon: XCircle },
  cancelled: { label: 'Cancelled', color: 'bg-slate-100 text-slate-600', icon: Ban },
  fulfilled: { label: 'Fulfilled', color: 'bg-emerald-100 text-emerald-800', icon: Truck },
};

function StatusBadge({ status }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.submitted;
  const Icon = config.icon;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${config.color}`}>
      <Icon className="h-3 w-3" />
      {config.label}
    </span>
  );
}

export default function CustomerOrders() {
  const { isAdmin } = useAuth();
  const today = getTodayKolkataDate();

  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [search, setSearch] = useState('');

  const [detailId, setDetailId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const [availability, setAvailability] = useState(null);

  const [action, setAction] = useState(null);
  const [reason, setReason] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  // State is only updated from promise callbacks so the effect below does not
  // call setState synchronously (react-hooks/set-state-in-effect).
  const fetchOrders = useCallback(() => {
    const params = { page: 1, page_size: 100 };
    if (statusFilter !== 'all') params.status = statusFilter;
    if (fromDate) params.from = fromDate;
    if (toDate) params.to = toDate;
    return getCustomerOrders(params)
      .then((response) => {
        setOrders(response?.items || []);
        setError(null);
      })
      .catch((err) => {
        setError(err?.message || 'Failed to load customer orders.');
      })
      .finally(() => {
        setLoading(false);
      });
  }, [statusFilter, fromDate, toDate]);

  // User-triggered refetch: resets loading/error outside the effect body.
  const refreshOrders = () => {
    setLoading(true);
    setError(null);
    fetchOrders();
  };

  useEffect(() => {
    fetchOrders();
  }, [fetchOrders]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return orders;
    return orders.filter((order) => {
      const customer = order.customer?.name || '';
      const email = order.account_email || '';
      return (
        order.order_no?.toLowerCase().includes(query) ||
        customer.toLowerCase().includes(query) ||
        email.toLowerCase().includes(query)
      );
    });
  }, [orders, search]);

  const loadDetail = useCallback(async (orderId) => {
    setDetailLoading(true);
    setDetailError(null);
    setAvailability(null);
    try {
      const response = await getCustomerOrder(orderId);
      const order = response?.order || null;
      setDetail(order);
      if (!order) return;

      const [stockResult, reservedResult] = await Promise.allSettled([
        getStock(order.requested_date),
        getCustomerOrders({
          page: 1,
          page_size: 100,
          status: 'approved',
          from: order.requested_date,
          to: order.requested_date,
        }),
      ]);

      if (stockResult.status === 'fulfilled') {
        const reserved =
          reservedResult.status === 'fulfilled'
            ? (reservedResult.value?.items || []).reduce(
                (sum, row) => sum + Number(row.quantity_litres || 0),
                0
              )
            : null;
        const closing = Number(stockResult.value?.closing_stock);
        setAvailability({
          closing: Number.isFinite(closing) ? closing : null,
          reserved,
          available:
            Number.isFinite(closing) && reserved !== null
              ? closing - reserved
              : null,
        });
      }
    } catch (err) {
      setDetailError(err?.message || 'Failed to load this order.');
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const openDetail = (order) => {
    setDetailId(order.id);
    setDetail(order);
    loadDetail(order.id);
  };

  const closeDetail = () => {
    setDetailId(null);
    setDetail(null);
    setDetailError(null);
    setAvailability(null);
  };

  const openAction = (type, order) => {
    setReason('');
    setAction({ type, order });
  };

  const closeAction = () => {
    if (actionLoading) return;
    setAction(null);
    setReason('');
  };

  const refreshAll = async () => {
    await fetchOrders();
    if (detailId) loadDetail(detailId);
  };

  const runAction = async () => {
    if (!action || actionLoading) return;
    const { type, order } = action;
    const trimmed = reason.trim();

    if ((type === 'reject' || type === 'cancel') && trimmed.length < 3) {
      toast.error('Enter a reason of at least 3 characters.');
      return;
    }

    setActionLoading(true);
    try {
      if (type === 'approve') await approveCustomerOrder(order.id);
      if (type === 'fulfil') await fulfilCustomerOrder(order.id);
      if (type === 'reject') await rejectCustomerOrder(order.id, trimmed);
      if (type === 'cancel') await cancelCustomerOrder(order.id, trimmed);
      toast.success(`Order ${order.order_no} updated.`);
      setAction(null);
      setReason('');
      await refreshAll();
    } catch (err) {
      toast.error(err?.message || 'Could not update this order.');
    } finally {
      setActionLoading(false);
    }
  };

  const fulfilBlockedReason = (order) => {
    if (!order) return null;
    if (order.requested_date > today) {
      return 'This order cannot be fulfilled before its requested date.';
    }
    if (!isAdmin && order.requested_date !== today) {
      return 'Operators can only fulfil orders requested for today.';
    }
    return null;
  };

  const totalLitres = filtered.reduce(
    (sum, row) => sum + Number(row.quantity_litres || 0),
    0
  );

  return (
    <div>
      <PageHeader
        title="Customer Orders"
        subtitle="Approve, reject, fulfil or cancel customer portal milk orders."
      >
        <button
          type="button"
          onClick={refreshOrders}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </PageHeader>

      <div className="mb-5 flex flex-wrap gap-2">
        {STATUS_FILTERS.map((status) => (
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
            {status}
          </button>
        ))}
      </div>

      <div className="mb-5 flex flex-col gap-3 lg:flex-row">
        <div className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-slate-500" />
          <input
            type="date"
            value={fromDate}
            onChange={(event) => {
              setLoading(true);
              setFromDate(event.target.value);
            }}
            aria-label="Requested from date"
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
          />
          <span className="text-xs text-slate-400">to</span>
          <input
            type="date"
            value={toDate}
            onChange={(event) => {
              setLoading(true);
              setToDate(event.target.value);
            }}
            aria-label="Requested to date"
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
          />
        </div>
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search order no., customer or portal email…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
          />
        </div>
      </div>

      {!loading && !error && (
        <p className="mb-3 text-xs text-slate-500">
          {filtered.length} order{filtered.length === 1 ? '' : 's'} ·{' '}
          {formatLitres(totalLitres)} requested
        </p>
      )}

      {loading ? (
        <LoadingSpinner message="Loading customer orders…" />
      ) : error ? (
        <ErrorAlert message={error} onRetry={refreshOrders} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={ClipboardList}
          title="No customer orders found"
          description="Orders placed through the customer portal will appear here."
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  {['Order', 'Customer', 'Requested', 'Quantity', 'Rate', 'Total', 'Status', ''].map(
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
                {filtered.map((order) => (
                  <tr
                    key={order.id}
                    className="cursor-pointer transition-colors hover:bg-slate-50"
                    onClick={() => openDetail(order)}
                  >
                    <td className="px-4 py-3 font-mono text-xs font-bold text-emerald-700">
                      {order.order_no}
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-800">
                        {order.customer?.name || `Customer #${order.customer?.id ?? '—'}`}
                      </p>
                      <p className="text-xs text-slate-500">{order.account_email || '—'}</p>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                      {formatDate(order.requested_date)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 font-semibold text-sky-700">
                      {formatLitres(order.quantity_litres)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                      {formatCurrency(order.rate_snapshot)}/L
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 font-bold text-emerald-700">
                      {formatCurrency(order.estimated_total)}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={order.status} />
                    </td>
                    <td className="px-4 py-3 text-right text-xs font-semibold text-emerald-700">
                      View
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
            aria-labelledby="customer-order-title"
            className="flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
          >
            <div className="flex items-start justify-between border-b border-slate-100 p-5 sm:p-6">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 id="customer-order-title" className="font-mono text-lg font-bold text-slate-900">
                    {detail?.order_no || 'Order'}
                  </h2>
                  {detail && <StatusBadge status={detail.status} />}
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  Placed {formatDateTime(detail?.created_at)}
                </p>
              </div>
              <button
                type="button"
                onClick={closeDetail}
                className="rounded-lg p-1.5 transition hover:bg-slate-100"
                aria-label="Close order detail"
              >
                <X className="h-5 w-5 text-slate-500" />
              </button>
            </div>

            <div className="overflow-y-auto p-5 sm:p-6">
              {detailLoading ? (
                <LoadingSpinner message="Loading order detail…" />
              ) : detailError ? (
                <ErrorAlert message={detailError} onRetry={() => loadDetail(detailId)} />
              ) : detail ? (
                <>
                  <div className="mb-5 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
                      <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-slate-500">
                        <User className="h-3.5 w-3.5" /> Customer
                      </div>
                      <p className="font-semibold text-slate-800">{detail.customer?.name || '—'}</p>
                      <p className="text-xs text-slate-500">{detail.customer?.phone || 'No phone'}</p>
                      {detail.account_email && (
                        <p className="mt-1 flex items-center gap-1 text-xs text-slate-500">
                          <Mail className="h-3 w-3" /> {detail.account_email}
                        </p>
                      )}
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
                      <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-slate-500">
                        <Droplets className="h-3.5 w-3.5" /> Order
                      </div>
                      <p className="text-slate-700">
                        {formatLitres(detail.quantity_litres)} on {formatDate(detail.requested_date)}
                      </p>
                      <p className="text-xs text-slate-500">
                        {formatCurrency(detail.rate_snapshot)}/L ·{' '}
                        <span className="font-semibold text-slate-700">
                          {formatCurrency(detail.estimated_total)}
                        </span>
                      </p>
                    </div>
                  </div>

                  <div className="mb-5 grid grid-cols-3 gap-3">
                    <div className="rounded-xl border border-slate-200 p-3">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                        Closing stock
                      </p>
                      <p className="mt-1 font-bold text-slate-800">
                        {availability?.closing === null || availability?.closing === undefined
                          ? '—'
                          : formatLitres(availability.closing)}
                      </p>
                    </div>
                    <div className="rounded-xl border border-slate-200 p-3">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                        Reserved
                      </p>
                      <p className="mt-1 font-bold text-amber-700">
                        {availability?.reserved === null || availability?.reserved === undefined
                          ? '—'
                          : formatLitres(availability.reserved)}
                      </p>
                    </div>
                    <div className="rounded-xl border border-slate-200 p-3">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                        Available
                      </p>
                      <p className="mt-1 font-bold text-emerald-700">
                        {availability?.available === null || availability?.available === undefined
                          ? '—'
                          : formatLitres(availability.available)}
                      </p>
                    </div>
                  </div>

                  {detail.note && (
                    <div className="mb-5 rounded-xl border border-slate-200 bg-white p-3 text-sm">
                      <p className="mb-1 text-xs font-bold uppercase tracking-wide text-slate-500">
                        Customer note
                      </p>
                      <p className="text-slate-700">{detail.note}</p>
                    </div>
                  )}

                  {detail.reason && (
                    <div className="mb-5 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm">
                      <p className="mb-1 text-xs font-bold uppercase tracking-wide text-rose-600">
                        Reason
                      </p>
                      <p className="text-rose-800">{detail.reason}</p>
                    </div>
                  )}

                  <div className="mb-5">
                    <h3 className="mb-2 text-sm font-bold text-slate-800">Timeline</h3>
                    {detail.events?.length ? (
                      <ol className="space-y-2">
                        {detail.events.map((event, index) => (
                          <li
                            key={`${event.to_status}-${event.created_at}-${index}`}
                            className="flex items-start gap-3 rounded-lg border border-slate-100 bg-slate-50 p-3 text-sm"
                          >
                            <Clock className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
                            <div>
                              <p className="font-medium text-slate-700">
                                {event.from_status ? `${event.from_status} → ` : ''}
                                {event.to_status}
                                <span className="ml-2 text-xs font-normal text-slate-500">
                                  by {event.actor_type}
                                </span>
                              </p>
                              {event.reason && (
                                <p className="text-xs text-slate-500">{event.reason}</p>
                              )}
                              <p className="text-[11px] text-slate-400">
                                {formatDateTime(event.created_at)}
                              </p>
                            </div>
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <p className="text-sm text-slate-500">No events recorded.</p>
                    )}
                  </div>

                  {(detail.sale || detail.invoice) && (
                    <div className="grid gap-3 sm:grid-cols-2">
                      {detail.sale && (
                        <div className="rounded-xl border border-slate-200 p-4 text-sm">
                          <p className="mb-1 text-xs font-bold uppercase tracking-wide text-slate-500">
                            Sale
                          </p>
                          <p className="text-slate-700">
                            {formatLitres(detail.sale.litres)} ·{' '}
                            {formatCurrency(detail.sale.amount)}
                          </p>
                          <p className="text-xs text-slate-500">
                            {formatDate(detail.sale.sale_date)} · {detail.sale.payment_status}
                          </p>
                        </div>
                      )}
                      {detail.invoice && (
                        <div className="rounded-xl border border-slate-200 p-4 text-sm">
                          <p className="mb-1 text-xs font-bold uppercase tracking-wide text-slate-500">
                            Invoice
                          </p>
                          <p className="font-mono text-xs text-emerald-700">
                            {detail.invoice.invoice_no}
                          </p>
                          <p className="text-slate-700">
                            Total {formatCurrency(detail.invoice.total_amount)} · Balance{' '}
                            {formatCurrency(detail.invoice.balance)}
                          </p>
                        </div>
                      )}
                    </div>
                  )}

                  {detail.status === 'approved' && fulfilBlockedReason(detail) && (
                    <p className="mt-4 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                      {fulfilBlockedReason(detail)}
                    </p>
                  )}
                </>
              ) : null}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 bg-slate-50 p-4 sm:px-6">
              <button
                type="button"
                onClick={closeDetail}
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
              >
                Close
              </button>
              {detail && (
                <div className="flex flex-wrap gap-2">
                  {detail.status === 'submitted' && (
                    <>
                      <button
                        type="button"
                        onClick={() => openAction('reject', detail)}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-semibold text-rose-700 transition hover:bg-rose-100"
                      >
                        <XCircle className="h-4 w-4" /> Reject
                      </button>
                      <button
                        type="button"
                        onClick={() => openAction('approve', detail)}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700"
                      >
                        <CheckCircle2 className="h-4 w-4" /> Approve
                      </button>
                    </>
                  )}
                  {detail.status === 'approved' && (
                    <button
                      type="button"
                      onClick={() => openAction('fulfil', detail)}
                      disabled={Boolean(fulfilBlockedReason(detail))}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Truck className="h-4 w-4" /> Fulfil
                    </button>
                  )}
                  {(detail.status === 'submitted' || detail.status === 'approved') && (
                    <button
                      type="button"
                      onClick={() => openAction('cancel', detail)}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
                    >
                      <Ban className="h-4 w-4" /> Cancel order
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <ConfirmModal
        isOpen={action?.type === 'approve' || action?.type === 'fulfil'}
        title={action?.type === 'approve' ? 'Approve customer order?' : 'Fulfil customer order?'}
        message={
          action?.type === 'approve'
            ? `${action?.order?.order_no} will reserve ${formatLitres(action?.order?.quantity_litres)} for ${formatDate(action?.order?.requested_date)}.`
            : `This creates the sale and invoice for ${action?.order?.order_no}. This cannot be undone.`
        }
        confirmText={action?.type === 'approve' ? 'Approve' : 'Fulfil'}
        confirmVariant="primary"
        isLoading={actionLoading}
        onConfirm={runAction}
        onClose={closeAction}
      />

      {action && (action.type === 'reject' || action.type === 'cancel') && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-2xl bg-white shadow-2xl">
            <div className="flex items-start justify-between border-b border-slate-100 p-5">
              <div>
                <h2 className="font-bold text-slate-900">
                  {action.type === 'reject' ? 'Reject order' : 'Cancel order'}
                </h2>
                <p className="mt-1 text-xs text-slate-500">
                  {action.order?.order_no} · {action.order?.customer?.name}
                </p>
              </div>
              <button
                type="button"
                onClick={closeAction}
                className="rounded-lg p-1.5 hover:bg-slate-100"
                aria-label="Close"
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
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Explain why this order is being rejected or cancelled…"
                className="w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
              />
              <p className="text-xs text-slate-500">Minimum 3 characters, maximum 500.</p>
            </div>
            <div className="flex justify-end gap-3 border-t border-slate-100 p-4">
              <button
                type="button"
                onClick={closeAction}
                disabled={actionLoading}
                className="rounded-lg bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-200 disabled:opacity-50"
              >
                Keep order
              </button>
              <button
                type="button"
                onClick={runAction}
                disabled={actionLoading}
                className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-rose-700 disabled:opacity-60"
              >
                {actionLoading
                  ? 'Saving…'
                  : action.type === 'reject'
                    ? 'Reject order'
                    : 'Cancel order'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
