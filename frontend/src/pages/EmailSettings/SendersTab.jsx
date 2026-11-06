import { useEffect, useState } from 'react';
import { toast } from 'react-toastify';
import {
  Ban,
  CheckCircle2,
  Mail,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import {
  activateSenderIdentity,
  createSenderIdentity,
  deactivateSenderIdentity,
  deleteSenderIdentity,
  getSenderIdentities,
  updateSenderIdentity,
} from '../../api/emailSettings';
import ConfirmModal from '../../components/ConfirmModal';
import EmptyState from '../../components/EmptyState';
import ErrorAlert from '../../components/ErrorAlert';
import LoadingSpinner from '../../components/LoadingSpinner';
import {
  Badge,
  Field,
  GhostButton,
  Modal,
  SectionCard,
  SubmitButton,
  TextArea,
  TextInput,
} from './EmailSettingsParts';

const EMPTY_FORM = {
  display_name: '',
  email: '',
  reply_to_email: '',
  description: '',
};

function senderForm(sender) {
  if (!sender) return { ...EMPTY_FORM };
  return {
    display_name: sender.display_name || '',
    email: sender.email || '',
    reply_to_email: sender.reply_to_email || '',
    description: sender.description || '',
  };
}

function validateForm(form) {
  if (!form.display_name.trim()) return 'Enter a display name.';
  const email = form.email.trim();
  if (!email) return 'Enter the From address.';
  if (!email.includes('@')) return 'Enter a valid email address.';
  if (form.reply_to_email.trim()) {
    const replyTo = form.reply_to_email.trim().toLowerCase();
    if (!replyTo.includes('@')) return 'Enter a valid Reply-To address.';
    if (replyTo === email.toLowerCase()) {
      return 'The Reply-To address must differ from the From address.';
    }
  }
  return null;
}

function buildPayload(form) {
  return {
    display_name: form.display_name.trim(),
    email: form.email.trim(),
    reply_to_email: form.reply_to_email.trim() || null,
    description: form.description.trim() || null,
  };
}

export default function SendersTab() {
  const [senders, setSenders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [modal, setModal] = useState(null);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [saving, setSaving] = useState(false);

  const [busyId, setBusyId] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const response = await getSenderIdentities();
        if (cancelled) return;
        setSenders(Array.isArray(response?.items) ? response.items : []);
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err?.message || 'Failed to load the sender identities.');
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

  const refresh = ({ quiet = false } = {}) => {
    if (!quiet) setLoading(true);
    setError(null);
    setReloadKey((current) => current + 1);
  };

  const openCreate = () => {
    setForm({ ...EMPTY_FORM });
    setModal({ mode: 'create', sender: null });
  };

  const openEdit = (sender) => {
    setForm(senderForm(sender));
    setModal({ mode: 'edit', sender });
  };

  const closeModal = () => {
    if (saving) return;
    setModal(null);
  };

  const updateField = (key) => (event) =>
    setForm((current) => ({ ...current, [key]: event.target.value }));

  const submit = async (event) => {
    event.preventDefault();
    const validation = validateForm(form);
    if (validation) {
      toast.error(validation);
      return;
    }
    setSaving(true);
    try {
      const payload = buildPayload(form);
      if (modal?.mode === 'edit') {
        await updateSenderIdentity(modal.sender.id, payload);
        toast.success('Sender identity updated.');
      } else {
        await createSenderIdentity(payload);
        toast.success('Sender identity created.');
      }
      setModal(null);
      refresh({ quiet: true });
    } catch (err) {
      toast.error(err?.message || 'Could not save this sender identity.');
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (sender) => {
    setBusyId(sender.id);
    try {
      if (sender.is_active) {
        await deactivateSenderIdentity(sender.id);
        toast.success('Sender deactivated. Existing mappings keep pointing at it.');
      } else {
        await activateSenderIdentity(sender.id);
        toast.success('Sender activated.');
      }
      refresh({ quiet: true });
    } catch (err) {
      toast.error(err?.message || 'Could not update this sender identity.');
    } finally {
      setBusyId(null);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteSenderIdentity(deleteTarget.id);
      toast.success('Sender identity removed.');
      setDeleteTarget(null);
      refresh({ quiet: true });
    } catch (err) {
      toast.error(err?.message || 'Could not remove this sender identity.');
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return <LoadingSpinner message="Loading sender identities…" />;
  }

  if (error) {
    return <ErrorAlert message={error} onRetry={() => refresh()} />;
  }

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-slate-500">
          A sender identity is the From name and address a workflow email is sent
          as. Workflows fall back to the application default when they have no
          override.
        </p>
        <GhostButton icon={RefreshCw} onClick={() => refresh()}>
          Refresh
        </GhostButton>
      </div>

      <SectionCard
        icon={Mail}
        title="Sender identities"
        description="Reply-To is optional and must differ from the From address. Used identities cannot be deleted while a workflow still references them."
        actions={
          <GhostButton icon={Plus} onClick={openCreate}>
            Add sender
          </GhostButton>
        }
      >
        {senders.length === 0 ? (
          <EmptyState
            icon={Mail}
            title="No sender identities yet"
            description="Add at least one so workflow emails have a From address and, optionally, a Reply-To."
            action={
              <GhostButton icon={Plus} onClick={openCreate}>
                Add sender
              </GhostButton>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  {['From', 'Reply-To', 'Description', 'Used by', 'Status', ''].map(
                    (heading) => (
                      <th
                        key={heading || 'actions'}
                        className={`px-3 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500 ${
                          heading === '' ? 'text-right' : ''
                        }`}
                      >
                        {heading || 'Actions'}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {senders.map((sender) => (
                  <tr key={sender.id} className="align-top hover:bg-slate-50">
                    <td className="px-3 py-3">
                      <p className="font-semibold text-slate-800">
                        {sender.display_name}
                      </p>
                      <p className="font-mono text-[11px] text-slate-500">
                        {sender.email}
                      </p>
                    </td>
                    <td className="px-3 py-3 font-mono text-[11px] text-slate-600">
                      {sender.reply_to_email || '—'}
                    </td>
                    <td className="max-w-[16rem] px-3 py-3 text-xs text-slate-600">
                      {sender.description || '—'}
                    </td>
                    <td className="px-3 py-3 text-xs text-slate-600">
                      {sender.usage_count}
                    </td>
                    <td className="px-3 py-3">
                      {sender.is_active ? (
                        <Badge tone="emerald">Active</Badge>
                      ) : (
                        <Badge tone="slate">Inactive</Badge>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex flex-wrap items-center justify-end gap-2">
                        <GhostButton
                          icon={Pencil}
                          onClick={() => openEdit(sender)}
                        >
                          Edit
                        </GhostButton>
                        <GhostButton
                          icon={sender.is_active ? Ban : CheckCircle2}
                          onClick={() => toggleActive(sender)}
                          disabled={busyId === sender.id}
                        >
                          {sender.is_active ? 'Deactivate' : 'Activate'}
                        </GhostButton>
                        <button
                          type="button"
                          onClick={() => setDeleteTarget(sender)}
                          disabled={sender.usage_count > 0}
                          title={
                            sender.usage_count > 0
                              ? 'This sender is referenced by a workflow mapping; deactivate it instead.'
                              : 'Delete this sender identity'
                          }
                          className="inline-flex items-center gap-2 rounded-lg border border-rose-200 bg-white px-3 py-2 text-sm font-medium text-rose-600 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <Trash2 className="h-4 w-4" />
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      <Modal
        open={Boolean(modal)}
        icon={Mail}
        title={
          modal?.mode === 'edit' ? 'Edit sender identity' : 'Add sender identity'
        }
        description="Only the address matters for delivery; the display name is what recipients see."
        onClose={closeModal}
        footer={
          <>
            <GhostButton onClick={closeModal} disabled={saving}>
              Cancel
            </GhostButton>
            <SubmitButton loading={saving} form="sender-identity-form">
              {modal?.mode === 'edit' ? 'Save changes' : 'Add sender'}
            </SubmitButton>
          </>
        }
      >
        <form id="sender-identity-form" onSubmit={submit} className="space-y-4">
          <Field label="Display name" htmlFor="sender-name">
            <TextInput
              id="sender-name"
              value={form.display_name}
              onChange={updateField('display_name')}
              maxLength={100}
              placeholder="DairyFlow Orders"
            />
          </Field>
          <Field label="From address" htmlFor="sender-email">
            <TextInput
              id="sender-email"
              type="email"
              value={form.email}
              onChange={updateField('email')}
              maxLength={150}
              placeholder="orders@dairy.example"
            />
          </Field>
          <Field
            label="Reply-To (optional)"
            htmlFor="sender-reply-to"
            hint="Leave blank to send without a Reply-To header."
          >
            <TextInput
              id="sender-reply-to"
              type="email"
              value={form.reply_to_email}
              onChange={updateField('reply_to_email')}
              maxLength={150}
              placeholder="support@dairy.example"
            />
          </Field>
          <Field
            label="Description (optional)"
            htmlFor="sender-description"
            hint="For your team only; never sent to recipients."
          >
            <TextArea
              id="sender-description"
              rows={3}
              value={form.description}
              onChange={updateField('description')}
              maxLength={255}
            />
          </Field>
        </form>
      </Modal>

      <ConfirmModal
        isOpen={Boolean(deleteTarget)}
        title={`Delete “${deleteTarget?.display_name || ''}”?`}
        message="The sender identity is removed permanently. Workflow mappings must point elsewhere first; deactivating keeps the mappings intact."
        confirmText="Delete sender"
        confirmVariant="danger"
        isLoading={deleting}
        onConfirm={confirmDelete}
        onClose={() => {
          if (!deleting) setDeleteTarget(null);
        }}
      />
    </div>
  );
}
