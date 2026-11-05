import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  Eye,
  Filter,
  Globe,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Target,
  User,
  X,
} from 'lucide-react';
import {
  getSecurityAuditEvent,
  getSecurityAuditEvents,
} from '../../api/securityAudit';
import PageHeader from '../../components/PageHeader';
import EmptyState from '../../components/EmptyState';
import LoadingSpinner from '../../components/LoadingSpinner';
import ErrorAlert from '../../components/ErrorAlert';
import { formatDateTime } from '../../utils/formatters';

const EMPTY_FILTERS = {
  search: '',
  category: '',
  event_type: '',
  actor_type: '',
  actor_user_id: '',
  actor_account_id: '',
  severity: '',
  outcome: '',
  target_type: '',
  target_id: '',
  ip_address: '',
  request_id: '',
  from: '',
  to: '',
};

const CATEGORY_OPTIONS = [
  ['auth', 'Authentication'],
  ['user', 'User management'],
  ['portal_account', 'Portal accounts'],
  ['customer', 'Customers'],
  ['query', 'Support queries'],
  ['sale', 'Sales'],
  ['invoice', 'Invoices'],
  ['expense', 'Expenses'],
  ['record', 'Record deletion'],
  ['report', 'Reports'],
  ['security', 'Security'],
];

const SEVERITY_STYLES = {
  info: 'bg-sky-50 text-sky-700 border-sky-200',
  warning: 'bg-amber-50 text-amber-800 border-amber-200',
  critical: 'bg-rose-50 text-rose-700 border-rose-200',
};

const OUTCOME_STYLES = {
  success: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  failure: 'bg-rose-50 text-rose-700 border-rose-200',
  denied: 'bg-orange-50 text-orange-700 border-orange-200',
};

const ACTOR_LABELS = {
  staff: 'Staff',
  customer: 'Customer',
  system: 'System',
  anonymous: 'Anonymous',
};

const FILTER_LABELS = {
  search: 'Search',
  category: 'Category',
  event_type: 'Event type',
  actor_type: 'Actor type',
  actor_user_id: 'Staff user',
  actor_account_id: 'Customer account',
  severity: 'Severity',
  outcome: 'Outcome',
  target_type: 'Target type',
  target_id: 'Target ID',
  ip_address: 'Source IP',
  request_id: 'Request ID',
  from: 'From',
  to: 'To',
};

const ADVANCED_FILTER_KEYS = [
  'event_type',
  'actor_type',
  'actor_user_id',
  'actor_account_id',
  'target_type',
  'target_id',
  'ip_address',
  'request_id',
  'from',
  'to',
];

const RANGE_PRESETS = [
  { label: 'Last 24 hours', hours: 24 },
  { label: 'Last 7 days', hours: 24 * 7 },
  { label: 'Last 30 days', hours: 24 * 30 },
];

function normalizeFilters(filters) {
  return Object.fromEntries(
    Object.entries(filters)
      .map(([key, value]) => [key, String(value).trim()])
      .filter(([, value]) => value !== '')
  );
}

function toIso(value) {
  if (!value) return undefined;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return undefined;
  return parsed.toISOString();
}

function toLocalInputValue(date) {
  const pad = (value) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
    date.getDate()
  )}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatFilterValue(key, value) {
  if (key === 'category') {
    const match = CATEGORY_OPTIONS.find(([option]) => option === value);
    return match ? match[1] : value;
  }
  if (key === 'from' || key === 'to') return String(value).replace('T', ' ');
  return String(value);
}

function buildParams(filters, page, pageSize) {
  const params = { page, page_size: pageSize };

  if (filters.search) params.search = filters.search;
  if (filters.category) params.category = filters.category;
  if (filters.event_type) params.event_type = filters.event_type;
  if (filters.actor_type) params.actor_type = filters.actor_type;
  if (filters.actor_user_id) params.actor_user_id = filters.actor_user_id;
  if (filters.actor_account_id) params.actor_account_id = filters.actor_account_id;
  if (filters.severity) params.severity = filters.severity;
  if (filters.outcome) params.outcome = filters.outcome;
  if (filters.target_type) params.target_type = filters.target_type;
  if (filters.target_id) params.target_id = filters.target_id;
  if (filters.ip_address) params.ip_address = filters.ip_address;
  if (filters.request_id) params.request_id = filters.request_id;

  const from = toIso(filters.from);
  const to = toIso(filters.to);
  if (from) params.from = from;
  if (to) params.to = to;

  return params;
}

function actorIdentity(event) {
  // The API resolves the actor's name and email, because a raw portal account
  // id is not displayed anywhere in the staff UI.
  if (event.actor_type === 'staff' && event.actor_user_id) {
    return {
      name: event.actor_name || `Staff #${event.actor_user_id}`,
      detail: event.actor_email || null,
    };
  }
  if (event.actor_type === 'customer' && event.actor_account_id) {
    return {
      name: event.actor_name || `Customer #${event.actor_account_id}`,
      detail: event.actor_email || null,
    };
  }
  return {
    name: ACTOR_LABELS[event.actor_type] || event.actor_type || 'Unknown',
    detail: null,
  };
}

function ActorIdentity({ event }) {
  const identity = actorIdentity(event);
  return (
    <div className="min-w-0">
      <p className="font-semibold text-slate-800 break-words">
        {identity.name}
      </p>
      {identity.detail && (
        <p className="text-[11px] text-slate-500 break-words">
          {identity.detail}
        </p>
      )}
    </div>
  );
}

function Badge({ value, styles }) {
  if (!value) return <span className="text-xs text-slate-400">—</span>;
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[11px] font-semibold capitalize ${
        styles[value] || 'bg-slate-50 text-slate-600 border-slate-200'
      }`}
    >
      {value}
    </span>
  );
}

function FilterField({ label, children, className = '' }) {
  return (
    <label className={`block ${className}`}>
      <span className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1.5">
        {label}
      </span>
      {children}
    </label>
  );
}

const inputClass =
  'h-10 w-full px-3 text-sm text-slate-800 border border-slate-200 rounded-lg bg-white transition placeholder:text-slate-400 hover:border-slate-300 focus:outline-none focus:border-amber-400 focus:ring-2 focus:ring-amber-400';

export default function SecurityAudit() {
  const [draft, setDraft] = useState(EMPTY_FILTERS);
  const [applied, setApplied] = useState({});
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [reloadKey, setReloadKey] = useState(0);
  const [data, setData] = useState({
    items: [],
    total: 0,
    total_pages: 1,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const loadEvents = async () => {
      try {
        const response = await getSecurityAuditEvents(
          buildParams(applied, page, pageSize)
        );
        if (cancelled) return;
        setData({
          items: Array.isArray(response?.items) ? response.items : [],
          total: response?.total ?? 0,
          total_pages: response?.total_pages ?? 1,
        });
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err?.message || 'Failed to load the security audit log.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    loadEvents();
    return () => {
      cancelled = true;
    };
  }, [applied, page, pageSize, reloadKey]);

  const reload = () => {
    setLoading(true);
    setError(null);
    setReloadKey((current) => current + 1);
  };

  const goToPage = (nextPage) => {
    setLoading(true);
    setError(null);
    setPage(nextPage);
  };

  const updateDraft = (key) => (event) => {
    setDraft((current) => ({ ...current, [key]: event.target.value }));
  };

  const handleApply = (event) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setApplied(normalizeFilters(draft));
    setPage(1);
  };

  const handleClear = () => {
    setLoading(true);
    setError(null);
    setDraft(EMPTY_FILTERS);
    setApplied({});
    setPage(1);
  };

  const removeFilter = (key) => {
    setLoading(true);
    setError(null);
    setDraft((current) => ({ ...current, [key]: '' }));
    setApplied((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });
    setPage(1);
  };

  // A quick range applies immediately on top of the filters already in force,
  // so it never picks up unsubmitted edits from the other fields.
  const applyRangePreset = (hours) => {
    const now = new Date();
    const start = new Date(now.getTime() - hours * 60 * 60 * 1000);
    const from = toLocalInputValue(start);
    const to = toLocalInputValue(now);
    setLoading(true);
    setError(null);
    setDraft((current) => ({ ...current, from, to }));
    setApplied((current) => normalizeFilters({ ...current, from, to }));
    setPage(1);
  };

  const openDetail = async (eventId) => {
    setDetailOpen(true);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      const response = await getSecurityAuditEvent(eventId);
      setDetail(response?.event || null);
    } catch (err) {
      setDetailError(err?.message || 'Failed to load this audit event.');
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetail = () => {
    setDetailOpen(false);
    setDetail(null);
    setDetailError(null);
  };

  const activeFilters = Object.entries(applied);
  const activeFilterCount = activeFilters.length;
  const advancedFilterCount = activeFilters.filter(([key]) =>
    ADVANCED_FILTER_KEYS.includes(key)
  ).length;
  const hasFilters = activeFilterCount > 0;
  const hasDraft = Object.values(draft).some(
    (value) => String(value).trim() !== ''
  );
  const firstRow = data.total === 0 ? 0 : (page - 1) * pageSize + 1;
  const lastRow = Math.min(page * pageSize, data.total);

  return (
    <div>
      <PageHeader
        title="Security Audit Log"
        subtitle="Search and inspect privileged, security and business activity. Admin access only."
        badge="Admin Only"
      >
        <button
          type="button"
          onClick={reload}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 rounded-lg transition disabled:opacity-60"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          <span className="hidden sm:inline">Refresh</span>
        </button>
      </PageHeader>

      <form
        onSubmit={handleApply}
        className="mb-5 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
      >
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 sm:px-5">
          <div className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50 text-amber-600">
              <Filter className="h-4 w-4" />
            </span>
            <div>
              <h2 className="text-sm font-bold text-slate-800">
                Search &amp; filters
              </h2>
              <p className="text-[11px] text-slate-500" aria-live="polite">
                {data.total} matching event{data.total === 1 ? '' : 's'}
                {hasFilters
                  ? ` · ${activeFilterCount} filter${
                      activeFilterCount === 1 ? '' : 's'
                    } active`
                  : ''}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="hidden text-[11px] text-slate-400 md:block">
              Stored in UTC, shown in IST
            </span>
            <button
              type="button"
              onClick={() => setShowAdvanced((current) => !current)}
              aria-expanded={showAdvanced}
              aria-controls="audit-advanced-filters"
              className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold transition ${
                showAdvanced || advancedFilterCount > 0
                  ? 'border-amber-300 bg-amber-50 text-amber-800'
                  : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50'
              }`}
            >
              <SlidersHorizontal className="h-3.5 w-3.5" />
              {showAdvanced ? 'Hide advanced' : 'Advanced filters'}
              {advancedFilterCount > 0 && (
                <span className="rounded-full bg-amber-500 px-1.5 text-[10px] font-bold text-white">
                  {advancedFilterCount}
                </span>
              )}
              <ChevronDown
                className={`h-3.5 w-3.5 transition-transform ${
                  showAdvanced ? 'rotate-180' : ''
                }`}
              />
            </button>
          </div>
        </div>

        <div className="space-y-4 p-4 sm:p-5">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <FilterField label="Search" className="sm:col-span-2">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  value={draft.search}
                  onChange={updateDraft('search')}
                  maxLength={100}
                  placeholder="Event, path, target, request ID or IP"
                  className={`${inputClass} pl-9 ${
                    draft.search ? 'pr-9' : ''
                  }`}
                />
                {draft.search && (
                  <button
                    type="button"
                    onClick={() =>
                      setDraft((current) => ({ ...current, search: '' }))
                    }
                    aria-label="Clear search text"
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </FilterField>

            <FilterField label="Category">
              <select
                value={draft.category}
                onChange={updateDraft('category')}
                className={inputClass}
              >
                <option value="">All categories</option>
                {CATEGORY_OPTIONS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </FilterField>

            <FilterField label="Severity">
              <select
                value={draft.severity}
                onChange={updateDraft('severity')}
                className={inputClass}
              >
                <option value="">Any severity</option>
                <option value="info">Info</option>
                <option value="warning">Warning</option>
                <option value="critical">Critical</option>
              </select>
            </FilterField>

            <FilterField label="Outcome">
              <select
                value={draft.outcome}
                onChange={updateDraft('outcome')}
                className={inputClass}
              >
                <option value="">Any outcome</option>
                <option value="success">Success</option>
                <option value="failure">Failure</option>
                <option value="denied">Denied</option>
              </select>
            </FilterField>
          </div>

          {hasFilters && (
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                Active
              </span>
              {activeFilters.map(([key, value]) => (
                <span
                  key={key}
                  className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white py-1 pl-2.5 pr-1 text-[11px] text-slate-700 shadow-sm"
                >
                  <span className="text-slate-500">
                    {FILTER_LABELS[key] || key}
                  </span>
                  <span className="max-w-[12rem] truncate font-semibold text-slate-800">
                    {formatFilterValue(key, value)}
                  </span>
                  <button
                    type="button"
                    onClick={() => removeFilter(key)}
                    aria-label={`Remove ${FILTER_LABELS[key] || key} filter`}
                    className="rounded-full p-0.5 text-slate-400 transition hover:bg-rose-50 hover:text-rose-600"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
              <button
                type="button"
                onClick={handleClear}
                className="ml-auto text-[11px] font-semibold text-slate-500 transition hover:text-rose-600"
              >
                Clear all
              </button>
            </div>
          )}

          {showAdvanced && (
            <div
              id="audit-advanced-filters"
              className="space-y-4 rounded-xl border border-slate-200 bg-slate-50 p-4"
            >
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <FilterField label="Event type">
                  <input
                    type="text"
                    value={draft.event_type}
                    onChange={updateDraft('event_type')}
                    maxLength={64}
                    placeholder="e.g. user.role.changed"
                    className={inputClass}
                  />
                </FilterField>

                <FilterField label="Actor type">
                  <select
                    value={draft.actor_type}
                    onChange={updateDraft('actor_type')}
                    className={inputClass}
                  >
                    <option value="">Any actor</option>
                    <option value="staff">Staff</option>
                    <option value="customer">Customer</option>
                    <option value="system">System</option>
                    <option value="anonymous">Anonymous</option>
                  </select>
                </FilterField>

                <FilterField label="Staff user ID">
                  <input
                    type="number"
                    min="1"
                    value={draft.actor_user_id}
                    onChange={updateDraft('actor_user_id')}
                    placeholder="Staff user ID"
                    className={inputClass}
                  />
                </FilterField>

                <FilterField label="Customer account ID">
                  <input
                    type="number"
                    min="1"
                    value={draft.actor_account_id}
                    onChange={updateDraft('actor_account_id')}
                    placeholder="Customer account ID"
                    className={inputClass}
                  />
                </FilterField>

                <FilterField label="Target type">
                  <input
                    type="text"
                    value={draft.target_type}
                    onChange={updateDraft('target_type')}
                    maxLength={40}
                    placeholder="e.g. invoice"
                    className={inputClass}
                  />
                </FilterField>

                <FilterField label="Target ID">
                  <input
                    type="text"
                    value={draft.target_id}
                    onChange={updateDraft('target_id')}
                    maxLength={64}
                    placeholder="e.g. 42"
                    className={inputClass}
                  />
                </FilterField>

                <FilterField label="Source IP (exact)">
                  <input
                    type="text"
                    value={draft.ip_address}
                    onChange={updateDraft('ip_address')}
                    maxLength={45}
                    placeholder="e.g. 203.0.113.10"
                    className={inputClass}
                  />
                </FilterField>

                <FilterField label="Request ID">
                  <input
                    type="text"
                    value={draft.request_id}
                    onChange={updateDraft('request_id')}
                    maxLength={64}
                    placeholder="Server request ID"
                    className={inputClass}
                  />
                </FilterField>
              </div>

              <div className="flex flex-wrap items-end justify-between gap-3 border-t border-slate-200 pt-4">
                <div className="grid w-full grid-cols-1 gap-3 sm:w-auto sm:grid-cols-2">
                  <FilterField label="From (local time)">
                    <input
                      type="datetime-local"
                      value={draft.from}
                      onChange={updateDraft('from')}
                      className={inputClass}
                    />
                  </FilterField>

                  <FilterField label="To (local time)">
                    <input
                      type="datetime-local"
                      value={draft.to}
                      onChange={updateDraft('to')}
                      className={inputClass}
                    />
                  </FilterField>
                </div>

                <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                    Quick range
                  </span>
                  {RANGE_PRESETS.map((preset) => (
                    <button
                      key={preset.hours}
                      type="button"
                      onClick={() => applyRangePreset(preset.hours)}
                      className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-600 transition hover:border-amber-300 hover:text-amber-700"
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          <div className="flex flex-col gap-3 border-t border-slate-100 pt-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-[11px] text-slate-500">
              {hasFilters
                ? 'Filters combine with AND. Remove a chip above to widen the results.'
                : 'No filters applied — newest events are shown first.'}
            </p>
            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={handleClear}
                disabled={!hasFilters && !hasDraft}
                className="rounded-lg bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Clear filters
              </button>
              <button
                type="submit"
                className="inline-flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-amber-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 focus-visible:ring-offset-2"
              >
                <Search className="h-4 w-4" />
                Apply filters
              </button>
            </div>
          </div>
        </div>
      </form>

      {loading ? (
        <LoadingSpinner message="Loading security audit events…" />
      ) : error ? (
        <ErrorAlert message={error} onRetry={reload} />
      ) : data.items.length === 0 ? (
        <EmptyState
          icon={ShieldCheck}
          title={hasFilters ? 'No audit events match these filters' : 'No audit events yet'}
          description={
            hasFilters
              ? 'Try widening the date range or removing one or more filters.'
              : 'Audited actions will appear here once the audit table is migrated and events are recorded.'
          }
        />
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">
                    Time (IST)
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">
                    Event
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">
                    Actor
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">
                    Target
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">
                    Outcome
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">
                    IP
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-bold text-slate-500 uppercase tracking-wider">
                    Details
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {data.items.map((event) => (
                  <tr key={event.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3 whitespace-nowrap">
                      <div className="flex items-center gap-1.5 text-xs text-slate-600">
                        <Clock className="w-3.5 h-3.5 text-slate-400" />
                        {formatDateTime(event.created_at)}
                      </div>
                      <span className="text-[11px] text-slate-400 font-mono">
                        #{event.id}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-mono text-xs font-semibold text-slate-800">
                        {event.event_type}
                      </p>
                      <p className="text-[11px] text-slate-500 truncate max-w-[18rem]">
                        {event.action || event.path || '—'}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-start gap-1.5 text-xs text-slate-700">
                        <User className="mt-0.5 w-3.5 h-3.5 shrink-0 text-slate-400" />
                        <ActorIdentity event={event} />
                      </div>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <div className="flex items-center gap-1.5 text-xs text-slate-600">
                        <Target className="w-3.5 h-3.5 text-slate-400" />
                        {event.target_type || '—'}
                        {event.target_id ? ` #${event.target_id}` : ''}
                      </div>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <div className="flex flex-col gap-1 items-start">
                        <Badge value={event.outcome} styles={OUTCOME_STYLES} />
                        <Badge value={event.severity} styles={SEVERITY_STYLES} />
                      </div>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {event.ip_address ? (
                        <span className="inline-flex items-center gap-1.5 text-xs font-mono text-slate-600">
                          <Globe className="w-3.5 h-3.5 text-slate-400" />
                          {event.ip_address}
                        </span>
                      ) : (
                        <span className="text-xs text-slate-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => openDetail(event.id)}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition"
                        aria-label={`View audit event ${event.id}`}
                      >
                        <Eye className="w-3.5 h-3.5" />
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 px-4 py-3 border-t border-slate-100 bg-slate-50">
            <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
              <span>
                Showing {firstRow}–{lastRow} of {data.total}
              </span>
              <label className="flex items-center gap-1.5">
                <span>Rows</span>
                <select
                  value={pageSize}
                  onChange={(event) => {
                    setLoading(true);
                    setError(null);
                    setPageSize(Number(event.target.value));
                    setPage(1);
                  }}
                  className="px-2 py-1 text-xs border border-slate-200 rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-amber-400"
                >
                  {[10, 25, 50, 100].map((size) => (
                    <option key={size} value={size}>
                      {size}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">
                Page {page} of {Math.max(1, data.total_pages)}
              </span>
              <button
                type="button"
                onClick={() => goToPage(Math.max(1, page - 1))}
                disabled={page <= 1 || loading}
                className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200 hover:bg-slate-100 rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
                Previous
              </button>
              <button
                type="button"
                onClick={() =>
                  goToPage(Math.min(Math.max(1, data.total_pages), page + 1))
                }
                disabled={page >= data.total_pages || loading}
                className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200 hover:bg-slate-100 rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Next
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      )}

      {detailOpen && (
        <div
          className="fixed inset-0 z-50 flex items-start sm:items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs overflow-y-auto"
          role="dialog"
          aria-modal="true"
          aria-labelledby="audit-detail-title"
        >
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl my-4">
            <div className="flex items-start justify-between gap-4 p-5 border-b border-slate-100">
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-xl bg-amber-100 flex items-center justify-center shrink-0">
                  <ShieldCheck className="w-5 h-5 text-amber-700" />
                </div>
                <div>
                  <h2
                    id="audit-detail-title"
                    className="font-bold text-slate-900"
                  >
                    Audit event details
                  </h2>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Append-only record. Metadata is allowlisted and redacted on
                    write.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={closeDetail}
                className="p-1.5 hover:bg-slate-100 rounded-lg transition"
                aria-label="Close audit event details"
              >
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>

            <div className="p-5">
              {detailLoading ? (
                <LoadingSpinner message="Loading event details…" size="sm" />
              ) : detailError ? (
                <ErrorAlert message={detailError} />
              ) : detail ? (
                <div className="space-y-5">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Event ID
                      </p>
                      <p className="font-mono text-slate-800">#{detail.id}</p>
                    </div>
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Timestamp
                      </p>
                      <p className="text-slate-800">
                        {formatDateTime(detail.created_at)}
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Event type
                      </p>
                      <p className="font-mono text-xs text-slate-800">
                        {detail.event_type}
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Category
                      </p>
                      <p className="text-slate-800">{detail.category}</p>
                    </div>
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Actor
                      </p>
                      <div className="mt-0.5 text-sm">
                        <ActorIdentity event={detail} />
                      </div>
                      <p className="mt-0.5 font-mono text-[11px] text-slate-400">
                        {detail.actor_type === 'staff' && detail.actor_user_id
                          ? `user #${detail.actor_user_id}`
                          : detail.actor_type === 'customer' &&
                              detail.actor_account_id
                            ? `portal account #${detail.actor_account_id}`
                            : detail.actor_type}
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Target
                      </p>
                      <p className="text-slate-800">
                        {detail.target_type || '—'}
                        {detail.target_id ? ` #${detail.target_id}` : ''}
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Outcome / severity
                      </p>
                      <div className="flex gap-1.5 mt-1">
                        <Badge value={detail.outcome} styles={OUTCOME_STYLES} />
                        <Badge value={detail.severity} styles={SEVERITY_STYLES} />
                      </div>
                    </div>
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Source IP
                      </p>
                      <p className="font-mono text-xs text-slate-800">
                        {detail.ip_address || '—'}
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Request ID
                      </p>
                      <p className="font-mono text-xs text-slate-800 break-all">
                        {detail.request_id || '—'}
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Request
                      </p>
                      <p className="font-mono text-xs text-slate-800 break-all">
                        {detail.http_method
                          ? `${detail.http_method} ${detail.path || ''}`
                          : detail.path || '—'}
                      </p>
                    </div>
                  </div>

                  {detail.reason_code && (
                    <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 flex items-start gap-2">
                      <AlertTriangle className="w-4 h-4 text-amber-700 shrink-0 mt-0.5" />
                      <div>
                        <p className="text-[11px] font-bold uppercase tracking-wider text-amber-700">
                          Reason code
                        </p>
                        <p className="text-xs font-mono text-amber-900">
                          {detail.reason_code}
                        </p>
                      </div>
                    </div>
                  )}

                  <div>
                    <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-2">
                      Safe metadata
                    </p>
                    {detail.metadata && Object.keys(detail.metadata).length > 0 ? (
                      <pre className="text-xs font-mono text-slate-700 bg-slate-50 border border-slate-200 rounded-lg p-3 overflow-x-auto max-h-64">
                        {JSON.stringify(detail.metadata, null, 2)}
                      </pre>
                    ) : (
                      <p className="text-xs text-slate-500">No metadata recorded.</p>
                    )}
                  </div>

                  <div className="text-[11px] text-slate-500">
                    User agent:{' '}
                    <span className="font-mono break-all">
                      {detail.user_agent || '—'}
                    </span>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-slate-500">
                  No event data was returned.
                </p>
              )}
            </div>

            <div className="flex justify-end p-4 border-t border-slate-100">
              <button
                type="button"
                onClick={closeDetail}
                className="px-4 py-2 text-sm font-semibold text-white bg-slate-800 hover:bg-slate-900 rounded-lg transition"
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
