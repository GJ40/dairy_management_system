import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'react-toastify';
import { getStock, createWastage } from '../../api/stock';
import { getTodayKolkataDate, formatDate, formatLitres } from '../../utils/formatters';
import PageHeader from '../../components/PageHeader';
import LoadingSpinner from '../../components/LoadingSpinner';
import ErrorAlert from '../../components/ErrorAlert';
import EmptyState from '../../components/EmptyState';
import {
  Layers,
  Droplets,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  RefreshCw,
  Calendar,
  X,
} from 'lucide-react';

const WASTAGE_REASONS = [
  { value: 'spoiled', label: 'Spoiled' },
  { value: 'spilled', label: 'Spilled' },
  { value: 'returned', label: 'Returned' },
];

function StockCard({ label, value, icon: Icon, color, bg, description }) {
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          {label}
        </span>
        <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${bg}`}>
          <Icon className={`h-4 w-4 ${color}`} />
        </div>
      </div>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      {description && <p className="text-xs text-slate-400">{description}</p>}
    </div>
  );
}

export default function Stock() {
  const today = getTodayKolkataDate();
  const requestSequence = useRef(0);

  const [date, setDate] = useState(today);
  const [stock, setStock] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showWastageForm, setShowWastageForm] = useState(false);
  const [wastageForm, setWastageForm] = useState({
    litres: '',
    reason: 'spoiled',
  });
  const [wastageError, setWastageError] = useState(null);
  const [wastageLoading, setWastageLoading] = useState(false);

  const fetchStock = useCallback((targetDate) => {
    const sequence = ++requestSequence.current;

    return getStock(targetDate)
      .then((response) => {
        if (sequence !== requestSequence.current) return;
        setStock(response);
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
    fetchStock(date);
  }, [date, fetchStock]);

  const handleDateChange = (event) => {
    if (!event.target.value) return;
    setDate(event.target.value);
    setError(null);
    setLoading(true);
  };

  const handleRefresh = () => {
    if (loading || wastageLoading) return;
    setError(null);
    setLoading(true);
    fetchStock(date);
  };

  const openWastageForm = () => {
    if (loading || error || !stock) return;
    setWastageError(null);
    setShowWastageForm(true);
  };

  const closeWastageForm = () => {
    if (wastageLoading) return;
    setShowWastageForm(false);
    setWastageError(null);
  };

  const closingNum = Number(stock?.closing_stock);
  const isOutOfStock =
    stock !== null && Number.isFinite(closingNum) && closingNum <= 0;
  const availableLitres =
    stock !== null && Number.isFinite(closingNum) ? closingNum : 0;
  const canRecordWastage =
    stock !== null && !loading && !error && availableLitres > 0;

  const handleWastage = async (event) => {
    event.preventDefault();
    const litres = Number(wastageForm.litres);

    if (!Number.isFinite(litres) || litres <= 0) {
      setWastageError('Enter a litres amount greater than zero.');
      return;
    }

    if (litres > availableLitres) {
      setWastageError(
        `Only ${formatLitres(availableLitres)} is available to waste for this date.`
      );
      return;
    }

    setWastageLoading(true);
    setWastageError(null);

    try {
      await createWastage({
        waste_date: date,
        litres: litres.toFixed(2),
        reason: wastageForm.reason,
      });
      toast.success('Wastage recorded successfully.');
      setShowWastageForm(false);
      setWastageForm({ litres: '', reason: 'spoiled' });
      setLoading(true);
      fetchStock(date);
    } catch (err) {
      setWastageError(err);
    } finally {
      setWastageLoading(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Milk Stock & Wastage"
        subtitle="Daily milk stock status — opening, produced, sold, wasted, and closing stock."
      >
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleRefresh}
            disabled={loading || wastageLoading}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50 disabled:opacity-60"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </button>
          <button
            type="button"
            onClick={openWastageForm}
            disabled={!canRecordWastage}
            className="inline-flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-amber-600 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <AlertTriangle className="h-4 w-4" /> Record Wastage
          </button>
        </div>
      </PageHeader>

      <div className="mb-5 flex items-center gap-3">
        <Calendar className="h-4 w-4 text-slate-500" />
        <input
          type="date"
          value={date}
          max={today}
          onChange={handleDateChange}
          aria-label="Stock date"
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
        />
        <span className="text-sm text-slate-500">{formatDate(date)}</span>
      </div>

      {loading ? (
        <LoadingSpinner message="Loading stock status…" />
      ) : error ? (
        <ErrorAlert error={error} onRetry={handleRefresh} />
      ) : !stock ? (
        <EmptyState
          icon={Layers}
          title="No stock data"
          description="No milk stock is available for this date."
        />
      ) : (
        <>
          {isOutOfStock && (
            <div className="mb-4 flex items-center gap-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-rose-700">
              <AlertTriangle className="h-5 w-5 shrink-0" />
              <p className="text-sm font-medium">
                No milk stock remains for this date. Closing stock is{' '}
                {formatLitres(closingNum)}.
              </p>
            </div>
          )}

          <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
            <StockCard
              label="Opening Stock"
              value={formatLitres(stock.opening_stock)}
              icon={Layers}
              color="text-slate-700"
              bg="bg-slate-100"
              description="Start of day"
            />
            <StockCard
              label="Produced"
              value={formatLitres(stock.produced)}
              icon={TrendingUp}
              color="text-emerald-700"
              bg="bg-emerald-100"
              description="Morning + evening"
            />
            <StockCard
              label="Sold"
              value={formatLitres(stock.sold)}
              icon={TrendingDown}
              color="text-sky-700"
              bg="bg-sky-100"
              description="Total dispatched"
            />
            <StockCard
              label="Wasted"
              value={formatLitres(stock.wasted)}
              icon={AlertTriangle}
              color="text-amber-700"
              bg="bg-amber-100"
              description="Spoiled, spilled, returned"
            />
            <StockCard
              label="Closing Stock"
              value={formatLitres(stock.closing_stock)}
              icon={Droplets}
              color={isOutOfStock ? 'text-rose-700' : 'text-indigo-700'}
              bg={isOutOfStock ? 'bg-rose-100' : 'bg-indigo-100'}
              description="End of day"
            />
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-6">
            <h3 className="mb-4 text-sm font-bold text-slate-700">
              Stock Flow for {formatDate(date)}
            </h3>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <div className="flex items-center gap-2 rounded-lg bg-slate-100 px-3 py-2">
                <span className="font-mono font-bold text-slate-700">
                  {formatLitres(stock.opening_stock)}
                </span>
                <span className="text-slate-500">Opening</span>
              </div>
              <span className="text-lg font-bold text-slate-400">+</span>
              <div className="flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2">
                <span className="font-mono font-bold text-emerald-700">
                  {formatLitres(stock.produced)}
                </span>
                <span className="text-emerald-600">Produced</span>
              </div>
              <span className="text-lg font-bold text-slate-400">-</span>
              <div className="flex items-center gap-2 rounded-lg bg-sky-50 px-3 py-2">
                <span className="font-mono font-bold text-sky-700">
                  {formatLitres(stock.sold)}
                </span>
                <span className="text-sky-600">Sold</span>
              </div>
              <span className="text-lg font-bold text-slate-400">-</span>
              <div className="flex items-center gap-2 rounded-lg bg-amber-50 px-3 py-2">
                <span className="font-mono font-bold text-amber-700">
                  {formatLitres(stock.wasted)}
                </span>
                <span className="text-amber-600">Wasted</span>
              </div>
              <span className="text-lg font-bold text-slate-400">=</span>
              <div
                className={`flex items-center gap-2 rounded-lg px-3 py-2 font-semibold ${
                  isOutOfStock ? 'bg-rose-50' : 'bg-indigo-50'
                }`}
              >
                <span
                  className={`font-mono text-lg font-bold ${
                    isOutOfStock ? 'text-rose-700' : 'text-indigo-700'
                  }`}
                >
                  {formatLitres(stock.closing_stock)}
                </span>
                <span className={isOutOfStock ? 'text-rose-600' : 'text-indigo-600'}>
                  Closing
                </span>
              </div>
            </div>
          </div>
        </>
      )}

      {showWastageForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs">
        <div
          className="w-full max-w-md rounded-2xl bg-white shadow-2xl"
          role="dialog"
          aria-modal="true"
          aria-labelledby="wastage-title"
        >
          <div className="flex items-center justify-between border-b border-slate-100 p-6">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-100">
                <AlertTriangle className="h-5 w-5 text-amber-600" />
              </div>
              <div>
                <h2 id="wastage-title" className="font-bold text-slate-900">
                  Record Milk Wastage
                </h2>
                  <p className="text-xs text-slate-500">
                    Spoilage, spillage, or returned milk
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={closeWastageForm}
                disabled={wastageLoading}
                aria-label="Close wastage form"
                className="rounded-lg p-1.5 transition hover:bg-slate-100 disabled:opacity-50"
              >
                <X className="h-5 w-5 text-slate-500" />
              </button>
            </div>

            <form onSubmit={handleWastage} className="space-y-4 p-6">
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-700">
                  Wastage Date
                </label>
                <input
                  type="date"
                  value={date}
                  readOnly
                  className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-700">
                    Litres Wasted <span className="text-rose-500">*</span>
                  </label>
                  <input
                    required
                    type="number"
                    min="0.01"
                    max={availableLitres > 0 ? availableLitres.toFixed(2) : undefined}
                    step="0.01"
                    placeholder="e.g. 2.50"
                    value={wastageForm.litres}
                    onChange={(event) => {
                      setWastageError(null);
                      setWastageForm({ ...wastageForm, litres: event.target.value });
                    }}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-700">
                    Reason <span className="text-rose-500">*</span>
                  </label>
                  <select
                    value={wastageForm.reason}
                    onChange={(event) => {
                      setWastageError(null);
                      setWastageForm({ ...wastageForm, reason: event.target.value });
                    }}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
                  >
                    {WASTAGE_REASONS.map((reason) => (
                      <option key={reason.value} value={reason.value}>
                        {reason.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <p className="text-xs text-slate-500">
                Available to waste:{' '}
                <span className="font-semibold text-slate-700">
                  {formatLitres(availableLitres)}
                </span>
              </p>

              {wastageError && <ErrorAlert error={wastageError} />}

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={closeWastageForm}
                  disabled={wastageLoading}
                  className="rounded-lg bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-200 disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={wastageLoading || availableLitres <= 0}
                  className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-amber-600 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {wastageLoading ? 'Saving…' : 'Record Wastage'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
