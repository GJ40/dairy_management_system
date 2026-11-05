import apiClient from './client';

export const getSecurityAuditEvents = (params) =>
  apiClient.get('/security-audit', { params });

export const getSecurityAuditEvent = (id) =>
  apiClient.get(`/security-audit/${id}`);
