import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getCustomerDashboard } from '../../api/customerPortal';
import {
  formatCurrency,
  formatDate,
  formatLitres,
  getTodayKolkataDate,
} from '../../utils/formatters';
import PageHeader from '../../components/PageHeader';
import LoadingSpinner from '../../components/LoadingSpinner';
import ErrorAlert from '../../components/ErrorAlert';
import EmptyState from '../../components/EmptyState';
import {
  Wallet,
  Droplets,
  MessagesSquare,
  ClipboardList,
  ReceiptText,
  ArrowRight,
  Plus,
  RefreshCw,
} from 'lucide-react';

const ORDER_BADGE = {
  submitted: 'bg-amber-100 text-amber-800',
  approved: 'bg-sky-100 text-sky-800',
  rejected: 'bg-rose-100 text-rose-800',
  cancelled: 'bg-slate-100 text-slate-600',
  fulfilled: 'bg-emerald-100 text-emerald-800',
};

const INVOICE_BADGE = {
  unpaid: 'bg-rose-100 text-rose-700',
  partial: 'bg-amber-100 text-amber-800',
  paid: 'bg-emerald-100 text-emerald-700',
};

export function CustomerDashboard() {
  const today = getTodayKolkataDate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  const load = useCallback(
    () =>
      getCustomerDashboard()
        .then((response) => {
          setData(response);
          setError(null);
        })
        .catch((err) => {
          setError(err?.message || 'Failed to load your dashboard.');
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

  const balance = data?.balance;
  const customer = data?.customer;

  return (
    <div>
      <PageHeader
        title={`Hello, ${customer?.name?.split(' ')[0] || 'there'}`}
        subtitle={`Your milk account at a glance · ${formatDate(today)}`}
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
        <LoadingSpinner message="Loading your account…" />
      ) : error ? (
        <ErrorAlert message={error} onRetry={refresh} />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl border border-rose-100 bg-white p-5 shadow-sm">
              <div className="flex items-center gap-2 text-rose-600">
                <Wallet className="h-4 w-4" />
                <span className="text-xs font-bold uppercase tracking-wider">
                  Outstanding
                </span>
              </div>
              <p className="mt-2 text-2xl font-extrabold text-slate-900">
                {formatCurrency(balance?.outstanding_balance)}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Paid to date {formatCurrency(balance?.total_paid_amount)}
              </p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center gap-2 text-slate-500">
                <ReceiptText className="h-4 w-4" />
                <span className="text-xs font-bold uppercase tracking-wider">
                  Billed
                </span>
              </div>
              <p className="mt-2 text-2xl font-extrabold text-slate-900">
                {formatCurrency(balance?.total_sales_amount)}
              </p>
              <Link
                to="/portal/invoices"
                className="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 hover:text-emerald-900"
              >
                View invoices <ArrowRight className="h-3 w-3" />
              </Link>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center gap-2 text-sky-600">
                <Droplets className="h-4 w-4" />
                <span className="text-xs font-bold uppercase tracking-wider">
                  Your rate
                </span>
              </div>
              <p className="mt-2 text-2xl font-extrabold text-slate-900">
                {formatCurrency(customer?.rate_per_litre)}
                <span className="text-sm font-semibold text-slate-400">/L</span>
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Applied to new orders automatically
              </p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center gap-2 text-amber-600">
                <MessagesSquare className="h-4 w-4" />
                <span className="text-xs font-bold uppercase tracking-wider">
                  Open queries
                </span>
              </div>
              <p className="mt-2 text-2xl font-extrabold text-slate-900">
                {data?.open_queries ?? 0}
              </p>
              <Link
                to="/portal/queries"
                className="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 hover:text-emerald-900"
              >
                Support inbox <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          </div>

          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              to="/portal/orders"
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700"
            >
              <Plus className="h-4 w-4" /> New milk order
            </Link>
            <Link
              to="/portal/queries"
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
            >
              <MessagesSquare className="h-4 w-4" /> Raise a query
            </Link>
          </div>

          <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <section>
              <div className="mb-3 flex items-center justify-between">
                <h2 className="flex items-center gap-2 text-sm font-bold text-slate-800">
                  <ClipboardList className="h-4 w-4 text-slate-400" />
                  Recent orders
                </h2>
                <Link
                  to="/portal/orders"
                  className="text-xs font-semibold text-emerald-700 hover:text-emerald-900"
                >
                  View all
                </Link>
              </div>
              {data?.recent_orders?.length ? (
                <div className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
                  {data.recent_orders.map((order) => (
                    <div
                      key={order.id}
                      className="flex flex-wrap items-center justify-between gap-2 px-4 py-3"
                    >
                      <div className="min-w-0">
                        <p className="font-mono text-xs font-bold text-emerald-700">
                          {order.order_no}
                        </p>
                        <p className="text-xs text-slate-500">
                          {formatDate(order.requested_date)} ·{' '}
                          {formatLitres(order.quantity_litres)} ·{' '}
                          {formatCurrency(order.estimated_total)}
                        </p>
                      </div>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[11px] font-semibold capitalize ${
                          ORDER_BADGE[order.status] || 'bg-slate-100 text-slate-600'
                        }`}
                      >
                        {order.status}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  icon={ClipboardList}
                  title="No orders yet"
                  description="Place your first milk order and it will show up here."
                />
              )}
            </section>

            <section>
              <div className="mb-3 flex items-center justify-between">
                <h2 className="flex items-center gap-2 text-sm font-bold text-slate-800">
                  <ReceiptText className="h-4 w-4 text-slate-400" />
                  Recent invoices
                </h2>
                <Link
                  to="/portal/invoices"
                  className="text-xs font-semibold text-emerald-700 hover:text-emerald-900"
                >
                  View all
                </Link>
              </div>
              {data?.recent_invoices?.length ? (
                <div className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
                  {data.recent_invoices.map((invoice) => (
                    <div
                      key={invoice.id}
                      className="flex flex-wrap items-center justify-between gap-2 px-4 py-3"
                    >
                      <div className="min-w-0">
                        <p className="font-mono text-xs font-bold text-slate-700">
                          {invoice.invoice_no}
                        </p>
                        <p className="text-xs text-slate-500">
                          {formatDate(invoice.period_end)} ·{' '}
                          {formatCurrency(invoice.total_amount)}
                        </p>
                      </div>
                      <div className="text-right">
                        <span
                          className={`rounded-full px-2 py-0.5 text-[11px] font-semibold capitalize ${
                            INVOICE_BADGE[invoice.status] ||
                            'bg-slate-100 text-slate-600'
                          }`}
                        >
                          {invoice.status}
                        </span>
                        <p className="mt-1 text-[11px] text-slate-500">
                          Balance {formatCurrency(invoice.balance)}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  icon={ReceiptText}
                  title="No invoices yet"
                  description="Invoices appear here once a delivered order is billed."
                />
              )}
            </section>
          </div>

          <p className="mt-8 rounded-xl border border-emerald-100 bg-emerald-50/60 px-4 py-3 text-xs leading-relaxed text-emerald-900">
            Orders can be placed for today up to 14 days ahead. Rates are
            captured when you submit an order, and staff confirm availability
            before delivery.
          </p>
        </>
      )}
    </div>
  );
}

export default CustomerDashboard;
