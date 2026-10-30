import { useState, useEffect, useCallback } from 'react';
import { toast } from 'react-toastify';
import { getDashboardReport, getProfitReport, downloadReportPdf } from '../../api/reports';
import { useAuth } from '../../hooks/useAuth';
import { getTodayKolkataDate, formatDate, formatCurrency, formatLitres } from '../../utils/formatters';
import PageHeader from '../../components/PageHeader';
import LoadingSpinner from '../../components/LoadingSpinner';
import ErrorAlert from '../../components/ErrorAlert';
import {
  TrendingUp, Milk, PawPrint,
  CalendarDays, ArrowUpRight, ArrowDownRight, RefreshCw, AlertTriangle,
  FileText, Wallet, FileDown,
} from 'lucide-react';

const REPORT_TYPE_OPTIONS = {
  profit: {
    label: 'Profit & Loss',
    description: 'Revenue, expenses, category split and daily net profit',
    adminOnly: true,
  },
  production: {
    label: 'Milk Production',
    description: 'Morning and evening collection with herd averages',
    adminOnly: false,
  },
  dashboard: {
    label: 'Operational Snapshot',
    description: 'Herd, production, stock and sales for one day',
    adminOnly: false,
  },
};

/** Trigger a browser download for a binary PDF response. */
function downloadPdfResponse(response, fallbackName) {
  const payload = response?.data ?? response;
  const blob = payload instanceof Blob ? payload : new Blob([payload], { type: 'application/pdf' });
  const disposition = response?.headers?.['content-disposition'] || '';
  const match = /filename="?([^";]+)"?/i.exec(disposition);
  const filename = match ? match[1] : fallbackName;

  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** Blob requests cannot read the JSON error envelope, so decode it for the toast. */
async function describeError(err, fallback) {
  const data = err?.raw?.response?.data;
  if (data instanceof Blob) {
    try {
      const payload = JSON.parse(await data.text());
      if (payload?.error?.message) return payload.error.message;
    } catch {
      // Not JSON - fall through to the axios message.
    }
  }
  return err?.message || fallback;
}

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
  const [profitLoading, setProfitLoading] = useState(isAdmin);
  const [dashError, setDashError] = useState(null);
  const [profitError, setProfitError] = useState(null);
  const [reportType, setReportType] = useState(isAdmin ? 'profit' : 'production');
  const [generating, setGenerating] = useState(false);

  const [fromDate, setFromDate] = useState(() => {
    // Default: first day of current month
    const d = new Date(today);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`;
  });
  const [toDate, setToDate] = useState(today);

  const fetchDashboard = useCallback(() => {
    return getDashboardReport()
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
    return getProfitReport(fromDate, toDate)
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

  const handleGenerateReport = async () => {
    if (fromDate > toDate) {
      toast.error('The start date cannot be after the end date.');
      return;
    }
    const option = REPORT_TYPE_OPTIONS[reportType];
    if (option.adminOnly && !isAdmin) {
      toast.error('Profit and loss reports are restricted to Admin users.');
      return;
    }

    setGenerating(true);
    try {
      const params = { type: reportType, from: fromDate, to: toDate };
      if (reportType === 'dashboard') {
        params.date = toDate;
      }
      const response = await downloadReportPdf(params);
      downloadPdfResponse(
        response,
        `dairy-${reportType}-report-${fromDate}_to_${toDate}.pdf`
      );
      toast.success(`${option.label} PDF generated.`);
      if (reportType === 'profit' && isAdmin) {
        refreshProfit();
      }
      if (reportType === 'dashboard') {
        refreshDashboard();
      }
    } catch (err) {
      toast.error(
        await describeError(err, 'Failed to generate the report PDF.')
      );
    } finally {
      setGenerating(false);
    }
  };

  const herd = dashData?.buffaloes || {};
  const production = dashData?.production || {};
  const stock = dashData?.stock || {};
  const sales = dashData?.sales || {};
  const financials = dashData?.financials || null;
  const profit = profitData?.summary || null;
  const dailyBreakdown = profitData?.daily_breakdown || [];
  const categoryBreakdown = profitData?.category_breakdown || [];
  const monthProfit = financials?.month_to_date?.profit;

  const availableTypes = Object.entries(REPORT_TYPE_OPTIONS).filter(
    ([, option]) => isAdmin || !option.adminOnly
  );

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
              <StatCard label="Active Buffaloes" value={herd.active ?? 0} icon={PawPrint} color="text-emerald-700" bg="bg-emerald-50" />
              <StatCard label="Dry" value={herd.dry ?? 0} icon={PawPrint} color="text-amber-700" bg="bg-amber-50" />
              <StatCard label="Sold" value={herd.sold ?? 0} icon={PawPrint} color="text-sky-700" bg="bg-sky-50" />
              <StatCard label="Total Herd" value={herd.total ?? 0} icon={PawPrint} color="text-slate-700" bg="bg-slate-100" />
            </div>

            {/* Production & Stock */}
            <p className="text-xs text-slate-400 font-semibold uppercase tracking-widest mb-2">Production & Stock</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
              <StatCard label="Produced Today" value={formatLitres(production.grand_total_litres ?? 0)} icon={Milk} color="text-emerald-700" bg="bg-emerald-50" />
              <StatCard label="Morning" value={formatLitres(production.morning_litres ?? 0)} icon={Milk} color="text-amber-700" bg="bg-amber-50" />
              <StatCard label="Evening" value={formatLitres(production.evening_litres ?? 0)} icon={Milk} color="text-indigo-700" bg="bg-indigo-50" />
              <StatCard label="Closing Stock" value={formatLitres(stock.closing_stock ?? 0)} icon={Milk} color="text-slate-700" bg="bg-slate-100" />
            </div>

            {/* Sales & Financials */}
            <p className="text-xs text-slate-400 font-semibold uppercase tracking-widest mb-2">
              Sales & Financial {!isAdmin && <span className="text-amber-500">(Restricted)</span>}
            </p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
              <StatCard label="Sales Today" value={sales.sales_count ?? 0} icon={FileText} color="text-sky-700" bg="bg-sky-50" />
              <StatCard label="Milk Sold Today" value={formatLitres(sales.litres_sold ?? 0)} icon={Milk} color="text-emerald-700" bg="bg-emerald-50" />
              <StatCard
                label="Today's Revenue"
                value={isAdmin ? formatCurrency(financials?.today?.revenue ?? 0) : '•••••'}
                icon={TrendingUp}
                color="text-emerald-700"
                bg="bg-emerald-50"
              />
              <StatCard
                label="Month Profit"
                value={isAdmin ? formatCurrency(monthProfit ?? 0) : '•••••'}
                icon={Wallet}
                color={isAdmin && monthProfit < 0 ? 'text-rose-700' : 'text-emerald-700'}
                bg={isAdmin && monthProfit < 0 ? 'bg-rose-50' : 'bg-emerald-50'}
                trendLabel={
                  isAdmin && monthProfit !== undefined
                    ? `${formatCurrency(financials?.month_to_date?.revenue ?? 0)} revenue month to date`
                    : undefined
                }
                trend={monthProfit ?? 0}
              />
            </div>
          </>
        )}
      </section>

      {/* === REPORT EXPORT === */}
      <section className="mb-8">
        <h2 className="text-sm font-bold text-slate-700 uppercase tracking-wider mb-4">Generate Report PDF</h2>
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-3 items-end">
            <div className="lg:col-span-1">
              <label className="block text-xs font-semibold text-slate-600 mb-1">Report type</label>
              <select
                value={reportType}
                onChange={(e) => setReportType(e.target.value)}
                className="w-full px-2.5 py-2 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400 bg-white"
              >
                {availableTypes.map(([value, option]) => (
                  <option key={value} value={value}>{option.label}</option>
                ))}
              </select>
            </div>
            <div className="lg:col-span-1">
              <label className="block text-xs font-semibold text-slate-600 mb-1">From</label>
              <input
                type="date"
                value={fromDate}
                max={toDate}
                onChange={handleFromDateChange}
                className="w-full px-2.5 py-2 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400 bg-white"
              />
            </div>
            <div className="lg:col-span-1">
              <label className="block text-xs font-semibold text-slate-600 mb-1">To</label>
              <input
                type="date"
                value={toDate}
                min={fromDate}
                max={today}
                onChange={handleToDateChange}
                className="w-full px-2.5 py-2 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400 bg-white"
              />
            </div>
            <div className="lg:col-span-1">
              <button
                onClick={handleGenerateReport}
                disabled={generating}
                className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 text-sm font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg transition disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {generating ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" /> Generating…
                  </>
                ) : (
                  <>
                    <FileDown className="w-4 h-4" /> Generate Report
                  </>
                )}
              </button>
            </div>
          </div>
          <p className="mt-3 text-xs text-slate-500">
            {REPORT_TYPE_OPTIONS[reportType]?.description}. A PDF with the selected period&apos;s
            KPIs, tables and charts is downloaded for the current range
            ({formatDate(fromDate)} – {formatDate(toDate)}).
          </p>
          {reportType === 'dashboard' && (
            <p className="mt-1 text-xs text-slate-400">
              The operational snapshot covers the end date of the range.
            </p>
          )}
        </div>
      </section>

      {/* === PROFIT REPORT (Admin Only) === */}
      {isAdmin && (
        <section>
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
            <h2 className="text-sm font-bold text-slate-700 uppercase tracking-wider">Profit & Loss Report</h2>
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-2">
                <CalendarDays className="w-4 h-4 text-slate-500" />
                <span className="text-xs text-slate-500">
                  {formatDate(fromDate)} – {formatDate(toDate)}
                </span>
              </div>
              <button
                onClick={refreshProfit}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 rounded-lg transition"
              >
                <RefreshCw className="w-3.5 h-3.5" /> Refresh
              </button>
            </div>
          </div>

          {profitLoading ? (
            <LoadingSpinner message="Calculating profit report…" />
          ) : profitError ? (
            <ErrorAlert message={profitError} onRetry={refreshProfit} />
          ) : !profit ? null : (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 mb-5">
                <div className="bg-white rounded-xl border border-emerald-200 p-4 shadow-sm">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Total Revenue</p>
                  <p className="text-2xl font-bold text-emerald-700">{formatCurrency(profit.total_revenue ?? 0)}</p>
                  <p className="text-xs text-slate-400 mt-1">{formatLitres(profit.total_litres_sold ?? 0)} sold</p>
                </div>
                <div className="bg-white rounded-xl border border-rose-200 p-4 shadow-sm">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Total Expenses</p>
                  <p className="text-2xl font-bold text-rose-700">{formatCurrency(profit.total_expenses ?? 0)}</p>
                  <p className="text-xs text-slate-400 mt-1">{categoryBreakdown.length} categories</p>
                </div>
                <div className={`rounded-xl border p-4 shadow-sm ${
                  (profit.net_profit ?? 0) >= 0
                    ? 'bg-emerald-50 border-emerald-300'
                    : 'bg-rose-50 border-rose-300'
                }`}>
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Net Profit</p>
                  <p className={`text-2xl font-bold ${(profit.net_profit ?? 0) >= 0 ? 'text-emerald-800' : 'text-rose-800'}`}>
                    {formatCurrency(profit.net_profit ?? 0)}
                  </p>
                  <div className={`flex items-center gap-1 text-xs font-medium mt-1 ${(profit.net_profit ?? 0) >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                    {(profit.net_profit ?? 0) >= 0
                      ? <><ArrowUpRight className="w-3 h-3" /> Profitable period</>
                      : <><ArrowDownRight className="w-3 h-3" /> Loss period</>
                    }
                  </div>
                </div>
                <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Days Recorded</p>
                  <p className="text-2xl font-bold text-slate-700">{dailyBreakdown.length}</p>
                  <p className="text-xs text-slate-400 mt-1">days with sales or expenses</p>
                </div>
              </div>

              {dailyBreakdown.length === 0 && categoryBreakdown.length === 0 ? (
                <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-center gap-3 text-amber-700">
                  <AlertTriangle className="w-5 h-5 shrink-0" />
                  <p className="text-sm font-medium">
                    No sales or expenses were recorded between {formatDate(fromDate)} and {formatDate(toDate)}.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                  {/* Daily Breakdown Table */}
                  <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
                    <div className="px-4 py-3 border-b border-slate-100 bg-slate-50">
                      <h3 className="text-sm font-bold text-slate-700">Daily Breakdown</h3>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-slate-100">
                            <th className="px-4 py-2.5 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Date</th>
                            <th className="px-4 py-2.5 text-right text-xs font-bold text-slate-500 uppercase tracking-wider">Revenue</th>
                            <th className="px-4 py-2.5 text-right text-xs font-bold text-slate-500 uppercase tracking-wider">Expenses</th>
                            <th className="px-4 py-2.5 text-right text-xs font-bold text-slate-500 uppercase tracking-wider">Net</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-50">
                          {dailyBreakdown.map((row) => {
                            const net = parseFloat(row.profit) || 0;
                            return (
                              <tr key={row.date} className="hover:bg-slate-50 transition-colors">
                                <td className="px-4 py-2 text-slate-600">{formatDate(row.date)}</td>
                                <td className="px-4 py-2 text-right text-emerald-700 font-semibold">{formatCurrency(row.revenue)}</td>
                                <td className="px-4 py-2 text-right text-rose-700">{formatCurrency(row.expenses)}</td>
                                <td className={`px-4 py-2 text-right font-bold ${net >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
                                  {formatCurrency(net)}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                        <tfoot>
                          <tr className="border-t border-slate-200 bg-slate-50 font-bold">
                            <td className="px-4 py-2 text-slate-700">Total</td>
                            <td className="px-4 py-2 text-right text-emerald-700">{formatCurrency(profit.total_revenue ?? 0)}</td>
                            <td className="px-4 py-2 text-right text-rose-700">{formatCurrency(profit.total_expenses ?? 0)}</td>
                            <td className={`px-4 py-2 text-right ${(profit.net_profit ?? 0) >= 0 ? 'text-emerald-800' : 'text-rose-800'}`}>
                              {formatCurrency(profit.net_profit ?? 0)}
                            </td>
                          </tr>
                        </tfoot>
                      </table>
                    </div>
                  </div>

                  {/* Expense Categories */}
                  <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
                    <div className="px-4 py-3 border-b border-slate-100 bg-slate-50">
                      <h3 className="text-sm font-bold text-slate-700">Expenses by Category</h3>
                    </div>
                    {categoryBreakdown.length === 0 ? (
                      <p className="px-4 py-3 text-xs text-slate-500">No expenses in this period.</p>
                    ) : (
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-slate-100">
                            <th className="px-4 py-2.5 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Category</th>
                            <th className="px-4 py-2.5 text-right text-xs font-bold text-slate-500 uppercase tracking-wider">Amount</th>
                            <th className="px-4 py-2.5 text-right text-xs font-bold text-slate-500 uppercase tracking-wider">Share</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-50">
                          {categoryBreakdown.map((row) => (
                            <tr key={row.category} className="hover:bg-slate-50 transition-colors">
                              <td className="px-4 py-2 text-slate-600 capitalize">{row.category}</td>
                              <td className="px-4 py-2 text-right text-rose-700 font-semibold">{formatCurrency(row.total_amount)}</td>
                              <td className="px-4 py-2 text-right text-slate-500">{row.percentage}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
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
