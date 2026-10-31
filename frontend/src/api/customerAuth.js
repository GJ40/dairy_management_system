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

export function forgotCustomerPassword(email) {
  return customerClient.post('/customer-auth/forgot-password', { email });
}

export function validateCustomerResetToken(token) {
  return customerClient.get('/customer-auth/reset-password/validate', {
    params: { token },
  });
}

export function resetCustomerPassword(token, password) {
  return customerClient.post('/customer-auth/reset-password', {
    token,
    password,
  });
}
