import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { setUnauthorizedHandler, tokenStore } from "../api/client";
import { auth } from "../api/endpoints";

export const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  // With a stored token we don't know who we are until /auth/me answers.
  const [loading, setLoading] = useState(() => Boolean(tokenStore.get()));
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!tokenStore.get()) return;
    auth
      .me()
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    // Any request whose token is rejected ends the session.
    setUnauthorizedHandler(() => {
      setUser(null);
      queryClient.clear();
      navigate("/login", { replace: true });
    });
    return () => setUnauthorizedHandler(null);
  }, [navigate, queryClient]);

  const startSession = useCallback((session) => {
    tokenStore.set(session.access_token);
    setUser(session.user);
    return session.user;
  }, []);

  const login = useCallback(
    async (email, password) => startSession(await auth.login({ email, password })),
    [startSession],
  );

  const register = useCallback(
    async (data) => startSession(await auth.register(data)),
    [startSession],
  );

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    queryClient.clear();
    navigate("/login", { replace: true });
  }, [navigate, queryClient]);

  const value = useMemo(
    () => ({ user, loading, isAgent: user?.role === "agent", login, register, logout }),
    [user, loading, login, register, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
