import { useState, useEffect, useCallback } from 'react';
import apiClient from '../../api/client';
import { useAuth } from '../../hooks/useAuth';
import { getTodayKolkataDate, formatDate, formatCurrency, formatLitres } from '../../utils/formatters';
import PageHeader from '../../components/PageHeader';
import LoadingSpinner from '../../components/LoadingSpinner';
import ErrorAlert from '../../components/ErrorAlert';
import {
  BarChart3, TrendingUp, Milk, PawPrint,
  CalendarDays, ArrowUpRight, ArrowDownRight, RefreshCw, AlertTriangle,
  FileText, Clock,
} from 'lucide-react';

function StatCard({ label, value, icon: Icon, color, bg, trend, trendLabel }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 flex flex-col gap-2 shadow-sm">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{label}</span>
        <div className={`w-8 h-8 rounded-lg ${bg} flex items-center justify-center`}>
          <Icon className={`w-4 h-4 ${color}`} />
        </div>
      </div>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      {trendLabel && (
        <div className={`flex items-center gap-1 text-xs font-medium ${trend >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
          {trend >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
          {trendLabel}
        </div>
      )}
    </div>
  );
}

export default function Reports() {
  const { isAdmin } = useAuth();
  const today = getTodayKolkataDate();

  const [dashData, setDashData] = useState(null);
  const [profitData, setProfitData] = useState(null);
  const [dashLoading, setDashLoading] = useState(true);
  const [profitLoading, setProfitLoading] = useState(false);
  const [dashError, setDashError] = useState(null);
  const [profitError, setProfitError] = useState(null);

  const [fromDate, setFromDate] = useState(() => {
    // Default: first day of current month
    const d = new Date(today);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`;
  });
  const [toDate, setToDate] = useState(today);

  const fetchDashboard = useCallback(() => {
    return apiClient.get('/reports/dashboard')
      .then((res) => {
        setDashData(res);
        setDashError(null);
      })
      .catch((err) => {
        setDashError(err.message || 'Failed to load dashboard data.');
      })
      .finally(() => {
        setDashLoading(false);
      });
  }, []);

  const fetchProfit = useCallback(() => {
    if (!isAdmin) return Promise.resolve();
    return apiClient.get('/reports/profit', { params: { from: fromDate, to: toDate } })
      .then((res) => {
        setProfitData(res);
        setProfitError(null);
      })
      .catch((err) => {
        setProfitError(err.message || 'Failed to load profit report.');
      })
      .finally(() => {
        setProfitLoading(false);
      });
  }, [isAdmin, fromDate, toDate]);

  useEffect(() => { fetchDashboard(); }, [fetchDashboard]);
  useEffect(() => { fetchProfit(); }, [fetchProfit]);

  const refreshDashboard = () => {
    setDashLoading(true);
    setDashError(null);
    fetchDashboard();
  };

  const refreshProfit = () => {
    if (!isAdmin) return;
    setProfitLoading(true);
    setProfitError(null);
    fetchProfit();
  };

  const handleFromDateChange = (e) => {
    setProfitLoading(true);
    setProfitError(null);
    setFromDate(e.target.value);
  };

  const handleToDateChange = (e) => {
    setProfitLoading(true);
    setProfitError(null);
    setToDate(e.target.value);
  };

  const herd = dashData?.herd || {};
  const production = dashData?.production || {};
  const stock = dashData?.stock || {};
  const financial = dashData?.financial || {};
  const profit = profitData?.summary || profitData;
  const dailyBreakdown = profitData?.daily || profitData?.breakdown || [];

  return (
    <div>
      <PageHeader
        title="Operational Reports"
        subtitle="Executive dashboard with daily farm stats, production summary, and financial analysis."
      />

      {/* === DASHBOARD SNAPSHOT === */}
      <section className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-bold text-slate-700 uppercase tracking-wider">Today's Farm Snapshot</h2>
          <button
            onClick={refreshDashboard}
            className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 rounded-lg transition"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
        </div>

        {dashLoading ? (
          <LoadingSpinner message="Loading dashboard…" />
        ) : dashError ? (
          <ErrorAlert message={dashError} onRetry={refreshDashboard} />
        ) : (
          <>
            {/* Herd */}
            <p className="text-xs text-slate-400 font-semibold uppercase tracking-widest mb-2">Buffalo Herd</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
              <StatCard label="Active Buffaloes" value={herd.active ?? '—'} icon={PawPrint} color="text-emerald-700" bg="bg-emerald-50" />
              <StatCard label="Dry" value={herd.dry ?? '—'} icon={PawPrint} color="text-amber-700" bg="bg-amber-50" />
              <StatCard label="Sold" value={herd.sold ?? '—'} icon={PawPrint} color="text-sky-700" bg="bg-sky-50" />
              <StatCard label="Total Herd" value={herd.total ?? '—'} icon={PawPrint} color="text-slate-700" bg="bg-slate-100" />
            </div>

            {/* Production & Stock */}
            <p className="text-xs text-slate-400 font-semibold uppercase tracking-widest mb-2">Production & Stock</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
              <StatCard label="Produced Today" value={formatLitres(production.today_total ?? 0)} icon={Milk} color="text-emerald-700" bg="bg-emerald-50" />
              <StatCard label="Morning" value={formatLitres(production.morning_total ?? 0)} icon={Milk} color="text-amber-700" bg="bg-amber-50" />
              <StatCard label="Evening" value={formatLitres(production.evening_total ?? 0)} icon={Milk} color="text-indigo-700" bg="bg-indigo-50" />
              <StatCard label="Closing Stock" value={formatLitres(stock.closing ?? 0)} icon={Milk} color="text-slate-700" bg="bg-slate-100" />
            </div>

            {/* Financial (admin-only or masked) */}
            <p className="text-xs text-slate-400 font-semibold uppercase tracking-widest mb-2">
              Financial {!isAdmin && <span className="text-amber-500">(Restricted)</span>}
            </p>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-5">
              <StatCard label="Today's Revenue" value={isAdmin ? formatCurrency(financial.today_revenue ?? 0) : '•••••'} icon={TrendingUp} color="text-emerald-700" bg="bg-emerald-50" />
              <StatCard label="Unpaid Balance" value={isAdmin ? formatCurrency(financial.unpaid_balance ?? 0) : '•••••'} icon={Clock} color="text-rose-700" bg="bg-rose-50" />
              <StatCard label="Total Invoices" value={financial.total_invoices ?? '—'} icon={FileText} color="text-sky-700" bg="bg-sky-50" />
            </div>
          </>
        )}
      </section>

      {/* === PROFIT REPORT (Admin Only) === */}
      {isAdmin && (
        <section>
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
            <h2 className="text-sm font-bold text-slate-700 uppercase tracking-wider">Profit & Loss Report</h2>
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-2">
                <CalendarDays className="w-4 h-4 text-slate-500" />
                <input
                  type="date"
                  value={fromDate}
                  max={toDate}
                  onChange={handleFromDateChange}
                  className="px-2.5 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400 bg-white"
                />
                <span className="text-slate-400 text-xs">to</span>
                <input
                  type="date"
                  value={toDate}
                  min={fromDate}
                  max={today}
                  onChange={handleToDateChange}
                  className="px-2.5 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400 bg-white"
                />
              </div>
              <button
                onClick={refreshProfit}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg transition"
              >
                <BarChart3 className="w-3.5 h-3.5" /> Generate Report
              </button>
            </div>
          </div>

          {profitLoading ? (
            <LoadingSpinner message="Calculating profit report…" />
          ) : profitError ? (
            <ErrorAlert message={profitError} onRetry={refreshProfit} />
          ) : !profitData ? null : (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-5">
                <div className="bg-white rounded-xl border border-emerald-200 p-4 shadow-sm">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Total Revenue</p>
                  <p className="text-2xl font-bold text-emerald-700">{formatCurrency(profit?.total_revenue ?? profit?.revenue ?? 0)}</p>
                  <p className="text-xs text-slate-400 mt-1">{formatDate(fromDate)} – {formatDate(toDate)}</p>
                </div>
                <div className="bg-white rounded-xl border border-rose-200 p-4 shadow-sm">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Total Expenses</p>
                  <p className="text-2xl font-bold text-rose-700">{formatCurrency(profit?.total_expenses ?? profit?.expenses ?? 0)}</p>
                </div>
                <div className={`rounded-xl border p-4 shadow-sm ${
                  (profit?.net_profit ?? profit?.net ?? 0) >= 0
                    ? 'bg-emerald-50 border-emerald-300'
                    : 'bg-rose-50 border-rose-300'
                }`}>
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Net Profit</p>
                  <p className={`text-2xl font-bold ${(profit?.net_profit ?? profit?.net ?? 0) >= 0 ? 'text-emerald-800' : 'text-rose-800'}`}>
                    {formatCurrency(profit?.net_profit ?? profit?.net ?? 0)}
                  </p>
                  <div className={`flex items-center gap-1 text-xs font-medium mt-1 ${(profit?.net_profit ?? profit?.net ?? 0) >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                    {(profit?.net_profit ?? profit?.net ?? 0) >= 0
                      ? <><ArrowUpRight className="w-3 h-3" /> Profitable period</>
                      : <><ArrowDownRight className="w-3 h-3" /> Loss period</>
                    }
                  </div>
                </div>
              </div>

              {/* Daily Breakdown Table */}
              {dailyBreakdown.length > 0 && (
                <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
                  <div className="px-4 py-3 border-b border-slate-100 bg-slate-50">
                    <h3 className="text-sm font-bold text-slate-700">Daily Breakdown</h3>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-slate-100">
                          <th className="px-4 py-2.5 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Date</th>
                          <th className="px-4 py-2.5 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Revenue</th>
                          <th className="px-4 py-2.5 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Expenses</th>
                          <th className="px-4 py-2.5 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Net</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-50">
                        {dailyBreakdown.map((row, i) => {
                          const net = (parseFloat(row.revenue) || 0) - (parseFloat(row.expenses) || 0);
                          return (
                            <tr key={i} className="hover:bg-slate-50 transition-colors">
                              <td className="px-4 py-2 text-slate-600">{formatDate(row.date)}</td>
                              <td className="px-4 py-2 text-emerald-700 font-semibold">{formatCurrency(row.revenue)}</td>
                              <td className="px-4 py-2 text-rose-700">{formatCurrency(row.expenses)}</td>
                              <td className={`px-4 py-2 font-bold ${net >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
                                {formatCurrency(net)}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </section>
      )}

      {!isAdmin && (
        <div className="mt-6 p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-center gap-3 text-amber-700">
          <AlertTriangle className="w-5 h-5 shrink-0" />
          <p className="text-sm font-medium">Profit & Loss reports are restricted to Admin users only.</p>
        </div>
      )}
    </div>
  );
}
