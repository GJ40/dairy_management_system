import { useState, useEffect, useCallback } from 'react';
import { toast } from 'react-toastify';
import { getUsers, createUser, deleteUser } from '../../api/users';
import PageHeader from '../../components/PageHeader';
import EmptyState from '../../components/EmptyState';
import LoadingSpinner from '../../components/LoadingSpinner';
import ErrorAlert from '../../components/ErrorAlert';
import { UserCog, Plus, Search, X, ShieldCheck, UserCheck, RefreshCw, Mail, User, Trash2, AlertTriangle } from 'lucide-react';

const EMPTY_FORM = {
  full_name: '',
  email: '',
  username: '',
  password: '',
  role: 'operator',
};

const ROLE_CONFIG = {
  admin: { label: 'Admin', color: 'bg-amber-100 text-amber-800', icon: ShieldCheck },
  operator: { label: 'Operator', color: 'bg-emerald-100 text-emerald-800', icon: UserCheck },
};

export default function UserManagement() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formLoading, setFormLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const fetchUsers = useCallback(() => {
    return getUsers({ page_size: 100 })
      .then((res) => {
        setUsers(Array.isArray(res) ? res : res?.items || res?.data || res?.users || []);
        setError(null);
      })
      .catch((err) => {
        setError(err.message || 'Failed to load users.');
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const refreshUsers = () => {
    setLoading(true);
    setError(null);
    fetchUsers();
  };

  const filtered = users.filter((u) => {
    const q = search.toLowerCase();
    return !q || u.full_name?.toLowerCase().includes(q) || u.email?.toLowerCase().includes(q) || u.username?.toLowerCase().includes(q);
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (form.password.length < 8) {
      toast.error('Password must be at least 8 characters.');
      return;
    }
    setFormLoading(true);
    try {
      await createUser({
        full_name: form.full_name.trim(),
        email: form.email.trim().toLowerCase(),
        username: form.username.trim().toLowerCase(),
        password: form.password,
        role: form.role,
      });
      toast.success(`User "${form.full_name}" created successfully!`);
      setShowForm(false);
      setForm(EMPTY_FORM);
      refreshUsers();
    } catch (err) {
      toast.error(err.message || 'Failed to create user. Email or username may already exist.');
    } finally {
      setFormLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteUser(deleteTarget.id);
      toast.success(`Operator "${deleteTarget.full_name}" deleted.`);
      setDeleteTarget(null);
      refreshUsers();
    } catch (err) {
      toast.error(err.message || 'Failed to delete user.');
    } finally {
      setDeleting(false);
    }
  };

  const adminCount = users.filter((u) => u.role === 'admin').length;
  const operatorCount = users.filter((u) => u.role === 'operator').length;

  return (
    <div>
      <PageHeader
        title="User Management"
        subtitle="Manage system users and their roles. Admin access only."
        badge="Admin Only"
      >
        <div className="flex items-center gap-3">
          <button
            onClick={refreshUsers}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 rounded-lg transition"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={() => { setShowForm(true); setForm(EMPTY_FORM); }}
            className="inline-flex items-center gap-2 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg text-sm font-semibold shadow-sm transition"
          >
            <Plus className="w-4 h-4" /> Create User
          </button>
        </div>
      </PageHeader>

      {/* Summary */}
      <div className="flex gap-4 mb-5">
        <div className="flex items-center gap-2 px-4 py-2 bg-white rounded-xl border border-slate-200 shadow-sm">
          <ShieldCheck className="w-4 h-4 text-amber-600" />
          <span className="text-sm font-bold text-slate-800">{adminCount}</span>
          <span className="text-xs text-slate-500">Admin{adminCount !== 1 ? 's' : ''}</span>
        </div>
        <div className="flex items-center gap-2 px-4 py-2 bg-white rounded-xl border border-slate-200 shadow-sm">
          <UserCheck className="w-4 h-4 text-emerald-600" />
          <span className="text-sm font-bold text-slate-800">{operatorCount}</span>
          <span className="text-xs text-slate-500">Operator{operatorCount !== 1 ? 's' : ''}</span>
        </div>
      </div>

      {/* Search */}
      <div className="relative mb-5">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <input
          type="text"
          placeholder="Search by name, email, or username…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-9 pr-4 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400 bg-white"
        />
      </div>

      {loading ? (
        <LoadingSpinner message="Loading users…" />
      ) : error ? (
        <ErrorAlert message={error} onRetry={refreshUsers} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={UserCog}
          title="No users found"
          description={search ? 'Try adjusting your search.' : 'Create the first system user.'}
        />
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">User</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Username</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Email</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Role</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">ID</th>
                  <th className="px-4 py-3 text-right text-xs font-bold text-slate-500 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filtered.map((u) => {
                  const RoleCfg = ROLE_CONFIG[u.role] || ROLE_CONFIG.operator;
                  const RoleIcon = RoleCfg.icon;
                  return (
                    <tr key={u.id} className="hover:bg-slate-50 transition-colors">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <div className={`w-9 h-9 rounded-full flex items-center justify-center font-bold text-sm ${RoleCfg.color}`}>
                            {u.full_name?.charAt(0)?.toUpperCase() || 'U'}
                          </div>
                          <span className="font-semibold text-slate-800">{u.full_name}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5 text-slate-600 font-mono text-xs">
                          <User className="w-3.5 h-3.5 text-slate-400" /> {u.username}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5 text-slate-600 text-xs">
                          <Mail className="w-3.5 h-3.5 text-slate-400" /> {u.email}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${RoleCfg.color}`}>
                          <RoleIcon className="w-3 h-3" /> {RoleCfg.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-400 text-xs font-mono">#{u.id}</td>
                      <td className="px-4 py-3 text-right">
                        {u.role === 'operator' ? (
                          <button
                            onClick={() => setDeleteTarget(u)}
                            title={`Delete operator ${u.full_name}`}
                            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold text-rose-700 bg-rose-50 border border-rose-200 hover:bg-rose-100 rounded-lg transition"
                          >
                            <Trash2 className="w-3.5 h-3.5" /> Delete
                          </button>
                        ) : (
                          <span
                            className="text-xs text-slate-400"
                            title="Admin accounts are managed by deactivation"
                          >
                            —
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="px-4 py-2 border-t border-slate-100 bg-slate-50 text-xs text-slate-500">
            {filtered.length} of {users.length} users
          </div>
        </div>
      )}

      {/* Delete Operator Confirmation */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm">
            <div className="flex items-start gap-3 p-6 border-b border-slate-100">
              <div className="w-9 h-9 rounded-xl bg-rose-100 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-5 h-5 text-rose-700" />
              </div>
              <div>
                <h2 className="font-bold text-slate-900">Delete operator account?</h2>
                <p className="text-xs text-slate-500 mt-1">
                  {deleteTarget.full_name} ({deleteTarget.username}) will be removed from
                  the user list and can no longer sign in. Their production, sales,
                  wastage and expense history is kept.
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-3 p-4">
              <button
                type="button"
                onClick={() => setDeleteTarget(null)}
                disabled={deleting}
                className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition disabled:opacity-60"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleting}
                className="px-4 py-2 text-sm font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded-lg transition disabled:opacity-60"
              >
                {deleting ? 'Deleting…' : 'Delete Operator'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create User Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-amber-100 flex items-center justify-center">
                  <UserCog className="w-5 h-5 text-amber-700" />
                </div>
                <div>
                  <h2 className="font-bold text-slate-900">Create User Account</h2>
                  <p className="text-xs text-slate-500">Add a staff member or admin account</p>
                </div>
              </div>
              <button onClick={() => setShowForm(false)} className="p-1.5 hover:bg-slate-100 rounded-lg transition">
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>
            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Full Name <span className="text-rose-500">*</span></label>
                <input
                  required
                  type="text"
                  placeholder="e.g. Rajesh Kumar"
                  value={form.full_name}
                  onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Username <span className="text-rose-500">*</span></label>
                  <input
                    required
                    type="text"
                    placeholder="e.g. rajesh_op"
                    value={form.username}
                    onChange={(e) => setForm({ ...form, username: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Role</label>
                  <select
                    value={form.role}
                    onChange={(e) => setForm({ ...form, role: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400 bg-white"
                  >
                    <option value="operator">Operator</option>
                    <option value="admin">Admin</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Email <span className="text-rose-500">*</span></label>
                <input
                  required
                  type="email"
                  placeholder="e.g. rajesh@dairyfarm.in"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Password <span className="text-rose-500">*</span></label>
                <input
                  required
                  type="password"
                  placeholder="Min. 8 characters"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400"
                />
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={() => setShowForm(false)} className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition">
                  Cancel
                </button>
                <button type="submit" disabled={formLoading} className="px-4 py-2 text-sm font-semibold text-white bg-amber-500 hover:bg-amber-600 rounded-lg transition disabled:opacity-60">
                  {formLoading ? 'Creating…' : 'Create User'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
