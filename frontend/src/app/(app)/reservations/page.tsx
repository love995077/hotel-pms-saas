"use client";

import { addDays } from "date-fns";
import { CircleAlert, Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { useReservationDialogs } from "@/components/reservations/reservation-dialogs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatStay, nightsBetween, toIso, today } from "@/lib/dates";
import { useCurrentUser, useTapeChart } from "@/lib/queries";
import { can } from "@/lib/roles";
import { SOURCE_STYLES, STATUS_CHIP, STATUS_LABELS } from "@/lib/sources";
import { cn, formatMoney } from "@/lib/utils";

export default function ReservationsPage() {
  const [search, setSearch] = useState("");
  const now = today();
  const { dialogs, openNew, openDetails } = useReservationDialogs();
  const canBook = can(useCurrentUser().data?.role, "frontOffice");
  const { data, isPending, isError, error, refetch } = useTapeChart(
    toIso(addDays(now, -30)),
    toIso(addDays(now, 90)),
    true,
  );

  const roomTypes = useMemo(
    () => new Map((data?.room_types ?? []).map((roomType) => [roomType.id, roomType])),
    [data],
  );
  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (data?.reservations ?? []).filter(
      (reservation) =>
        needle === "" ||
        reservation.guest_name.toLowerCase().includes(needle) ||
        reservation.confirmation_number.toLowerCase().includes(needle),
    );
  }, [data, search]);

  return (
    <div className="mx-auto max-w-[1600px]">
      <section className="overflow-hidden rounded-xl border border-border bg-card shadow-soft">
        <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3 sm:px-5">
          <div className="mr-auto">
            <h2 className="text-[15px] font-semibold leading-tight">Reservations</h2>
            <p className="mt-0.5 text-[13px] text-muted-foreground">
              Stays from the last 30 days to the next 90
            </p>
          </div>
          <div className="relative w-full sm:w-72">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Guest or confirmation number"
              aria-label="Search reservations"
              className="h-9 pl-9"
            />
          </div>
          {canBook && (
            <Button size="sm" className="h-9" onClick={() => openNew()}>
              <Plus className="size-3.5" />
              New reservation
            </Button>
          )}
        </div>

        {isPending ? (
          <TableSkeleton />
        ) : isError ? (
          <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
            <CircleAlert className="size-6 text-destructive" />
            <p className="text-sm text-muted-foreground">{error.message}</p>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              Try again
            </Button>
          </div>
        ) : rows.length === 0 ? (
          <p className="px-6 py-16 text-center text-sm text-muted-foreground">
            {search ? "No reservations match that search." : "No reservations in this period."}
          </p>
        ) : (
          <div className="scroll-slim overflow-x-auto">
            <table className="w-full min-w-[820px] text-left text-[13px]">
              <thead className="text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
                <tr className="border-b border-border">
                  {["Confirmation", "Guest", "Room", "Stay", "Source", "Status"].map((heading) => (
                    <th key={heading} className="px-4 py-2.5 font-medium sm:px-5">
                      {heading}
                    </th>
                  ))}
                  <th className="px-4 py-2.5 text-right font-medium sm:px-5">Rate / night</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((reservation) => {
                  const roomType = roomTypes.get(reservation.room_type_id);
                  const room = roomType?.rooms.find((r) => r.id === reservation.room_id);
                  const nights = nightsBetween(reservation.check_in_date, reservation.check_out_date);
                  const source = SOURCE_STYLES[reservation.source];
                  return (
                    <tr
                      key={reservation.id}
                      onClick={() => openDetails(reservation.id)}
                      className="cursor-pointer border-b border-border/70 transition-colors last:border-b-0 hover:bg-accent/40"
                    >
                      <td className="px-4 py-3 font-mono text-xs tracking-wide sm:px-5">
                        {/* The button makes the row reachable by keyboard; the row click is for the mouse. */}
                        <button
                          type="button"
                          aria-label={`Open reservation ${reservation.confirmation_number}, ${reservation.guest_name}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            openDetails(reservation.id);
                          }}
                          className="rounded-sm hover:text-primary"
                        >
                          {reservation.confirmation_number}
                        </button>
                      </td>
                      <td className="px-4 py-3 font-medium sm:px-5">{reservation.guest_name}</td>
                      <td className="px-4 py-3 sm:px-5">
                        {room ? room.room_number : <span className="text-muted-foreground">Unassigned</span>}
                        <span className="text-muted-foreground"> · {roomType?.code ?? "—"}</span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 sm:px-5">
                        {formatStay(reservation.check_in_date, reservation.check_out_date)}
                        <span className="text-muted-foreground">
                          {" "}
                          · {nights} night{nights === 1 ? "" : "s"}
                        </span>
                      </td>
                      <td className="px-4 py-3 sm:px-5">
                        <span className="flex items-center gap-2">
                          <span aria-hidden className={cn("size-2 rounded-full", source.accent)} />
                          {source.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 sm:px-5">
                        <span
                          className={cn(
                            "rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset",
                            STATUS_CHIP[reservation.status],
                          )}
                        >
                          {STATUS_LABELS[reservation.status]}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums sm:px-5">
                        {formatMoney(reservation.rate_per_night)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {dialogs}
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="space-y-3 p-5" aria-busy="true" aria-label="Loading reservations">
      {Array.from({ length: 8 }, (_, index) => (
        <div key={index} className="h-6 animate-pulse rounded-md bg-muted" />
      ))}
    </div>
  );
}
