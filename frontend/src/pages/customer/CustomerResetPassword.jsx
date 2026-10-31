import { PasswordResetConfirm } from '../../components/PasswordResetForms';
import {
  resetCustomerPassword,
  validateCustomerResetToken,
} from '../../api/customerAuth';

export function CustomerResetPassword() {
  return (
    <PasswordResetConfirm
      audience="Customer portal"
      validateToken={validateCustomerResetToken}
      resetPassword={resetCustomerPassword}
      loginPath="/portal/login"
      forgotPath="/portal/forgot-password"
    />
  );
}

export default CustomerResetPassword;
