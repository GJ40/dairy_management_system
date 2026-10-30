import { useCallback, useEffect, useState } from 'react';
import { toast } from 'react-toastify';
import {
  fetchMyInvoicePdf,
  getMyBalance,
  getMyInvoice,
  getMyInvoices,
} from '../../api/customerPortal';
import {
  formatCurrency,
  formatDate,
  formatLitres,
} from '../../utils/formatters';
import PageHeader from '../../components/PageHeader';
import LoadingSpinner from '../../components/LoadingSpinner';
import ErrorAlert from '../../components/ErrorAlert';
import EmptyState from '../../components/EmptyState';
import {
  ReceiptText,
  Download,
  Loader2,
  RefreshCw,
  Wallet,
  X,
} from 'lucide-react';

const STATUS_BADGE = {
  unpaid: 'bg-rose-100 text-rose-700',
  partial: 'bg-amber-100 text-amber-800',
  paid: 'bg-emerald-100 text-emerald-700',
};

const STATUS_FILTERS = ['all', 'unpaid', 'partial', 'paid'];

export function CustomerInvoices() {
  const [invoices, setInvoices] = useState([]);
  const [balance, setBalance] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [reloadKey, setReloadKey] = useState(0);

  const [detailId, setDetailId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const [downloading, setDownloading] = useState(false);

  const load = useCallback(
    () =>
      Promise.all([
        getMyInvoices({
          page: 1,
          page_size: 100,
          status: statusFilter === 'all' ? undefined : statusFilter,
        }),
        getMyBalance(),
      ])
        .then(([invoiceResponse, balanceResponse]) => {
          setInvoices(invoiceResponse?.items || []);
          setBalance(balanceResponse?.balance || null);
          setError(null);
        })
        .catch((err) => {
          setError(err?.message || 'Failed to load your invoices.');
        })
        .finally(() => {
          setLoading(false);
        }),
    [statusFilter]
  );

  useEffect(() => {
    load();
  }, [load, reloadKey]);

  const refresh = () => {
    setLoading(true);
    setError(null);
    setReloadKey((key) => key + 1);
  };

  const openDetail = (invoice) => {
    setDetailId(invoice.id);
    setDetail(invoice);
    setDetailError(null);
    setDetailLoading(true);
    getMyInvoice(invoice.id)
      .then((response) => setDetail(response?.invoice || null))
      .catch((err) => setDetailError(err?.message || 'Failed to load invoice.'))
      .finally(() => setDetailLoading(false));
  };

  const closeDetail = () => {
    setDetailId(null);
    setDetail(null);
    setDetailError(null);
  };

  const downloadPdf = async (invoiceId, invoiceNo) => {
    setDownloading(true);
    try {
      const blob = await fetchMyInvoicePdf(invoiceId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `invoice-${invoiceNo}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(err?.message || 'Could not download the invoice PDF.');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Invoices & Balance"
        subtitle="Every delivered order is billed on a daily invoice."
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

      {balance && (
        <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-2 text-slate-500">
              <Wallet className="h-4 w-4" />
              <span className="text-xs font-bold uppercase tracking-wider">
                Outstanding
              </span>
            </div>
            <p className="mt-2 text-2xl font-extrabold text-rose-700">
              {formatCurrency(balance.outstanding_balance)}
            </p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Total billed
            </span>
            <p className="mt-2 text-2xl font-extrabold text-slate-900">
              {formatCurrency(balance.total_sales_amount)}
            </p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Paid to date
            </span>
            <p className="mt-2 text-2xl font-extrabold text-emerald-700">
              {formatCurrency(balance.total_paid_amount)}
            </p>
          </div>
        </div>
      )}

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

      {loading ? (
        <LoadingSpinner message="Loading your invoices…" />
      ) : error ? (
        <ErrorAlert message={error} onRetry={refresh} />
      ) : invoices.length === 0 ? (
        <EmptyState
          icon={ReceiptText}
          title="No invoices yet"
          description="Once an order is delivered and billed, the invoice appears here."
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  {['Invoice', 'Period', 'Total', 'Paid', 'Balance', 'Status', ''].map(
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
                {invoices.map((invoice) => (
                  <tr
                    key={invoice.id}
                    onClick={() => openDetail(invoice)}
                    className="cursor-pointer transition hover:bg-slate-50"
                  >
                    <td className="px-4 py-3 font-mono text-xs font-bold text-slate-700">
                      {invoice.invoice_no}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                      {formatDate(invoice.period_start)}
                      {invoice.period_start !== invoice.period_end
                        ? ` – ${formatDate(invoice.period_end)}`
                        : ''}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 font-semibold text-slate-800">
                      {formatCurrency(invoice.total_amount)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                      {formatCurrency(invoice.paid_amount)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 font-bold text-rose-700">
                      {formatCurrency(invoice.balance)}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[11px] font-semibold capitalize ${
                          STATUS_BADGE[invoice.status] || 'bg-slate-100 text-slate-600'
                        }`}
                      >
                        {invoice.status}
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
            aria-labelledby="customer-invoice-title"
            className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
          >
            <div className="flex items-start justify-between border-b border-slate-100 p-5">
              <div>
                <h2
                  id="customer-invoice-title"
                  className="font-mono text-lg font-bold text-slate-900"
                >
                  {detail?.invoice_no || 'Invoice'}
                </h2>
                {detail && (
                  <p className="mt-1 text-xs text-slate-500">
                    {formatDate(detail.period_start)}
                    {detail.period_start !== detail.period_end
                      ? ` – ${formatDate(detail.period_end)}`
                      : ''}
                  </p>
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
                <LoadingSpinner message="Loading invoice…" size="sm" />
              ) : detailError ? (
                <ErrorAlert message={detailError} />
              ) : detail ? (
                <div className="space-y-5">
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Total
                      </p>
                      <p className="mt-0.5 font-bold text-slate-900">
                        {formatCurrency(detail.total_amount)}
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Paid
                      </p>
                      <p className="mt-0.5 font-semibold text-slate-700">
                        {formatCurrency(detail.paid_amount)}
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Balance
                      </p>
                      <p className="mt-0.5 font-bold text-rose-700">
                        {formatCurrency(detail.balance)}
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Status
                      </p>
                      <p className="mt-0.5 font-semibold capitalize text-slate-700">
                        {detail.status}
                      </p>
                    </div>
                  </div>

                  <div>
                    <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">
                      Billed sales
                    </h3>
                    {detail.sales?.length ? (
                      <div className="divide-y divide-slate-100 rounded-xl border border-slate-200">
                        {detail.sales.map((sale) => (
                          <div
                            key={sale.id}
                            className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-xs text-slate-600"
                          >
                            <span>{formatDate(sale.sale_date)}</span>
                            <span>
                              {formatLitres(sale.litres)} ×{' '}
                              {formatCurrency(sale.rate)}
                            </span>
                            <span className="font-semibold text-slate-800">
                              {formatCurrency(sale.amount)}
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-slate-400">
                        No sales linked to this invoice.
                      </p>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={() => downloadPdf(detail.id, detail.invoice_no)}
                    disabled={downloading}
                    className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-60"
                  >
                    {downloading ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Download className="h-3.5 w-3.5" />
                    )}
                    Download PDF
                  </button>
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

export default CustomerInvoices;
