import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { getDashboardReport } from '../../api/reports';
import {
  formatDate,
  formatCurrency,
  formatLitres,
  getTodayKolkataDate,
} from '../../utils/formatters';
import PageHeader from '../../components/PageHeader';
import ErrorAlert from '../../components/ErrorAlert';
import {
  PawPrint,
  Milk,
  Layers,
  ShoppingCart,
  TrendingUp,
  TrendingDown,
  Calendar,
  RefreshCw,
  Plus,
  Shield,
  ArrowRight,
  Sun,
  Moon,
  AlertTriangle,
  AlertCircle,
} from 'lucide-react';

const hasValue = (value) =>
  value !== null && value !== undefined && value !== '';

function parseNumeric(value) {
  if (!hasValue(value)) return null;
  const numeric = typeof value === 'string' ? parseFloat(value) : Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function displayCount(value) {
  return hasValue(value) ? value : '—';
}

function displayLitres(value) {
  return hasValue(value) ? formatLitres(value) : '—';
}

function displayCurrency(value) {
  return hasValue(value) ? formatCurrency(value) : '—';
}

function isCanceledRequest(error) {
  return (
    error?.raw?.code === 'ERR_CANCELED' ||
    error?.raw?.name === 'CanceledError' ||
    error?.code === 'ERR_CANCELED'
  );
}

function SkeletonBlock({ className = '' }) {
  return <div className={`animate-pulse rounded-lg bg-slate-200/80 ${className}`} />;
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading dashboard data…</span>

      <SkeletonBlock className="h-14 w-full" />

      <div className="space-y-3">
        <SkeletonBlock className="h-4 w-40" />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {Array.from({ length: 5 }).map((_, index) => (
            <SkeletonBlock key={index} className="h-24 w-full" />
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <SkeletonBlock className="h-72 w-full lg:col-span-6" />
        <SkeletonBlock className="h-72 w-full lg:col-span-6" />
      </div>
    </div>
  );
}

function HerdCard({ label, value, hint, tone = 'slate' }) {
  const tones = {
    slate: 'bg-white border-slate-200 text-slate-900',
    emerald: 'bg-emerald-50/80 border-emerald-200 text-emerald-900',
    amber: 'bg-amber-50/80 border-amber-200 text-amber-900',
  };

  return (
    <div className={`rounded-xl border p-4 shadow-xs ${tones[tone] || tones.slate}`}>
      <span className="mb-1 block text-xs font-semibold opacity-75">{label}</span>
      <p className="text-2xl font-black">{value}</p>
      {hint && <span className="text-[11px] opacity-60">{hint}</span>}
    </div>
  );
}

function FinancialCard({ label, value, hint, tone = 'slate' }) {
  return (
    <div className={`rounded-xl border p-5 shadow-xs ${tone}`}>
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wider opacity-70">
        {label}
      </span>
      <p className="text-2xl font-black">{value}</p>
      {hint && <p className="mt-1 text-[11px] opacity-60">{hint}</p>}
    </div>
  );
}

export function Dashboard() {
  const { isAdmin } = useAuth();
  const [selectedDate, setSelectedDate] = useState(getTodayKolkataDate);
  const [dashboardData, setDashboardData] = useState(null);
  const [status, setStatus] = useState('loading');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const requestSequence = useRef(0);

  const fetchDashboard = useCallback((date, { signal, keepData = false } = {}) => {
    const sequence = ++requestSequence.current;

    return getDashboardReport(date, { signal })
      .then((data) => {
        if (sequence !== requestSequence.current) return;
        setDashboardData(data);
        setError(null);
        setStatus('ready');
      })
      .catch((err) => {
        if (sequence !== requestSequence.current) return;
        if (isCanceledRequest(err)) return;
        setError(err);
        if (!keepData) setDashboardData(null);
        setStatus('error');
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchDashboard(selectedDate, { signal: controller.signal });
    return () => controller.abort();
  }, [selectedDate, fetchDashboard]);

  const handleRefresh = () => {
    if (isRefreshing) return;
    setIsRefreshing(true);
    fetchDashboard(selectedDate, { keepData: true }).finally(() => {
      setIsRefreshing(false);
    });
  };

  const handleRetry = () => {
    setError(null);
    setStatus('loading');
    fetchDashboard(selectedDate, { keepData: true });
  };

  const handleDateChange = (event) => {
    setSelectedDate(event.target.value);
    setDashboardData(null);
    setError(null);
    setIsRefreshing(false);
    setStatus('loading');
  };

  const dataDate = dashboardData?.date || selectedDate;
  const isToday = dataDate === getTodayKolkataDate();

  const buffaloes = dashboardData?.buffaloes;
  const production = dashboardData?.production;
  const stock = dashboardData?.stock;
  const sales = dashboardData?.sales;
  const financials = isAdmin ? dashboardData?.financials : null;

  const morningLitres = parseNumeric(production?.morning_litres);
  const eveningLitres = parseNumeric(production?.evening_litres);
  const totalProduction = parseNumeric(production?.grand_total_litres) ?? 0;
  const hasProduction = morningLitres !== null || eveningLitres !== null;
  const morningPct =
    totalProduction > 0 && morningLitres !== null
      ? ((morningLitres / totalProduction) * 100).toFixed(1)
      : null;
  const eveningPct =
    totalProduction > 0 && eveningLitres !== null
      ? ((eveningLitres / totalProduction) * 100).toFixed(1)
      : null;

  const closingStock = parseNumeric(stock?.closing_stock);
  const isOutOfStock = closingStock !== null && closingStock <= 0;

  const activeCount = parseNumeric(buffaloes?.active);
  const averageYield =
    activeCount !== null && activeCount > 0 && hasProduction
      ? `${(totalProduction / activeCount).toFixed(2)} L / head`
      : '—';

  const showNewFarmHint = parseNumeric(buffaloes?.total) === 0;
  const showNoProductionHint =
    hasValue(production?.grand_total_litres) && totalProduction === 0;

  const renderDateControls = (
    <div className="flex flex-wrap items-center gap-2.5">
      <div className="flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-1.5 shadow-xs">
        <Calendar className="h-4 w-4 text-slate-500" />
        <input
          type="date"
          value={selectedDate}
          onChange={handleDateChange}
          max={getTodayKolkataDate()}
          aria-label="Dashboard date"
          className="bg-transparent text-xs font-semibold text-slate-800 focus:outline-hidden"
        />
      </div>
      <button
        type="button"
        onClick={handleRefresh}
        disabled={isRefreshing || status === 'loading'}
        className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-xs transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        title="Refresh live data"
      >
        <RefreshCw
          className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin text-emerald-600' : ''}`}
        />
        <span>Refresh</span>
      </button>
    </div>
  );

  const header = (
    <PageHeader
      title="Farm Operations Dashboard"
      subtitle={
        isToday
          ? `Real-time herd, production, stock, and sales metrics for today (${formatDate(dataDate)}).`
          : `Historical operations snapshot for ${formatDate(dataDate)}.`
      }
      badge={isAdmin ? 'Admin View' : 'Operator View'}
      action={renderDateControls}
    />
  );

  if (status === 'loading' && !dashboardData) {
    return (
      <div className="space-y-6">
        {header}
        <DashboardSkeleton />
      </div>
    );
  }

  if (error && !dashboardData) {
    return (
      <div className="space-y-6">
        {header}
        <div className="rounded-xl border border-rose-200 bg-white p-5 shadow-xs">
          <ErrorAlert error={error} />
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleRetry}
              className="inline-flex items-center gap-2 rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-rose-700"
            >
              <RefreshCw className="h-4 w-4" />
              <span>Try again</span>
            </button>
            <p className="text-xs text-slate-500">
              The dashboard could not be loaded. Check your connection and try again.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {header}

      {error && (
        <div className="space-y-1">
          <ErrorAlert error={error} onDismiss={() => setError(null)} />
          <p className="px-1 text-xs text-slate-500">
            Showing the last successfully loaded snapshot.
          </p>
        </div>
      )}

      {showNewFarmHint && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-200 bg-emerald-50/70 p-4">
          <div className="flex items-center gap-3">
            <PawPrint className="h-5 w-5 text-emerald-700" />
            <p className="text-sm font-medium text-emerald-900">
              No buffaloes are registered yet. Register the first buffalo to start tracking
              production and stock.
            </p>
          </div>
          <Link
            to="/buffaloes"
            className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-emerald-700"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>Register Buffalo</span>
          </Link>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-xs">
        <span className="hidden px-2 text-xs font-bold uppercase tracking-wider text-slate-500 sm:inline">
          Quick Actions:
        </span>
        <Link
          to="/production"
          className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-xs transition hover:bg-emerald-700"
        >
          <Plus className="h-3.5 w-3.5" />
          <span>Record Milk Production</span>
        </Link>
        <Link
          to="/sales"
          className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700 transition hover:bg-emerald-100"
        >
          <ShoppingCart className="h-3.5 w-3.5" />
          <span>New Customer Sale</span>
        </Link>
        <Link
          to="/stock"
          className="inline-flex items-center gap-1.5 rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-200"
        >
          <Layers className="h-3.5 w-3.5" />
          <span>Record Wastage</span>
        </Link>
        <Link
          to="/buffaloes"
          className="inline-flex items-center gap-1.5 rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-200"
        >
          <PawPrint className="h-3.5 w-3.5" />
          <span>Buffalo Registry</span>
        </Link>
      </div>

      {isAdmin && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-amber-700">
              <Shield className="h-4 w-4 text-amber-600" />
              <span>Financial Overview (Admin Only)</span>
            </h3>
            {financials?.month_to_date && (
              <span className="text-xs text-slate-500">
                Month-to-Date: {formatDate(financials.month_to_date.from)} –{' '}
                {formatDate(financials.month_to_date.to)}
              </span>
            )}
          </div>

          {financials ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <FinancialCard
                label="Day Sales Revenue"
                value={displayCurrency(financials.today?.revenue)}
                hint="From recorded milk customer sales"
                tone="bg-white border-slate-200 text-slate-900"
              />
              <FinancialCard
                label="Day Farm Expenses"
                value={displayCurrency(financials.today?.expenses)}
                hint="Fodder, labour, medical & electricity"
                tone="bg-white border-slate-200 text-slate-900"
              />
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
                <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Day Net Profit
                </span>
                <div className="flex items-baseline gap-2">
                  <p
                    className={`text-2xl font-black ${
                      (parseNumeric(financials.today?.profit) ?? 0) >= 0
                        ? 'text-emerald-600'
                        : 'text-rose-600'
                    }`}
                  >
                    {displayCurrency(financials.today?.profit)}
                  </p>
                  {(parseNumeric(financials.today?.profit) ?? 0) >= 0 ? (
                    <TrendingUp className="h-4 w-4 text-emerald-600" />
                  ) : (
                    <TrendingDown className="h-4 w-4 text-rose-600" />
                  )}
                </div>
                <p className="mt-1 text-[11px] text-slate-500">
                  Revenue minus logged expenses
                </p>
              </div>
              <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-5 shadow-xs">
                <span className="mb-1 block text-xs font-bold uppercase tracking-wider text-amber-900">
                  MTD Net Profit
                </span>
                <div className="flex items-baseline gap-2">
                  <p className="text-2xl font-black text-amber-950">
                    {displayCurrency(financials.month_to_date?.profit)}
                  </p>
                  <TrendingUp className="h-4 w-4 text-amber-700" />
                </div>
                <p className="mt-1 text-[11px] text-amber-800">
                  Revenue {displayCurrency(financials.month_to_date?.revenue)} • Exp{' '}
                  {displayCurrency(financials.month_to_date?.expenses)}
                </p>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
              <AlertCircle className="h-5 w-5 shrink-0" />
              <span>Financial figures are not available for this date.</span>
            </div>
          )}
        </div>
      )}

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Buffalo Herd Population
          </h3>
          <Link
            to="/buffaloes"
            className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600 hover:text-emerald-700"
          >
            <span>Manage Herd</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <HerdCard
            label="Total Herd"
            value={displayCount(buffaloes?.total)}
            hint="Registered head"
          />
          <HerdCard
            label="Active Milking"
            value={displayCount(buffaloes?.active)}
            hint="Eligible for production"
            tone="emerald"
          />
          <HerdCard
            label="Dry (Resting)"
            value={displayCount(buffaloes?.dry)}
            hint="Non-lactating"
            tone="amber"
          />
          <HerdCard
            label="Sold"
            value={displayCount(buffaloes?.sold)}
            hint="History preserved"
          />
          <HerdCard
            label="Deceased"
            value={displayCount(buffaloes?.dead)}
            hint="Inactive"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-6 shadow-xs lg:col-span-6">
          <div>
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <div className="flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-100 font-bold text-emerald-700">
                  <Milk className="h-5 w-5" />
                </div>
                <div>
                  <h4 className="text-base font-bold text-slate-900">Day Milk Production</h4>
                  <p className="text-xs text-slate-500">Morning & evening session totals</p>
                </div>
              </div>
              <Link
                to="/production"
                className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600 hover:text-emerald-700"
              >
                <span>Grid Entry</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>

            <div className="my-6 grid grid-cols-3 gap-3 text-center">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <div className="mb-1 flex items-center justify-center gap-1 text-xs font-semibold text-amber-700">
                  <Sun className="h-3.5 w-3.5" />
                  <span>Morning</span>
                </div>
                <p className="text-lg font-black text-slate-900">
                  {displayLitres(production?.morning_litres)}
                </p>
                <span className="text-[10px] text-slate-500">
                  {morningPct !== null ? `${morningPct}% of total` : '—'}
                </span>
              </div>

              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <div className="mb-1 flex items-center justify-center gap-1 text-xs font-semibold text-indigo-700">
                  <Moon className="h-3.5 w-3.5" />
                  <span>Evening</span>
                </div>
                <p className="text-lg font-black text-slate-900">
                  {displayLitres(production?.evening_litres)}
                </p>
                <span className="text-[10px] text-slate-500">
                  {eveningPct !== null ? `${eveningPct}% of total` : '—'}
                </span>
              </div>

              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3">
                <span className="mb-1 block text-xs font-bold text-emerald-800">Grand Total</span>
                <p className="text-lg font-black text-emerald-900">
                  {displayLitres(production?.grand_total_litres)}
                </p>
                <span className="text-[10px] font-medium text-emerald-700">Daily yield</span>
              </div>
            </div>

            {showNoProductionHint ? (
              <p className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-3 py-2 text-xs text-slate-500">
                No milk production has been recorded for this date yet.
              </p>
            ) : (
              morningPct !== null &&
              eveningPct !== null && (
                <div>
                  <div className="mb-1.5 flex items-center justify-between text-xs font-medium text-slate-500">
                    <span>Morning Session ({morningPct}%)</span>
                    <span>Evening Session ({eveningPct}%)</span>
                  </div>
                  <div
                    className="flex h-3 w-full overflow-hidden rounded-full bg-indigo-100"
                    role="img"
                    aria-label={`Morning ${displayLitres(
                      production?.morning_litres
                    )}, evening ${displayLitres(production?.evening_litres)}`}
                  >
                    <div
                      style={{ width: `${morningPct}%` }}
                      className="h-full bg-amber-400 transition-all duration-500"
                    />
                    <div
                      style={{ width: `${eveningPct}%` }}
                      className="h-full bg-indigo-500 transition-all duration-500"
                    />
                  </div>
                </div>
              )
            )}
          </div>

          <div className="mt-6 flex items-center justify-between border-t border-slate-100 pt-4 text-xs text-slate-500">
            <span>Average yield per active buffalo:</span>
            <span className="font-bold text-slate-800">{averageYield}</span>
          </div>
        </div>

        <div className="flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-6 shadow-xs lg:col-span-6">
          <div>
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <div className="flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-100 font-bold text-emerald-700">
                  <Layers className="h-5 w-5" />
                </div>
                <div>
                  <h4 className="text-base font-bold text-slate-900">Milk Stock Balance</h4>
                  <p className="text-xs text-slate-500">
                    Closing = Opening + Produced - Sold - Wasted
                  </p>
                </div>
              </div>
              <Link
                to="/stock"
                className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600 hover:text-emerald-700"
              >
                <span>Stock Ledger</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>

            <div className="my-6 grid grid-cols-2 gap-2.5 text-center text-xs sm:grid-cols-4">
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-2.5">
                <span className="mb-0.5 block text-slate-500">Opening</span>
                <p className="font-bold text-slate-800">
                  {displayLitres(stock?.opening_stock)}
                </p>
              </div>
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-2.5 text-emerald-800">
                <span className="mb-0.5 block">+ Produced</span>
                <p className="font-bold">{displayLitres(stock?.produced)}</p>
              </div>
              <div className="rounded-lg border border-rose-200 bg-rose-50 p-2.5 text-rose-800">
                <span className="mb-0.5 block">- Sold</span>
                <p className="font-bold">{displayLitres(stock?.sold)}</p>
              </div>
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-amber-800">
                <span className="mb-0.5 block">- Wasted</span>
                <p className="font-bold">{displayLitres(stock?.wasted)}</p>
              </div>
            </div>

            <div
              className={`flex items-center justify-between rounded-xl border p-4 ${
                isOutOfStock
                  ? 'border-rose-300 bg-rose-50 text-rose-900'
                  : 'border-emerald-300 bg-emerald-500/10 text-emerald-950'
              }`}
            >
              <div>
                <span className="block text-xs font-bold uppercase tracking-wider">
                  Available Closing Stock
                </span>
                <p className="mt-0.5 text-2xl font-black">
                  {displayLitres(stock?.closing_stock)}
                </p>
              </div>
              {isOutOfStock && (
                <div className="flex items-center gap-1 rounded-md bg-white/70 px-2.5 py-1 text-xs font-semibold text-rose-700">
                  <AlertTriangle className="h-4 w-4 text-rose-600" />
                  <span>No stock available</span>
                </div>
              )}
            </div>
          </div>

          <div className="mt-6 flex items-center justify-between border-t border-slate-100 pt-4 text-xs text-slate-500">
            <span>Customer sales recorded for this date:</span>
            <span className="font-bold text-slate-800">
              {displayCount(sales?.sales_count)} orders ({displayLitres(sales?.litres_sold)})
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
