import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import AppLayout from './layouts/AppLayout';
import Landing from './pages/Landing/Landing';
import Login from './pages/Login/Login';
import Dashboard from './pages/Dashboard/Dashboard';
import Buffaloes from './pages/Buffaloes/Buffaloes';
import Production from './pages/Production/Production';
import Stock from './pages/Stock/Stock';
import Customers from './pages/Customers/Customers';
import Sales from './pages/Sales/Sales';
import Invoices from './pages/Invoices/Invoices';
import Reports from './pages/Reports/Reports';
import Expenses from './pages/Expenses/Expenses';
import UserManagement from './pages/Users/Users';
import { Link } from 'react-router-dom';

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Public-facing Dairy Landing Page */}
          <Route path="/" element={<Landing />} />

          {/* Dedicated Staff / Operator Login Screen */}
          <Route path="/login" element={<Login />} />

          {/* Authenticated Application Shell Routes */}
          <Route
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/buffaloes" element={<Buffaloes />} />
            <Route path="/production" element={<Production />} />
            <Route path="/stock" element={<Stock />} />
            <Route path="/customers" element={<Customers />} />
            <Route path="/sales" element={<Sales />} />
            <Route path="/invoices" element={<Invoices />} />
            <Route path="/reports" element={<Reports />} />

            {/* Admin Only Routes */}
            <Route
              path="/expenses"
              element={
                <ProtectedRoute allowedRoles={['admin']}>
                  <Expenses />
                </ProtectedRoute>
              }
            />

            <Route
              path="/users"
              element={
                <ProtectedRoute allowedRoles={['admin']}>
                  <UserManagement />
                </ProtectedRoute>
              }
            />
          </Route>

          {/* 404 Route */}
          <Route
            path="*"
            element={
              <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-6 text-center">
                <h1 className="text-5xl font-extrabold text-slate-800 mb-2">404</h1>
                <p className="text-slate-600 mb-6">The requested page does not exist.</p>
                <Link
                  to="/"
                  className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 transition shadow-xs"
                >
                  Return to Dairy Homepage
                </Link>
              </div>
            }
          />
        </Routes>
        <ToastContainer position="top-right" autoClose={3000} hideProgressBar={false} />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
