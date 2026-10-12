"use client";

import { BedDouble, CalendarDays, CircleAlert, IndianRupee, LoaderCircle, Mail, NotebookPen, Phone, Users } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { FolioPanel } from "@/components/reservations/folio-panel";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FormError, Segmented, Select } from "@/components/ui/field";
import { formatStay, nightsBetween } from "@/lib/dates";
import {
  type ReservationAction,
  useCurrentUser,
  useFolio,
  useGuest,
  useReservation,
  useReservationAction,
  useRoomQuote,
  useRooms,
  useRoomTypes,
} from "@/lib/queries";
import { can } from "@/lib/roles";
import { SOURCE_STYLES, STATUS_CHIP, STATUS_LABELS } from "@/lib/sources";
import type { Reservation } from "@/lib/types";
import { cn, formatAmount, formatMoney } from "@/lib/utils";

const byRoomNumber = new Intl.Collator("en", { numeric: true });

const ACTION_TOAST: Record<ReservationAction, string> = {
  "check-in": "Guest checked in",
  "check-out": "Guest checked out",
  cancel: "Reservation cancelled",
};

export function ReservationDialog({ reservationId, onClose }: { reservationId: string; onClose: () => void }) {
  const reservation = useReservation(reservationId);
  const [tab, setTab] = useState<"stay" | "folio">("stay");

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl" aria-describedby={undefined}>
        {reservation.data ? (
          <Loaded reservation={reservation.data} tab={tab} onTabChange={setTab} />
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Reservation</DialogTitle>
            </DialogHeader>
            <DialogBody className="flex min-h-48 items-center justify-center">
              {reservation.isError ? (
                <div className="flex flex-col items-center gap-3 text-center">
                  <CircleAlert className="size-6 text-destructive" />
                  <p className="text-sm text-muted-foreground">{reservation.error.message}</p>
                  <Button variant="outline" size="sm" onClick={() => reservation.refetch()}>
                    Try again
                  </Button>
                </div>
              ) : (
                <LoaderCircle className="size-5 animate-spin text-muted-foreground" aria-label="Loading" />
              )}
            </DialogBody>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Loaded({
  reservation,
  tab,
  onTabChange,
}: {
  reservation: Reservation;
  tab: "stay" | "folio";
  onTabChange: (tab: "stay" | "folio") => void;
}) {
  const role = useCurrentUser().data?.role;
  const guest = useGuest(reservation.guest_id).data;
  const roomType = useRoomTypes().data?.find((candidate) => candidate.id === reservation.room_type_id);
  const rooms = (useRooms().data ?? [])
    .filter((room) => room.room_type_id === reservation.room_type_id && (room.is_active || room.id === reservation.room_id))
    .sort((a, b) => byRoomNumber.compare(a.room_number, b.room_number));
  const folio = useFolio(reservation.id);
  const action = useReservationAction();
  const [confirmingCancel, setConfirmingCancel] = useState(false);

  const nights = nightsBetween(reservation.check_in_date, reservation.check_out_date);
  const quote = useRoomQuote(Number(reservation.rate_per_night).toString(), nights).data;
  const source = SOURCE_STYLES[reservation.source];
  const guestName = guest ? `${guest.first_name} ${guest.last_name}` : "Reservation";

  const canFrontOffice = can(role, "frontOffice");
  const isConfirmed = reservation.status === "confirmed";
  const isInHouse = reservation.status === "checked_in";
  const balance = folio.data ? Number(folio.data.balance) : 0;
  const settled = folio.data !== undefined && balance === 0;

  const run = (name: ReservationAction) =>
    action.mutate(
      { id: reservation.id, action: name },
      {
        onSuccess: () => {
          toast.success(ACTION_TOAST[name], { description: guestName });
          setConfirmingCancel(false);
          if (name === "check-in") onTabChange("folio");
        },
      },
    );

  return (
    <>
      <DialogHeader>
        <div className="flex flex-wrap items-center gap-2.5">
          <DialogTitle>{guestName}</DialogTitle>
          <span
            className={cn(
              "rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset",
              STATUS_CHIP[reservation.status],
            )}
          >
            {STATUS_LABELS[reservation.status]}
          </span>
        </div>
        <DialogDescription className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-mono text-xs tracking-wide">{reservation.confirmation_number}</span>
          <span aria-hidden>·</span>
          <span className="flex items-center gap-1.5">
            <span aria-hidden className={cn("size-2 rounded-full", source.accent)} />
            {source.label}
          </span>
        </DialogDescription>
        <Segmented
          label="Section"
          value={tab}
          onChange={onTabChange}
          className="mt-3 self-start"
          options={[
            { value: "stay", label: "Stay" },
            {
              value: "folio",
              label: (
                <>
                  Folio &amp; billing
                  {folio.data && balance !== 0 && (
                    <span className="rounded-full bg-amber-100 px-1.5 text-[11px] font-semibold tabular-nums text-amber-800">
                      {formatMoney(Math.abs(balance))}
                    </span>
                  )}
                </>
              ),
            },
          ]}
        />
      </DialogHeader>

      <DialogBody className="min-h-64">
        <FormError className="mb-4" message={action.error?.message} />

        {tab === "stay" ? (
          <div className="space-y-4">
            <dl className="grid gap-x-6 gap-y-3.5 sm:grid-cols-2">
              <Fact icon={CalendarDays} label="Stay">
                {formatStay(reservation.check_in_date, reservation.check_out_date)}
                <span className="text-muted-foreground">
                  {" "}
                  · {nights} night{nights === 1 ? "" : "s"}
                </span>
              </Fact>
              <Fact icon={Users} label="Guests">
                {reservation.adults} adult{reservation.adults === 1 ? "" : "s"}
                {reservation.children > 0 &&
                  `, ${reservation.children} child${reservation.children === 1 ? "" : "ren"}`}
              </Fact>
              <Fact icon={BedDouble} label="Room type">
                {roomType ? `${roomType.name} (${roomType.code})` : "—"}
              </Fact>
              <Fact icon={IndianRupee} label="Rate">
                {formatMoney(reservation.rate_per_night)}
                <span className="text-muted-foreground"> per night</span>
                {quote && (
                  <span className="block text-xs text-muted-foreground">
                    {formatAmount(quote.total_amount)} for the stay incl. {Number(quote.gst_rate)}% GST
                  </span>
                )}
              </Fact>
              {guest?.phone && (
                <Fact icon={Phone} label="Phone">
                  {guest.phone}
                </Fact>
              )}
              {guest?.email && (
                <Fact icon={Mail} label="Email">
                  {guest.email}
                </Fact>
              )}
            </dl>

            <div className="rounded-lg border border-border bg-muted/40 p-3.5">
              <label htmlFor="assigned-room" className="text-[13px] font-medium">
                Room
              </label>
              {canFrontOffice && (isConfirmed || isInHouse) ? (
                <>
                  <Select
                    id="assigned-room"
                    className="mt-2"
                    value={reservation.room_id ?? ""}
                    disabled={action.isPending}
                    onChange={(event) => {
                      const roomId = event.target.value;
                      if (roomId === "") return;
                      action.mutate(
                        { id: reservation.id, action: "assign-room", roomId },
                        {
                          onSuccess: (updated) =>
                            toast.success(
                              `Room ${rooms.find((room) => room.id === updated.room_id)?.room_number ?? ""} assigned`,
                            ),
                        },
                      );
                    }}
                  >
                    {reservation.room_id === null && <option value="">Not assigned yet</option>}
                    {rooms.map((room) => (
                      <option key={room.id} value={room.id}>
                        {room.room_number}
                        {room.floor ? ` · Floor ${room.floor}` : ""}
                      </option>
                    ))}
                  </Select>
                  {reservation.room_id === null && (
                    <p className="mt-2 text-xs text-muted-foreground">A room must be assigned before check-in.</p>
                  )}
                </>
              ) : (
                <p className="mt-1 text-sm">
                  {rooms.find((room) => room.id === reservation.room_id)?.room_number ?? "Not assigned"}
                </p>
              )}
            </div>

            {reservation.notes && (
              <div className="flex items-start gap-2.5 text-[13px]">
                <NotebookPen className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                <p className="whitespace-pre-wrap">{reservation.notes}</p>
              </div>
            )}
          </div>
        ) : folio.isPending ? (
          <div className="space-y-3" aria-busy="true" aria-label="Loading folio">
            {Array.from({ length: 4 }, (_, index) => (
              <div key={index} className="h-10 animate-pulse rounded-md bg-muted" />
            ))}
          </div>
        ) : folio.isError ? (
          <FormError message={folio.error.message} />
        ) : (
          <FolioPanel
            reservation={reservation}
            folio={folio.data}
            canBill={can(role, "billing")}
            canReverse={can(role, "ledgerControl")}
          />
        )}
      </DialogBody>

      {canFrontOffice && (isConfirmed || isInHouse) && (
        <DialogFooter>
          {isConfirmed &&
            (confirmingCancel ? (
              <div className="flex items-center gap-2 sm:mr-auto">
                <span className="text-[13px] text-muted-foreground">Cancel this reservation?</span>
                <Button
                  size="sm"
                  disabled={action.isPending}
                  onClick={() => run("cancel")}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  Yes, cancel it
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setConfirmingCancel(false)}>
                  Keep
                </Button>
              </div>
            ) : (
              <Button
                variant="ghost"
                onClick={() => setConfirmingCancel(true)}
                className="text-destructive hover:bg-destructive/10 hover:text-destructive sm:mr-auto"
              >
                Cancel reservation
              </Button>
            ))}

          {isConfirmed && (
            <Button disabled={action.isPending || reservation.room_id === null} onClick={() => run("check-in")}>
              {action.isPending && <LoaderCircle className="size-4 animate-spin" />}
              Check in
            </Button>
          )}

          {isInHouse && (
            <>
              {!settled && folio.data && (
                <p className="text-[13px] text-muted-foreground sm:mr-auto">
                  {balance > 0
                    ? `Settle ${formatAmount(balance)} to check out.`
                    : `Refund ${formatAmount(-balance)} to check out.`}
                </p>
              )}
              {tab === "stay" && !settled ? (
                <Button onClick={() => onTabChange("folio")}>Open folio</Button>
              ) : (
                <Button disabled={action.isPending || !settled} onClick={() => run("check-out")}>
                  {action.isPending && <LoaderCircle className="size-4 animate-spin" />}
                  Check out
                </Button>
              )}
            </>
          )}
        </DialogFooter>
      )}
    </>
  );
}

function Fact({ icon: Icon, label, children }: { icon: typeof Users; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
        <Icon className="size-4" strokeWidth={1.75} />
      </span>
      <div className="min-w-0">
        <dt className="text-xs text-muted-foreground">{label}</dt>
        <dd className="text-[13.5px] font-medium">{children}</dd>
      </div>
    </div>
  );
}
