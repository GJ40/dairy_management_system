import { useEffect, useState } from 'react';
import { toast } from 'react-toastify';
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Mail,
  Pencil,
  Plus,
  RefreshCw,
  Send,
  ShieldCheck,
  X,
} from 'lucide-react';
import {
  activateSmtpProfile,
  createSmtpProfile,
  getSmtpSettings,
  revertSmtpToEnvironment,
  sendSmtpTestEmail,
  testSmtpConnection,
  updateSmtpProfile,
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
  Toggle,
} from './EmailSettingsParts';

const EMPTY_FORM = {
  name: '',
  provider_mode: 'custom',
  host: '',
  port: '587',
  auth_enabled: false,
  username: '',
  password: '',
  encryption_mode: 'starttls',
  timeout_seconds: '10',
};

const EMPTY_RECIPIENT = 'admin@example.com';

const SOURCE_COPY = {
  database: {
    tone: 'emerald',
    title: 'Database profile is active',
    detail:
      'All emails use the active SMTP profile below. The SMTP_* environment variables are ignored until you switch back.',
  },
  environment: {
    tone: 'sky',
    title: 'Using the environment transport',
    detail: 'Emails use the SMTP_* and MAIL_FROM_* variables from the server environment.',
  },
  unconfigured: {
    tone: 'amber',
    title: 'No transport configured',
    detail:
      'Nothing is sent until a profile is activated or the environment variables are set. Sign-in links and order emails are silently skipped.',
  },
};

function statusTone(status) {
  if (status === 'active') return 'emerald';
  if (status === 'draft') return 'sky';
  return 'slate';
}

function providerLabel(profile) {
  return profile.provider_mode === 'mailpit' ? 'Mailpit' : 'Custom SMTP';
}

function profileForm(profile) {
  if (!profile) return { ...EMPTY_FORM };
  return {
    name: profile.name,
    provider_mode: profile.provider_mode,
    host: profile.host,
    port: String(profile.port),
    auth_enabled: profile.auth_enabled,
    username: '',
    password: '',
    encryption_mode: profile.encryption_mode,
    timeout_seconds: String(profile.timeout_seconds),
  };
}

function validateForm(form, isEdit) {
  if (!form.name.trim()) return 'Enter a profile name.';
  if (!form.host.trim()) return 'Enter the SMTP host.';
  if (form.host.includes('://') || form.host.includes('/')) {
    return 'The host must be a hostname or IP address, not a URL.';
  }
  const port = Number(form.port);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    return 'The port must be a whole number between 1 and 65535.';
  }
  const timeout = Number(form.timeout_seconds);
  if (!Number.isInteger(timeout) || timeout < 1 || timeout > 120) {
    return 'The timeout must be a whole number between 1 and 120 seconds.';
  }
  if (form.provider_mode === 'custom' && form.auth_enabled) {
    if (!isEdit && !form.username.trim()) {
      return 'Enter the SMTP username when authentication is enabled.';
    }
    if (!isEdit && !form.password) {
      return 'Enter the SMTP password when authentication is enabled.';
    }
  }
  return null;
}

// The server never returns stored credentials, so a blank field means "keep
// what is stored". Clearing credentials is explicit: turn authentication off
// (or switch to Mailpit), which sends nulls.
function buildPayload(form, isEdit) {
  const payload = {
    name: form.name.trim(),
    provider_mode: form.provider_mode,
    host: form.host.trim(),
    port: Number(form.port),
    auth_enabled: form.provider_mode === 'custom' ? form.auth_enabled : false,
    encryption_mode:
      form.provider_mode === 'mailpit' ? 'none' : form.encryption_mode,
    timeout_seconds: Number(form.timeout_seconds),
  };
  if (payload.auth_enabled) {
    if (form.username.trim()) payload.username = form.username.trim();
    if (form.password) payload.password = form.password;
  } else {
    payload.username = null;
    payload.password = null;
  }
  if (!isEdit && payload.auth_enabled) {
    payload.username = form.username.trim();
    payload.password = form.password;
  }
  return payload;
}

export default function SmtpTab() {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [modal, setModal] = useState(null);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [saving, setSaving] = useState(false);

  const [busyProfileId, setBusyProfileId] = useState(null);
  const [testEmailTarget, setTestEmailTarget] = useState(null);
  const [testEmailRecipient, setTestEmailRecipient] = useState('');
  const [testEmailSending, setTestEmailSending] = useState(false);

  const [activateTarget, setActivateTarget] = useState(null);
  const [environmentConfirm, setEnvironmentConfirm] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const response = await getSmtpSettings();
        if (cancelled) return;
        setOverview(response || null);
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err?.message || 'Failed to load the SMTP settings.');
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
    setModal({ mode: 'create', profile: null });
  };

  const openEdit = (profile) => {
    setForm(profileForm(profile));
    setModal({ mode: 'edit', profile });
  };

  const closeModal = () => {
    if (saving) return;
    setModal(null);
  };

  const updateField = (key) => (event) =>
    setForm((current) => ({ ...current, [key]: event.target.value }));

  const applyMailpitPreset = () => {
    const preset = overview?.mailpit_preset || {};
    setForm((current) => ({
      ...current,
      provider_mode: 'mailpit',
      host: preset.host || '127.0.0.1',
      port: String(preset.port || 1025),
      auth_enabled: false,
      username: '',
      password: '',
      encryption_mode: 'none',
    }));
  };

  const submitProfile = async (event) => {
    event.preventDefault();
    const isEdit = modal?.mode === 'edit';
    const validation = validateForm(form, isEdit);
    if (validation) {
      toast.error(validation);
      return;
    }
    setSaving(true);
    try {
      const payload = buildPayload(form, isEdit);
      if (isEdit) {
        await updateSmtpProfile(modal.profile.id, payload);
        toast.success(
          'SMTP profile updated. Test it again before activating it.'
        );
      } else {
        await createSmtpProfile(payload);
        toast.success('SMTP profile saved as a draft. Test it, then activate it.');
      }
      setModal(null);
      refresh({ quiet: true });
    } catch (err) {
      toast.error(err?.message || 'Could not save this SMTP profile.');
    } finally {
      setSaving(false);
    }
  };

  const runConnectionTest = async (profile) => {
    setBusyProfileId(profile.id);
    try {
      const result = await testSmtpConnection(profile.id);
      if (result?.test_status === 'success') {
        toast.success(result.message || 'Connection succeeded.');
      } else {
        toast.error(result?.message || 'The connection test failed.');
      }
      refresh({ quiet: true });
    } catch (err) {
      toast.error(err?.message || 'Could not run the connection test.');
    } finally {
      setBusyProfileId(null);
    }
  };

  const openTestEmail = (profile) => {
    setTestEmailTarget(profile);
    setTestEmailRecipient(
      overview?.environment?.from_email || EMPTY_RECIPIENT
    );
  };

  const closeTestEmail = () => {
    if (testEmailSending) return;
    setTestEmailTarget(null);
    setTestEmailRecipient('');
  };

  const submitTestEmail = async (event) => {
    event.preventDefault();
    const recipient = testEmailRecipient.trim();
    if (!recipient) {
      toast.error('Enter the address that should receive the test email.');
      return;
    }
    setTestEmailSending(true);
    try {
      const result = await sendSmtpTestEmail(testEmailTarget.id, recipient);
      if (result?.test_status === 'success') {
        toast.success(result.message || 'Test email sent.');
      } else {
        toast.error(result?.message || 'The test email could not be sent.');
      }
      setTestEmailTarget(null);
      setTestEmailRecipient('');
      refresh({ quiet: true });
    } catch (err) {
      toast.error(err?.message || 'Could not send the test email.');
    } finally {
      setTestEmailSending(false);
    }
  };

  const confirmActivate = async () => {
    if (!activateTarget) return;
    setActionLoading(true);
    try {
      const response = await activateSmtpProfile(activateTarget.id);
      setOverview(response || null);
      toast.success('SMTP profile activated. New emails use it immediately.');
      setActivateTarget(null);
    } catch (err) {
      toast.error(err?.message || 'Could not activate this profile.');
    } finally {
      setActionLoading(false);
    }
  };

  const confirmEnvironment = async () => {
    setActionLoading(true);
    try {
      const response = await revertSmtpToEnvironment();
      setOverview(response || null);
      toast.success('Reverted to the environment transport.');
      setEnvironmentConfirm(false);
    } catch (err) {
      toast.error(err?.message || 'Could not switch back to the environment.');
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return <LoadingSpinner message="Loading SMTP transport settings…" />;
  }

  if (error) {
    return <ErrorAlert message={error} onRetry={() => refresh()} />;
  }

  const profiles = Array.isArray(overview?.profiles) ? overview.profiles : [];
  const activeProfileId = overview?.active_profile?.id ?? null;
  const source = overview?.source || 'unconfigured';
  const sourceCopy = SOURCE_COPY[source] || SOURCE_COPY.unconfigured;
  const environment = overview?.environment || {};
  const credentialsAllowed = overview?.encryption_key_configured !== false;

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-slate-500">
          Credentials are stored encrypted and are never sent back to the
          browser.
        </p>
        <div className="flex items-center gap-2">
          <GhostButton icon={RefreshCw} onClick={() => refresh()}>
            Refresh
          </GhostButton>
          {source === 'database' && (
            <GhostButton onClick={() => setEnvironmentConfirm(true)}>
              Use environment transport
            </GhostButton>
          )}
        </div>
      </div>

      <div
        className={`mb-5 flex items-start gap-3 rounded-xl border p-4 ${
          sourceCopy.tone === 'emerald'
            ? 'border-emerald-200 bg-emerald-50'
            : sourceCopy.tone === 'sky'
              ? 'border-sky-200 bg-sky-50'
              : 'border-amber-200 bg-amber-50'
        }`}
      >
        <ShieldCheck
          className={`mt-0.5 h-5 w-5 shrink-0 ${
            sourceCopy.tone === 'amber' ? 'text-amber-700' : 'text-emerald-700'
          }`}
        />
        <div>
          <p className="text-sm font-bold text-slate-900">
            {sourceCopy.title}
            {overview?.active_profile?.name
              ? `: ${overview.active_profile.name}`
              : ''}
          </p>
          <p className="mt-0.5 text-xs leading-relaxed text-slate-600">
            {sourceCopy.detail}
          </p>
        </div>
      </div>

      {!credentialsAllowed && (
        <div className="mb-5 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" />
          <div>
            <p className="text-sm font-bold text-slate-900">
              EMAIL_SETTINGS_ENCRYPTION_KEY is not configured
            </p>
            <p className="mt-0.5 text-xs leading-relaxed text-slate-600">
              SMTP credentials cannot be stored or decrypted until that key is
              set on the server. Profiles without authentication (such as
              Mailpit) still work.
            </p>
          </div>
        </div>
      )}

      <SectionCard
        icon={Mail}
        title="Environment transport"
        description="Read-only view of the SMTP_* and MAIL_FROM_* variables. Used only while no database profile is active."
      >
        <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <dt className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Configured
            </dt>
            <dd className="text-slate-800">
              {environment.configured ? 'Yes' : 'No'}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Host
            </dt>
            <dd className="font-mono text-xs text-slate-800">
              {environment.host ? `${environment.host}:${environment.port}` : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Encryption
            </dt>
            <dd className="text-slate-800">{environment.encryption_mode || '—'}</dd>
          </div>
          <div>
            <dt className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Authentication
            </dt>
            <dd className="text-slate-800">
              {environment.auth_enabled ? 'Username set' : 'None'}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              From
            </dt>
            <dd className="text-slate-800">
              {environment.from_email
                ? `${environment.from_name || ''} <${environment.from_email}>`
                : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Timeout
            </dt>
            <dd className="text-slate-800">
              {environment.timeout_seconds
                ? `${environment.timeout_seconds} s`
                : '—'}
            </dd>
          </div>
        </dl>
      </SectionCard>

      <SectionCard
        icon={ShieldCheck}
        title="SMTP profiles"
        description="A profile must pass a connection test before it can be activated. Activating one archives the profile that was active."
        actions={
          <GhostButton icon={Plus} onClick={openCreate}>
            Add profile
          </GhostButton>
        }
      >
        {profiles.length === 0 ? (
          <EmptyState
            icon={Mail}
            title="No SMTP profiles yet"
            description="Add a profile to send through your own mail server instead of the environment variables."
            action={
              <GhostButton icon={Plus} onClick={openCreate}>
                Add profile
              </GhostButton>
            }
          />
        ) : (
          <div className="space-y-3">
            {profiles.map((profile) => {
              const isActive = profile.id === activeProfileId;
              const testedAfterChange =
                profile.last_test_status === 'success' &&
                profile.tested_fingerprint === profile.config_fingerprint;
              const canActivate =
                profile.status !== 'active' && testedAfterChange;
              let activateHint = '';
              if (profile.status === 'active') {
                activateHint = 'This profile is already active.';
              } else if (profile.last_test_status !== 'success') {
                activateHint = 'Run a successful connection test first.';
              } else if (!testedAfterChange) {
                activateHint =
                  'The configuration changed after the last test; test it again.';
              }

              return (
                <article
                  key={profile.id}
                  className={`rounded-xl border p-4 ${
                    isActive
                      ? 'border-emerald-300 bg-emerald-50/40'
                      : 'border-slate-200 bg-white'
                  }`}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-sm font-bold text-slate-900">
                          {profile.name}
                        </h3>
                        <Badge tone={statusTone(profile.status)}>
                          {profile.status}
                        </Badge>
                        {isActive && <Badge tone="emerald">In use</Badge>}
                        {profile.provider_mode === 'mailpit' && (
                          <Badge tone="sky">Local Mailpit</Badge>
                        )}
                      </div>
                      <p className="mt-1 font-mono text-xs text-slate-600">
                        {profile.host}:{profile.port} · {providerLabel(profile)} ·{' '}
                        {profile.encryption_mode}
                        {profile.auth_enabled
                          ? profile.username_configured
                            ? ' · credentials stored'
                            : ' · credentials missing'
                          : ' · no authentication'}
                      </p>
                      <p className="mt-1 text-[11px] text-slate-500">
                        Timeout {profile.timeout_seconds}s · updated{' '}
                        {formatDateTime(profile.updated_at)}
                      </p>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <GhostButton
                        icon={Pencil}
                        onClick={() => openEdit(profile)}
                      >
                        Edit
                      </GhostButton>
                      <GhostButton
                        icon={busyProfileId === profile.id ? Loader2 : RefreshCw}
                        onClick={() => runConnectionTest(profile)}
                        disabled={busyProfileId === profile.id}
                      >
                        {busyProfileId === profile.id
                          ? 'Testing…'
                          : 'Test connection'}
                      </GhostButton>
                      <GhostButton
                        icon={Send}
                        onClick={() => openTestEmail(profile)}
                      >
                        Test email
                      </GhostButton>
                      <button
                        type="button"
                        onClick={() => setActivateTarget(profile)}
                        disabled={!canActivate}
                        title={activateHint || undefined}
                        className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <CheckCircle2 className="h-4 w-4" />
                        Activate
                      </button>
                    </div>
                  </div>

                  <div
                    className={`mt-3 rounded-lg border px-3 py-2 text-[11px] ${
                      profile.last_test_status === 'success' && testedAfterChange
                        ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                        : profile.last_test_status === 'failure'
                          ? 'border-rose-200 bg-rose-50 text-rose-800'
                          : 'border-slate-200 bg-slate-50 text-slate-600'
                    }`}
                  >
                    {profile.last_test_status === 'success' ? (
                      testedAfterChange ? (
                        <>
                          {profile.last_test_kind === 'email'
                            ? 'Test email'
                            : 'Connection test'}{' '}
                          passed {formatDateTime(profile.last_tested_at)}.
                        </>
                      ) : (
                        <>
                          Last test passed {formatDateTime(profile.last_tested_at)},
                          but the configuration changed since then — test it
                          again before activating.
                        </>
                      )
                    ) : profile.last_test_status === 'failure' ? (
                      <>
                        Last test failed {formatDateTime(profile.last_tested_at)}
                        {profile.last_test_reason
                          ? ` (${profile.last_test_reason})`
                          : ''}
                        . Fix the settings and test again.
                      </>
                    ) : (
                      'Not tested yet. Run a connection test to enable activation.'
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </SectionCard>

      <Modal
        open={Boolean(modal)}
        wide
        icon={ShieldCheck}
        title={modal?.mode === 'edit' ? 'Edit SMTP profile' : 'Add SMTP profile'}
        description="Profiles are saved as drafts. Saving invalidates any earlier test result."
        onClose={closeModal}
        footer={
          <>
            <GhostButton onClick={closeModal} disabled={saving}>
              Cancel
            </GhostButton>
            <SubmitButton loading={saving} form="smtp-profile-form">
              {modal?.mode === 'edit' ? 'Save changes' : 'Save draft'}
            </SubmitButton>
          </>
        }
      >
        <form id="smtp-profile-form" onSubmit={submitProfile} className="space-y-4">
          <Field label="Profile name" htmlFor="smtp-name">
            <TextInput
              id="smtp-name"
              value={form.name}
              onChange={updateField('name')}
              maxLength={100}
              placeholder="Production mail server"
            />
          </Field>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field
              label="Provider"
              htmlFor="smtp-provider"
              hint="Mailpit is the local dev catcher on 127.0.0.1:1025."
            >
              <SelectInput
                id="smtp-provider"
                value={form.provider_mode}
                onChange={(event) => {
                  updateField('provider_mode')(event);
                  if (event.target.value === 'mailpit') {
                    setForm((current) => ({
                      ...current,
                      provider_mode: 'mailpit',
                      auth_enabled: false,
                      username: '',
                      password: '',
                      encryption_mode: 'none',
                    }));
                  }
                }}
              >
                <option value="custom">Custom SMTP</option>
                <option value="mailpit">Mailpit (local)</option>
              </SelectInput>
            </Field>

            <Field label="Quick preset" hint="Fills the local Mailpit defaults.">
              <GhostButton icon={Mail} onClick={applyMailpitPreset}>
                Use Mailpit defaults
              </GhostButton>
            </Field>

            <Field label="Host" htmlFor="smtp-host">
              <TextInput
                id="smtp-host"
                value={form.host}
                onChange={updateField('host')}
                maxLength={255}
                placeholder="smtp.example.com"
              />
            </Field>

            <Field label="Port" htmlFor="smtp-port">
              <TextInput
                id="smtp-port"
                type="number"
                min="1"
                max="65535"
                value={form.port}
                onChange={updateField('port')}
              />
            </Field>

            <Field label="Encryption" htmlFor="smtp-encryption">
              <SelectInput
                id="smtp-encryption"
                value={form.encryption_mode}
                onChange={updateField('encryption_mode')}
                disabled={form.provider_mode === 'mailpit'}
              >
                <option value="none">None</option>
                <option value="starttls">STARTTLS</option>
                <option value="ssl">SSL / TLS</option>
              </SelectInput>
            </Field>

            <Field label="Timeout (seconds)" htmlFor="smtp-timeout">
              <TextInput
                id="smtp-timeout"
                type="number"
                min="1"
                max="120"
                value={form.timeout_seconds}
                onChange={updateField('timeout_seconds')}
              />
            </Field>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-bold text-slate-800">
                  SMTP authentication
                </p>
                <p className="text-[11px] text-slate-500">
                  {form.provider_mode === 'mailpit'
                    ? 'Mailpit accepts no credentials.'
                    : 'Credentials are encrypted at rest and never returned by the API.'}
                </p>
              </div>
              <Toggle
                checked={
                  form.provider_mode === 'custom' ? form.auth_enabled : false
                }
                disabled={form.provider_mode === 'mailpit'}
                label="SMTP authentication"
                onChange={(value) =>
                  setForm((current) => ({ ...current, auth_enabled: value }))
                }
              />
            </div>

            {form.provider_mode === 'custom' && form.auth_enabled && (
              <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Field
                  label="Username"
                  htmlFor="smtp-username"
                  hint={
                    modal?.mode === 'edit' && modal.profile?.username_configured
                      ? 'Leave blank to keep the stored username.'
                      : undefined
                  }
                >
                  <TextInput
                    id="smtp-username"
                    value={form.username}
                    onChange={updateField('username')}
                    autoComplete="off"
                    maxLength={320}
                  />
                </Field>
                <Field
                  label="Password"
                  htmlFor="smtp-password"
                  hint={
                    modal?.mode === 'edit' && modal.profile?.password_configured
                      ? 'Leave blank to keep the stored password.'
                      : undefined
                  }
                >
                  <TextInput
                    id="smtp-password"
                    type="password"
                    value={form.password}
                    onChange={updateField('password')}
                    autoComplete="new-password"
                    maxLength={1024}
                  />
                </Field>
              </div>
            )}
          </div>
        </form>
      </Modal>

      <Modal
        open={Boolean(testEmailTarget)}
        icon={Send}
        title="Send a test email"
        description={
          testEmailTarget
            ? `Sent through “${testEmailTarget.name}”. This does not activate the profile.`
            : ''
        }
        onClose={closeTestEmail}
        footer={
          <>
            <GhostButton onClick={closeTestEmail} disabled={testEmailSending}>
              <X className="h-4 w-4" />
              Cancel
            </GhostButton>
            <SubmitButton
              loading={testEmailSending}
              form="smtp-test-email-form"
            >
              Send test email
            </SubmitButton>
          </>
        }
      >
        <form
          id="smtp-test-email-form"
          onSubmit={submitTestEmail}
          className="space-y-3"
        >
          <Field
            label="Recipient"
            htmlFor="smtp-test-recipient"
            hint="Type the address explicitly; it never defaults to the sender."
          >
            <TextInput
              id="smtp-test-recipient"
              type="email"
              value={testEmailRecipient}
              onChange={(event) => setTestEmailRecipient(event.target.value)}
              maxLength={150}
              placeholder="you@example.com"
            />
          </Field>
        </form>
      </Modal>

      <ConfirmModal
        isOpen={Boolean(activateTarget)}
        title={`Activate “${activateTarget?.name || ''}”?`}
        message="All emails start using this profile immediately. The profile that is currently active is archived, and the SMTP_* environment variables stop being used. Only a successfully tested profile can be activated."
        confirmText="Activate profile"
        confirmVariant="primary"
        isLoading={actionLoading}
        onConfirm={confirmActivate}
        onClose={() => {
          if (!actionLoading) setActivateTarget(null);
        }}
      />

      <ConfirmModal
        isOpen={environmentConfirm}
        title="Use the environment transport again?"
        message="The active database profile will be archived and emails will use the SMTP_* and MAIL_FROM_* variables. Nothing else about the profile changes."
        confirmText="Switch to environment"
        confirmVariant="primary"
        isLoading={actionLoading}
        onConfirm={confirmEnvironment}
        onClose={() => {
          if (!actionLoading) setEnvironmentConfirm(false);
        }}
      />
    </div>
  );
}
