import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'react-toastify';
import { useAuth } from '../../hooks/useAuth';
import {
  getBuffaloes,
  getBuffaloCount,
  createBuffalo,
  updateBuffalo,
  deleteBuffalo,
} from '../../api/buffaloes';
import { formatDate, getTodayKolkataDate } from '../../utils/formatters';
import PageHeader from '../../components/PageHeader';
import ConfirmModal from '../../components/ConfirmModal';
import EmptyState from '../../components/EmptyState';
import LoadingSpinner from '../../components/LoadingSpinner';
import ErrorAlert from '../../components/ErrorAlert';
import {
  Plus,
  Trash2,
  Pencil,
  PawPrint,
  Filter,
  Search,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  X,
  Tag,
  Calendar,
  Dna,
  CheckCircle2,
  AlertCircle,
  ZapOff,
  Skull,
  RefreshCw,
} from 'lucide-react';

const PAGE_SIZE = 20;

const STATUS_CONFIG = {
  active: { label: 'Active', color: 'bg-emerald-100 text-emerald-800', icon: CheckCircle2 },
  dry: { label: 'Dry', color: 'bg-amber-100 text-amber-800', icon: ZapOff },
  sold: { label: 'Sold', color: 'bg-sky-100 text-sky-800', icon: AlertCircle },
  dead: { label: 'Dead', color: 'bg-slate-100 text-slate-600', icon: Skull },
};

const BREEDS = [
  'Murrah',
  'Surti',
  'Jaffarabadi',
  'Nili-Ravi',
  'Bhadawari',
  'Mehsana',
  'Mehsani',
  'Pandharpuri',
  'Other',
];

const EMPTY_FORM = {
  tag_no: '',
  name: '',
  breed: 'Murrah',
  dob: '',
  purchase_date: '',
  status: 'active',
};

function StatusBadge({ status }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.active;
  const Icon = config.icon;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${config.color}`}
    >
      <Icon className="h-3 w-3" />
      {config.label}
    </span>
  );
}

function buildFormFromBuffalo(buffalo) {
  return {
    tag_no: buffalo?.tag_no || '',
    name: buffalo?.name || '',
    breed: buffalo?.breed || 'Murrah',
    dob: buffalo?.dob || '',
    purchase_date: buffalo?.purchase_date || '',
    status: buffalo?.status || 'active',
  };
}

export default function Buffaloes() {
  const { isAdmin } = useAuth();
  const [buffaloes, setBuffaloes] = useState([]);
  const [counts, setCounts] = useState(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [refreshToken, setRefreshToken] = useState(0);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState('');
  const [formLoading, setFormLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const requestSequence = useRef(0);

  const listParams = useMemo(
    () => ({
      page,
      page_size: PAGE_SIZE,
      ...(debouncedSearch ? { search: debouncedSearch } : {}),
      ...(statusFilter !== 'all' ? { status: statusFilter } : {}),
    }),
    [page, debouncedSearch, statusFilter]
  );

  const loadBuffaloes = useCallback((params) => {
    const sequence = ++requestSequence.current;

    return getBuffaloes(params)
      .then((response) => {
        if (sequence !== requestSequence.current) return;
        setBuffaloes(response?.items || []);
        setTotal(Number(response?.total) || 0);
        setError(null);
      })
      .catch((err) => {
        if (sequence !== requestSequence.current) return;
        setError(err);
      })
      .finally(() => {
        if (sequence === requestSequence.current) setLoading(false);
      });
  }, []);

  const loadCounts = useCallback(() => {
    return getBuffaloCount()
      .then((response) => setCounts(response || null))
      .catch(() => setCounts(null));
  }, []);

  useEffect(() => {
    loadBuffaloes(listParams);
  }, [loadBuffaloes, listParams, refreshToken]);

  useEffect(() => {
    loadCounts();
  }, [loadCounts]);

  useEffect(() => {
    const nextSearch = search.trim();
    if (nextSearch === debouncedSearch) return undefined;

    const timer = setTimeout(() => {
      setLoading(true);
      setPage(1);
      setDebouncedSearch(nextSearch);
    }, 350);

    return () => clearTimeout(timer);
  }, [search, debouncedSearch]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const firstVisible = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const lastVisible = Math.min(page * PAGE_SIZE, total);
  const isFiltered = Boolean(debouncedSearch) || statusFilter !== 'all';

  const refreshData = ({ resetPage = false } = {}) => {
    setLoading(true);
    if (resetPage && page !== 1) setPage(1);
    setRefreshToken((token) => token + 1);
    loadCounts();
  };

  const handleRetry = () => {
    refreshData();
  };

  const handleStatusFilter = (nextStatus) => {
    setStatusFilter(nextStatus);
    setPage(1);
    setLoading(true);
  };

  const handleStatusCardClick = (status) => {
    handleStatusFilter(statusFilter === status ? 'all' : status);
  };

  const goToPage = (nextPage) => {
    if (nextPage < 1 || nextPage > totalPages || nextPage === page) return;
    setPage(nextPage);
    setLoading(true);
  };

  const openCreateForm = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError('');
    setShowForm(true);
  };

  const openEditForm = (buffalo) => {
    setEditing(buffalo);
    setForm(buildFormFromBuffalo(buffalo));
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
    if (!form.tag_no.trim()) return 'Tag number is required.';
    if (!form.breed.trim()) return 'Breed is required.';

    const today = getTodayKolkataDate();
    if (form.dob && form.dob > today) {
      return 'Date of birth cannot be in the future.';
    }
    if (form.purchase_date && form.purchase_date > today) {
      return 'Purchase date cannot be in the future.';
    }
    if (form.dob && form.purchase_date && form.purchase_date < form.dob) {
      return 'Purchase date cannot be earlier than the date of birth.';
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

    const payload = {
      tag_no: form.tag_no.trim(),
      name: form.name.trim() || undefined,
      breed: form.breed.trim(),
      dob: form.dob || undefined,
      purchase_date: form.purchase_date || undefined,
      status: form.status,
    };

    setFormLoading(true);
    setFormError('');

    try {
      if (editing) {
        await updateBuffalo(editing.id, payload);
        toast.success(`Buffalo ${payload.tag_no} updated.`);
      } else {
        await createBuffalo(payload);
        toast.success('Buffalo registered successfully!');
      }

      setShowForm(false);
      setEditing(null);
      setForm(EMPTY_FORM);
      refreshData({ resetPage: !editing });
    } catch (err) {
      setFormError(err?.message || 'Failed to save buffalo.');
    } finally {
      setFormLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;

    setDeleteLoading(true);
    try {
      await deleteBuffalo(deleteTarget.id);
      toast.success(`Buffalo ${deleteTarget.tag_no} deleted.`);
      setDeleteTarget(null);

      if (buffaloes.length === 1 && page > 1) {
        setPage(page - 1);
        setLoading(true);
        loadCounts();
      } else {
        refreshData();
      }
    } catch (err) {
      toast.error(err?.message || 'Failed to delete buffalo.');
    } finally {
      setDeleteLoading(false);
    }
  };

  const countValue = (status) => {
    if (!counts || counts[status] === null || counts[status] === undefined) return '—';
    return counts[status];
  };

  return (
    <div>
      <PageHeader
        title="Buffalo Herd Management"
        subtitle="Track and manage your entire buffalo herd — active, dry, sold, and deceased animals."
      >
        <button
          type="button"
          onClick={openCreateForm}
          className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700"
        >
          <Plus className="h-4 w-4" /> Add Buffalo
        </button>
      </PageHeader>

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {Object.entries(STATUS_CONFIG).map(([status, config]) => {
          const Icon = config.icon;
          const selected = statusFilter === status;
          return (
            <button
              key={status}
              type="button"
              onClick={() => handleStatusCardClick(status)}
              aria-pressed={selected}
              className={`flex items-center gap-3 rounded-xl border p-3 text-left transition ${
                selected
                  ? 'border-emerald-400 bg-emerald-50 shadow-sm'
                  : 'border-slate-200 bg-white hover:border-slate-300'
              }`}
            >
              <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${config.color}`}>
                <Icon className="h-4 w-4" />
              </div>
              <div>
                <p className="text-lg font-bold text-slate-800">{countValue(status)}</p>
                <p className="text-xs text-slate-500">{config.label}</p>
              </div>
            </button>
          );
        })}
      </div>

      <div className="mb-5 flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search by tag, name, or breed…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
          />
        </div>
        <div className="relative">
          <Filter className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <select
            value={statusFilter}
            onChange={(event) => handleStatusFilter(event.target.value)}
            className="cursor-pointer appearance-none rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
          >
            <option value="all">All Status</option>
            {Object.entries(STATUS_CONFIG).map(([status, config]) => (
              <option key={status} value={status}>
                {config.label}
              </option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        </div>
        <button
          type="button"
          onClick={handleRetry}
          disabled={loading}
          className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-60"
          title="Refresh herd list"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          <span className="hidden sm:inline">Refresh</span>
        </button>
      </div>

      {error && <ErrorAlert error={error} onRetry={handleRetry} />}

      {loading ? (
        <LoadingSpinner message="Loading buffalo herd…" />
      ) : error ? null : buffaloes.length === 0 ? (
        <EmptyState
          icon={PawPrint}
          title="No buffaloes found"
          description={
            isFiltered
              ? 'Try adjusting your search or status filter.'
              : 'Register your first buffalo to get started.'
          }
          action={
            !isFiltered && (
              <button
                type="button"
                onClick={openCreateForm}
                className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700"
              >
                <Plus className="h-4 w-4" /> Add Buffalo
              </button>
            )
          }
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-slate-500">
                    Tag No.
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-slate-500">
                    Name
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-slate-500">
                    Breed
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-slate-500">
                    Date of Birth
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-slate-500">
                    Purchase Date
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-slate-500">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-slate-500">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {buffaloes.map((buffalo) => (
                  <tr key={buffalo.id} className="transition-colors hover:bg-slate-50">
                    <td className="px-4 py-3 font-mono font-semibold text-emerald-700">
                      <div className="flex items-center gap-1.5">
                        <Tag className="h-3.5 w-3.5" /> {buffalo.tag_no}
                      </div>
                    </td>
                    <td className="px-4 py-3 font-medium text-slate-800">
                      {buffalo.name || <span className="italic text-slate-400">Unnamed</span>}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5 text-slate-700">
                        <Dna className="h-3.5 w-3.5 text-slate-400" /> {buffalo.breed || '—'}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      <div className="flex items-center gap-1.5">
                        <Calendar className="h-3.5 w-3.5 text-slate-400" /> {formatDate(buffalo.dob)}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {formatDate(buffalo.purchase_date)}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={buffalo.status} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => openEditForm(buffalo)}
                          className="rounded-lg p-1.5 text-slate-400 transition hover:bg-emerald-50 hover:text-emerald-700"
                          title={`Edit ${buffalo.tag_no}`}
                          aria-label={`Edit buffalo ${buffalo.tag_no}`}
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        {isAdmin && (
                          <button
                            type="button"
                            onClick={() => setDeleteTarget(buffalo)}
                            className="rounded-lg p-1.5 text-slate-400 transition hover:bg-rose-50 hover:text-rose-600"
                            title={`Delete ${buffalo.tag_no}`}
                            aria-label={`Delete buffalo ${buffalo.tag_no}`}
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col items-center justify-between gap-3 border-t border-slate-100 bg-slate-50 px-4 py-3 text-xs text-slate-500 sm:flex-row">
            <span>
              Showing {firstVisible}–{lastVisible} of {total} animals
              {counts?.total !== undefined && ` (${counts.total} total registered)`}
            </span>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => goToPage(page - 1)}
                disabled={page <= 1}
                className="rounded-lg border border-slate-200 bg-white p-1.5 text-slate-600 transition hover:bg-slate-100 disabled:opacity-40"
                aria-label="Previous page"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <span className="px-2 font-semibold text-slate-700">
                Page {page} of {totalPages}
              </span>
              <button
                type="button"
                onClick={() => goToPage(page + 1)}
                disabled={page >= totalPages}
                className="rounded-lg border border-slate-200 bg-white p-1.5 text-slate-600 transition hover:bg-slate-100 disabled:opacity-40"
                aria-label="Next page"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="buffalo-form-title"
            className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white shadow-2xl"
          >
            <div className="flex items-center justify-between border-b border-slate-100 p-6">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-100">
                  <PawPrint className="h-5 w-5 text-emerald-700" />
                </div>
                <div>
                  <h2 id="buffalo-form-title" className="font-bold text-slate-900">
                    {editing ? 'Edit Buffalo' : 'Register New Buffalo'}
                  </h2>
                  <p className="text-xs text-slate-500">
                    {editing
                      ? `Update details for ${editing.tag_no}`
                      : 'Add a buffalo to your herd register'}
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
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="buffalo-tag" className="mb-1 block text-xs font-semibold text-slate-700">
                    Tag Number <span className="text-rose-500">*</span>
                  </label>
                  <input
                    id="buffalo-tag"
                    required
                    type="text"
                    placeholder="e.g. BUF-042"
                    value={form.tag_no}
                    onChange={(event) => updateFormField('tag_no', event.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
                  />
                </div>
                <div>
                  <label htmlFor="buffalo-name" className="mb-1 block text-xs font-semibold text-slate-700">
                    Name
                  </label>
                  <input
                    id="buffalo-name"
                    type="text"
                    placeholder="e.g. Gauri"
                    value={form.name}
                    onChange={(event) => updateFormField('name', event.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="buffalo-breed" className="mb-1 block text-xs font-semibold text-slate-700">
                    Breed <span className="text-rose-500">*</span>
                  </label>
                  <input
                    id="buffalo-breed"
                    required
                    list="buffalo-breeds"
                    placeholder="e.g. Murrah"
                    value={form.breed}
                    onChange={(event) => updateFormField('breed', event.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
                  />
                  <datalist id="buffalo-breeds">
                    {BREEDS.map((breed) => (
                      <option key={breed} value={breed} />
                    ))}
                  </datalist>
                </div>
                <div>
                  <label htmlFor="buffalo-status" className="mb-1 block text-xs font-semibold text-slate-700">
                    Status
                  </label>
                  <select
                    id="buffalo-status"
                    value={form.status}
                    onChange={(event) => updateFormField('status', event.target.value)}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
                  >
                    {Object.entries(STATUS_CONFIG).map(([status, config]) => (
                      <option key={status} value={status}>
                        {config.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="buffalo-dob" className="mb-1 block text-xs font-semibold text-slate-700">
                    Date of Birth
                  </label>
                  <input
                    id="buffalo-dob"
                    type="date"
                    max={getTodayKolkataDate()}
                    value={form.dob}
                    onChange={(event) => updateFormField('dob', event.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
                  />
                </div>
                <div>
                  <label htmlFor="buffalo-purchase" className="mb-1 block text-xs font-semibold text-slate-700">
                    Purchase Date
                  </label>
                  <input
                    id="buffalo-purchase"
                    type="date"
                    max={getTodayKolkataDate()}
                    value={form.purchase_date}
                    onChange={(event) => updateFormField('purchase_date', event.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
                  />
                </div>
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
                  {formLoading
                    ? 'Saving…'
                    : editing
                      ? 'Save Changes'
                      : 'Register Buffalo'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <ConfirmModal
        isOpen={Boolean(deleteTarget)}
        title="Delete Buffalo"
        message={`Delete buffalo ${deleteTarget?.tag_no}${
          deleteTarget?.name ? ` (${deleteTarget.name})` : ''
        }? This removes it from the active herd register; historical records are retained.`}
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
