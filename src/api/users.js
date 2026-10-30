import apiClient from './client';

export const getUsers = (params) => apiClient.get('/users', { params });
export const createUser = (data) => apiClient.post('/users', data);
export const deleteUser = (id) => apiClient.delete(`/users/${id}`);
