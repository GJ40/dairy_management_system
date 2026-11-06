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
  activateNotificationRecipient,
  createNotificationRecipient,
  deactivateNotificationRecipient,
  deleteNotificationRecipient,
  getNotificationRecipients,
  getWorkflowCatalogue,
  updateNotificationRecipient,
} from '../../api/emailSettings';
import ConfirmModal from '../../components/ConfirmModal';
import EmptyState from '../../components/EmptyState';
import ErrorAlert from '../../components/ErrorAlert';
import LoadingSpinner from '../../components/LoadingSpinner';
import { formatDateTime } from '../../utils/formatters';
import {
  Badge,
  Field,
  GhostButton,
  Modal,
  SectionCard,
  SelectInput,
  SubmitButton,
  TextInput,
} from './EmailSettingsParts';

const EMPTY_ADD_FORM = { scope: 'event', mapping_key: '', email: '' };
const EMPTY_EDIT_FORM = { email: '' };

function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

export default function RecipientsTab() {
  const [recipients, setRecipients] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [addOpen, setAddOpen] = useState(false);
  const [addForm, setAddForm] = useState({ ...EMPTY_ADD_FORM });
  const [adding, setAdding] = useState(false);

  const [editTarget, setEditTarget] = useState(null);
  const [editForm, setEditForm] = useState({ ...EMPTY_EDIT_FORM });
  const [saving, setSaving] = useState(false);

  const [busyId, setBusyId] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [recipientsResponse, catalogueResponse] = await Promise.all([
          getNotificationRecipients(),
          getWorkflowCatalogue(),
        ]);
        if (cancelled) return;
        setRecipients(
          Array.isArray(recipientsResponse?.items) ? recipientsResponse.items : []
        );
        setCategories(
          Array.isArray(catalogueResponse?.categories)
            ? catalogueResponse.categories
            : []
        );
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err?.message || 'Failed to load the internal recipients.');
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

  const eventOptions = categories.flatMap((category) =>
    (category.events || []).map((event) => ({
      value: event.key,
      label: `${category.label} · ${event.name}`,
    }))
  );
  const categoryOptions = categories.map((category) => ({
    value: category.key,
    label: category.label,
  }));
  const targetOptions =
    addForm.scope === 'event' ? eventOptions : categoryOptions;

  const openAdd = () => {
    setAddForm({ ...EMPTY_ADD_FORM });
    setAddOpen(true);
  };

  const closeAdd = () => {
    if (adding) return;
    setAddOpen(false);
  };

  const submitAdd = async (event) => {
    event.preventDefault();
    const email = addForm.email.trim().toLowerCase();
    if (!addForm.mapping_key) {
      toast.error('Choose the workflow that should notify this address.');
      return;
    }
    if (!isValidEmail(email)) {
      toast.error('Enter a valid email address.');
      return;
    }
    setAdding(true);
    try {
      await createNotificationRecipient({
        scope: addForm.scope,
        mapping_key: addForm.mapping_key,
        email,
      });
      toast.success('Recipient added.');
      setAddOpen(false);
      refresh({ quiet: true });
    } catch (err) {
      toast.error(err?.message || 'Could not add this recipient.');
    } finally {
      setAdding(false);
    }
  };

  const openEdit = (recipient) => {
    setEditForm({ email: recipient.email });
    setEditTarget(recipient);
  };

  const closeEdit = () => {
    if (saving) return;
    setEditTarget(null);
  };

  const submitEdit = async (event) => {
    event.preventDefault();
    const email = editForm.email.trim().toLowerCase();
    if (!isValidEmail(email)) {
      toast.error('Enter a valid email address.');
      return;
    }
    setSaving(true);
    try {
      await updateNotificationRecipient(editTarget.id, { email });
      toast.success('Recipient updated.');
      setEditTarget(null);
      refresh({ quiet: true });
    } catch (err) {
      toast.error(err?.message || 'Could not update this recipient.');
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (recipient) => {
    setBusyId(recipient.id);
    try {
      if (recipient.is_active) {
        await deactivateNotificationRecipient(recipient.id);
        toast.success('Recipient deactivated. They will not be notified.');
      } else {
        await activateNotificationRecipient(recipient.id);
        toast.success('Recipient activated.');
      }
      refresh({ quiet: true });
    } catch (err) {
      toast.error(err?.message || 'Could not update this recipient.');
    } finally {
      setBusyId(null);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteNotificationRecipient(deleteTarget.id);
      toast.success('Recipient removed.');
      setDeleteTarget(null);
      refresh({ quiet: true });
    } catch (err) {
      toast.error(err?.message || 'Could not remove this recipient.');
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return <LoadingSpinner message="Loading internal recipients…" />;
  }

  if (error) {
    return <ErrorAlert message={error} onRetry={() => refresh()} />;
  }

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-xs leading-relaxed text-slate-500">
          Internal copies go out for failed-login alerts, account lockouts and
          new customer orders — the affected person still receives their own
          email. Each recipient gets a separate message, so nobody learns who
          else is on the list.
        </p>
        <div className="flex items-center gap-2">
          <GhostButton icon={RefreshCw} onClick={() => refresh()}>
            Refresh
          </GhostButton>
          <GhostButton icon={Plus} onClick={openAdd}>
            Add recipient
          </GhostButton>
        </div>
      </div>

      <SectionCard
        icon={Mail}
        title="Internal recipients"
        description="A category recipient covers every event in that category. A person listed at both levels still receives one message."
      >
        {recipients.length === 0 ? (
          <EmptyState
            icon={Mail}
            title="No internal recipients yet"
            description="Until an address is added, internal copies are not sent at all — the affected person's own email is unaffected."
            action={
              <GhostButton icon={Plus} onClick={openAdd}>
                Add recipient
              </GhostButton>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  {['Workflow', 'Email', 'Status', 'Added', 'Actions'].map(
                    (heading, index) => (
                      <th
                        key={heading}
                        className={`px-3 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500 ${
                          index === 4 ? 'text-right' : ''
                        }`}
                      >
                        {heading}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {recipients.map((recipient) => (
                  <tr key={recipient.id} className="align-top hover:bg-slate-50">
                    <td className="px-3 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs font-semibold text-slate-800">
                          {recipient.label}
                        </span>
                        <Badge
                          tone={recipient.scope === 'event' ? 'sky' : 'amber'}
                        >
                          {recipient.scope}
                        </Badge>
                      </div>
                      <p className="mt-0.5 font-mono text-[10px] text-slate-400">
                        {recipient.mapping_key}
                      </p>
                    </td>
                    <td className="px-3 py-3 font-mono text-xs text-slate-700">
                      {recipient.email}
                    </td>
                    <td className="px-3 py-3">
                      {recipient.is_active ? (
                        <Badge tone="emerald">Active</Badge>
                      ) : (
                        <Badge tone="slate">Inactive</Badge>
                      )}
                    </td>
                    <td className="px-3 py-3 text-[11px] text-slate-500">
                      {formatDateTime(recipient.created_at)}
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex flex-wrap items-center justify-end gap-2">
                        <GhostButton
                          icon={Pencil}
                          onClick={() => openEdit(recipient)}
                        >
                          Edit
                        </GhostButton>
                        <GhostButton
                          icon={recipient.is_active ? Ban : CheckCircle2}
                          onClick={() => toggleActive(recipient)}
                          disabled={busyId === recipient.id}
                        >
                          {recipient.is_active ? 'Deactivate' : 'Activate'}
                        </GhostButton>
                        <button
                          type="button"
                          onClick={() => setDeleteTarget(recipient)}
                          className="inline-flex items-center gap-2 rounded-lg border border-rose-200 bg-white px-3 py-2 text-sm font-medium text-rose-600 transition hover:bg-rose-50"
                        >
                          <Trash2 className="h-4 w-4" />
                          Remove
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
        open={addOpen}
        icon={Mail}
        title="Add internal recipient"
        description="The scope and workflow cannot be changed later; remove the row and add it again instead."
        onClose={closeAdd}
        footer={
          <>
            <GhostButton onClick={closeAdd} disabled={adding}>
              Cancel
            </GhostButton>
            <SubmitButton loading={adding} form="recipient-add-form">
              Add recipient
            </SubmitButton>
          </>
        }
      >
        <form id="recipient-add-form" onSubmit={submitAdd} className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Scope" htmlFor="recipient-scope">
              <SelectInput
                id="recipient-scope"
                value={addForm.scope}
                onChange={(event) =>
                  setAddForm((current) => ({
                    ...current,
                    scope: event.target.value,
                    mapping_key: '',
                  }))
                }
              >
                <option value="event">One workflow</option>
                <option value="category">Whole category</option>
              </SelectInput>
            </Field>
            <Field label="Workflow" htmlFor="recipient-workflow">
              <SelectInput
                id="recipient-workflow"
                value={addForm.mapping_key}
                onChange={(event) =>
                  setAddForm((current) => ({
                    ...current,
                    mapping_key: event.target.value,
                  }))
                }
              >
                <option value="">Choose a workflow</option>
                {targetOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </SelectInput>
            </Field>
          </div>
          <Field
            label="Email address"
            htmlFor="recipient-email"
            hint="Each recipient receives their own copy; addresses are never shared between recipients."
          >
            <TextInput
              id="recipient-email"
              type="email"
              value={addForm.email}
              onChange={(event) =>
                setAddForm((current) => ({
                  ...current,
                  email: event.target.value,
                }))
              }
              maxLength={150}
              placeholder="owner@dairy.example"
            />
          </Field>
        </form>
      </Modal>

      <Modal
        open={Boolean(editTarget)}
        icon={Mail}
        title="Edit internal recipient"
        description={
          editTarget ? `${editTarget.scope} · ${editTarget.label}` : ''
        }
        onClose={closeEdit}
        footer={
          <>
            <GhostButton onClick={closeEdit} disabled={saving}>
              Cancel
            </GhostButton>
            <SubmitButton loading={saving} form="recipient-edit-form">
              Save changes
            </SubmitButton>
          </>
        }
      >
        <form id="recipient-edit-form" onSubmit={submitEdit} className="space-y-4">
          <Field label="Email address" htmlFor="recipient-edit-email">
            <TextInput
              id="recipient-edit-email"
              type="email"
              value={editForm.email}
              onChange={(event) =>
                setEditForm({ email: event.target.value })
              }
              maxLength={150}
            />
          </Field>
        </form>
      </Modal>

      <ConfirmModal
        isOpen={Boolean(deleteTarget)}
        title="Remove this internal recipient?"
        message="The address stops receiving internal copies immediately. This cannot be undone; deactivate instead if you may add it back later."
        confirmText="Remove recipient"
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
