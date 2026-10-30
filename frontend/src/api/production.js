import apiClient from './client';

export const getProduction = (date) => apiClient.get('/production', { params: date ? { date } : {} });
export const getProductionGrid = (date) => apiClient.get('/production/grid', { params: date ? { date } : {} });
export const createProduction = (data) => apiClient.post('/production', data);
export const deleteProduction = (id) => apiClient.delete(`/production/${id}`);
