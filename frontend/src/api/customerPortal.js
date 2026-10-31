import { customerClient } from './customerClient';

export function getCustomerDashboard() {
  return customerClient.get('/customer-portal/dashboard');
}

export function getCustomerProfile() {
  return customerClient.get('/customer-portal/profile');
}

export function getMyOrders(params) {
  return customerClient.get('/customer-portal/orders', { params });
}

export function createMyOrder(data) {
  return customerClient.post('/customer-portal/orders', data);
}

export function getMyOrder(orderId) {
  return customerClient.get(`/customer-portal/orders/${orderId}`);
}

export function cancelMyOrder(orderId, reason) {
  return customerClient.post(`/customer-portal/orders/${orderId}/cancel`, {
    reason: reason ? reason.trim() : null,
  });
}

export function getMyInvoices(params) {
  return customerClient.get('/customer-portal/invoices', { params });
}

export function getMyInvoice(invoiceId) {
  return customerClient.get(`/customer-portal/invoices/${invoiceId}`);
}

export function getMyBalance() {
  return customerClient.get('/customer-portal/balance');
}

export async function fetchMyInvoicePdf(invoiceId) {
  const response = await customerClient.get(
    `/customer-portal/invoices/${invoiceId}/pdf`,
    { responseType: 'blob' }
  );
  return response.data;
}

export function getMyQueries(params) {
  return customerClient.get('/customer-portal/queries', { params });
}

export function createMyQuery(data) {
  return customerClient.post('/customer-portal/queries', data);
}

export function getMyQuery(queryId) {
  return customerClient.get(`/customer-portal/queries/${queryId}`);
}

export function addMyQueryMessage(queryId, message) {
  return customerClient.post(`/customer-portal/queries/${queryId}/messages`, {
    message,
  });
}
