import apiClient from './client';

export const getSales = (params) => apiClient.get('/sales', { params });
export const createSale = (data) => apiClient.post('/sales', data);
export const deleteSale = (id) => apiClient.delete(`/sales/${id}`);
