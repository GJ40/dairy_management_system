import apiClient from './client';

export const getBuffaloes = (params) => apiClient.get('/buffaloes', { params });
export const getBuffaloCount = () => apiClient.get('/buffaloes/count');
export const createBuffalo = (data) => apiClient.post('/buffaloes', data);
export const updateBuffalo = (id, data) => apiClient.put(`/buffaloes/${id}`, data);
export const deleteBuffalo = (id) => apiClient.delete(`/buffaloes/${id}`);
