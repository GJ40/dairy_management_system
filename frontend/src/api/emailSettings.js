import apiClient from './client';

// Every endpoint under /email-settings is Admin-only on the server; a non-admin
// gets 403 and the UI shows the message from the error normaliser.
const BASE = '/email-settings';

/* Transport (SMTP) */
export const getSmtpSettings = () => apiClient.get(`${BASE}/smtp`);
export const getSmtpProfile = (profileId) =>
  apiClient.get(`${BASE}/smtp/profiles/${profileId}`);
export const createSmtpProfile = (data) =>
  apiClient.post(`${BASE}/smtp/profiles`, data);
export const updateSmtpProfile = (profileId, data) =>
  apiClient.patch(`${BASE}/smtp/profiles/${profileId}`, data);
export const testSmtpConnection = (profileId) =>
  apiClient.post(`${BASE}/smtp/profiles/${profileId}/test-connection`);
export const sendSmtpTestEmail = (profileId, recipientEmail) =>
  apiClient.post(`${BASE}/smtp/profiles/${profileId}/test-email`, {
    recipient_email: recipientEmail,
  });
export const activateSmtpProfile = (profileId) =>
  apiClient.post(`${BASE}/smtp/profiles/${profileId}/activate`);
// Not named `useEnvironmentSmtp`: the `use` prefix makes the react-hooks lint
// rule treat it as a React hook.
export const revertSmtpToEnvironment = () =>
  apiClient.post(`${BASE}/smtp/use-environment`);

/* Sender identities */
export const getSenderIdentities = () => apiClient.get(`${BASE}/senders`);
export const getSenderIdentity = (senderId) =>
  apiClient.get(`${BASE}/senders/${senderId}`);
export const createSenderIdentity = (data) =>
  apiClient.post(`${BASE}/senders`, data);
export const updateSenderIdentity = (senderId, data) =>
  apiClient.patch(`${BASE}/senders/${senderId}`, data);
export const activateSenderIdentity = (senderId) =>
  apiClient.post(`${BASE}/senders/${senderId}/activate`);
export const deactivateSenderIdentity = (senderId) =>
  apiClient.post(`${BASE}/senders/${senderId}/deactivate`);
export const deleteSenderIdentity = (senderId) =>
  apiClient.delete(`${BASE}/senders/${senderId}`);

/* Workflow catalogue and sender mappings */
export const getWorkflowCatalogue = () => apiClient.get(`${BASE}/workflows`);
export const getWorkflowMappings = () =>
  apiClient.get(`${BASE}/workflow-mappings`);
export const replaceWorkflowMappings = (data) =>
  apiClient.put(`${BASE}/workflow-mappings`, data);

/* Internal notification recipients */
export const getNotificationRecipients = () =>
  apiClient.get(`${BASE}/recipients`);
export const createNotificationRecipient = (data) =>
  apiClient.post(`${BASE}/recipients`, data);
export const updateNotificationRecipient = (recipientId, data) =>
  apiClient.patch(`${BASE}/recipients/${recipientId}`, data);
export const activateNotificationRecipient = (recipientId) =>
  apiClient.post(`${BASE}/recipients/${recipientId}/activate`);
export const deactivateNotificationRecipient = (recipientId) =>
  apiClient.post(`${BASE}/recipients/${recipientId}/deactivate`);
export const deleteNotificationRecipient = (recipientId) =>
  apiClient.delete(`${BASE}/recipients/${recipientId}`);
