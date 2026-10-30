import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'react-toastify';
import { useAuth } from '../../hooks/useAuth';
import {
  getCustomers,
  createCustomer,
  updateCustomer,
  deleteCustomer,
  getCustomerBalance,
} from '../../api/customers';
import { getSales } from '../../api/sales';
import { formatCurrency, formatDate, formatLitres } from '../../utils/formatters';
import PageHeader from '../../components/PageHeader';
import ConfirmModal from '../../components/ConfirmModal';
import EmptyState from '../../components/EmptyState';
import LoadingSpinner from '../../components/LoadingSpinner';
import ErrorAlert from '../../components/ErrorAlert';
import {
  Users,
  Plus,
  Trash2,
  Search,
  Phone,
  MapPin,
  X,
  CheckCircle2,
  XCircle,
  IndianRupee,
  Pencil,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  Wallet,
  ReceiptText,
  AlertCircle,
} from 'lucide-react';

const FETCH_PAGE_SIZE = 100;
const LIST_PAGE_SIZE = 20;

const EMPTY_FORM = {
  name: '',
  phone: '',
  address: '',
  rate_per_litre: '',
  is_active: true,
};

function buildFormFromCustomer(customer) {
  return {
    name: customer?.name || '',
    phone: customer?.phone || '',
    address: customer?.address || '',
    rate_per_litre: customer?.rate_per_litre ?? '',
    is_active: customer?.is_active ?? true,
  };
}

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

function CustomerStatus({ active }) {
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-semibold ${
        active ? 'text-emerald-600' : 'text-slate-400'
      }`}
    >
      {active ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
      {active ? 'Active' : 'Inactive'}
    </span>
  );
}

export default function Customers() {
  const { isAdmin } = useAuth();
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [page, setPage] = useState(1);
  const [refreshToken, setRefreshToken] = useState(0);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState('');
  const [formLoading, setFormLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [detailTarget, setDetailTarget] = useState(null);
  const [detailData, setDetailData] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const listRequestSequence = useRef(0);
  const detailRequestSequence = useRef(0);

  const loadCustomers = useCallback(() => {
    const sequence = ++listRequestSequence.current;

    return fetchAllCustomers()
      .then((items) => {
        if (sequence !== listRequestSequence.current) return;
        setCustomers(items);
        setError(null);
      })
      .catch((err) => {
        if (sequence !== listRequestSequence.current) return;
        setError(err);
      })
      .finally(() => {
        if (sequence === listRequestSequence.current) setLoading(false);
      });
  }, []);

  useEffect(() => {
    loadCustomers();
  }, [loadCustomers, refreshToken]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();

    return customers.filter((customer) => {
      const matchesStatus =
        statusFilter === 'all'
          ? true
          : statusFilter === 'active'
            ? customer.is_active
            : !customer.is_active;
      if (!matchesStatus) return false;
      if (!query) return true;

      return (
        customer.name?.toLowerCase().includes(query) ||
        customer.phone?.toLowerCase().includes(query) ||
        customer.address?.toLowerCase().includes(query)
      );
    });
  }, [customers, search, statusFilter]);

  const activeCount = customers.filter((customer) => customer.is_active).length;
  const inactiveCount = customers.length - activeCount;
  const totalPages = Math.max(1, Math.ceil(filtered.length / LIST_PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const firstIndex = (currentPage - 1) * LIST_PAGE_SIZE;
  const pageCustomers = filtered.slice(firstIndex, firstIndex + LIST_PAGE_SIZE);
  const firstVisible = filtered.length === 0 ? 0 : firstIndex + 1;
  const lastVisible = Math.min(firstIndex + LIST_PAGE_SIZE, filtered.length);
  const isFiltered = Boolean(search.trim()) || statusFilter !== 'all';

  const refreshCustomers = ({ showLoading = true } = {}) => {
    if (showLoading) setLoading(true);
    setRefreshToken((token) => token + 1);
  };

  const handleRetry = () => {
    refreshCustomers();
  };

  const handleSearchChange = (value) => {
    setSearch(value);
    setPage(1);
  };

  const handleStatusFilter = (value) => {
    setStatusFilter(value);
    setPage(1);
  };

  const goToPage = (nextPage) => {
    if (nextPage < 1 || nextPage > totalPages || nextPage === currentPage) return;
    setPage(nextPage);
  };

  const openCreateForm = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError('');
    setShowForm(true);
  };

  const openEditForm = (customer) => {
    setEditing(customer);
    setForm(buildFormFromCustomer(customer));
    setFormError('');
    setShowForm(true);
  };

  const closeForm = () => {
    if (formLoading) return;
    setShowForm(false);
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError('');
  };

  const updateFormField = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
    if (formError) setFormError('');
  };

  const validateForm = () => {
    const name = form.name.trim();
    if (!name) return 'Customer name is required.';
    if (name.length > 100) return 'Customer name must be 100 characters or fewer.';

    const rate = Number(form.rate_per_litre);
    if (!Number.isFinite(rate) || rate <= 0) {
      return 'Enter a rate per litre greater than zero.';
    }

    const phone = form.phone.trim();
    const phoneDigits = phone.replace(/\D/g, '');
    if (
      phone &&
      (!/^\+?[\d\s\-()]+$/.test(phone) || phoneDigits.length < 6 || phoneDigits.length > 15)
    ) {
      return 'Enter a valid phone number using 6-15 digits, spaces, hyphens, or parentheses.';
    }
    if (form.address.trim().length > 255) {
      return 'Address must be 255 characters or fewer.';
    }

    return '';
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    const validationError = validateForm();
    if (validationError) {
      setFormError(validationError);
      return;
    }

    const rate = Number(form.rate_per_litre);
    const payload = {
      name: form.name.trim(),
      phone: form.phone.trim() || null,
      address: form.address.trim() || null,
      rate_per_litre: rate.toFixed(2),
      is_active: form.is_active,
    };

    setFormLoading(true);
    setFormError('');

    try {
      if (editing) {
        await updateCustomer(editing.id, payload);
        toast.success(`Customer "${payload.name}" updated.`);
      } else {
        await createCustomer(payload);
        toast.success('Customer registered successfully.');
        setPage(1);
      }

      setShowForm(false);
      setEditing(null);
      setForm(EMPTY_FORM);
      refreshCustomers();
    } catch (err) {
      setFormError(err?.message || 'Failed to save customer.');
    } finally {
      setFormLoading(false);
    }
  };

  const loadDetails = useCallback(async (customer) => {
    const sequence = ++detailRequestSequence.current;
    setDetailLoading(true);
    setDetailError(null);

    try {
      const [balance, salesResponse] = await Promise.all([
        getCustomerBalance(customer.id),
        getSales({ customer_id: customer.id, page_size: 10 }),
      ]);

      if (sequence !== detailRequestSequence.current) return;
      setDetailData({ balance, sales: salesResponse?.items || [] });
    } catch (err) {
      if (sequence !== detailRequestSequence.current) return;
      setDetailData(null);
      setDetailError(err);
    } finally {
      if (sequence === detailRequestSequence.current) setDetailLoading(false);
    }
  }, []);

  const openDetails = (customer) => {
    setDetailTarget(customer);
    setDetailData(null);
    loadDetails(customer);
  };

  const closeDetails = () => {
    detailRequestSequence.current += 1;
    setDetailTarget(null);
    setDetailData(null);
    setDetailError(null);
    setDetailLoading(false);
  };

  const handleDelete = async () => {
    if (!deleteTarget || deleteLoading) return;

    setDeleteLoading(true);
    try {
      await deleteCustomer(deleteTarget.id);
      toast.success(`Customer "${deleteTarget.name}" deleted.`);
      setDeleteTarget(null);

      if (pageCustomers.length === 1 && currentPage > 1) {
        setPage(currentPage - 1);
      }
      refreshCustomers();
    } catch (err) {
      toast.error(err?.message || 'Failed to delete customer.');
    } finally {
      setDeleteLoading(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Customer Accounts"
        subtitle="Manage milk buyers, contact details, per-litre pricing, and outstanding balances."
      >
        <button
          type="button"
          onClick={openCreateForm}
          className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700"
        >
          <Plus className="h-4 w-4" /> Add Customer
        </button>
      </PageHeader>

      <div className="mb-5 flex flex-wrap gap-3">
        {[
          { key: 'all', label: `All (${customers.length})` },
          { key: 'active', label: `Active (${activeCount})` },
          { key: 'inactive', label: `Inactive (${inactiveCount})` },
        ].map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => handleStatusFilter(key)}
            aria-pressed={statusFilter === key}
            className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
              statusFilter === key
                ? 'bg-emerald-600 text-white shadow-sm'
                : 'border border-slate-200 bg-white text-slate-600 hover:border-emerald-300'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="mb-5 flex gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search by name, phone, or address..."
            value={search}
            onChange={(event) => handleSearchChange(event.target.value)}
            className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
          />
        </div>
        <button
          type="button"
          onClick={handleRetry}
          disabled={loading}
          className="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-60"
          title="Refresh customer list"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          <span className="hidden sm:inline">Refresh</span>
        </button>
      </div>

      {loading ? (
        <LoadingSpinner message="Loading customers..." />
      ) : error ? (
        <ErrorAlert error={error} onRetry={handleRetry} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No customers found"
          description={
            isFiltered
              ? 'Try adjusting your search or status filter.'
              : 'Add your first customer to get started.'
          }
          action={
            !isFiltered && (
              <button
                type="button"
                onClick={openCreateForm}
                className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700"
              >
                <Plus className="h-4 w-4" /> Add Customer
              </button>
            )
          }
        />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {pageCustomers.map((customer) => (
              <div
                key={customer.id}
                className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md"
              >
                <div className="mb-3 flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-3">
                    <div
                      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-bold ${
                        customer.is_active
                          ? 'bg-emerald-100 text-emerald-800'
                          : 'bg-slate-100 text-slate-500'
                      }`}
                    >
                      {customer.name?.charAt(0)?.toUpperCase() || 'C'}
                    </div>
                    <div className="min-w-0">
                      <h3 className="truncate text-sm font-semibold text-slate-800">
                        {customer.name}
                      </h3>
                      <CustomerStatus active={customer.is_active} />
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      type="button"
                      onClick={() => openEditForm(customer)}
                      className="rounded-lg p-1.5 text-slate-400 transition hover:bg-emerald-50 hover:text-emerald-700"
                      title={`Edit ${customer.name}`}
                      aria-label={`Edit customer ${customer.name}`}
                    >
                      <Pencil className="h-4 w-4" />
                    </button>
                    {isAdmin && (
                      <button
                        type="button"
                        onClick={() => setDeleteTarget(customer)}
                        className="rounded-lg p-1.5 text-slate-400 transition hover:bg-rose-50 hover:text-rose-600"
                        title={`Delete ${customer.name}`}
                        aria-label={`Delete customer ${customer.name}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>

                <div className="space-y-1.5 text-xs text-slate-600">
                  {customer.phone ? (
                    <div className="flex items-center gap-2">
                      <Phone className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                      <span className="truncate">{customer.phone}</span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 text-slate-400">
                      <Phone className="h-3.5 w-3.5 shrink-0" />
                      <span>No phone</span>
                    </div>
                  )}
                  {customer.address ? (
                    <div className="flex items-start gap-2">
                      <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
                      <span className="line-clamp-2">{customer.address}</span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 text-slate-400">
                      <MapPin className="h-3.5 w-3.5 shrink-0" />
                      <span>No address</span>
                    </div>
                  )}
                  <div className="mt-2 flex items-center gap-2 border-t border-slate-100 pt-2">
                    <IndianRupee className="h-3.5 w-3.5 text-emerald-600" />
                    <span className="font-bold text-emerald-700">
                      {formatCurrency(customer.rate_per_litre)}/L
                    </span>
                    <span className="text-slate-400">per litre</span>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => openDetails(customer)}
                  className="mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-700 transition hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-700"
                >
                  <ReceiptText className="h-3.5 w-3.5" /> Balance &amp; history
                </button>
              </div>
            ))}
          </div>

          <div className="mt-5 flex flex-col items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs text-slate-500 sm:flex-row">
            <span>
              Showing {firstVisible}-{lastVisible} of {filtered.length} customers
              {isFiltered && ` (${customers.length} total)`}
            </span>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => goToPage(currentPage - 1)}
                disabled={currentPage <= 1}
                className="rounded-lg border border-slate-200 bg-white p-1.5 text-slate-600 transition hover:bg-slate-100 disabled:opacity-40"
                aria-label="Previous page"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <span className="px-2 font-semibold text-slate-700">
                Page {currentPage} of {totalPages}
              </span>
              <button
                type="button"
                onClick={() => goToPage(currentPage + 1)}
                disabled={currentPage >= totalPages}
                className="rounded-lg border border-slate-200 bg-white p-1.5 text-slate-600 transition hover:bg-slate-100 disabled:opacity-40"
                aria-label="Next page"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </>
      )}

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="customer-form-title"
            className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-2xl bg-white shadow-2xl"
          >
            <div className="flex items-center justify-between border-b border-slate-100 p-6">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-100">
                  <Users className="h-5 w-5 text-emerald-700" />
                </div>
                <div>
                  <h2 id="customer-form-title" className="font-bold text-slate-900">
                    {editing ? 'Edit Customer' : 'Register Customer'}
                  </h2>
                  <p className="text-xs text-slate-500">
                    {editing
                      ? `Update details for ${editing.name}`
                      : 'Add a new milk buyer account'}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={closeForm}
                disabled={formLoading}
                className="rounded-lg p-1.5 transition hover:bg-slate-100 disabled:opacity-50"
                aria-label="Close form"
              >
                <X className="h-5 w-5 text-slate-500" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4 p-6">
              <div>
                <label htmlFor="customer-name" className="mb-1 block text-xs font-semibold text-slate-700">
                  Full Name <span className="text-rose-500">*</span>
                </label>
                <input
                  id="customer-name"
                  required
                  type="text"
                  maxLength={100}
                  placeholder="e.g. Aarav Sharma"
                  value={form.name}
                  onChange={(event) => updateFormField('name', event.target.value)}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
                />
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="customer-phone" className="mb-1 block text-xs font-semibold text-slate-700">
                    Phone
                  </label>
                  <input
                    id="customer-phone"
                    type="tel"
                    maxLength={20}
                    placeholder="e.g. 9876543210"
                    value={form.phone}
                    onChange={(event) => updateFormField('phone', event.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
                  />
                </div>
                <div>
                  <label htmlFor="customer-rate" className="mb-1 block text-xs font-semibold text-slate-700">
                    Rate per Litre (INR) <span className="text-rose-500">*</span>
                  </label>
                  <input
                    id="customer-rate"
                    required
                    type="number"
                    min="0.01"
                    step="0.01"
                    placeholder="e.g. 60.00"
                    value={form.rate_per_litre}
                    onChange={(event) => updateFormField('rate_per_litre', event.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
                  />
                </div>
              </div>

              <div>
                <label htmlFor="customer-address" className="mb-1 block text-xs font-semibold text-slate-700">
                  Address
                </label>
                <textarea
                  id="customer-address"
                  rows={2}
                  maxLength={255}
                  placeholder="e.g. Station Road, Anand"
                  value={form.address}
                  onChange={(event) => updateFormField('address', event.target.value)}
                  className="w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
                />
              </div>

              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="customer-active"
                  checked={form.is_active}
                  onChange={(event) => updateFormField('is_active', event.target.checked)}
                  className="h-4 w-4 rounded text-emerald-600"
                />
                <label htmlFor="customer-active" className="text-xs font-semibold text-slate-700">
                  Active customer (available for new sales)
                </label>
              </div>

              {formError && (
                <div
                  role="alert"
                  className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800"
                >
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />
                  <span>{formError}</span>
                </div>
              )}

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={closeForm}
                  disabled={formLoading}
                  className="rounded-lg bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-200 disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={formLoading}
                  className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-60"
                >
                  {formLoading ? 'Saving...' : editing ? 'Save Changes' : 'Register Customer'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {detailTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="customer-detail-title"
            className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
          >
            <div className="flex items-start justify-between border-b border-slate-100 p-5 sm:p-6">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-base font-bold text-emerald-800">
                  {detailTarget.name?.charAt(0)?.toUpperCase() || 'C'}
                </div>
                <div className="min-w-0">
                  <h2 id="customer-detail-title" className="truncate text-lg font-bold text-slate-900">
                    {detailTarget.name}
                  </h2>
                  <CustomerStatus active={detailTarget.is_active} />
                </div>
              </div>
              <button
                type="button"
                onClick={closeDetails}
                className="rounded-lg p-1.5 transition hover:bg-slate-100"
                aria-label="Close customer details"
              >
                <X className="h-5 w-5 text-slate-500" />
              </button>
            </div>

            <div className="overflow-y-auto p-5 sm:p-6">
              <div className="mb-5 flex flex-wrap gap-x-5 gap-y-2 text-xs text-slate-600">
                <span className="inline-flex items-center gap-1.5">
                  <Phone className="h-3.5 w-3.5 text-slate-400" />
                  {detailTarget.phone || 'No phone'}
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <MapPin className="h-3.5 w-3.5 text-slate-400" />
                  {detailTarget.address || 'No address'}
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <IndianRupee className="h-3.5 w-3.5 text-emerald-600" />
                  {formatCurrency(detailTarget.rate_per_litre)}/L
                </span>
              </div>

              {detailLoading ? (
                <LoadingSpinner message="Loading balance and sales..." />
              ) : detailError ? (
                <ErrorAlert
                  error={detailError}
                  onRetry={() => loadDetails(detailTarget)}
                />
              ) : detailData ? (
                <>
                  <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Total billed
                      </p>
                      <p className="mt-1 text-lg font-bold text-slate-800">
                        {formatCurrency(detailData.balance?.total_sales_amount)}
                      </p>
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Total paid
                      </p>
                      <p className="mt-1 text-lg font-bold text-emerald-700">
                        {formatCurrency(detailData.balance?.total_paid_amount)}
                      </p>
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Outstanding
                      </p>
                      <p
                        className={`mt-1 text-lg font-bold ${
                          Number(detailData.balance?.outstanding_balance) > 0
                            ? 'text-rose-600'
                            : 'text-emerald-700'
                        }`}
                      >
                        {formatCurrency(detailData.balance?.outstanding_balance)}
                      </p>
                    </div>
                  </div>

                  <div className="mb-3 flex items-center gap-2">
                    <Wallet className="h-4 w-4 text-slate-400" />
                    <h3 className="text-sm font-bold text-slate-800">Recent sales</h3>
                  </div>

                  {detailData.sales.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
                      No sales recorded for this customer yet.
                    </div>
                  ) : (
                    <div className="overflow-x-auto rounded-xl border border-slate-200">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-slate-100 bg-slate-50">
                            <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wide text-slate-500">
                              Date
                            </th>
                            <th className="px-3 py-2.5 text-right text-xs font-bold uppercase tracking-wide text-slate-500">
                              Litres
                            </th>
                            <th className="px-3 py-2.5 text-right text-xs font-bold uppercase tracking-wide text-slate-500">
                              Rate
                            </th>
                            <th className="px-3 py-2.5 text-right text-xs font-bold uppercase tracking-wide text-slate-500">
                              Amount
                            </th>
                            <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wide text-slate-500">
                              Payment
                            </th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-50">
                          {detailData.sales.map((sale) => (
                            <tr key={sale.id}>
                              <td className="whitespace-nowrap px-3 py-2.5 text-slate-600">
                                {formatDate(sale.sale_date)}
                              </td>
                              <td className="whitespace-nowrap px-3 py-2.5 text-right text-slate-700">
                                {formatLitres(sale.litres)}
                              </td>
                              <td className="whitespace-nowrap px-3 py-2.5 text-right text-slate-600">
                                {formatCurrency(sale.rate)}
                              </td>
                              <td className="whitespace-nowrap px-3 py-2.5 text-right font-semibold text-slate-800">
                                {formatCurrency(sale.amount)}
                              </td>
                              <td className="whitespace-nowrap px-3 py-2.5">
                                <span
                                  className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${
                                    sale.payment_status === 'paid'
                                      ? 'bg-emerald-100 text-emerald-800'
                                      : 'bg-amber-100 text-amber-800'
                                  }`}
                                >
                                  {sale.payment_status === 'paid' ? 'Paid' : 'Unpaid'}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              ) : null}
            </div>

            <div className="flex justify-end gap-3 border-t border-slate-100 bg-slate-50 p-4 sm:px-6">
              <button
                type="button"
                onClick={closeDetails}
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
              >
                Close
              </button>
              <button
                type="button"
                onClick={() => {
                  const customer = detailTarget;
                  closeDetails();
                  openEditForm(customer);
                }}
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700"
              >
                <Pencil className="h-4 w-4" /> Edit Customer
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmModal
        isOpen={Boolean(deleteTarget)}
        title="Delete Customer"
        message={`Delete customer "${deleteTarget?.name}"? They will be hidden from customer lists and cannot receive new sales. Historical sales and invoices are retained.`}
        confirmText="Delete"
        confirmVariant="danger"
        isLoading={deleteLoading}
        onConfirm={handleDelete}
        onClose={() => {
          if (!deleteLoading) setDeleteTarget(null);
        }}
      />
    </div>
  );
}
