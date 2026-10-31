import { Navigate, useLocation } from 'react-router-dom';
import { useCustomerAuth } from '../hooks/useCustomerAuth';
import { Loader2 } from 'lucide-react';

export function CustomerProtectedRoute({ children }) {
  const { isAuthenticated, isLoading } = useCustomerAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 text-slate-700">
        <Loader2 className="w-10 h-10 text-emerald-600 animate-spin mb-3" />
        <p className="text-sm font-medium text-slate-500">
          Checking your customer session...
        </p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/portal/login" state={{ from: location }} replace />;
  }

  return children;
}

export default CustomerProtectedRoute;
