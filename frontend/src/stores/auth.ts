import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

interface AuthState {
  token: string | null;
  /** Epoch milliseconds after which the token is no longer accepted. */
  expiresAt: number | null;
  /** Remembered so the login form can prefill it. */
  hotelSlug: string;
  /** False until the persisted state has been read on the client. */
  hydrated: boolean;
  setSession: (token: string, expiresInSeconds: number, hotelSlug: string) => void;
  clearSession: () => void;
  /** Prefill the login form for a hotel that has no session yet (after sign-up). */
  rememberHotel: (hotelSlug: string) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      expiresAt: null,
      hotelSlug: "",
      hydrated: false,
      setSession: (token, expiresInSeconds, hotelSlug) =>
        set({ token, expiresAt: Date.now() + expiresInSeconds * 1000, hotelSlug }),
      clearSession: () => set({ token: null, expiresAt: null }),
      rememberHotel: (hotelSlug) => set({ hotelSlug }),
    }),
    {
      name: "pms-auth",
      storage: createJSONStorage(() => localStorage),
      partialize: ({ token, expiresAt, hotelSlug }) => ({ token, expiresAt, hotelSlug }),
      // Read localStorage only after mount (see Providers), so the first client
      // render matches the server-rendered HTML.
      skipHydration: true,
      onRehydrateStorage: () => () => {
        useAuthStore.setState({ hydrated: true });
      },
    },
  ),
);

export function hasValidSession(state: Pick<AuthState, "token" | "expiresAt">): boolean {
  return Boolean(state.token && state.expiresAt && state.expiresAt > Date.now());
}
