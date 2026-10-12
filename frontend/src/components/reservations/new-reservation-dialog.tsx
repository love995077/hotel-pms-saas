"use client";

import { addDays } from "date-fns";
import { Check, Search, UserPlus, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FormError, Segmented, Select, SubmitButton, Textarea } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { fromIso, nightsBetween, toIso, today } from "@/lib/dates";
import {
  useCreateGuest,
  useCreateReservation,
  useGuests,
  useRoomQuote,
  useRooms,
  useRoomTypes,
  useStayAvailability,
} from "@/lib/queries";
import type { BookingSource, Guest, Reservation } from "@/lib/types";
import { cn, formatAmount, formatMoney, initials } from "@/lib/utils";

/** Where on the tape chart the booking was started, if anywhere. */
export interface ReservationDraft {
  roomTypeId?: string;
  roomId?: string;
  checkIn?: string;
}

// Bookings staff take themselves. OTA sources arrive through the channel manager.
const SOURCES: readonly { value: BookingSource; label: string }[] = [
  { value: "walk_in", label: "Walk-in" },
  { value: "phone", label: "Phone" },
  { value: "direct", label: "Direct" },
  { value: "corporate", label: "Corporate" },
  { value: "travel_agent", label: "Travel agent" },
];

const MONEY_PATTERN = /^\d{1,10}(\.\d{1,2})?$/;
const byRoomNumber = new Intl.Collator("en", { numeric: true });

function useDebounced<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function NewReservationDialog({
  draft,
  onClose,
  onCreated,
}: {
  draft: ReservationDraft;
  onClose: () => void;
  onCreated: (reservation: Reservation) => void;
}) {
  const todayIso = toIso(today());
  const roomTypes = useRoomTypes().data?.filter((roomType) => roomType.is_active);
  const allRooms = useRooms().data;
  const createGuest = useCreateGuest();
  const createReservation = useCreateReservation();

  const [source, setSource] = useState<BookingSource>(
    (draft.checkIn ?? todayIso) === todayIso ? "walk_in" : "phone",
  );

  // Guest: pick an existing profile or enter a new one.
  const [guest, setGuest] = useState<Guest | null>(null);
  const [guestMode, setGuestMode] = useState<"search" | "new">("search");
  const [search, setSearch] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const matches = useGuests(useDebounced(search.trim()));

  // Stay
  const [checkIn, setCheckIn] = useState(draft.checkIn ?? todayIso);
  const [checkOut, setCheckOut] = useState(toIso(addDays(fromIso(draft.checkIn ?? todayIso), 1)));
  const [roomTypeId, setRoomTypeId] = useState(draft.roomTypeId ?? "");
  const [roomId, setRoomId] = useState(draft.roomId ?? "");
  const [adults, setAdults] = useState("2");
  const [children, setChildren] = useState("0");
  // Empty means "use the room type's base rate".
  const [rate, setRate] = useState("");
  const [notes, setNotes] = useState("");
  const [submitted, setSubmitted] = useState(false);

  // Default to the first room type once they have loaded.
  useEffect(() => {
    if (roomTypeId === "" && roomTypes && roomTypes.length > 0) setRoomTypeId(roomTypes[0].id);
  }, [roomTypeId, roomTypes]);

  const roomType = roomTypes?.find((candidate) => candidate.id === roomTypeId);
  const rooms = (allRooms ?? [])
    .filter((room) => room.is_active && room.room_type_id === roomTypeId)
    .sort((a, b) => byRoomNumber.compare(a.room_number, b.room_number));

  const datesValid = checkIn !== "" && checkOut !== "" && checkIn < checkOut;
  const nights = datesValid ? nightsBetween(checkIn, checkOut) : 0;
  const effectiveRate = rate.trim() === "" ? (roomType ? Number(roomType.base_rate).toString() : "") : rate.trim();
  const availability = useStayAvailability(roomTypeId, checkIn, checkOut);
  const quote = useRoomQuote(effectiveRate, nights);

  const occupants = Number(adults) + Number(children);
  const errors = {
    guest:
      guest === null && guestMode === "search"
        ? "Choose a guest, or add a new one."
        : guest === null && (firstName.trim() === "" || lastName.trim() === "")
          ? "Enter the guest's first and last name."
          : null,
    dates: !datesValid ? "Check-out must be after check-in." : nights > 365 ? "A stay can't exceed 365 nights." : null,
    occupancy:
      roomType && occupants > roomType.max_occupancy ? `${roomType.name} sleeps at most ${roomType.max_occupancy}.` : null,
    rate: rate.trim() !== "" && !MONEY_PATTERN.test(rate.trim()) ? "Enter an amount such as 4500 or 4500.50." : null,
  };
  const soldOut = datesValid && availability.data !== undefined && availability.data <= 0;
  const pending = createGuest.isPending || createReservation.isPending;

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    if (Object.values(errors).some(Boolean) || !roomType) return;
    try {
      let bookingGuest = guest;
      if (bookingGuest === null) {
        bookingGuest = await createGuest.mutateAsync({
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          phone: phone.trim() || null,
          email: email.trim() || null,
        });
        // If the booking itself now fails, a retry reuses this profile instead of adding a duplicate.
        setGuest(bookingGuest);
      }
      const reservation = await createReservation.mutateAsync({
        guest_id: bookingGuest.id,
        room_type_id: roomType.id,
        room_id: roomId || null,
        check_in_date: checkIn,
        check_out_date: checkOut,
        adults: Number(adults),
        children: Number(children),
        ...(rate.trim() !== "" ? { rate_per_night: rate.trim() } : {}),
        source,
        notes: notes.trim() || null,
      });
      toast.success("Reservation confirmed", {
        description: `${bookingGuest.first_name} ${bookingGuest.last_name} · ${reservation.confirmation_number}`,
      });
      onCreated(reservation);
    } catch {
      // Shown from the mutation state below.
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl">
        <form onSubmit={onSubmit} className="flex min-h-0 flex-col">
          <DialogHeader>
            <DialogTitle>New reservation</DialogTitle>
            <DialogDescription>Book a stay for a walk-in, phone or direct guest.</DialogDescription>
          </DialogHeader>

          <DialogBody className="space-y-5">
            <FormError message={createReservation.error?.message ?? createGuest.error?.message} />

            <Segmented label="Booking source" value={source} onChange={setSource} options={SOURCES} className="flex" />

            {/* Guest */}
            <section aria-label="Guest" className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-[13px] font-semibold">Guest</h3>
                {guest === null && (
                  <button
                    type="button"
                    onClick={() => setGuestMode(guestMode === "search" ? "new" : "search")}
                    className="flex items-center gap-1.5 text-[13px] font-medium text-primary underline-offset-4 hover:underline"
                  >
                    {guestMode === "search" ? (
                      <>
                        <UserPlus className="size-3.5" /> New guest
                      </>
                    ) : (
                      <>
                        <Search className="size-3.5" /> Find existing guest
                      </>
                    )}
                  </button>
                )}
              </div>

              {guest ? (
                <div className="flex items-center gap-3 rounded-lg border border-border bg-accent/40 px-3 py-2.5">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-semibold text-accent-foreground">
                    {initials(`${guest.first_name} ${guest.last_name}`)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {guest.first_name} {guest.last_name}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {[guest.phone, guest.email].filter(Boolean).join(" · ") || "No contact details"}
                    </p>
                  </div>
                  <Button type="button" variant="ghost" size="sm" onClick={() => setGuest(null)}>
                    <X className="size-3.5" /> Change
                  </Button>
                </div>
              ) : guestMode === "search" ? (
                <div>
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                      placeholder="Search by name, phone or email"
                      aria-label="Search guests"
                      aria-invalid={submitted && errors.guest !== null}
                      className="pl-9"
                      autoFocus
                    />
                  </div>
                  {search.trim().length >= 2 && (
                    <ul className="scroll-slim mt-2 max-h-44 overflow-y-auto rounded-lg border border-border">
                      {matches.data?.length === 0 ? (
                        <li className="px-3 py-3 text-[13px] text-muted-foreground">
                          No guest matches &ldquo;{search.trim()}&rdquo;.{" "}
                          <button
                            type="button"
                            className="font-medium text-primary underline-offset-4 hover:underline"
                            onClick={() => {
                              const [first, ...rest] = search.trim().split(/\s+/);
                              setFirstName(first ?? "");
                              setLastName(rest.join(" "));
                              setGuestMode("new");
                            }}
                          >
                            Add as a new guest
                          </button>
                        </li>
                      ) : (
                        matches.data?.slice(0, 8).map((match) => (
                          <li key={match.id} className="border-b border-border/70 last:border-b-0">
                            <button
                              type="button"
                              onClick={() => setGuest(match)}
                              className="flex w-full items-center gap-3 px-3 py-2 text-left transition-colors hover:bg-accent/60"
                            >
                              <span className="min-w-0 flex-1">
                                <span className="block truncate text-[13px] font-medium">
                                  {match.first_name} {match.last_name}
                                </span>
                                <span className="block truncate text-xs text-muted-foreground">
                                  {[match.phone, match.email].filter(Boolean).join(" · ") || "No contact details"}
                                </span>
                              </span>
                            </button>
                          </li>
                        ))
                      )}
                    </ul>
                  )}
                </div>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="First name">
                    {(field) => (
                      <Input
                        {...field}
                        value={firstName}
                        onChange={(event) => setFirstName(event.target.value)}
                        maxLength={100}
                        autoComplete="off"
                        autoFocus
                      />
                    )}
                  </Field>
                  <Field label="Last name">
                    {(field) => (
                      <Input
                        {...field}
                        value={lastName}
                        onChange={(event) => setLastName(event.target.value)}
                        maxLength={100}
                        autoComplete="off"
                      />
                    )}
                  </Field>
                  <Field label="Phone (optional)">
                    {(field) => (
                      <Input
                        {...field}
                        type="tel"
                        value={phone}
                        onChange={(event) => setPhone(event.target.value)}
                        maxLength={32}
                        autoComplete="off"
                      />
                    )}
                  </Field>
                  <Field label="Email (optional)">
                    {(field) => (
                      <Input
                        {...field}
                        type="email"
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                        autoComplete="off"
                      />
                    )}
                  </Field>
                </div>
              )}
              {submitted && errors.guest && <p className="text-xs text-destructive">{errors.guest}</p>}
            </section>

            {/* Stay */}
            <section aria-label="Stay" className="space-y-3">
              <h3 className="text-[13px] font-semibold">Stay</h3>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Check-in">
                  {(field) => (
                    <Input
                      {...field}
                      type="date"
                      value={checkIn}
                      onChange={(event) => {
                        const next = event.target.value;
                        setCheckIn(next);
                        // Keep the stay at least one night long.
                        if (next !== "" && checkOut <= next) setCheckOut(toIso(addDays(fromIso(next), 1)));
                      }}
                      required
                    />
                  )}
                </Field>
                <Field label="Check-out" error={errors.dates}>
                  {(field) => (
                    <Input
                      {...field}
                      type="date"
                      value={checkOut}
                      min={checkIn}
                      onChange={(event) => setCheckOut(event.target.value)}
                      required
                    />
                  )}
                </Field>
                <Field label="Room type">
                  {(field) => (
                    <Select
                      {...field}
                      value={roomTypeId}
                      onChange={(event) => {
                        setRoomTypeId(event.target.value);
                        setRoomId("");
                      }}
                      required
                    >
                      {roomTypes?.map((option) => (
                        <option key={option.id} value={option.id}>
                          {option.name} · {formatMoney(option.base_rate)}
                        </option>
                      ))}
                    </Select>
                  )}
                </Field>
                <Field label="Room" hint="Can be assigned any time before check-in.">
                  {(field) => (
                    <Select {...field} value={roomId} onChange={(event) => setRoomId(event.target.value)}>
                      <option value="">Assign later</option>
                      {rooms.map((room) => (
                        <option key={room.id} value={room.id}>
                          {room.room_number}
                          {room.floor ? ` · Floor ${room.floor}` : ""}
                        </option>
                      ))}
                    </Select>
                  )}
                </Field>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <Field label="Adults">
                  {(field) => (
                    <Input
                      {...field}
                      type="number"
                      min={1}
                      max={20}
                      value={adults}
                      onChange={(event) => setAdults(event.target.value)}
                      required
                    />
                  )}
                </Field>
                <Field label="Children" error={errors.occupancy}>
                  {(field) => (
                    <Input
                      {...field}
                      type="number"
                      min={0}
                      max={20}
                      value={children}
                      onChange={(event) => setChildren(event.target.value)}
                      required
                    />
                  )}
                </Field>
                <Field label="Rate / night" error={submitted ? errors.rate : null}>
                  {(field) => (
                    <div className="relative">
                      <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                        ₹
                      </span>
                      <Input
                        {...field}
                        value={rate}
                        onChange={(event) => setRate(event.target.value)}
                        placeholder={roomType ? Number(roomType.base_rate).toString() : ""}
                        inputMode="decimal"
                        className="pl-7"
                      />
                    </div>
                  )}
                </Field>
              </div>
            </section>

            {/* What the stay comes to */}
            {datesValid && roomType && (
              <div className="rounded-lg border border-border bg-muted/40 px-4 py-3 text-[13px]">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-muted-foreground">
                    {nights} night{nights === 1 ? "" : "s"} × {effectiveRate ? formatMoney(effectiveRate) : "—"}
                  </span>
                  <span
                    className={cn(
                      "flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11.5px] font-medium ring-1 ring-inset",
                      availability.data === undefined
                        ? "text-muted-foreground ring-border"
                        : soldOut
                          ? "bg-rose-50 text-rose-700 ring-rose-200"
                          : "bg-emerald-50 text-emerald-700 ring-emerald-200",
                    )}
                  >
                    {availability.data === undefined ? (
                      "Checking availability…"
                    ) : soldOut ? (
                      "Sold out for these dates"
                    ) : (
                      <>
                        <Check className="size-3" strokeWidth={2.5} />
                        {availability.data} {availability.data === 1 ? "room" : "rooms"} free
                      </>
                    )}
                  </span>
                </div>
                {quote.data && (
                  <dl className="mt-2.5 space-y-1 border-t border-border pt-2.5">
                    <div className="flex justify-between">
                      <dt className="text-muted-foreground">Room charges</dt>
                      <dd className="tabular-nums">{formatAmount(quote.data.taxable_amount)}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-muted-foreground">GST ({Number(quote.data.gst_rate)}%)</dt>
                      <dd className="tabular-nums">{formatAmount(quote.data.total_tax)}</dd>
                    </div>
                    <div className="flex justify-between pt-1 text-sm font-semibold">
                      <dt>Estimated total</dt>
                      <dd className="tabular-nums">{formatAmount(quote.data.total_amount)}</dd>
                    </div>
                  </dl>
                )}
              </div>
            )}

            <Field label="Notes (optional)">
              {(field) => (
                <Textarea
                  {...field}
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  rows={2}
                  placeholder="Late arrival, extra bed, airport pickup…"
                />
              )}
            </Field>
          </DialogBody>

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <SubmitButton pending={pending} disabled={soldOut || !roomType}>
              Confirm reservation
            </SubmitButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
