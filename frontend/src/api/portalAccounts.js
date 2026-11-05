import apiClient from './client';

export const getPortalAccounts = (params) =>
  apiClient.get('/customer-portal-accounts', { params });
export const getPortalAccount = (id) =>
  apiClient.get(`/customer-portal-accounts/${id}`);
export const provisionPortalAccount = (data) =>
  apiClient.post('/customer-portal-accounts', data);
export const reactivatePortalAccount = (id) =>
  apiClient.post(`/customer-portal-accounts/${id}/reactivate`);
export const unlockPortalAccount = (id) =>
  apiClient.post(`/customer-portal-accounts/${id}/unlock`);
export const deactivatePortalAccount = (id, reason) =>
  apiClient.post(`/customer-portal-accounts/${id}/deactivate`, { reason });
export const resetPortalAccountActivation = (id) =>
  apiClient.post(`/customer-portal-accounts/${id}/reset-activation`);
