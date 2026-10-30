import { useState, useEffect, useCallback } from 'react';
import { toast } from 'react-toastify';
import { useAuth } from '../../hooks/useAuth';
import { getSales, createSale, deleteSale } from '../../api/sales';
import { getCustomers } from '../../api/customers';
import { getTodayKolkataDate, formatDate, formatCurrency, formatLitres } from '../../utils/formatters';
import PageHeader from '../../components/PageHeader';
import ConfirmModal from '../../components/ConfirmModal';
import EmptyState from '../../components/EmptyState';
import LoadingSpinner from '../../components/LoadingSpinner';
import ErrorAlert from '../../components/ErrorAlert';
import { ShoppingCart, Plus, Trash2, Search, X, Calendar, CheckCircle2, Clock, RefreshCw, IndianRupee } from 'lucide-react';

const EMPTY_FORM = {
  customer_id: '',
  sale_date: '',
  litres: '',
  rate: '',
  payment_status: 'unpaid',
};

const PAYMENT_BADGE = {
  unpaid: 'bg-rose-100 text-rose-700',
  paid: 'bg-emerald-100 text-emerald-700',
};

export default function Sales() {
  const { isAdmin } = useAuth();
  const today = getTodayKolkataDate();
  const [sales, setSales] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [dateFilter, setDateFilter] = useState(today);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_FORM, sale_date: today });
  const [formLoading, setFormLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const fetchSales = useCallback(() => {
    // Both APIs return { items: [...], ... }
    return Promise.all([
      getSales(dateFilter ? { date: dateFilter } : {}),
      getCustomers(),
    ])
      .then(([salesRes, custRes]) => {
        setSales(salesRes?.items || []);
        setCustomers(custRes?.items || []);
        setError(null);
      })
      .catch((err) => {
        setError(err.message || 'Failed to load sales data.');
      })
      .finally(() => {
        setLoading(false);
      });
  }, [dateFilter]);

  // User-triggered refetch: resets the loading/error state outside the effect body.
  const refreshSales = () => {
    setLoading(true);
    setError(null);
    fetchSales();
  };

  useEffect(() => { fetchSales(); }, [fetchSales]);

  // API embeds `customer` object in each sale; customers state is for the add-form dropdown
  const getCustomerName = (sale) => sale?.customer?.name || customers.find((c) => c.id === sale?.customer_id)?.name || `Customer #${sale?.customer_id}`;
  const getCustomerRate = (id) => customers.find((c) => c.id === parseInt(id))?.rate_per_litre || '';

  const handleCustomerChange = (id) => {
    const rate = getCustomerRate(parseInt(id));
    setForm((prev) => ({ ...prev, customer_id: id, rate: rate ? String(parseFloat(rate)) : '' }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const litres = parseFloat(form.litres);
    const rate = parseFloat(form.rate);
    if (isNaN(litres) || litres <= 0 || isNaN(rate) || rate <= 0) {
      toast.error('Enter valid litres and rate values.');
      return;
    }
    setFormLoading(true);
    try {
      await createSale({
        customer_id: parseInt(form.customer_id),
        sale_date: form.sale_date,
        litres: litres.toFixed(2),
        rate: rate.toFixed(2),
        payment_status: form.payment_status,
      });
      toast.success('Sale recorded successfully!');
      setShowForm(false);
      setForm({ ...EMPTY_FORM, sale_date: today });
      refreshSales();
    } catch (err) {
      toast.error(err.message || 'Failed to record sale.');
    } finally {
      setFormLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteSale(deleteTarget.id);
      toast.success('Sale record deleted.');
      setDeleteTarget(null);
      refreshSales();
    } catch (err) {
      toast.error(err.message || 'Failed to delete sale.');
    }
  };

  const filtered = sales.filter((s) => {
    const q = search.toLowerCase();
    const custName = getCustomerName(s).toLowerCase();
    return !q || custName.includes(q);
  });

  const totalRevenue = filtered.reduce((sum, s) => sum + (parseFloat(s.amount) || 0), 0);
  const totalLitres = filtered.reduce((sum, s) => sum + (parseFloat(s.litres) || 0), 0);
  const computedAmount = form.litres && form.rate
    ? (parseFloat(form.litres) * parseFloat(form.rate)).toFixed(2)
    : null;

  return (
    <div>
      <PageHeader
        title="Daily Milk Sales"
        subtitle="Record and review milk sales transactions with stock deduction."
      >
        <button
          onClick={() => { setShowForm(true); setForm({ ...EMPTY_FORM, sale_date: today }); }}
          className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-semibold shadow-sm transition"
        >
          <Plus className="w-4 h-4" /> Record Sale
        </button>
      </PageHeader>

      {/* Controls */}
      <div className="flex flex-col sm:flex-row gap-3 mb-5">
        <div className="flex items-center gap-2">
          <Calendar className="w-4 h-4 text-slate-500" />
          <input
            type="date"
            value={dateFilter}
            onChange={(e) => {
              setLoading(true);
              setError(null);
              setDateFilter(e.target.value);
            }}
            className="px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400 bg-white"
          />
        </div>
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search by customer name…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400 bg-white"
          />
        </div>
        <button
          onClick={refreshSales}
          className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 rounded-lg transition"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Summary */}
      {!loading && !error && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-5">
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <p className="text-xs text-slate-500 mb-1">Total Transactions</p>
            <p className="text-2xl font-bold text-slate-800">{filtered.length}</p>
          </div>
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <p className="text-xs text-slate-500 mb-1">Litres Sold</p>
            <p className="text-2xl font-bold text-sky-700">{formatLitres(totalLitres)}</p>
          </div>
          <div className="bg-white rounded-xl border border-slate-200 p-4 col-span-2 sm:col-span-1">
            <p className="text-xs text-slate-500 mb-1">Total Revenue</p>
            <p className="text-2xl font-bold text-emerald-700">{formatCurrency(totalRevenue)}</p>
          </div>
        </div>
      )}

      {loading ? (
        <LoadingSpinner message="Loading sales…" />
      ) : error ? (
        <ErrorAlert message={error} onRetry={refreshSales} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={ShoppingCart}
          title="No sales found"
          description="Record your first milk sale for this date."
        />
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">#</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Customer</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Date</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Litres</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Rate</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Amount</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Payment</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Recorded By</th>
                  {isAdmin && <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider"></th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filtered.map((s, idx) => (
                  <tr key={s.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3 text-slate-400 text-xs">{idx + 1}</td>
                    <td className="px-4 py-3 font-medium text-slate-800">{getCustomerName(s)}</td>
                    <td className="px-4 py-3 text-slate-600">{formatDate(s.sale_date)}</td>
                    <td className="px-4 py-3 font-semibold text-sky-700">{formatLitres(s.litres)}</td>
                    <td className="px-4 py-3 text-slate-600">{formatCurrency(s.rate)}/L</td>
                    <td className="px-4 py-3 font-bold text-emerald-700">{formatCurrency(s.amount)}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${PAYMENT_BADGE[s.payment_status] || 'bg-slate-100 text-slate-600'}`}>
                        {s.payment_status === 'paid' ? <CheckCircle2 className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
                        {s.payment_status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-500 text-xs">{s.recorder?.username || '—'}</td>
                    {isAdmin && (
                      <td className="px-4 py-3">
                        <button
                          onClick={() => setDeleteTarget(s)}
                          className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition"
                          title="Delete sale"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Record Sale Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-emerald-100 flex items-center justify-center">
                  <ShoppingCart className="w-5 h-5 text-emerald-700" />
                </div>
                <div>
                  <h2 className="font-bold text-slate-900">Record Milk Sale</h2>
                  <p className="text-xs text-slate-500">Log a customer delivery with stock deduction</p>
                </div>
              </div>
              <button onClick={() => setShowForm(false)} className="p-1.5 hover:bg-slate-100 rounded-lg transition">
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>
            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Customer <span className="text-rose-500">*</span></label>
                <select
                  required
                  value={form.customer_id}
                  onChange={(e) => handleCustomerChange(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400 bg-white"
                >
                  <option value="">Select a customer…</option>
                  {customers.filter((c) => c.is_active).map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Sale Date <span className="text-rose-500">*</span></label>
                  <input
                    required
                    type="date"
                    value={form.sale_date}
                    max={today}
                    onChange={(e) => setForm({ ...form, sale_date: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Payment Status</label>
                  <select
                    value={form.payment_status}
                    onChange={(e) => setForm({ ...form, payment_status: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400 bg-white"
                  >
                    <option value="unpaid">Unpaid</option>
                    <option value="paid">Paid</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Litres <span className="text-rose-500">*</span></label>
                  <input
                    required
                    type="number"
                    min="0.01"
                    step="0.01"
                    placeholder="e.g. 12.00"
                    value={form.litres}
                    onChange={(e) => setForm({ ...form, litres: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Rate/L (₹) <span className="text-rose-500">*</span></label>
                  <input
                    required
                    type="number"
                    min="0.01"
                    step="0.01"
                    placeholder="e.g. 60.00"
                    value={form.rate}
                    onChange={(e) => setForm({ ...form, rate: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400"
                  />
                </div>
              </div>
              {computedAmount && (
                <div className="flex items-center gap-2 p-3 bg-emerald-50 rounded-lg border border-emerald-200">
                  <IndianRupee className="w-4 h-4 text-emerald-600" />
                  <span className="text-sm text-emerald-700 font-semibold">Total: {formatCurrency(computedAmount)}</span>
                </div>
              )}
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={formLoading}
                  className="px-4 py-2 text-sm font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg transition disabled:opacity-60"
                >
                  {formLoading ? 'Recording…' : 'Record Sale'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <ConfirmModal
        isOpen={!!deleteTarget}
        title="Delete Sale Record"
        message={`Delete this sale of ${formatLitres(deleteTarget?.litres)} to ${getCustomerName(deleteTarget)}? This will restore stock.`}
        confirmText="Delete"
        confirmVariant="danger"
        onConfirm={handleDelete}
        onClose={() => setDeleteTarget(null)}
      />
    </div>
  );
}
