import { PasswordResetConfirm } from '../../components/PasswordResetForms';
import { resetPasswordApi, validateResetTokenApi } from '../../api/auth';

export function ResetPassword() {
  return (
    <PasswordResetConfirm
      audience="Staff"
      validateToken={validateResetTokenApi}
      resetPassword={resetPasswordApi}
      loginPath="/login"
      forgotPath="/forgot-password"
    />
  );
}

export default ResetPassword;
