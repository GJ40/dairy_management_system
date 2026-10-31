import { PasswordResetRequest } from '../../components/PasswordResetForms';
import { forgotPasswordApi } from '../../api/auth';

export function ForgotPassword() {
  return (
    <PasswordResetRequest
      audience="Staff"
      onSubmit={forgotPasswordApi}
      loginPath="/login"
    />
  );
}

export default ForgotPassword;
