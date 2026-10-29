import { useState, useEffect, useCallback } from 'react';
import { toast } from 'react-toastify';
import { getExpenses, getExpenseCategories, createExpense, deleteExpense } from '../../api/expenses';
import { getTodayKolkataDate, formatDate, formatCurrency } from '../../utils/formatters';
import PageHeader from '../../components/PageHeader';
import ConfirmModal from '../../components/ConfirmModal';
import EmptyState from '../../components/EmptyState';
import LoadingSpinner from '../../components/LoadingSpinner';
import ErrorAlert from '../../components/ErrorAlert';
import { Wallet, Plus, Trash2, Search, X, Calendar, Filter, ChevronDown, RefreshCw, Tag } from 'lucide-react';

// API returns { categories: [...] } with { id, name } (lowercase names like "feed", "labour")

const EMPTY_FORM = {
  category_id: '',
  expense_date: '',
  amount: '',
  note: '',
};

// Capitalize first letter for display
const capitalize = (str) => str ? str.charAt(0).toUpperCase() + str.slice(1) : '';

export default function Expenses() {
  const today = getTodayKolkataDate();
  const [expenses, setExpenses] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [catFilter, setCatFilter] = useState('all');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_FORM, expense_date: today });
  const [formLoading, setFormLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const fetchExpenses = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // expenses API: { items: [...], page, page_size, total, total_expense_amount }
      // categories API: { categories: [...] }
      const [expRes, catRes] = await Promise.all([
        getExpenses(),
        getExpenseCategories(),
      ]);
      setExpenses(expRes?.items || []);
      const cats = catRes?.categories || [];
      setCategories(cats);
      // Auto-select first category if form is empty
      if (cats.length > 0 && !form.category_id) {
        setForm((prev) => ({ ...prev, category_id: String(cats[0].id) }));
      }
    } catch (err) {
      setError(err.message || 'Failed to load expenses.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchExpenses(); }, [fetchExpenses]);

  // Use embedded category.name from expense item, fall back to categories list
  const getCategoryName = (expense) => {
    if (expense?.category?.name) return capitalize(expense.category.name);
    const cat = categories.find((c) => c.id === expense?.category_id);
    return cat ? capitalize(cat.name) : `Category #${expense?.category_id}`;
  };

  // For the category filter chips and form
  const getCategoryNameById = (id) => {
    const cat = categories.find((c) => c.id === parseInt(id));
    return cat ? capitalize(cat.name) : `Category #${id}`;
  };

  const filtered = expenses.filter((e) => {
    const matchCat = catFilter === 'all' || String(e.category_id) === catFilter;
    const q = search.toLowerCase();
    const catName = getCategoryName(e).toLowerCase();
    const matchSearch = !q || catName.includes(q) || e.note?.toLowerCase().includes(q);
    return matchCat && matchSearch;
  });

  const handleSubmit = async (ev) => {
    ev.preventDefault();
    const amount = parseFloat(form.amount);
    if (isNaN(amount) || amount <= 0) { toast.error('Enter a valid amount.'); return; }
    setFormLoading(true);
    try {
      await createExpense({
        category_id: parseInt(form.category_id),
        expense_date: form.expense_date,
        amount: amount.toFixed(2),
        note: form.note.trim() || undefined,
      });
      toast.success('Expense recorded successfully!');
      setShowForm(false);
      setForm({ ...EMPTY_FORM, expense_date: today, category_id: categories[0] ? String(categories[0].id) : '' });
      fetchExpenses();
    } catch (err) {
      toast.error(err.message || 'Failed to record expense.');
    } finally {
      setFormLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteExpense(deleteTarget.id);
      toast.success('Expense deleted.');
      setDeleteTarget(null);
      fetchExpenses();
    } catch (err) {
      toast.error(err.message || 'Failed to delete expense.');
    }
  };

  const totalAmount = filtered.reduce((s, e) => s + (parseFloat(e.amount) || 0), 0);

  // Group by category for summary chips
  const categoryTotals = categories.map((cat) => ({
    ...cat,
    displayName: capitalize(cat.name),
    total: expenses.filter((e) => e.category_id === cat.id).reduce((s, e) => s + (parseFloat(e.amount) || 0), 0),
  })).filter((c) => c.total > 0).sort((a, b) => b.total - a.total);

  return (
    <div>
      <PageHeader
        title="Farm Expense Logging"
        subtitle="Track all farm operating expenses by category. Admin only."
        badge="Admin Only"
      >
        <button
          onClick={() => { setShowForm(true); setForm({ ...EMPTY_FORM, expense_date: today, category_id: categories[0] ? String(categories[0].id) : '' }); }}
          className="inline-flex items-center gap-2 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg text-sm font-semibold shadow-sm transition"
        >
          <Plus className="w-4 h-4" /> Log Expense
        </button>
      </PageHeader>

      {/* Category Summary */}
      {!loading && categoryTotals.length > 0 && (
        <div className="mb-5 p-4 bg-white rounded-xl border border-slate-200 shadow-sm">
          <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">Expense Breakdown by Category</p>
          <div className="flex flex-wrap gap-2">
            {categoryTotals.map((cat) => (
              <button
                key={cat.id}
                onClick={() => setCatFilter(catFilter === String(cat.id) ? 'all' : String(cat.id))}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                  catFilter === String(cat.id)
                    ? 'bg-amber-500 text-white'
                    : 'bg-slate-100 text-slate-700 hover:bg-amber-50 hover:text-amber-700'
                }`}
              >
                <Tag className="w-3 h-3" />
                {cat.displayName}
                <span className="font-bold">{formatCurrency(cat.total)}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 mb-5">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search by category or note…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400 bg-white"
          />
        </div>
        <div className="relative">
          <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <select
            value={catFilter}
            onChange={(e) => setCatFilter(e.target.value)}
            className="pl-9 pr-8 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400 bg-white appearance-none cursor-pointer"
          >
            <option value="all">All Categories</option>
            {categories.map((c) => (
              <option key={c.id} value={String(c.id)}>{capitalize(c.name)}</option>
            ))}
          </select>
          <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
        </div>
        <button
          onClick={fetchExpenses}
          className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 rounded-lg transition"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {loading ? (
        <LoadingSpinner message="Loading expenses…" />
      ) : error ? (
        <ErrorAlert message={error} onRetry={fetchExpenses} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={Wallet}
          title="No expenses found"
          description={search || catFilter !== 'all' ? 'Try adjusting your filters.' : 'Log your first farm expense.'}
        />
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 bg-slate-50">
            <span className="text-sm font-semibold text-slate-700">
              {filtered.length} expense{filtered.length !== 1 ? 's' : ''}
            </span>
            <span className="text-sm font-bold text-amber-700">Total: {formatCurrency(totalAmount)}</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Date</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Category</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Amount</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Note</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filtered.map((exp) => (
                  <tr key={exp.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3 text-slate-600">
                      <div className="flex items-center gap-1.5">
                        <Calendar className="w-3.5 h-3.5 text-slate-400" /> {formatDate(exp.expense_date)}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 bg-amber-100 text-amber-800 rounded-full text-xs font-semibold">
                        <Tag className="w-3 h-3" /> {getCategoryName(exp)}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-bold text-amber-700">{formatCurrency(exp.amount)}</td>
                    <td className="px-4 py-3 text-slate-500 text-xs max-w-xs truncate">{exp.note || '—'}</td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => setDeleteTarget(exp)}
                        className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition"
                        title="Delete expense"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Log Expense Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-amber-100 flex items-center justify-center">
                  <Wallet className="w-5 h-5 text-amber-700" />
                </div>
                <div>
                  <h2 className="font-bold text-slate-900">Log Farm Expense</h2>
                  <p className="text-xs text-slate-500">Record a farm operating cost</p>
                </div>
              </div>
              <button onClick={() => setShowForm(false)} className="p-1.5 hover:bg-slate-100 rounded-lg transition">
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>
            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Category <span className="text-rose-500">*</span></label>
                  <select
                    required
                    value={form.category_id}
                    onChange={(e) => setForm({ ...form, category_id: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400 bg-white"
                  >
                    {categories.map((c) => (
                      <option key={c.id} value={String(c.id)}>{capitalize(c.name)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Date <span className="text-rose-500">*</span></label>
                  <input
                    required
                    type="date"
                    value={form.expense_date}
                    max={today}
                    onChange={(e) => setForm({ ...form, expense_date: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Amount (₹) <span className="text-rose-500">*</span></label>
                <input
                  required
                  type="number"
                  min="0.01"
                  step="0.01"
                  placeholder="e.g. 900.00"
                  value={form.amount}
                  onChange={(e) => setForm({ ...form, amount: e.target.value })}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Note</label>
                <textarea
                  rows={2}
                  placeholder="e.g. Cattle feed pellets from Anand Market"
                  value={form.note}
                  onChange={(e) => setForm({ ...form, note: e.target.value })}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400 resize-none"
                />
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={() => setShowForm(false)} className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition">
                  Cancel
                </button>
                <button type="submit" disabled={formLoading} className="px-4 py-2 text-sm font-semibold text-white bg-amber-500 hover:bg-amber-600 rounded-lg transition disabled:opacity-60">
                  {formLoading ? 'Logging…' : 'Log Expense'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <ConfirmModal
        isOpen={!!deleteTarget}
        title="Delete Expense"
        message={`Delete this expense of ${formatCurrency(deleteTarget?.amount)} for ${getCategoryName(deleteTarget)} on ${formatDate(deleteTarget?.expense_date)}?`}
        confirmText="Delete"
        confirmVariant="danger"
        onConfirm={handleDelete}
        onClose={() => setDeleteTarget(null)}
      />
    </div>
  );
}
