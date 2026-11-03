import { PasswordResetConfirm } from '../../components/PasswordResetForms';
import { resetPasswordApi, validateResetTokenApi } from '../../api/auth';
import { useAuth } from '../../hooks/useAuth';

export function ResetPassword() {
  const { logout } = useAuth();

  return (
    <PasswordResetConfirm
      audience="Staff"
      validateToken={validateResetTokenApi}
      resetPassword={resetPasswordApi}
      loginPath="/login"
      forgotPath="/forgot-password"
      onSuccess={logout}
    />
  );
}

export default ResetPassword;
