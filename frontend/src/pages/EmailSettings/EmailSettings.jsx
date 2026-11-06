import { useSearchParams } from 'react-router-dom';
import { Mail, ShieldCheck, SlidersHorizontal, Users } from 'lucide-react';
import PageHeader from '../../components/PageHeader';
import RecipientsTab from './RecipientsTab';
import SendersTab from './SendersTab';
import SmtpTab from './SmtpTab';
import WorkflowsTab from './WorkflowsTab';

const TABS = [
  {
    key: 'transport',
    label: 'Transport',
    icon: ShieldCheck,
    hint: 'SMTP profile, tests and the environment fallback',
  },
  {
    key: 'senders',
    label: 'Senders',
    icon: Mail,
    hint: 'From names, addresses and Reply-To',
  },
  {
    key: 'workflows',
    label: 'Workflows',
    icon: SlidersHorizontal,
    hint: 'Which sender each email uses, and what may be disabled',
  },
  {
    key: 'recipients',
    label: 'Internal recipients',
    icon: Users,
    hint: 'Who receives internal copies of security alerts and new orders',
  },
];

const TAB_KEYS = TABS.map((tab) => tab.key);

export default function EmailSettings() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get('tab');
  const active = TAB_KEYS.includes(requested) ? requested : 'transport';

  const selectTab = (key) => {
    setSearchParams(key === 'transport' ? {} : { tab: key }, { replace: true });
  };

  return (
    <div>
      <PageHeader
        title="Email & Notifications"
        subtitle="Send dairy email through the database SMTP profile, control every From address, and choose who gets internal copies."
        badge="Admin Only"
      />

      <div
        role="tablist"
        aria-label="Email settings sections"
        className="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-4"
      >
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = tab.key === active;
          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => selectTab(tab.key)}
              className={`flex items-start gap-2.5 rounded-xl border px-3 py-2.5 text-left transition ${
                isActive
                  ? 'border-amber-300 bg-amber-50 text-amber-900 shadow-sm'
                  : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50'
              }`}
            >
              <Icon
                className={`mt-0.5 h-4 w-4 shrink-0 ${
                  isActive ? 'text-amber-600' : 'text-slate-400'
                }`}
              />
              <span className="min-w-0">
                <span className="block text-xs font-bold">{tab.label}</span>
                <span className="mt-0.5 block text-[10px] leading-snug text-slate-500">
                  {tab.hint}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      {active === 'transport' && <SmtpTab />}
      {active === 'senders' && <SendersTab />}
      {active === 'workflows' && <WorkflowsTab />}
      {active === 'recipients' && <RecipientsTab />}
    </div>
  );
}
