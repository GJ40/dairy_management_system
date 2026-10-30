import apiClient from './client';

export const getCustomerOrders = (params) =>
  apiClient.get('/customer-orders', { params });
export const getCustomerOrder = (id) => apiClient.get(`/customer-orders/${id}`);
export const approveCustomerOrder = (id, data = {}) =>
  apiClient.post(`/customer-orders/${id}/approve`, data);
export const rejectCustomerOrder = (id, reason) =>
  apiClient.post(`/customer-orders/${id}/reject`, { reason });
export const fulfilCustomerOrder = (id) =>
  apiClient.post(`/customer-orders/${id}/fulfil`);
export const cancelCustomerOrder = (id, reason) =>
  apiClient.post(`/customer-orders/${id}/cancel`, { reason });
