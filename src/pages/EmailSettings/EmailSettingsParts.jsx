import { Loader2, X } from 'lucide-react';

const INPUT_CLASS =
  'h-10 w-full px-3 text-sm text-slate-800 border border-slate-200 rounded-lg bg-white transition placeholder:text-slate-400 hover:border-slate-300 focus:outline-none focus:border-amber-400 focus:ring-2 focus:ring-amber-400 disabled:bg-slate-50 disabled:text-slate-500';

const TEXTAREA_CLASS =
  'w-full px-3 py-2 text-sm text-slate-800 border border-slate-200 rounded-lg bg-white transition placeholder:text-slate-400 hover:border-slate-300 focus:outline-none focus:border-amber-400 focus:ring-2 focus:ring-amber-400';

const TONE_CLASSES = {
  emerald: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  amber: 'bg-amber-50 text-amber-800 border-amber-200',
  rose: 'bg-rose-50 text-rose-700 border-rose-200',
  sky: 'bg-sky-50 text-sky-700 border-sky-200',
  slate: 'bg-slate-100 text-slate-600 border-slate-200',
};

export function Badge({ tone = 'slate', children }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${
        TONE_CLASSES[tone] || TONE_CLASSES.slate
      }`}
    >
      {children}
    </span>
  );
}

export function SectionCard({
  icon: Icon,
  title,
  description,
  actions,
  children,
}) {
  return (
    <section className="mb-5 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-4 py-3 sm:px-5">
        <div className="flex items-start gap-2.5">
          {Icon && (
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-50 text-amber-600">
              <Icon className="h-4 w-4" />
            </span>
          )}
          <div>
            <h2 className="text-sm font-bold text-slate-800">{title}</h2>
            {description && (
              <p className="mt-0.5 max-w-xl text-[11px] leading-relaxed text-slate-500">
                {description}
              </p>
            )}
          </div>
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
      <div className="p-4 sm:p-5">{children}</div>
    </section>
  );
}

export function Field({ label, hint, htmlFor, className = '', children }) {
  return (
    <div className={className}>
      <label
        htmlFor={htmlFor}
        className="mb-1.5 block text-[11px] font-bold uppercase tracking-wider text-slate-500"
      >
        {label}
      </label>
      {children}
      {hint && (
        <p className="mt-1 text-[11px] leading-relaxed text-slate-500">{hint}</p>
      )}
    </div>
  );
}

export function TextInput({ className = '', ...props }) {
  return <input {...props} className={`${INPUT_CLASS} ${className}`} />;
}

export function SelectInput({ className = '', children, ...props }) {
  return (
    <select {...props} className={`${INPUT_CLASS} ${className}`}>
      {children}
    </select>
  );
}

export function TextArea({ className = '', ...props }) {
  return <textarea {...props} className={`${TEXTAREA_CLASS} ${className}`} />;
}

export function Toggle({ checked, onChange, disabled = false, label }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 focus-visible:ring-offset-2 ${
        checked ? 'bg-emerald-500' : 'bg-slate-300'
      } ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition ${
          checked ? 'translate-x-4' : 'translate-x-0.5'
        }`}
      />
    </button>
  );
}

export function GhostButton({ icon: Icon, children, className = '', ...props }) {
  return (
    <button
      {...props}
      type={props.type || 'button'}
      className={`inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
    >
      {Icon && <Icon className="h-4 w-4" />}
      {children}
    </button>
  );
}

export function Modal({
  open,
  title,
  description,
  icon: Icon,
  wide = false,
  onClose,
  children,
  footer,
}) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/60 p-4 backdrop-blur-xs sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div
        className={`my-4 w-full ${
          wide ? 'max-w-2xl' : 'max-w-lg'
        } rounded-2xl bg-white shadow-2xl`}
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 p-5">
          <div className="flex items-start gap-3">
            {Icon && (
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-100 text-amber-700">
                <Icon className="h-5 w-5" />
              </span>
            )}
            <div>
              <h2 className="font-bold text-slate-900">{title}</h2>
              {description && (
                <p className="mt-0.5 text-xs text-slate-500">{description}</p>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-100"
            aria-label="Close dialog"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="p-5">{children}</div>
        {footer && (
          <div className="flex flex-col-reverse gap-3 border-t border-slate-100 p-4 sm:flex-row sm:justify-end">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

export function SubmitButton({ loading, children, ...props }) {
  return (
    <button
      {...props}
      type={props.type || 'submit'}
      disabled={loading || props.disabled}
      className="inline-flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-amber-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
}
