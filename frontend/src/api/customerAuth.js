import { customerClient } from './customerClient';

export function activateCustomerAccount(token, password) {
  return customerClient.post('/customer-auth/activate', { token, password });
}

export function loginCustomer(email, password) {
  return customerClient.post('/customer-auth/login', { email, password });
}

export function getCustomerMe() {
  return customerClient.get('/customer-auth/me');
}

export function logoutCustomer() {
  return customerClient.post('/customer-auth/logout');
}
