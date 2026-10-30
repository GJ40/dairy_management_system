import { useState, useEffect, useCallback } from 'react';
import { toast } from 'react-toastify';
import { useAuth } from '../../hooks/useAuth';
import { getInvoices, createInvoice, recordPayment, downloadInvoicePdf, deleteInvoice } from '../../api/invoices';
import { getCustomers } from '../../api/customers';
import { formatDate, formatCurrency } from '../../utils/formatters';
import PageHeader from '../../components/PageHeader';
import ConfirmModal from '../../components/ConfirmModal';
import EmptyState from '../../components/EmptyState';
import LoadingSpinner from '../../components/LoadingSpinner';
import ErrorAlert from '../../components/ErrorAlert';
import {
  ReceiptText, Plus, Trash2, Search, X, Download,
  CreditCard, CheckCircle2, Clock, AlertCircle, RefreshCw,
} from 'lucide-react';

const STATUS_CONFIG = {
  unpaid:  { label: 'Unpaid',  color: 'bg-rose-100 text-rose-700',    icon: Clock },
  partial: { label: 'Partial', color: 'bg-amber-100 text-amber-700',  icon: AlertCircle },
  paid:    { label: 'Paid',    color: 'bg-emerald-100 text-emerald-700', icon: CheckCircle2 },
};

export default function Invoices() {
  const { isAdmin } = useAuth();
  const [invoices, setInvoices] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createForm, setCreateForm] = useState({ customer_id: '' });
  const [createLoading, setCreateLoading] = useState(false);
  const [paymentTarget, setPaymentTarget] = useState(null);
  const [paymentForm, setPaymentForm] = useState({ amount: '' });
  const [paymentLoading, setPaymentLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [downloadingId, setDownloadingId] = useState(null);

  const fetchData = useCallback(() => {
    // Both APIs return { items: [...], ... }
    return Promise.all([getInvoices(), getCustomers()])
      .then(([invRes, custRes]) => {
        setInvoices(invRes?.items || []);
        setCustomers(custRes?.items || []);
        setError(null);
      })
      .catch((err) => {
        setError(err.message || 'Failed to load invoices.');
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData, reloadKey]);

  const refreshData = () => {
    setLoading(true);
    setError(null);
    setReloadKey((key) => key + 1);
  };

  // Invoice items have embedded `customer` object; fall back to customers list for form
  const getCustomerName = (inv) => inv?.customer?.name || customers.find((c) => c.id === inv?.customer_id)?.name || `Customer #${inv?.customer_id}`;

  const filtered = invoices.filter((inv) => {
    const matchStatus = statusFilter === 'all' || inv.status === statusFilter;
    const q = search.toLowerCase();
    const custName = getCustomerName(inv).toLowerCase();
    const matchSearch = !q || inv.invoice_no?.toLowerCase().includes(q) || custName.includes(q);
    return matchStatus && matchSearch;
  });

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!createForm.customer_id) { toast.error('Select a customer.'); return; }
    setCreateLoading(true);
    try {
      await createInvoice({ customer_id: parseInt(createForm.customer_id) });
      toast.success('Invoice generated successfully!');
      setShowCreateForm(false);
      setCreateForm({ customer_id: '' });
      refreshData();
    } catch (err) {
      toast.error(err.message || 'Failed to generate invoice. Ensure the customer has un-invoiced sales.');
    } finally {
      setCreateLoading(false);
    }
  };

  const handlePayment = async (e) => {
    e.preventDefault();
    const amount = parseFloat(paymentForm.amount);
    if (isNaN(amount) || amount <= 0) { toast.error('Enter a valid amount.'); return; }
    setPaymentLoading(true);
    try {
      await recordPayment(paymentTarget.id, { amount: amount.toFixed(2) });
      toast.success('Payment recorded!');
      setPaymentTarget(null);
      setPaymentForm({ amount: '' });
      refreshData();
    } catch (err) {
      toast.error(err.message || 'Failed to record payment.');
    } finally {
      setPaymentLoading(false);
    }
  };

  const handleDownloadPdf = async (inv) => {
    setDownloadingId(inv.id);
    try {
      const response = await downloadInvoicePdf(inv.id);
      const blob = response.data || response;
      const url = URL.createObjectURL(blob instanceof Blob ? blob : new Blob([blob], { type: 'application/pdf' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `${inv.invoice_no}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(err.message || 'Failed to download PDF.');
    } finally {
      setDownloadingId(null);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteInvoice(deleteTarget.id);
      toast.success(`Invoice ${deleteTarget.invoice_no} deleted.`);
      setDeleteTarget(null);
      refreshData();
    } catch (err) {
      toast.error(err.message || 'Failed to delete invoice.');
    }
  };

  const totalOutstanding = filtered.reduce((s, inv) => s + (parseFloat(inv.balance) || 0), 0);

  return (
    <div>
      <PageHeader
        title="Invoices & Billing"
        subtitle="Generate and manage customer invoices. Record payments and download PDFs."
      >
        <div className="flex items-center gap-3">
          <button
            onClick={refreshData}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 rounded-lg transition"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={() => setShowCreateForm(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-semibold shadow-sm transition"
          >
            <Plus className="w-4 h-4" /> Generate Invoice
          </button>
        </div>
      </PageHeader>

      {/* Status Filter Chips */}
      <div className="flex gap-2 flex-wrap mb-5">
        {['all', 'unpaid', 'partial', 'paid'].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold capitalize transition ${
              statusFilter === s
                ? 'bg-emerald-600 text-white shadow-sm'
                : 'bg-white border border-slate-200 text-slate-600 hover:border-emerald-300'
            }`}
          >
            {s === 'all' ? `All (${invoices.length})` : `${STATUS_CONFIG[s]?.label} (${invoices.filter((i) => i.status === s).length})`}
          </button>
        ))}
        {totalOutstanding > 0 && (
          <span className="ml-auto text-xs font-semibold text-rose-700 bg-rose-50 border border-rose-200 px-3 py-1.5 rounded-full">
            Outstanding: {formatCurrency(totalOutstanding)}
          </span>
        )}
      </div>

      {/* Search */}
      <div className="relative mb-5">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <input
          type="text"
          placeholder="Search by invoice no. or customer name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-9 pr-4 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400 bg-white"
        />
      </div>

      {loading ? (
        <LoadingSpinner message="Loading invoices…" />
      ) : error ? (
          <ErrorAlert message={error} onRetry={refreshData} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={ReceiptText}
          title="No invoices found"
          description="Generate an invoice for a customer with un-invoiced sales."
        />
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Invoice No.</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Customer</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Period</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Total</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Paid</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Balance</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filtered.map((inv) => {
                  const StatusIcon = STATUS_CONFIG[inv.status]?.icon || Clock;
                  return (
                    <tr key={inv.id} className="hover:bg-slate-50 transition-colors">
                      <td className="px-4 py-3 font-mono text-xs font-bold text-emerald-700">{inv.invoice_no}</td>
                      <td className="px-4 py-3 font-medium text-slate-800">{getCustomerName(inv)}</td>
                      <td className="px-4 py-3 text-slate-500 text-xs">
                        {formatDate(inv.period_start)} – {formatDate(inv.period_end)}
                      </td>
                      <td className="px-4 py-3 font-bold text-slate-800">{formatCurrency(inv.total_amount)}</td>
                      <td className="px-4 py-3 text-emerald-700">{formatCurrency(inv.paid_amount)}</td>
                      <td className="px-4 py-3 font-semibold text-rose-700">{formatCurrency(inv.balance)}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${STATUS_CONFIG[inv.status]?.color || 'bg-slate-100 text-slate-500'}`}>
                          <StatusIcon className="w-3 h-3" />
                          {STATUS_CONFIG[inv.status]?.label || inv.status}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleDownloadPdf(inv)}
                            disabled={downloadingId === inv.id}
                            className="p-1.5 text-slate-400 hover:text-sky-600 hover:bg-sky-50 rounded-lg transition"
                            title="Download PDF"
                          >
                            <Download className="w-4 h-4" />
                          </button>
                          {inv.status !== 'paid' && (
                            <button
                              onClick={() => { setPaymentTarget(inv); setPaymentForm({ amount: inv.balance }); }}
                              className="p-1.5 text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition"
                              title="Record payment"
                            >
                              <CreditCard className="w-4 h-4" />
                            </button>
                          )}
                          {isAdmin && (
                            <button
                              onClick={() => setDeleteTarget(inv)}
                              className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition"
                              title="Delete invoice"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Generate Invoice Modal */}
      {showCreateForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm">
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-emerald-100 flex items-center justify-center">
                  <ReceiptText className="w-5 h-5 text-emerald-700" />
                </div>
                <div>
                  <h2 className="font-bold text-slate-900">Generate Invoice</h2>
                  <p className="text-xs text-slate-500">Groups all un-invoiced sales</p>
                </div>
              </div>
              <button onClick={() => setShowCreateForm(false)} className="p-1.5 hover:bg-slate-100 rounded-lg transition">
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>
            <form onSubmit={handleCreate} className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Customer <span className="text-rose-500">*</span></label>
                <select
                  required
                  value={createForm.customer_id}
                  onChange={(e) => setCreateForm({ customer_id: e.target.value })}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400 bg-white"
                >
                  <option value="">Select a customer…</option>
                  {customers.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <p className="text-xs text-slate-500 bg-slate-50 rounded-lg px-3 py-2 border border-slate-200">
                This will group all un-invoiced sales for the selected customer into one invoice.
              </p>
              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={() => setShowCreateForm(false)} className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition">
                  Cancel
                </button>
                <button type="submit" disabled={createLoading} className="px-4 py-2 text-sm font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg transition disabled:opacity-60">
                  {createLoading ? 'Generating…' : 'Generate Invoice'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Record Payment Modal */}
      {paymentTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm">
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-emerald-100 flex items-center justify-center">
                  <CreditCard className="w-5 h-5 text-emerald-700" />
                </div>
                <div>
                  <h2 className="font-bold text-slate-900">Record Payment</h2>
                  <p className="text-xs text-slate-500">{paymentTarget.invoice_no} — Balance: {formatCurrency(paymentTarget.balance)}</p>
                </div>
              </div>
              <button onClick={() => setPaymentTarget(null)} className="p-1.5 hover:bg-slate-100 rounded-lg transition">
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>
            <form onSubmit={handlePayment} className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Payment Amount (₹) <span className="text-rose-500">*</span></label>
                <input
                  required
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={paymentForm.amount}
                  onChange={(e) => setPaymentForm({ amount: e.target.value })}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400"
                />
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={() => setPaymentTarget(null)} className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition">
                  Cancel
                </button>
                <button type="submit" disabled={paymentLoading} className="px-4 py-2 text-sm font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg transition disabled:opacity-60">
                  {paymentLoading ? 'Recording…' : 'Record Payment'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <ConfirmModal
        isOpen={!!deleteTarget}
        title="Delete Invoice"
        message={`Delete invoice ${deleteTarget?.invoice_no}? This action cannot be undone.`}
        confirmText="Delete"
        confirmVariant="danger"
        onConfirm={handleDelete}
        onClose={() => setDeleteTarget(null)}
      />
    </div>
  );
}
