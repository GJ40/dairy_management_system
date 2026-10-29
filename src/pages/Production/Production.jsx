import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'react-toastify';
import { useAuth } from '../../hooks/useAuth';
import {
  getProductionGrid,
  createProduction,
  getProduction,
  deleteProduction,
} from '../../api/production';
import { getTodayKolkataDate, formatDate, formatLitres } from '../../utils/formatters';
import PageHeader from '../../components/PageHeader';
import ConfirmModal from '../../components/ConfirmModal';
import LoadingSpinner from '../../components/LoadingSpinner';
import ErrorAlert from '../../components/ErrorAlert';
import EmptyState from '../../components/EmptyState';
import {
  Milk,
  Save,
  Trash2,
  Sun,
  Moon,
  Calendar,
  RefreshCw,
  PawPrint,
  AlertCircle,
} from 'lucide-react';

const EMPTY_TOTALS = { morning: '0.00', evening: '0.00', grand_total: '0.00' };

const SESSION_CONFIG = {
  morning: {
    label: 'Morning',
    icon: Sun,
    color: 'text-amber-600',
    bg: 'bg-amber-50',
    inputClass: 'border-amber-200 focus:ring-amber-400 bg-amber-50',
  },
  evening: {
    label: 'Evening',
    icon: Moon,
    color: 'text-indigo-600',
    bg: 'bg-indigo-50',
    inputClass: 'border-indigo-200 focus:ring-indigo-400 bg-indigo-50',
  },
};

function inputFieldFor(session) {
  return session === 'morning' ? 'morningInput' : 'eveningInput';
}

function savedLitresFor(row, session) {
  return session === 'morning' ? row.morning_litres : row.evening_litres;
}

export default function Production() {
  const { isAdmin } = useAuth();
  const today = getTodayKolkataDate();

  const [date, setDate] = useState(today);
  const [session, setSession] = useState('morning');
  const [grid, setGrid] = useState([]);
  const [entries, setEntries] = useState([]);
  const [herdTotals, setHerdTotals] = useState(EMPTY_TOTALS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [overwriteTarget, setOverwriteTarget] = useState(null);
  const requestSequence = useRef(0);

  const fetchAll = useCallback((targetDate) => {
    const sequence = ++requestSequence.current;

    return Promise.all([getProductionGrid(targetDate), getProduction(targetDate)])
      .then(([gridResponse, productionResponse]) => {
        if (sequence !== requestSequence.current) return;

        setHerdTotals(gridResponse?.herd_totals || EMPTY_TOTALS);
        setEntries(productionResponse?.entries || []);
        setGrid(
          (gridResponse?.grid || []).map((row) => ({
            ...row,
            morningInput: row.morning_litres !== null ? String(row.morning_litres) : '',
            eveningInput: row.evening_litres !== null ? String(row.evening_litres) : '',
          }))
        );
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

  useEffect(() => {
    fetchAll(date);
  }, [date, fetchAll]);

  const getEntry = (buffaloId, targetSession = session) =>
    entries.find(
      (entry) =>
        entry.buffalo_id === buffaloId &&
        entry.session === targetSession &&
        !entry.is_deleted
    );

  const updateInput = (index, field, value) => {
    setGrid((previous) =>
      previous.map((row, rowIndex) =>
        rowIndex === index ? { ...row, [field]: value } : row
      )
    );
  };

  const handleDateChange = (event) => {
    if (!event.target.value) return;
    setDate(event.target.value);
    setError(null);
    setLoading(true);
  };

  const handleRefresh = () => {
    if (saving) return;
    setError(null);
    setLoading(true);
    fetchAll(date);
  };

  const handleSessionChange = (nextSession) => {
    if (saving || nextSession === session) return;
    setSession(nextSession);
  };

  const parseLitresInput = (rawValue) => {
    const raw = String(rawValue ?? '').trim();
    if (raw === '') return { empty: true };
    const litres = Number(raw);
    if (!Number.isFinite(litres) || litres < 0) {
      return { invalid: true };
    }
    return { litres };
  };

  const buildBulkItems = () => {
    const items = [];

    for (const row of grid) {
      const parsed = parseLitresInput(row[inputFieldFor(session)]);
      if (parsed.empty) continue;
      if (parsed.invalid) {
        return { error: `Enter a valid litres amount for ${row.tag_no}.` };
      }
      const existingEntry = getEntry(row.buffalo_id);
      if (existingEntry && Number(existingEntry.litres) === parsed.litres) continue;
      items.push({ row, litres: parsed.litres });
    }

    if (items.length === 0) return { error: 'No changes to save.' };
    return { items };
  };

  const performRowSave = async (target) => {
    setSaving(true);
    setOverwriteTarget(null);

    try {
      await createProduction({
        buffalo_id: target.row.buffalo_id,
        prod_date: target.date,
        session: target.session,
        litres: target.litres.toFixed(2),
        ...(target.overwrite ? { overwrite: true } : {}),
      });
      toast.success(
        `${target.overwrite ? 'Updated' : 'Saved'} ${target.row.tag_no} (${target.session})`
      );
      setLoading(true);
      fetchAll(target.date);
    } catch (err) {
      if (err?.code === 'DUPLICATE_PRODUCTION_ENTRY') {
        setOverwriteTarget({
          ...target,
          overwrite: true,
          existingLitres: target.existingLitres ?? null,
        });
        toast.info('An entry already exists. Confirm to overwrite it.');
      } else {
        toast.error(err?.message || 'Failed to save production record.');
      }
    } finally {
      setSaving(false);
    }
  };

  const performBulkSave = async (target) => {
    setSaving(true);
    setOverwriteTarget(null);

    try {
      const results = await Promise.allSettled(
        target.items.map(({ row, litres }) => {
          const existingEntry = getEntry(row.buffalo_id, target.session);
          return createProduction({
            buffalo_id: row.buffalo_id,
            prod_date: target.date,
            session: target.session,
            litres: litres.toFixed(2),
            ...(existingEntry ? { overwrite: true } : {}),
          });
        })
      );

      const failures = results.filter((result) => result.status === 'rejected');
      const savedCount = results.length - failures.length;

      if (failures.length === 0) {
        toast.success(
          `Saved ${savedCount} ${target.session} record${savedCount === 1 ? '' : 's'}.`
        );
      } else {
        const firstFailure = failures[0].reason;
        toast.warn(
          `Saved ${savedCount} of ${results.length}. ${failures.length} failed: ${
            firstFailure?.message || 'Unknown error'
          }`
        );
      }

      setLoading(true);
      fetchAll(target.date);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveRow = (row) => {
    if (saving || !canEdit) return;

    const parsed = parseLitresInput(row[inputFieldFor(session)]);
    if (parsed.empty) {
      toast.error(`Enter litres for ${row.tag_no}.`);
      return;
    }
    if (parsed.invalid) {
      toast.error(`Enter a valid litres amount for ${row.tag_no}.`);
      return;
    }

    const existingEntry = getEntry(row.buffalo_id);

    if (existingEntry) {
      setOverwriteTarget({
        mode: 'row',
        row,
        litres: parsed.litres,
        session,
        date,
        existingLitres: existingEntry.litres,
      });
      return;
    }

    performRowSave({
      row,
      litres: parsed.litres,
      session,
      date,
      overwrite: false,
    });
  };

  const handleBulkSave = () => {
    if (saving || !canEdit) return;

    const built = buildBulkItems();
    if (built.error) {
      if (built.error === 'No changes to save.') {
        toast.info(built.error);
      } else {
        toast.error(built.error);
      }
      return;
    }

    const existingCount = built.items.filter(({ row }) =>
      Boolean(getEntry(row.buffalo_id))
    ).length;

    if (existingCount > 0) {
      setOverwriteTarget({
        mode: 'bulk',
        items: built.items,
        session,
        date,
        existingCount,
      });
      return;
    }

    performBulkSave({ items: built.items, session, date });
  };

  const handleConfirmOverwrite = () => {
    if (!overwriteTarget) return;

    if (overwriteTarget.mode === 'row') {
      performRowSave({ ...overwriteTarget, overwrite: true });
    } else {
      performBulkSave(overwriteTarget);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;

    setDeleteLoading(true);
    try {
      await deleteProduction(deleteTarget.id);
      toast.success('Production record deleted.');
      setDeleteTarget(null);
      setLoading(true);
      fetchAll(date);
    } catch (err) {
      toast.error(err?.message || 'Failed to delete record.');
    } finally {
      setDeleteLoading(false);
    }
  };

  const isPastDate = date < today;
  const canEdit = isAdmin || date === today;
  const sessionConfig = SESSION_CONFIG[session];
  const SessionIcon = sessionConfig.icon;

  const overwriteMessage = overwriteTarget
    ? overwriteTarget.mode === 'row'
      ? `Buffalo ${overwriteTarget.row.tag_no} already has a ${overwriteTarget.session} record${
          overwriteTarget.existingLitres != null
            ? ` of ${formatLitres(overwriteTarget.existingLitres)}`
            : ''
        }. Replace it with ${formatLitres(overwriteTarget.litres)}?`
      : `${overwriteTarget.existingCount} of ${overwriteTarget.items.length} selected rows already have a ${overwriteTarget.session} record. Saving will replace those values. Continue?`
    : '';

  return (
    <div>
      <PageHeader
        title="Milk Production Entry"
        subtitle="Record morning and evening milk production for each active buffalo."
      >
        <button
          type="button"
          onClick={handleRefresh}
          disabled={saving || loading}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50 disabled:opacity-60"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </PageHeader>

      <div className="mb-5 flex flex-col gap-3 sm:flex-row">
        <div className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-slate-500" />
          <input
            type="date"
            value={date}
            max={today}
            disabled={saving}
            onChange={handleDateChange}
            aria-label="Production date"
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400 disabled:opacity-60"
          />
        </div>
        <div className="flex overflow-hidden rounded-lg border border-slate-200">
          {Object.entries(SESSION_CONFIG).map(([key, config]) => {
            const Icon = config.icon;
            return (
              <button
                key={key}
                type="button"
                onClick={() => handleSessionChange(key)}
                disabled={saving}
                aria-pressed={session === key}
                className={`flex items-center gap-2 px-4 py-2 text-sm font-medium transition disabled:opacity-60 ${
                  session === key
                    ? `${config.bg} ${config.color} font-semibold`
                    : 'bg-white text-slate-500 hover:bg-slate-50'
                }`}
              >
                <Icon className="h-4 w-4" /> {config.label}
              </button>
            );
          })}
        </div>
      </div>

      {isPastDate && !isAdmin && (
        <div className="mb-5 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
          <span>
            Operators can only add or edit production for today. Past dates are view-only.
          </span>
        </div>
      )}

      <div className="mb-5 grid grid-cols-3 gap-3">
        {[
          {
            label: 'Morning Total',
            value: formatLitres(herdTotals.morning),
            icon: Sun,
            color: 'text-amber-600',
            bg: 'bg-amber-50',
          },
          {
            label: 'Evening Total',
            value: formatLitres(herdTotals.evening),
            icon: Moon,
            color: 'text-indigo-600',
            bg: 'bg-indigo-50',
          },
          {
            label: 'Day Total',
            value: formatLitres(herdTotals.grand_total),
            icon: Milk,
            color: 'text-emerald-700',
            bg: 'bg-emerald-50',
          },
        ].map((item) => {
          const Icon = item.icon;
          return (
            <div
              key={item.label}
              className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4"
            >
              <div
                className={`flex h-10 w-10 items-center justify-center rounded-xl ${item.bg}`}
              >
                <Icon className={`h-5 w-5 ${item.color}`} />
              </div>
              <div>
                <p className="text-xl font-bold text-slate-800">{item.value}</p>
                <p className="text-xs text-slate-500">{item.label}</p>
              </div>
            </div>
          );
        })}
      </div>

      {error && <ErrorAlert error={error} onRetry={handleRefresh} />}

      {loading ? (
        <LoadingSpinner message="Loading production grid…" />
      ) : error ? null : grid.length === 0 ? (
        <EmptyState
          icon={PawPrint}
          title="No active buffaloes"
          description="Add active buffaloes to start recording milk production."
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50 px-4 py-3">
            <span className="text-sm font-semibold text-slate-700">
              {formatDate(date)} — <SessionIcon className="inline-block h-4 w-4" />{' '}
              {sessionConfig.label} Session
            </span>
            {canEdit ? (
              <button
                type="button"
                onClick={handleBulkSave}
                disabled={saving || loading}
                className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-60"
              >
                <Save className="h-3.5 w-3.5" /> {saving ? 'Saving…' : 'Save All'}
              </button>
            ) : (
              <span className="rounded-full bg-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-600">
                View only
              </span>
            )}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-slate-500">
                    Tag No.
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-slate-500">
                    Name
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-slate-500">
                    <div className="flex items-center gap-1">
                      <Sun className="h-3.5 w-3.5 text-amber-500" /> Morning (L)
                    </div>
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-slate-500">
                    <div className="flex items-center gap-1">
                      <Moon className="h-3.5 w-3.5 text-indigo-500" /> Evening (L)
                    </div>
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-slate-500">
                    Day Total
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-slate-500">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {grid.map((row, index) => {
                  const savedEntry = getEntry(row.buffalo_id);
                  const hasCurrentSession = savedLitresFor(row, session) != null;
                  const morningValue =
                    session === 'morning'
                      ? Number(row.morningInput)
                      : Number(row.morning_litres);
                  const eveningValue =
                    session === 'evening'
                      ? Number(row.eveningInput)
                      : Number(row.evening_litres);
                  const dayTotal =
                    (Number.isFinite(morningValue) ? morningValue : 0) +
                    (Number.isFinite(eveningValue) ? eveningValue : 0);

                  return (
                    <tr key={row.buffalo_id} className="transition-colors hover:bg-slate-50">
                      <td className="px-4 py-2.5 font-mono font-semibold text-emerald-700">
                        {row.tag_no}
                      </td>
                      <td className="px-4 py-2.5 text-slate-700">{row.name || '—'}</td>
                      <td className="px-4 py-2.5">
                        {session === 'morning' ? (
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={row.morningInput}
                            disabled={!canEdit || saving}
                            onChange={(event) =>
                              updateInput(index, 'morningInput', event.target.value)
                            }
                            placeholder="0.00"
                            aria-label={`Morning litres for ${row.tag_no}`}
                            className={`w-24 rounded-lg border px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 disabled:cursor-not-allowed disabled:opacity-60 ${SESSION_CONFIG.morning.inputClass}`}
                          />
                        ) : (
                          <span className="text-slate-600">
                            {row.morning_litres !== null ? (
                              formatLitres(row.morning_litres)
                            ) : (
                              <span className="text-slate-400">—</span>
                            )}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        {session === 'evening' ? (
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={row.eveningInput}
                            disabled={!canEdit || saving}
                            onChange={(event) =>
                              updateInput(index, 'eveningInput', event.target.value)
                            }
                            placeholder="0.00"
                            aria-label={`Evening litres for ${row.tag_no}`}
                            className={`w-24 rounded-lg border px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 disabled:cursor-not-allowed disabled:opacity-60 ${SESSION_CONFIG.evening.inputClass}`}
                          />
                        ) : (
                          <span className="text-slate-600">
                            {row.evening_litres !== null ? (
                              formatLitres(row.evening_litres)
                            ) : (
                              <span className="text-slate-400">—</span>
                            )}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 font-semibold text-emerald-700">
                        {dayTotal > 0 ? (
                          formatLitres(dayTotal)
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        {canEdit ? (
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => handleSaveRow(row)}
                              disabled={saving}
                              title="Save this entry"
                              aria-label={`Save ${session} production for ${row.tag_no}`}
                              className="rounded-lg p-1.5 text-emerald-600 transition hover:bg-emerald-50 disabled:opacity-40"
                            >
                              <Save className="h-4 w-4" />
                            </button>
                            {isAdmin && (savedEntry || hasCurrentSession) && (
                              <button
                                type="button"
                                onClick={() =>
                                  setDeleteTarget({
                                    id: savedEntry?.id,
                                    tag: row.tag_no,
                                    session,
                                  })
                                }
                                disabled={saving || deleteLoading || !savedEntry}
                                title="Delete this record"
                                aria-label={`Delete ${session} production for ${row.tag_no}`}
                                className="rounded-lg p-1.5 text-slate-400 transition hover:bg-rose-50 hover:text-rose-600 disabled:opacity-40"
                              >
                                <Trash2 className="h-4 w-4" />
                              </button>
                            )}
                          </div>
                        ) : (
                          <span className="text-slate-300">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="border-t border-slate-100 bg-slate-50 px-4 py-2 text-xs text-slate-500">
            {grid.length} active buffaloes
          </div>
        </div>
      )}

      <ConfirmModal
        isOpen={Boolean(overwriteTarget)}
        title="Overwrite Existing Records"
        message={overwriteMessage}
        confirmText="Overwrite & Save"
        confirmVariant="danger"
        isLoading={saving}
        onConfirm={handleConfirmOverwrite}
        onClose={() => {
          if (!saving) setOverwriteTarget(null);
        }}
      />

      <ConfirmModal
        isOpen={Boolean(deleteTarget)}
        title="Delete Production Record"
        message={`Delete the ${deleteTarget?.session} milk record for buffalo ${deleteTarget?.tag}? It will no longer count toward production totals.`}
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
