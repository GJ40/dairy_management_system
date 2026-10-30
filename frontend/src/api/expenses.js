import apiClient from './client';

export const getExpenses = (params) => apiClient.get('/expenses', { params });
export const getExpenseCategories = () => apiClient.get('/expense-categories');
export const createExpense = (data) => apiClient.post('/expenses', data);
export const deleteExpense = (id) => apiClient.delete(`/expenses/${id}`);
