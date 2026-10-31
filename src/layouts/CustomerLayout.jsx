import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useCustomerAuth } from '../hooks/useCustomerAuth';
import {
  Milk,
  LayoutDashboard,
  ClipboardList,
  ReceiptText,
  MessagesSquare,
  UserRound,
  LogOut,
  ArrowLeft,
} from 'lucide-react';

const NAV_ITEMS = [
  { to: '/portal', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/portal/orders', label: 'Milk Orders', icon: ClipboardList },
  { to: '/portal/invoices', label: 'Invoices', icon: ReceiptText },
  { to: '/portal/queries', label: 'Support', icon: MessagesSquare },
  { to: '/portal/profile', label: 'Profile', icon: UserRound },
];

export function CustomerLayout() {
  const { account, customer, logout } = useCustomerAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/portal/login', { replace: true });
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-600 text-white shadow-sm">
              <Milk className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-bold text-slate-900">
                {customer?.name || 'Customer Portal'}
              </p>
              <p className="truncate text-[11px] font-medium uppercase tracking-wider text-emerald-700">
                AmritDhara Dairy · My Account
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="hidden max-w-[180px] truncate text-xs text-slate-500 sm:block">
              {account?.email}
            </span>
            <button
              type="button"
              onClick={handleLogout}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 transition hover:bg-slate-50"
            >
              <LogOut className="h-3.5 w-3.5" /> Sign out
            </button>
          </div>
        </div>

        <nav className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-3 pb-2 sm:px-5">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `inline-flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition ${
                  isActive
                    ? 'bg-emerald-50 text-emerald-700'
                    : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                }`
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
        <Outlet />
      </main>

      <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-slate-400 sm:px-6">
        <NavLink
          to="/"
          className="inline-flex items-center gap-1.5 hover:text-emerald-700"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back to dairy homepage
        </NavLink>
      </footer>
    </div>
  );
}

export default CustomerLayout;
