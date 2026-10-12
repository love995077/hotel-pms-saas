"use client";

import { Building2, ChevronRight, CircleAlert, MapPin, Search, UserPlus, Users } from "lucide-react";
import { useEffect, useState } from "react";

import { GuestDialog } from "@/components/guests/guest-dialog";
import { useReservationDialogs } from "@/components/reservations/reservation-dialogs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCurrentUser, useGuests } from "@/lib/queries";
import { can } from "@/lib/roles";
import type { Guest } from "@/lib/types";
import { initials } from "@/lib/utils";

export default function GuestsPage() {
  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  // undefined: closed. null: adding a new guest.
  const [selected, setSelected] = useState<Guest | null | undefined>(undefined);
  const canEdit = can(useCurrentUser().data?.role, "frontOffice");
  const { dialogs, openDetails } = useReservationDialogs();

  // Wait for a pause in typing before asking the server.
  useEffect(() => {
    const timer = setTimeout(() => setSearch(input.trim()), 250);
    return () => clearTimeout(timer);
  }, [input]);

  const { data, isPending, isError, error, refetch } = useGuests(search);

  return (
    <div className="mx-auto max-w-[1600px]">
      <section className="overflow-hidden rounded-xl border border-border bg-card shadow-soft">
        <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3 sm:px-5">
          <div className="mr-auto">
            <h2 className="text-[15px] font-semibold leading-tight">Guests</h2>
            <p className="mt-0.5 text-[13px] text-muted-foreground">
              {data && !search
                ? `${data.length}${data.length === 200 ? "+" : ""} guest profile${data.length === 1 ? "" : "s"} at this hotel`
                : "Everyone who has a profile at this hotel"}
            </p>
          </div>
          <div className="relative w-full sm:w-72">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Name, email or phone"
              aria-label="Search guests"
              className="h-9 pl-9"
            />
          </div>
          {canEdit && (
            <Button size="sm" className="h-9" onClick={() => setSelected(null)}>
              <UserPlus className="size-3.5" />
              Add guest
            </Button>
          )}
        </div>

        {isPending ? (
          <div className="space-y-3 p-5" aria-busy="true" aria-label="Loading guests">
            {Array.from({ length: 8 }, (_, index) => (
              <div key={index} className="h-9 animate-pulse rounded-md bg-muted" />
            ))}
          </div>
        ) : isError ? (
          <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
            <CircleAlert className="size-6 text-destructive" />
            <p className="text-sm text-muted-foreground">{error.message}</p>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              Try again
            </Button>
          </div>
        ) : data.length === 0 ? (
          <div className="flex flex-col items-center px-6 py-16 text-center">
            <span className="flex size-12 items-center justify-center rounded-xl bg-accent text-accent-foreground">
              <Users className="size-6" strokeWidth={1.75} />
            </span>
            <p className="mt-4 text-sm font-medium">{search ? "No guests match that search" : "No guests yet"}</p>
            <p className="mt-1 max-w-xs text-sm text-muted-foreground">
              {search
                ? "Try a different name, email or phone number."
                : "Guests are added here when you take a booking, or you can add one now."}
            </p>
            {canEdit && !search && (
              <Button className="mt-5" onClick={() => setSelected(null)}>
                <UserPlus className="size-4" />
                Add guest
              </Button>
            )}
          </div>
        ) : (
          <ul className="divide-y divide-border/70">
            {data.map((guest) => {
              const name = `${guest.first_name} ${guest.last_name}`;
              const place = [guest.city, guest.country].filter(Boolean).join(", ");
              return (
                <li key={guest.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(guest)}
                    className="group flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-accent/40 focus-visible:ring-inset focus-visible:ring-offset-0 sm:px-5"
                  >
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-semibold text-accent-foreground">
                      {initials(name)}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{name}</span>
                      <span className="block truncate text-[13px] text-muted-foreground">
                        {[guest.phone, guest.email].filter(Boolean).join(" · ") || "No contact details"}
                      </span>
                    </span>
                    {guest.company_name && (
                      <span className="hidden min-w-0 max-w-[14rem] items-center gap-1.5 text-[13px] text-muted-foreground md:flex">
                        <Building2 className="size-3.5 shrink-0" />
                        <span className="truncate">{guest.company_name}</span>
                      </span>
                    )}
                    {place && (
                      <span className="hidden w-44 min-w-0 items-center gap-1.5 text-[13px] text-muted-foreground lg:flex">
                        <MapPin className="size-3.5 shrink-0" />
                        <span className="truncate">{place}</span>
                      </span>
                    )}
                    <ChevronRight className="size-4 shrink-0 text-muted-foreground/50 transition-transform group-hover:translate-x-0.5 group-hover:text-muted-foreground" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {selected !== undefined && (
        <GuestDialog
          key={selected?.id ?? "new"}
          guest={selected}
          canEdit={canEdit}
          onClose={() => setSelected(undefined)}
          onOpenReservation={(reservationId) => {
            setSelected(undefined);
            openDetails(reservationId);
          }}
        />
      )}
      {dialogs}
    </div>
  );
}
