export function EmptyState({
  icon: Icon,
  title = 'No records found',
  description = 'There is currently no data to display for this view.',
  action,
}) {
  return (
    <div className="flex flex-col items-center justify-center p-8 sm:p-12 text-center bg-white rounded-xl border border-dashed border-slate-300">
      {Icon && (
        <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mb-4">
          <Icon className="w-6 h-6" />
        </div>
      )}
      <h3 className="text-base font-semibold text-slate-800 mb-1">{title}</h3>
      <p className="text-sm text-slate-500 max-w-sm mb-6">{description}</p>
      {action && <div>{action}</div>}
    </div>
  );
}

export default EmptyState;
