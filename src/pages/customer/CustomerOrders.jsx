import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'react-toastify';
import { useCustomerAuth } from '../../hooks/useCustomerAuth';
import {
  cancelMyOrder,
  createMyOrder,
  getMyOrder,
  getMyOrders,
} from '../../api/customerPortal';
import {
  formatCurrency,
  formatDate,
  formatDateTime,
  formatLitres,
  getTodayKolkataDate,
} from '../../utils/formatters';
import PageHeader from '../../components/PageHeader';
import LoadingSpinner from '../../components/LoadingSpinner';
import ErrorAlert from '../../components/ErrorAlert';
import EmptyState from '../../components/EmptyState';
import {
  ClipboardList,
  Plus,
  X,
  Calendar,
  Droplets,
  Loader2,
  Ban,
  RefreshCw,
  Info,
} from 'lucide-react';

const STATUS_BADGE = {
  submitted: 'bg-amber-100 text-amber-800',
  approved: 'bg-sky-100 text-sky-800',
  rejected: 'bg-rose-100 text-rose-800',
  cancelled: 'bg-slate-100 text-slate-600',
  fulfilled: 'bg-emerald-100 text-emerald-800',
};

const STATUS_FILTERS = [
  'all',
  'submitted',
  'approved',
  'fulfilled',
  'rejected',
  'cancelled',
];

function addDays(isoDate, days) {
  const [year, month, day] = isoDate.split('-').map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function CustomerOrders() {
  const { customer } = useCustomerAuth();
  const today = getTodayKolkataDate();
  const latestDate = addDays(today, 14);

  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [reloadKey, setReloadKey] = useState(0);

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    quantity_litres: '',
    requested_date: today,
    note: '',
  });
  const [formLoading, setFormLoading] = useState(false);

  const [detailId, setDetailId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const [cancelReason, setCancelReason] = useState('');
  const [cancelLoading, setCancelLoading] = useState(false);

  const loadOrders = useCallback(
    () =>
      getMyOrders({
        page: 1,
        page_size: 100,
        status: statusFilter === 'all' ? undefined : statusFilter,
      })
        .then((response) => {
          setOrders(response?.items || []);
          setError(null);
        })
        .catch((err) => {
          setError(err?.message || 'Failed to load your orders.');
        })
        .finally(() => {
          setLoading(false);
        }),
    [statusFilter]
  );

  useEffect(() => {
    loadOrders();
  }, [loadOrders, reloadKey]);

  const reload = () => {
    setLoading(true);
    setError(null);
    setReloadKey((key) => key + 1);
  };

  const rate = Number(customer?.rate_per_litre || 0);
  const quantityValue = Number(form.quantity_litres);
  const estimate =
    Number.isFinite(quantityValue) && quantityValue > 0
      ? (Math.round(quantityValue * rate * 100) / 100).toFixed(2)
      : null;

  const submitOrder = async (event) => {
    event.preventDefault();
    const quantity = Number(form.quantity_litres);
    if (!Number.isFinite(quantity) || quantity <= 0) {
      toast.error('Enter the quantity in litres.');
      return;
    }
    if (!form.requested_date) {
      toast.error('Choose a delivery date.');
      return;
    }

    setFormLoading(true);
    try {
      await createMyOrder({
        quantity_litres: quantity,
        requested_date: form.requested_date,
        note: form.note.trim() || undefined,
      });
      toast.success('Order submitted for approval.');
      setShowForm(false);
      setForm({ quantity_litres: '', requested_date: today, note: '' });
      reload();
    } catch (err) {
      toast.error(err?.message || 'Could not place the order.');
    } finally {
      setFormLoading(false);
    }
  };

  const openDetail = (order) => {
    setDetailId(order.id);
    setDetail(order);
    setDetailError(null);
    setCancelReason('');
    setDetailLoading(true);
    getMyOrder(order.id)
      .then((response) => {
        setDetail(response?.order || null);
      })
      .catch((err) => {
        setDetailError(err?.message || 'Failed to load this order.');
      })
      .finally(() => {
        setDetailLoading(false);
      });
  };

  const closeDetail = () => {
    setDetailId(null);
    setDetail(null);
    setDetailError(null);
    setCancelReason('');
  };

  const cancelOrder = async () => {
    if (!detail) return;
    setCancelLoading(true);
    try {
      await cancelMyOrder(detail.id, cancelReason);
      toast.success('Order cancelled.');
      closeDetail();
      reload();
    } catch (err) {
      toast.error(err?.message || 'Could not cancel this order.');
    } finally {
      setCancelLoading(false);
    }
  };

  const filtered = useMemo(() => {
    if (statusFilter === 'all') return orders;
    return orders.filter((order) => order.status === statusFilter);
  }, [orders, statusFilter]);

  return (
    <div>
      <PageHeader
        title="Milk Orders"
        subtitle="Place a milk order and follow its approval and delivery."
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
              setForm({ quantity_litres: '', requested_date: today, note: '' });
              setShowForm(true);
            }}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700"
          >
            <Plus className="h-4 w-4" /> New order
          </button>
        </div>
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

      {showForm && (
        <form
          onSubmit={submitOrder}
          className="mb-6 rounded-2xl border border-emerald-100 bg-white p-5 shadow-sm"
        >
          <div className="mb-4 flex items-start justify-between">
            <div>
              <h2 className="text-sm font-bold text-slate-900">New milk order</h2>
              <p className="text-xs text-slate-500">
                Today’s rate is {formatCurrency(rate)} per litre. Orders can be
                requested for today through {formatDate(latestDate)}.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              aria-label="Cancel new order"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label
                htmlFor="order-quantity"
                className="block text-xs font-semibold uppercase tracking-wider text-slate-600"
              >
                Quantity (litres)
              </label>
              <div className="relative mt-1.5">
                <Droplets className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  id="order-quantity"
                  type="number"
                  min="0.01"
                  max="500"
                  step="0.01"
                  required
                  disabled={formLoading}
                  value={form.quantity_litres}
                  onChange={(event) =>
                    setForm({ ...form, quantity_litres: event.target.value })
                  }
                  placeholder="12.50"
                  className="w-full rounded-lg border border-slate-300 py-2.5 pl-9 pr-3 text-sm focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="order-date"
                className="block text-xs font-semibold uppercase tracking-wider text-slate-600"
              >
                Delivery date
              </label>
              <div className="relative mt-1.5">
                <Calendar className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  id="order-date"
                  type="date"
                  required
                  min={today}
                  max={latestDate}
                  disabled={formLoading}
                  value={form.requested_date}
                  onChange={(event) =>
                    setForm({ ...form, requested_date: event.target.value })
                  }
                  className="w-full rounded-lg border border-slate-300 py-2.5 pl-9 pr-3 text-sm focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="order-note"
                className="block text-xs font-semibold uppercase tracking-wider text-slate-600"
              >
                Note (optional)
              </label>
              <input
                id="order-note"
                type="text"
                maxLength={1000}
                disabled={formLoading}
                value={form.note}
                onChange={(event) => setForm({ ...form, note: event.target.value })}
                placeholder="Evening delivery, gate code…"
                className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500"
              />
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
            <p className="text-xs text-slate-500">
              Estimated total{' '}
              <span className="font-bold text-slate-800">
                {estimate ? formatCurrency(estimate) : '—'}
              </span>{' '}
              · final amount uses the rate at submission
            </p>
            <button
              type="submit"
              disabled={formLoading}
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-60"
            >
              {formLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Submitting…
                </>
              ) : (
                'Submit order'
              )}
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <LoadingSpinner message="Loading your orders…" />
      ) : error ? (
        <ErrorAlert message={error} onRetry={reload} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={ClipboardList}
          title="No orders here yet"
          description="Orders you place will appear here with their approval and delivery status."
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  {['Order', 'Delivery date', 'Quantity', 'Rate', 'Total', 'Status', ''].map(
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
                    onClick={() => openDetail(order)}
                    className="cursor-pointer transition hover:bg-slate-50"
                  >
                    <td className="px-4 py-3 font-mono text-xs font-bold text-emerald-700">
                      {order.order_no}
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
                    <td className="whitespace-nowrap px-4 py-3 font-bold text-slate-800">
                      {formatCurrency(order.estimated_total)}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[11px] font-semibold capitalize ${
                          STATUS_BADGE[order.status] || 'bg-slate-100 text-slate-600'
                        }`}
                      >
                        {order.status}
                      </span>
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="customer-order-title"
            className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
          >
            <div className="flex items-start justify-between border-b border-slate-100 p-5">
              <div>
                <h2
                  id="customer-order-title"
                  className="font-mono text-lg font-bold text-slate-900"
                >
                  {detail?.order_no || 'Order'}
                </h2>
                {detail && (
                  <span
                    className={`mt-1 inline-block rounded-full px-2 py-0.5 text-[11px] font-semibold capitalize ${
                      STATUS_BADGE[detail.status] || 'bg-slate-100 text-slate-600'
                    }`}
                  >
                    {detail.status}
                  </span>
                )}
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

            <div className="overflow-y-auto p-5">
              {detailLoading ? (
                <LoadingSpinner message="Loading order…" size="sm" />
              ) : detailError ? (
                <ErrorAlert message={detailError} />
              ) : detail ? (
                <div className="space-y-5">
                  <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Delivery
                      </p>
                      <p className="mt-0.5 font-semibold text-slate-800">
                        {formatDate(detail.requested_date)}
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Quantity
                      </p>
                      <p className="mt-0.5 font-semibold text-slate-800">
                        {formatLitres(detail.quantity_litres)}
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Rate
                      </p>
                      <p className="mt-0.5 font-semibold text-slate-800">
                        {formatCurrency(detail.rate_snapshot)}/L
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Total
                      </p>
                      <p className="mt-0.5 font-bold text-emerald-700">
                        {formatCurrency(detail.estimated_total)}
                      </p>
                    </div>
                  </div>

                  {detail.note && (
                    <div className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
                      <span className="font-semibold text-slate-700">Note:</span>{' '}
                      {detail.note}
                    </div>
                  )}
                  {detail.reason && (
                    <div className="rounded-lg border border-rose-100 bg-rose-50 px-3 py-2 text-xs text-rose-800">
                      <span className="font-semibold">Reason:</span>{' '}
                      {detail.reason}
                    </div>
                  )}

                  {detail.events?.length > 0 && (
                    <div>
                      <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">
                        Timeline
                      </h3>
                      <ol className="space-y-2 border-l border-slate-200 pl-4">
                        {detail.events.map((event, index) => (
                          <li key={index} className="text-xs text-slate-600">
                            <span className="font-semibold capitalize text-slate-800">
                              {event.to_status}
                            </span>{' '}
                            · {formatDateTime(event.created_at)}
                            {event.reason ? ` · ${event.reason}` : ''}
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}

                  {detail.sale && (
                    <div className="rounded-xl border border-slate-200 p-3 text-xs text-slate-600">
                      <p className="font-bold uppercase tracking-wider text-slate-500">
                        Delivery recorded
                      </p>
                      <p className="mt-1">
                        {formatDate(detail.sale.sale_date)} ·{' '}
                        {formatLitres(detail.sale.litres)} ·{' '}
                        {formatCurrency(detail.sale.amount)} ·{' '}
                        <span className="capitalize">
                          {detail.sale.payment_status}
                        </span>
                      </p>
                    </div>
                  )}

                  {detail.invoice && (
                    <div className="rounded-xl border border-slate-200 p-3 text-xs text-slate-600">
                      <p className="font-bold uppercase tracking-wider text-slate-500">
                        Invoice
                      </p>
                      <p className="mt-1 font-mono text-slate-800">
                        {detail.invoice.invoice_no}
                      </p>
                      <p className="mt-0.5">
                        {formatCurrency(detail.invoice.total_amount)} · balance{' '}
                        {formatCurrency(detail.invoice.balance)}
                      </p>
                    </div>
                  )}

                  {detail.status === 'submitted' && (
                    <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-3">
                      <p className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-amber-800">
                        <Ban className="h-3.5 w-3.5" /> Cancel this order
                      </p>
                      <p className="mt-1 text-[11px] text-amber-900">
                        Orders can only be cancelled before staff review.
                      </p>
                      <input
                        type="text"
                        maxLength={500}
                        value={cancelReason}
                        onChange={(event) => setCancelReason(event.target.value)}
                        placeholder="Reason (optional)"
                        className="mt-2 w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-xs focus:border-amber-400 focus:ring-2 focus:ring-amber-200"
                      />
                      <button
                        type="button"
                        onClick={cancelOrder}
                        disabled={cancelLoading}
                        className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-rose-700 disabled:opacity-60"
                      >
                        {cancelLoading && (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        )}
                        Cancel order
                      </button>
                    </div>
                  )}

                  <p className="flex items-start gap-1.5 text-[11px] text-slate-400">
                    <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    Placed {formatDateTime(detail.created_at)}
                  </p>
                </div>
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
    </div>
  );
}

export default CustomerOrders;
