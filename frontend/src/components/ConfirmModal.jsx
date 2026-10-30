import { useEffect } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';

export function ConfirmModal({
  isOpen,
  title = 'Are you sure?',
  message = 'This action cannot be undone.',
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  confirmVariant = 'danger',
  isLoading = false,
  onConfirm,
  onClose,
}) {
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen && !isLoading) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isLoading, onClose]);

  if (!isOpen) return null;

  const confirmBtnClasses =
    confirmVariant === 'danger'
      ? 'bg-rose-600 hover:bg-rose-700 text-white focus:ring-rose-500'
      : 'bg-emerald-600 hover:bg-emerald-700 text-white focus:ring-emerald-500';

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-screen items-center justify-center p-4 text-center sm:p-0">
        {/* Backdrop */}
        <div
          className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs transition-opacity"
          onClick={isLoading ? undefined : onClose}
          aria-hidden="true"
        />

        {/* Modal Dialog */}
        <div className="relative transform overflow-hidden rounded-xl bg-white text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-md border border-slate-200 p-6 z-10">
          <div className="flex items-start gap-4">
            <div
              className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${
                confirmVariant === 'danger'
                  ? 'bg-rose-100 text-rose-600'
                  : 'bg-emerald-100 text-emerald-600'
              }`}
            >
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
              <div className="mt-2 text-sm text-slate-600 leading-normal">{message}</div>
            </div>
          </div>

          <div className="mt-6 flex flex-col-reverse sm:flex-row sm:justify-end gap-3">
            <button
              type="button"
              disabled={isLoading}
              onClick={onClose}
              className="w-full sm:w-auto px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 focus:outline-hidden focus:ring-2 focus:ring-slate-400 disabled:opacity-50 transition cursor-pointer"
            >
              {cancelText}
            </button>
            <button
              type="button"
              disabled={isLoading}
              onClick={onConfirm}
              className={`w-full sm:w-auto inline-flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium rounded-lg focus:outline-hidden focus:ring-2 focus:ring-offset-2 disabled:opacity-50 transition cursor-pointer ${confirmBtnClasses}`}
            >
              {isLoading && <Loader2 className="w-4 h-4 animate-spin" />}
              {confirmText}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ConfirmModal;
