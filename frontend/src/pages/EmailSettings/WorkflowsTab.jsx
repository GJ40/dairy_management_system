import { useEffect, useState } from 'react';
import { toast } from 'react-toastify';
import { AlertTriangle, RefreshCw, Save, SlidersHorizontal } from 'lucide-react';
import {
  getWorkflowCatalogue,
  getWorkflowMappings,
  replaceWorkflowMappings,
} from '../../api/emailSettings';
import EmptyState from '../../components/EmptyState';
import ErrorAlert from '../../components/ErrorAlert';
import LoadingSpinner from '../../components/LoadingSpinner';
import {
  Badge,
  Field,
  GhostButton,
  SectionCard,
  SelectInput,
  Toggle,
} from './EmailSettingsParts';

const EMPTY_ROW = { sender: '', reply: '', enabled: true };

function rowFromMapping(row) {
  return {
    sender: row?.sender_identity_id ?? '',
    reply: row?.reply_to_sender_identity_id ?? '',
    enabled: row?.is_enabled !== false,
  };
}

function buildDraft(mappings) {
  const categories = {};
  (mappings?.categories || []).forEach((row) => {
    categories[row.category_key] = rowFromMapping(row);
  });
  const events = {};
  (mappings?.events || []).forEach((row) => {
    events[row.event_key] = rowFromMapping(row);
  });
  return {
    application: rowFromMapping(mappings?.application),
    categories,
    events,
  };
}

function toRefs(row) {
  return {
    sender_identity_id: row?.sender ? Number(row.sender) : null,
    reply_to_sender_identity_id: row?.reply ? Number(row.reply) : null,
  };
}

// The endpoint replaces the whole mapping set, so the body always enumerates
// every catalogue category and event. An all-null row means "no override".
function buildBody(draft, catalogue) {
  const categories = catalogue?.categories || [];
  return {
    application: toRefs(draft.application),
    categories: categories.map((category) => ({
      category_key: category.key,
      ...toRefs(draft.categories[category.key]),
    })),
    events: categories.flatMap((category) =>
      (category.events || []).map((event) => ({
        event_key: event.key,
        ...toRefs(draft.events[event.key]),
        is_enabled: event.allow_disable
          ? draft.events[event.key]?.enabled !== false
          : true,
      }))
    ),
  };
}

function SenderSelect({ id, value, onChange, senders, emptyLabel }) {
  return (
    <SelectInput id={id} value={value} onChange={onChange} className="text-xs">
      <option value="">{emptyLabel}</option>
      {senders.map((sender) => (
        <option key={sender.id} value={sender.id}>
          {sender.display_name} · {sender.email}
          {sender.is_active ? '' : ' (inactive)'}
        </option>
      ))}
    </SelectInput>
  );
}

export default function WorkflowsTab() {
  const [catalogue, setCatalogue] = useState(null);
  const [mappings, setMappings] = useState(null);
  const [draft, setDraft] = useState(null);
  const [saved, setSaved] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [catalogueResponse, mappingsResponse] = await Promise.all([
          getWorkflowCatalogue(),
          getWorkflowMappings(),
        ]);
        if (cancelled) return;
        const nextDraft = buildDraft(mappingsResponse);
        setCatalogue(catalogueResponse || { categories: [] });
        setMappings(mappingsResponse || null);
        setDraft(nextDraft);
        setSaved(nextDraft);
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err?.message || 'Failed to load the workflow mappings.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const refresh = () => {
    setLoading(true);
    setError(null);
    setReloadKey((current) => current + 1);
  };

  const setApplication = (field) => (event) =>
    setDraft((current) => ({
      ...current,
      application: { ...current.application, [field]: event.target.value },
    }));

  const setCategory = (key, field) => (event) =>
    setDraft((current) => ({
      ...current,
      categories: {
        ...current.categories,
        [key]: {
          ...(current.categories[key] || EMPTY_ROW),
          [field]: event.target.value,
        },
      },
    }));

  const setEvent = (key, field) => (valueOrEvent) =>
    setDraft((current) => {
      const value =
        field === 'enabled' ? valueOrEvent : valueOrEvent.target.value;
      return {
        ...current,
        events: {
          ...current.events,
          [key]: { ...(current.events[key] || EMPTY_ROW), [field]: value },
        },
      };
    });

  const save = async () => {
    const rows = [
      ['Application default', draft.application],
      ...Object.entries(draft.categories).map(([key, row]) => [key, row]),
      ...Object.entries(draft.events).map(([key, row]) => [key, row]),
    ];
    const clash = rows.find(
      ([, row]) => row.sender && row.sender === row.reply
    );
    if (clash) {
      toast.error(`Sender and Reply-To must differ (${clash[0]}).`);
      return;
    }

    setSaving(true);
    try {
      const response = await replaceWorkflowMappings(
        buildBody(draft, catalogue)
      );
      const nextDraft = buildDraft(response);
      setMappings(response || null);
      setDraft(nextDraft);
      setSaved(nextDraft);
      toast.success('Workflow mappings saved.');
    } catch (err) {
      toast.error(err?.message || 'Could not save the workflow mappings.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <LoadingSpinner message="Loading the workflow catalogue…" />;
  }

  if (error) {
    return <ErrorAlert message={error} onRetry={refresh} />;
  }

  const categories = catalogue?.categories || [];
  const senders = mappings?.senders || [];
  const dirty =
    Boolean(draft) &&
    JSON.stringify(buildBody(draft, catalogue)) !==
      JSON.stringify(buildBody(saved, catalogue));

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-xs leading-relaxed text-slate-500">
          Every email takes its From and Reply-To from the most specific mapping:
          event first, then its category, then the application default, then the
          environment variables. A workflow with nothing selected sends as the
          environment sender.
        </p>
        <div className="flex items-center gap-2">
          <GhostButton icon={RefreshCw} onClick={refresh}>
            Discard &amp; reload
          </GhostButton>
          <button
            type="button"
            onClick={save}
            disabled={saving || !dirty}
            className="inline-flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-amber-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            {saving ? 'Saving…' : 'Save mappings'}
          </button>
        </div>
      </div>

      {dirty && (
        <div className="mb-5 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-[11px] text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          Unsaved changes. Saving replaces the whole mapping set in one call.
        </div>
      )}

      {senders.length === 0 && (
        <div className="mb-5 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-[11px] text-slate-600">
          No sender identities exist yet. Add one on the Senders tab to choose a
          From address here; until then every workflow sends as the environment
          sender.
        </div>
      )}

      <SectionCard
        icon={SlidersHorizontal}
        title="Application default"
        description="Used by every workflow that has no category or event override."
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="From sender" htmlFor="mapping-application-sender">
            <SenderSelect
              id="mapping-application-sender"
              value={draft.application.sender}
              onChange={setApplication('sender')}
              senders={senders}
              emptyLabel="Environment sender"
            />
          </Field>
          <Field label="Reply-To sender" htmlFor="mapping-application-reply">
            <SenderSelect
              id="mapping-application-reply"
              value={draft.application.reply}
              onChange={setApplication('reply')}
              senders={senders}
              emptyLabel="No Reply-To override"
            />
          </Field>
        </div>
      </SectionCard>

      {categories.length === 0 ? (
        <EmptyState
          icon={SlidersHorizontal}
          title="The workflow catalogue is empty"
          description="The server returned no workflows to configure."
        />
      ) : (
        categories.map((category) => {
          const categoryRow = draft.categories[category.key] || EMPTY_ROW;
          return (
            <SectionCard
              key={category.key}
              icon={SlidersHorizontal}
              title={category.label}
              description={`${category.key} · applies to every workflow in this category without its own override.`}
            >
              <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Field
                  label="Category From"
                  htmlFor={`mapping-category-${category.key}-sender`}
                >
                  <SenderSelect
                    id={`mapping-category-${category.key}-sender`}
                    value={categoryRow.sender}
                    onChange={setCategory(category.key, 'sender')}
                    senders={senders}
                    emptyLabel="Inherit application default"
                  />
                </Field>
                <Field
                  label="Category Reply-To"
                  htmlFor={`mapping-category-${category.key}-reply`}
                >
                  <SenderSelect
                    id={`mapping-category-${category.key}-reply`}
                    value={categoryRow.reply}
                    onChange={setCategory(category.key, 'reply')}
                    senders={senders}
                    emptyLabel="Inherit application default"
                  />
                </Field>
              </div>

              <div className="space-y-2">
                {(category.events || []).map((event) => {
                  const row = draft.events[event.key] || EMPTY_ROW;
                  return (
                    <div
                      key={event.key}
                      className="rounded-xl border border-slate-200 p-3"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="text-sm font-semibold text-slate-800">
                              {event.name}
                            </p>
                            <Badge
                              tone={
                                event.audience === 'staff' ? 'amber' : 'sky'
                              }
                            >
                              {event.audience}
                            </Badge>
                            {!event.implemented && (
                              <Badge tone="slate">Not sending yet</Badge>
                            )}
                            {!event.allow_disable && (
                              <Badge tone="rose">Required</Badge>
                            )}
                          </div>
                          <p className="mt-0.5 text-[11px] leading-relaxed text-slate-500">
                            {event.description}
                          </p>
                          <p className="mt-0.5 font-mono text-[10px] text-slate-400">
                            {event.key}
                          </p>
                        </div>

                        <div className="flex items-center gap-2">
                          <span className="text-[11px] font-semibold text-slate-500">
                            {row.enabled ? 'Enabled' : 'Disabled'}
                          </span>
                          <Toggle
                            checked={row.enabled}
                            disabled={!event.allow_disable}
                            label={`${event.name} enabled`}
                            onChange={setEvent(event.key, 'enabled')}
                          />
                        </div>
                      </div>

                      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                        <Field
                          label="From"
                          htmlFor={`mapping-event-${event.key}-sender`}
                        >
                          <SenderSelect
                            id={`mapping-event-${event.key}-sender`}
                            value={row.sender}
                            onChange={setEvent(event.key, 'sender')}
                            senders={senders}
                            emptyLabel="Inherit category default"
                          />
                        </Field>
                        <Field
                          label="Reply-To"
                          htmlFor={`mapping-event-${event.key}-reply`}
                        >
                          <SenderSelect
                            id={`mapping-event-${event.key}-reply`}
                            value={row.reply}
                            onChange={setEvent(event.key, 'reply')}
                            senders={senders}
                            emptyLabel="Inherit category default"
                          />
                        </Field>
                      </div>

                      {!row.enabled && (
                        <p className="mt-2 text-[11px] text-amber-800">
                          {event.audience === 'staff'
                            ? 'Disabled: internal recipients receive nothing for this workflow.'
                            : 'Disabled: this email is skipped for customers and no internal copy is sent.'}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </SectionCard>
          );
        })
      )}

      <div className="flex justify-end">
        <button
          type="button"
          onClick={save}
          disabled={saving || !dirty}
          className="inline-flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-amber-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Save className="h-4 w-4" />
          {saving ? 'Saving…' : 'Save mappings'}
        </button>
      </div>

    </div>
  );
}
