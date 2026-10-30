import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { getTodayKolkataDate, formatDate } from '../utils/formatters';
import ConfirmModal from '../components/ConfirmModal';
import {
  LayoutDashboard,
  PawPrint,
  Milk,
  Layers,
  Users,
  ShoppingCart,
  ReceiptText,
  BarChart3,
  Wallet,
  UserCog,
  LogOut,
  Menu,
  X,
  ShieldCheck,
  UserCheck,
} from 'lucide-react';

export function AppLayout() {
  const { user, isAdmin, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  const navItems = [
    { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
    { name: 'Buffalo Herd', path: '/buffaloes', icon: PawPrint },
    { name: 'Milk Production', path: '/production', icon: Milk },
    { name: 'Stock & Wastage', path: '/stock', icon: Layers },
    { name: 'Customers', path: '/customers', icon: Users },
    { name: 'Sales', path: '/sales', icon: ShoppingCart },
    { name: 'Invoices', path: '/invoices', icon: ReceiptText },
    { name: 'Reports', path: '/reports', icon: BarChart3 },
  ];

  const adminNavItems = [
    { name: 'Expenses', path: '/expenses', icon: Wallet },
    { name: 'User Management', path: '/users', icon: UserCog },
  ];

  const todayStr = getTodayKolkataDate();

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col md:flex-row">
      {/* Mobile Drawer Backdrop */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-slate-900/50 backdrop-blur-xs md:hidden"
          onClick={() => setMobileMenuOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar (Desktop + Mobile Drawer) */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-64 bg-white border-r border-slate-200 flex flex-col transition-transform duration-200 ease-in-out md:translate-x-0 md:static md:inset-auto ${
          mobileMenuOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full'
        }`}
      >
        {/* Brand Header */}
        <div className="h-16 flex items-center justify-between px-6 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-emerald-600 text-white flex items-center justify-center font-bold text-lg shadow-sm">
              <Milk className="w-5 h-5" />
            </div>
            <div>
              <span className="font-bold text-slate-900 text-base block leading-tight">DairyFlow</span>
              <span className="text-[10px] text-slate-500 uppercase tracking-widest font-semibold block">
                Farm Ops
              </span>
            </div>
          </div>
          <button
            type="button"
            className="md:hidden text-slate-400 hover:text-slate-600 p-1"
            onClick={() => setMobileMenuOpen(false)}
            aria-label="Close navigation"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation Links */}
        <div className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
          <div>
            <div className="px-3 mb-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Operations
            </div>
            <nav className="space-y-1">
              {navItems.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    onClick={() => setMobileMenuOpen(false)}
                    className={({ isActive }) =>
                      `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition ${
                        isActive
                          ? 'bg-emerald-50 text-emerald-700 font-semibold shadow-xs'
                          : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                      }`
                    }
                  >
                    <Icon className="w-4 h-4 shrink-0" />
                    <span>{item.name}</span>
                  </NavLink>
                );
              })}
            </nav>
          </div>

          {/* Admin Restricted Section */}
          {isAdmin && (
            <div>
              <div className="px-3 mb-2 text-[11px] font-bold uppercase tracking-wider text-amber-600 flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>Administration</span>
              </div>
              <nav className="space-y-1">
                {adminNavItems.map((item) => {
                  const Icon = item.icon;
                  return (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      onClick={() => setMobileMenuOpen(false)}
                      className={({ isActive }) =>
                        `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition ${
                          isActive
                            ? 'bg-amber-50 text-amber-900 font-semibold shadow-xs'
                            : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                        }`
                      }
                    >
                      <Icon className="w-4 h-4 shrink-0 text-amber-600" />
                      <span>{item.name}</span>
                    </NavLink>
                  );
                })}
              </nav>
            </div>
          )}
        </div>

        {/* User Profile & Logout in Sidebar Footer */}
        <div className="p-4 border-t border-slate-100 bg-slate-50/60">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 min-w-0">
              <div
                className={`w-9 h-9 rounded-full flex items-center justify-center font-bold text-sm shrink-0 ${
                  isAdmin ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'
                }`}
              >
                {user?.full_name?.charAt(0)?.toUpperCase() || 'U'}
              </div>
              <div className="min-w-0">
                <p className="text-xs font-semibold text-slate-800 truncate">{user?.full_name}</p>
                <span
                  className={`inline-flex items-center gap-1 text-[10px] font-medium uppercase tracking-wider px-1.5 py-0.2 rounded ${
                    isAdmin
                      ? 'bg-amber-100 text-amber-800'
                      : 'bg-emerald-100 text-emerald-800'
                  }`}
                >
                  {isAdmin ? <ShieldCheck className="w-3 h-3" /> : <UserCheck className="w-3 h-3" />}
                  {user?.role}
                </span>
              </div>
            </div>

            <button
              type="button"
              onClick={() => setShowLogoutConfirm(true)}
              className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition"
              title="Sign out"
              aria-label="Sign out"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Viewport */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Topbar */}
        <header className="h-16 bg-white border-b border-slate-200 px-4 sm:px-6 flex items-center justify-between sticky top-0 z-30">
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="md:hidden text-slate-500 hover:text-slate-700 p-2 rounded-lg hover:bg-slate-100"
              onClick={() => setMobileMenuOpen(true)}
              aria-label="Open navigation"
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="hidden sm:block">
              <span className="text-xs text-slate-500 font-medium">Farm Date:</span>{' '}
              <span className="text-xs font-semibold text-slate-800 bg-slate-100 px-2 py-0.5 rounded">
                {formatDate(todayStr)}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3 sm:gap-4">
            <div className="text-right hidden sm:block">
              <p className="text-xs font-medium text-slate-700">{user?.email}</p>
              <p className="text-[11px] text-slate-500">Timezone: Asia/Kolkata</p>
            </div>
            <button
              type="button"
              onClick={() => setShowLogoutConfirm(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-rose-50 hover:text-rose-700 rounded-lg transition"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        </header>

        {/* Main Content Area */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>

      {/* Logout Confirmation Dialog */}
      <ConfirmModal
        isOpen={showLogoutConfirm}
        title="Sign out of DairyFlow?"
        message="Are you sure you want to log out? You will need to sign in again to access the dairy operations dashboard."
        confirmText="Sign out"
        confirmVariant="danger"
        onConfirm={handleLogout}
        onClose={() => setShowLogoutConfirm(false)}
      />
    </div>
  );
}

export default AppLayout;
