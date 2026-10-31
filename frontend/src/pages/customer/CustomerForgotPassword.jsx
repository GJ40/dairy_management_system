import { PasswordResetRequest } from '../../components/PasswordResetForms';
import { forgotCustomerPassword } from '../../api/customerAuth';

export function CustomerForgotPassword() {
  return (
    <PasswordResetRequest
      audience="Customer portal"
      onSubmit={forgotCustomerPassword}
      loginPath="/portal/login"
    />
  );
}

export default CustomerForgotPassword;
