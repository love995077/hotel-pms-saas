import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, apiFile, type DownloadedFile, saveFile } from "@/lib/api";
import type {
  ChannelConnection,
  ChannelConnectionCreated,
  ChannelWebhookEvent,
  ChargeInput,
  CurrentUser,
  DashboardStats,
  Folio,
  FolioTransaction,
  GstQuote,
  Guest,
  GuestInput,
  Hotel,
  HotelInput,
  OutboundTestResult,
  PaymentInput,
  Reservation,
  ReservationInput,
  RegisterRequest,
  RegisterResponse,
  Room,
  RoomInput,
  RoomType,
  RoomTypeAvailability,
  RoomTypeInput,
  TapeChart,
} from "@/lib/types";

/** Self-service sign-up: creates a hotel and its owner account. */
export function useRegisterHotel() {
  return useMutation<RegisterResponse, ApiError, RegisterRequest>({
    mutationFn: (body) =>
      api<RegisterResponse>("/onboarding/register", {
        method: "POST",
        anonymous: true,
        body,
      }),
  });
}

export function useCurrentUser(enabled = true) {
  return useQuery({
    queryKey: ["me"],
    queryFn: ({ signal }) => api<CurrentUser>("/auth/me", { signal }),
    staleTime: 5 * 60_000,
    enabled,
  });
}

/** Today's KPIs and the 30 days before it. */
export function useDashboardStats() {
  return useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: ({ signal }) => api<DashboardStats>("/reports/dashboard-stats", { signal }),
    refetchInterval: 60_000,
  });
}

/** Rooms, availability and reservations for nights in [start, end). */
export function useTapeChart(start: string, end: string, includeReleased = false) {
  return useQuery({
    queryKey: ["tape-chart", start, end, includeReleased],
    queryFn: ({ signal }) =>
      api<TapeChart>("/tape-chart", {
        query: { start, end, include_released: includeReleased },
        signal,
      }),
    // Keep the old window on screen while the next one loads, so paging
    // through dates does not flash an empty chart.
    placeholderData: keepPreviousData,
    refetchInterval: 60_000,
  });
}

export function useGuests(search: string) {
  return useQuery({
    queryKey: ["guests", search],
    queryFn: ({ signal }) =>
      api<Guest[]>("/guests", {
        query: { q: search.length >= 2 ? search : null, limit: 200 },
        signal,
      }),
    placeholderData: keepPreviousData,
  });
}

/** Every room type, including deactivated ones (the settings page manages both). */
export function useRoomTypes() {
  return useQuery({
    queryKey: ["room-types"],
    queryFn: ({ signal }) =>
      api<RoomType[]>("/room-types", {
        query: { include_inactive: true, limit: 200 },
        signal,
      }),
  });
}

/** Every physical room, including deactivated ones. */
export function useRooms() {
  return useQuery({
    queryKey: ["rooms"],
    queryFn: ({ signal }) =>
      api<Room[]>("/rooms", {
        query: { include_inactive: true, limit: 500 },
        signal,
      }),
  });
}

/** Inventory changes alter what the tape chart shows, so it is refreshed too. */
function useInvalidateInventory() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all(["room-types", "rooms", "tape-chart"].map((key) => queryClient.invalidateQueries({ queryKey: [key] })));
}

export function useCreateRoomType() {
  const invalidate = useInvalidateInventory();
  return useMutation<RoomType, ApiError, RoomTypeInput>({
    mutationFn: (body) => api<RoomType>("/room-types", { method: "POST", body }),
    onSuccess: invalidate,
  });
}

export function useUpdateRoomType() {
  const invalidate = useInvalidateInventory();
  return useMutation<RoomType, ApiError, { id: string; changes: Partial<RoomTypeInput> & { is_active?: boolean } }>({
    mutationFn: ({ id, changes }) => api<RoomType>(`/room-types/${id}`, { method: "PATCH", body: changes }),
    onSuccess: invalidate,
  });
}

export function useDeleteRoomType() {
  const invalidate = useInvalidateInventory();
  return useMutation<void, ApiError, string>({
    mutationFn: (id) => api<void>(`/room-types/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
}

export interface CreateRoomsResult {
  created: Room[];
  failed: { room_number: string; message: string }[];
}

/** Add several rooms of one type. A number that is already taken does not stop the rest. */
export function useCreateRooms() {
  const invalidate = useInvalidateInventory();
  return useMutation<CreateRoomsResult, ApiError, Omit<RoomInput, "room_number"> & { room_numbers: string[] }>({
    mutationFn: async ({ room_numbers, ...rest }) => {
      const result: CreateRoomsResult = { created: [], failed: [] };
      for (const room_number of room_numbers) {
        try {
          result.created.push(
            await api<Room>("/rooms", {
              method: "POST",
              body: { ...rest, room_number },
            }),
          );
        } catch (error) {
          if (!(error instanceof ApiError)) throw error;
          result.failed.push({ room_number, message: error.message });
        }
      }
      return result;
    },
    onSettled: invalidate,
  });
}

export function useUpdateRoom() {
  const invalidate = useInvalidateInventory();
  return useMutation<Room, ApiError, { id: string; changes: Partial<RoomInput> & { is_active?: boolean } }>({
    mutationFn: ({ id, changes }) => api<Room>(`/rooms/${id}`, { method: "PATCH", body: changes }),
    onSuccess: invalidate,
  });
}

export function useDeleteRoom() {
  const invalidate = useInvalidateInventory();
  return useMutation<void, ApiError, string>({
    mutationFn: (id) => api<void>(`/rooms/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
}

// --- guests -------------------------------------------------------------------

export function useGuest(id: string | null) {
  return useQuery({
    queryKey: ["guest", id],
    queryFn: ({ signal }) => api<Guest>(`/guests/${id}`, { signal }),
    enabled: id !== null,
  });
}

function useInvalidateGuests() {
  const queryClient = useQueryClient();
  // Guest names are printed on the tape chart, so it is refreshed as well.
  return () =>
    Promise.all(["guests", "guest", "tape-chart"].map((key) => queryClient.invalidateQueries({ queryKey: [key] })));
}

export function useCreateGuest() {
  const invalidate = useInvalidateGuests();
  return useMutation<Guest, ApiError, Partial<GuestInput> & Pick<GuestInput, "first_name" | "last_name">>({
    mutationFn: (body) => api<Guest>("/guests", { method: "POST", body }),
    onSuccess: invalidate,
  });
}

export function useUpdateGuest() {
  const invalidate = useInvalidateGuests();
  return useMutation<Guest, ApiError, { id: string; changes: Partial<GuestInput> }>({
    mutationFn: ({ id, changes }) => api<Guest>(`/guests/${id}`, { method: "PATCH", body: changes }),
    onSuccess: invalidate,
  });
}

/** Every stay a guest has had or has booked, oldest first. */
export function useGuestReservations(guestId: string | null) {
  return useQuery({
    queryKey: ["reservations", "guest", guestId],
    queryFn: ({ signal }) =>
      api<Reservation[]>("/reservations", {
        query: { guest_id: guestId, limit: 200 },
        signal,
      }),
    enabled: guestId !== null,
  });
}

// --- reservations -------------------------------------------------------------

export function useReservation(id: string | null) {
  return useQuery({
    queryKey: ["reservation", id],
    queryFn: ({ signal }) => api<Reservation>(`/reservations/${id}`, { signal }),
    enabled: id !== null,
  });
}

/** Rooms of one type that are free for every night of a stay. */
export function useStayAvailability(roomTypeId: string, start: string, end: string) {
  return useQuery({
    queryKey: ["availability", roomTypeId, start, end],
    queryFn: async ({ signal }) => {
      const rows = await api<RoomTypeAvailability[]>("/availability", {
        query: { start, end, room_type_id: roomTypeId },
        signal,
      });
      return rows[0]?.available_for_stay ?? 0;
    },
    enabled: roomTypeId !== "" && start !== "" && start < end,
    staleTime: 0,
  });
}

const MONEY = /^\d{1,10}(\.\d{1,2})?$/;

/** What a stay costs with GST. The slab is decided by the API, never here. */
export function useRoomQuote(ratePerNight: string, nights: number) {
  return useQuery({
    queryKey: ["room-quote", ratePerNight, nights],
    queryFn: ({ signal }) =>
      api<GstQuote>("/gst/room-quote", {
        query: { tariff_per_night: ratePerNight, nights },
        signal,
      }),
    enabled: MONEY.test(ratePerNight) && nights >= 1 && nights <= 365,
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
  });
}

function useInvalidateReservations() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all(
      ["tape-chart", "reservation", "reservations", "availability", "folio", "dashboard-stats"].map((key) =>
        queryClient.invalidateQueries({ queryKey: [key] }),
      ),
    );
}

export function useCreateReservation() {
  const invalidate = useInvalidateReservations();
  return useMutation<Reservation, ApiError, ReservationInput>({
    mutationFn: (body) => api<Reservation>("/reservations", { method: "POST", body }),
    onSuccess: invalidate,
  });
}

export type ReservationAction = "check-in" | "check-out" | "cancel";

/** Move a reservation through its lifecycle, or give it a physical room. */
export function useReservationAction() {
  const invalidate = useInvalidateReservations();
  return useMutation<
    Reservation,
    ApiError,
    { id: string; action: ReservationAction } | { id: string; action: "assign-room"; roomId: string }
  >({
    mutationFn: (variables) =>
      api<Reservation>(`/reservations/${variables.id}/${variables.action}`, {
        method: "POST",
        body: variables.action === "assign-room" ? { room_id: variables.roomId } : undefined,
      }),
    onSuccess: invalidate,
  });
}

// --- folios -------------------------------------------------------------------

/** The reservation's folio, or null if none has been opened yet. */
export function useFolio(reservationId: string | null) {
  return useQuery({
    queryKey: ["folio", reservationId],
    queryFn: async ({ signal }) => {
      try {
        return await api<Folio>("/folios", {
          query: { reservation_id: reservationId },
          signal,
        });
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
    enabled: reservationId !== null,
  });
}

function useInvalidateFolio() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ["folio"] });
}

export function useOpenFolio() {
  const invalidate = useInvalidateFolio();
  return useMutation<Folio, ApiError, string>({
    mutationFn: (reservationId) =>
      api<Folio>("/folios", {
        method: "POST",
        body: { reservation_id: reservationId },
      }),
    onSuccess: invalidate,
  });
}

export function usePostCharge(folioId: string) {
  const invalidate = useInvalidateFolio();
  return useMutation<FolioTransaction, ApiError, ChargeInput>({
    mutationFn: (body) =>
      api<FolioTransaction>(`/folios/${folioId}/charges`, {
        method: "POST",
        body,
      }),
    onSuccess: invalidate,
  });
}

export function usePostPayment(folioId: string) {
  const invalidate = useInvalidateFolio();
  return useMutation<FolioTransaction, ApiError, PaymentInput>({
    mutationFn: (body) =>
      api<FolioTransaction>(`/folios/${folioId}/payments`, {
        method: "POST",
        body,
      }),
    onSuccess: invalidate,
  });
}

/** Ledger lines are never edited: this posts the mirror image of one. */
export function useReverseTransaction(folioId: string) {
  const invalidate = useInvalidateFolio();
  return useMutation<FolioTransaction, ApiError, { transactionId: string; reason: string }>({
    mutationFn: ({ transactionId, reason }) =>
      api<FolioTransaction>(`/folios/${folioId}/transactions/${transactionId}/reverse`, {
        method: "POST",
        body: { reason },
      }),
    onSuccess: invalidate,
  });
}

/**
 * Download the folio's invoice PDF. For a closed folio the first download
 * issues its invoice number, so the folio is refreshed afterwards.
 */
export function useDownloadInvoice() {
  const invalidate = useInvalidateFolio();
  return useMutation<DownloadedFile, ApiError, Pick<Folio, "id" | "folio_number">>({
    mutationFn: (folio) => apiFile(`/folios/${folio.id}/invoice`, `Invoice-${folio.folio_number}.pdf`),
    onSuccess: (file) => {
      saveFile(file);
      return invalidate();
    },
  });
}

// --- hotel profile ------------------------------------------------------------

export function useHotel() {
  return useQuery({
    queryKey: ["hotel"],
    queryFn: ({ signal }) => api<Hotel>("/hotel", { signal }),
  });
}

export function useUpdateHotel() {
  const queryClient = useQueryClient();
  return useMutation<Hotel, ApiError, Partial<HotelInput>>({
    mutationFn: (changes) => api<Hotel>("/hotel", { method: "PATCH", body: changes }),
    onSuccess: (hotel) => queryClient.setQueryData(["hotel"], hotel),
  });
}

// --- channel manager ----------------------------------------------------------

export function useChannelConnections(enabled: boolean) {
  return useQuery({
    queryKey: ["channel-connections"],
    queryFn: ({ signal }) => api<ChannelConnection[]>("/channel-connections", { signal }),
    enabled,
    // Pushes are delivered in the background; this keeps their last result current.
    refetchInterval: 15_000,
  });
}

export function useCreateChannelConnection() {
  const queryClient = useQueryClient();
  return useMutation<ChannelConnectionCreated, ApiError, string>({
    mutationFn: (name) =>
      api<ChannelConnectionCreated>("/channel-connections", {
        method: "POST",
        body: { name },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["channel-connections"] }),
  });
}

export function useUpdateChannelConnection() {
  const queryClient = useQueryClient();
  return useMutation<
    ChannelConnection,
    ApiError,
    {
      id: string;
      changes: {
        name?: string;
        is_active?: boolean;
        outbound_url?: string | null;
      };
    }
  >({
    mutationFn: ({ id, changes }) =>
      api<ChannelConnection>(`/channel-connections/${id}`, {
        method: "PATCH",
        body: changes,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["channel-connections"] }),
  });
}

/** Send a signed ping to a connection's outbound URL and report what came back. */
export function useTestOutbound() {
  return useMutation<OutboundTestResult, ApiError, string>({
    mutationFn: (id) =>
      api<OutboundTestResult>(`/channel-connections/${id}/test-outbound`, {
        method: "POST",
      }),
  });
}

/** Queue a push of every room type's availability for the coming weeks. */
export function useSyncChannel() {
  const queryClient = useQueryClient();
  return useMutation<{ room_types_queued: number }, ApiError, string>({
    mutationFn: (id) =>
      api<{ room_types_queued: number }>(`/channel-connections/${id}/sync`, {
        method: "POST",
      }),
    // Give the worker a moment, then pick up the result of the push.
    onSuccess: () => {
      setTimeout(
        () =>
          void queryClient.invalidateQueries({
            queryKey: ["channel-connections"],
          }),
        3000,
      );
    },
  });
}

export function useChannelEvents(enabled: boolean) {
  return useQuery({
    queryKey: ["channel-events"],
    queryFn: ({ signal }) =>
      api<ChannelWebhookEvent[]>("/channel-connections/events", {
        query: { limit: 15 },
        signal,
      }),
    enabled,
    refetchInterval: 60_000,
  });
}
