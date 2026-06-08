import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AuthState {
  token: string | null;
  username: string | null;
  role: string | null;
  email: string | null;
  login: (token: string, username: string, role: string, email?: string) => void;
  logout: () => void;
  updateProfile: (data: { username?: string; email?: string; role?: string }) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      username: null,
      role: null,
      email: null,
      login: (token, username, role, email) =>
        set({ token, username, role, email: email || null }),
      logout: () =>
        set({ token: null, username: null, role: null, email: null }),
      updateProfile: (data) =>
        set((state) => ({
          ...state,
          username: data.username ?? state.username,
          email: data.email ?? state.email,
          role: data.role ?? state.role,
        })),
    }),
    {
      name: 'ado-jk-auth',
      partialize: (state) => ({
        token: state.token,
        username: state.username,
        role: state.role,
        email: state.email,
      }),
    }
  )
);
