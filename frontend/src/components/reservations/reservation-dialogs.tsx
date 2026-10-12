"use client";

import { useState } from "react";

import { NewReservationDialog, type ReservationDraft } from "@/components/reservations/new-reservation-dialog";
import { ReservationDialog } from "@/components/reservations/reservation-dialog";

type Open = { kind: "new"; draft: ReservationDraft } | { kind: "details"; reservationId: string };

/**
 * The booking and reservation-details dialogs for a page. Render `dialogs`
 * once, then open them from anywhere on the page.
 */
export function useReservationDialogs() {
  const [open, setOpen] = useState<Open | null>(null);
  const close = () => setOpen(null);

  const dialogs =
    open?.kind === "new" ? (
      <NewReservationDialog
        draft={open.draft}
        onClose={close}
        // Straight into the new booking, so a walk-in can be checked in at once.
        onCreated={(reservation) => setOpen({ kind: "details", reservationId: reservation.id })}
      />
    ) : open?.kind === "details" ? (
      // Keyed so switching reservation starts on the Stay tab with clean state.
      <ReservationDialog key={open.reservationId} reservationId={open.reservationId} onClose={close} />
    ) : null;

  return {
    dialogs,
    openNew: (draft: ReservationDraft = {}) => setOpen({ kind: "new", draft }),
    openDetails: (reservationId: string) => setOpen({ kind: "details", reservationId }),
  };
}
