import apiClient from './client';

export const getStock = (date) => apiClient.get('/stock', { params: date ? { date } : {} });
export const createWastage = (data) => apiClient.post('/wastage', data);
export const deleteWastage = (id) => apiClient.delete(`/wastage/${id}`);
