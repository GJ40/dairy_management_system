import apiClient from './client';

export const getCustomerQueries = (params) =>
  apiClient.get('/customer-queries', { params });
export const getCustomerQuery = (id) => apiClient.get(`/customer-queries/${id}`);
export const addCustomerQueryMessage = (id, data) =>
  apiClient.post(`/customer-queries/${id}/messages`, data);
export const updateCustomerQueryStatus = (id, status) =>
  apiClient.post(`/customer-queries/${id}/status`, { status });
export const assignCustomerQuery = (id, assignedTo) =>
  apiClient.post(`/customer-queries/${id}/assign`, { assigned_to: assignedTo });
