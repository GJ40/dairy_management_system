import { useState, useEffect, useCallback } from 'react';
import { AuthContext } from './authContextDef';
import { loginApi, getMeApi } from '../api/auth';
import { TOKEN_STORAGE_KEY, USER_STORAGE_KEY } from '../api/client';

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_STORAGE_KEY));
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem(USER_STORAGE_KEY);
    if (!saved) return null;
    try {
      return JSON.parse(saved);
    } catch {
      return null;
    }
  });
  const [isLoading, setIsLoading] = useState(true);
  const [authError, setAuthError] = useState(null);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    localStorage.removeItem(USER_STORAGE_KEY);
    setToken(null);
    setUser(null);
    setAuthError(null);
  }, []);

  // Listen for 401 unauthorized events emitted from API client
  useEffect(() => {
    const handleUnauthorized = () => {
      logout();
    };
    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => {
      window.removeEventListener('auth:unauthorized', handleUnauthorized);
    };
  }, [logout]);

  // Bootstrap current user session on initial mount
  useEffect(() => {
    let isMounted = true;

    async function bootstrap() {
      const storedToken = localStorage.getItem(TOKEN_STORAGE_KEY);
      if (!storedToken) {
        if (isMounted) setIsLoading(false);
        return;
      }

      try {
        const response = await getMeApi();
        if (isMounted) {
          if (response?.user) {
            setUser(response.user);
            localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(response.user));
          } else {
            logout();
          }
        }
      } catch {
        if (isMounted) {
          logout();
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    bootstrap();

    return () => {
      isMounted = false;
    };
  }, [logout]);

  const login = async (email, password) => {
    setAuthError(null);
    try {
      const response = await loginApi(email, password);
      const { token: receivedToken, user: receivedUser } = response;

      localStorage.setItem(TOKEN_STORAGE_KEY, receivedToken);
      localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(receivedUser));

      setToken(receivedToken);
      setUser(receivedUser);
      return receivedUser;
    } catch (err) {
      const message = err.message || 'Invalid email or password.';
      setAuthError(message);
      throw err;
    }
  };

  const value = {
    user,
    token,
    isAuthenticated: Boolean(token && user),
    isAdmin: user?.role === 'admin',
    isOperator: user?.role === 'operator',
    isLoading,
    authError,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export default AuthProvider;
