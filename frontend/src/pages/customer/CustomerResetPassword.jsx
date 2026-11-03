import { PasswordResetConfirm } from '../../components/PasswordResetForms';
import {
  resetCustomerPassword,
  validateCustomerResetToken,
} from '../../api/customerAuth';
import { useCustomerAuth } from '../../hooks/useCustomerAuth';

export function CustomerResetPassword() {
  const { logout } = useCustomerAuth();

  return (
    <PasswordResetConfirm
      audience="Customer portal"
      validateToken={validateCustomerResetToken}
      resetPassword={resetCustomerPassword}
      loginPath="/portal/login"
      forgotPath="/portal/forgot-password"
      onSuccess={logout}
    />
  );
}

export default CustomerResetPassword;
