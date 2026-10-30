import { useContext } from 'react';
import { CustomerAuthContext } from '../context/customerAuthContextDef';

export function useCustomerAuth() {
  const context = useContext(CustomerAuthContext);
  if (!context) {
    throw new Error('useCustomerAuth must be used within a CustomerAuthProvider');
  }
  return context;
}

export default useCustomerAuth;
