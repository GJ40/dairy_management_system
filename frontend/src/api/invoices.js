import apiClient from './client';

export const getInvoices = (params) => apiClient.get('/invoices', { params });
export const createInvoice = (data) => apiClient.post('/invoices', data);
export const recordPayment = (id, data) => apiClient.patch(`/invoices/${id}/payment`, data);
export const downloadInvoicePdf = (id) =>
  apiClient.get(`/invoices/${id}/pdf`, { responseType: 'blob' });
export const deleteInvoice = (id) => apiClient.delete(`/invoices/${id}`);
