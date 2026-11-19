"use client";

import { addDays, format, isSameDay } from "date-fns";
import {
  ArrowRight,
  BedDouble,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  DoorOpen,
  LoaderCircle,
  LogIn,
  LogOut,
  Wrench,
  X,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { useReservationDialogs } from "@/components/reservations/reservation-dialogs";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { fromIso, toIso, today } from "@/lib/dates";
import { useCurrentUser, usePropertyMap } from "@/lib/queries";
import { can } from "@/lib/roles";
import { SOURCE_STYLES } from "@/lib/sources";
import { type Terms, unitGroup, useTerms } from "@/lib/terminology";
import type { PropertyMapRoomType, PropertyMapUnit, TapeChartReservation, UnitStatus } from "@/lib/types";
import { cn, formatMoney } from "@/lib/utils";

const byNumber = new Intl.Collator("en", { numeric: true });

interface StatusStyle {
  label: string;
  /** The pill in the top bar. */
  dot: string;
  pill: string;
  pillActive: string;
  /** The unit card. */
  card: string;
  edge: string;
  text: string;
}

const STATUS: Record<UnitStatus, StatusStyle> = {
  available: {
    label: "Available",
    dot: "bg-emerald-500",
    pill: "border-emerald-200 bg-emerald-50 text-emerald-800 hover:bg-emerald-100",
    pillActive: "border-emerald-500 bg-emerald-100 text-emerald-900 ring-1 ring-emerald-500",
    card: "border-emerald-200 bg-emerald-50/70 hover:border-emerald-300 hover:bg-emerald-50",
    edge: "bg-emerald-500",
    text: "text-emerald-800",
  },
  occupied: {
    label: "Occupied / In-house",
    dot: "bg-blue-500",
    pill: "border-blue-200 bg-blue-50 text-blue-800 hover:bg-blue-100",
    pillActive: "border-blue-500 bg-blue-100 text-blue-900 ring-1 ring-blue-500",
    card: "border-blue-200 bg-blue-50/80 hover:border-blue-300 hover:bg-blue-50",
    edge: "bg-blue-500",
    text: "text-blue-800",
  },
  reserved: {
    label: "Reserved / Arriving",
    dot: "bg-amber-500",
    pill: "border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100",
    pillActive: "border-amber-500 bg-amber-100 text-amber-900 ring-1 ring-amber-500",
    card: "border-amber-200 bg-amber-50/80 hover:border-amber-300 hover:bg-amber-50",
    edge: "bg-amber-500",
    text: "text-amber-800",
  },
  out_of_order: {
    label: "Maintenance",
    dot: "bg-rose-400",
    pill: "border-rose-200 bg-rose-50 text-rose-800 hover:bg-rose-100",
    pillActive: "border-rose-400 bg-rose-100 text-rose-900 ring-1 ring-rose-400",
    card: "border-dashed border-slate-300 bg-slate-100/80",
    edge: "bg-rose-400",
    text: "text-slate-600",
  },
};

const STATUS_ORDER: UnitStatus[] = ["available", "occupied", "reserved", "out_of_order"];

export function PropertyMap() {
  const words = useTerms();
  const canBook = can(useCurrentUser().data?.role, "frontOffice");
  const { dialogs, openNew, openDetails } = useReservationDialogs();

  const [day, setDay] = useState(today);
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<UnitStatus | null>(null);

  const date = toIso(day);
  const isToday = isSameDay(day, today());
  const { data, isPending, isError, error, isFetching, refetch } = usePropertyMap(date);

  const roomTypes = useMemo(
    () => new Map((data?.room_types ?? []).map((roomType) => [roomType.id, roomType])),
    [data],
  );
  const ofType = useMemo(
    () => (data?.units ?? []).filter((unit) => typeFilter === "" || unit.room_type_id === typeFilter),
    [data, typeFilter],
  );
  const counts = useMemo(() => {
    const result: Record<UnitStatus, number> = { available: 0, occupied: 0, reserved: 0, out_of_order: 0 };
    for (const unit of ofType) result[unit.status] += 1;
    return result;
  }, [ofType]);
  const groups = useMemo(() => {
    const visible = ofType.filter((unit) => statusFilter === null || unit.status === statusFilter);
    const grouped = new Map<string, PropertyMapUnit[]>();
    for (const unit of [...visible].sort((a, b) => byNumber.compare(a.room_number, b.room_number))) {
      const name = unitGroup(unit, words);
      grouped.set(name, [...(grouped.get(name) ?? []), unit]);
    }
    return Array.from(grouped.entries()).sort(([a], [b]) => byNumber.compare(a, b));
  }, [ofType, statusFilter, words]);
  const unassigned = (data?.unassigned ?? []).filter(
    (stay) => typeFilter === "" || stay.room_type_id === typeFilter,
  );

  const shift = (days: number) => setDay((current) => addDays(current, days));

  return (
    <div className="space-y-4">
      {/* Top bar */}
      <section className="space-y-3.5 rounded-xl border border-border bg-card p-3.5 shadow-soft sm:p-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
          <div className="mr-auto min-w-0">
            <h2 className="flex items-center gap-2 text-[15px] font-semibold leading-tight">
              {format(day, "EEEE, d MMMM yyyy")}
              {isFetching && !isPending && (
                <LoaderCircle className="size-3.5 animate-spin text-muted-foreground" aria-label="Refreshing" />
              )}
            </h2>
            <p className="mt-0.5 text-[13px] text-muted-foreground">
              {isToday ? "Today. " : ""}What each {words.unitLower} holds on this night.
            </p>
          </div>

          <div className="flex w-full items-center gap-1.5 sm:w-auto">
            <Button variant="outline" size="icon" aria-label="Previous day" onClick={() => shift(-1)} className="shrink-0">
              <ChevronLeft className="size-4" />
            </Button>
            <div className="relative min-w-0 flex-1 sm:w-40 sm:flex-none">
              <CalendarDays className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="date"
                aria-label="Date"
                value={date}
                onChange={(event) => event.target.value && setDay(fromIso(event.target.value))}
                className="h-8 pl-8 text-[13px]"
              />
            </div>
            <Button variant="outline" size="sm" onClick={() => setDay(today())} disabled={isToday} className="shrink-0">
              Today
            </Button>
            <Button variant="outline" size="icon" aria-label="Next day" onClick={() => shift(1)} className="shrink-0">
              <ChevronRight className="size-4" />
            </Button>
          </div>

          <Select
            aria-label={`Filter by ${words.unitType.toLowerCase()}`}
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value)}
            className="h-8 w-full text-[13px] sm:w-52"
          >
            <option value="">All {words.unitTypes.toLowerCase()}</option>
            {(data?.room_types ?? []).map((roomType) => (
              <option key={roomType.id} value={roomType.id}>
                {roomType.name} · {roomType.available} of {roomType.total_rooms} free
              </option>
            ))}
          </Select>
        </div>

        <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by status">
          {STATUS_ORDER.map((status) => {
            const style = STATUS[status];
            const active = statusFilter === status;
            return (
              <button
                key={status}
                type="button"
                aria-pressed={active}
                onClick={() => setStatusFilter(active ? null : status)}
                className={cn(
                  "flex items-center gap-2 rounded-full border px-3 py-1 text-[13px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                  active ? style.pillActive : style.pill,
                )}
              >
                <span aria-hidden className={cn("size-2 rounded-full", style.dot)} />
                {style.label}
                <span className="tabular-nums opacity-80">{isPending ? "–" : counts[status]}</span>
              </button>
            );
          })}
          {statusFilter !== null && (
            <button
              type="button"
              onClick={() => setStatusFilter(null)}
              className="flex items-center gap-1 rounded-full px-2.5 py-1 text-[13px] text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <X className="size-3.5" />
              Show all
            </button>
          )}
        </div>
      </section>

      {unassigned.length > 0 && (
        <UnassignedBanner stays={unassigned} words={words} roomTypes={roomTypes} onOpen={openDetails} />
      )}

      {isError ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-border bg-card px-6 py-16 text-center shadow-soft">
          <CircleAlert className="size-6 text-destructive" />
          <p className="text-sm text-muted-foreground">{error.message}</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      ) : isPending ? (
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-[repeat(auto-fill,minmax(11.5rem,1fr))]" aria-busy="true" aria-label="Loading property map">
          {Array.from({ length: 12 }, (_, index) => (
            <div key={index} className="h-[5.5rem] animate-pulse rounded-lg border border-border bg-card" />
          ))}
        </div>
      ) : data.units.length === 0 ? (
        <div className="flex flex-col items-center rounded-xl border border-dashed border-input bg-card px-6 py-16 text-center shadow-soft">
          <BedDouble className="size-6 text-muted-foreground" strokeWidth={1.75} />
          <p className="mt-3 text-sm font-medium">No {words.unitsLower} yet</p>
          <p className="mt-1 max-w-sm text-[13px] text-muted-foreground">
            Add {words.unitTypes.toLowerCase()} and {words.unitsLower} in Settings, and they will appear here grouped by{" "}
            {words.group.toLowerCase()}.
          </p>
          <Button asChild variant="outline" size="sm" className="mt-4">
            <Link href="/settings">
              Open settings <ArrowRight className="size-3.5" />
            </Link>
          </Button>
        </div>
      ) : groups.length === 0 ? (
        <p className="rounded-xl border border-border bg-card px-6 py-10 text-center text-sm text-muted-foreground shadow-soft">
          No {words.unitsLower} match these filters.
        </p>
      ) : (
        <div className="space-y-5">
          {groups.map(([name, units]) => (
            <section key={name} aria-label={name}>
              <h3 className="mb-2 flex items-baseline gap-2 px-0.5 text-[13px] font-semibold">
                {name}
                <span className="text-xs font-normal text-muted-foreground">
                  {units.length} {units.length === 1 ? words.unitLower : words.unitsLower}
                </span>
              </h3>
              <ul className="grid grid-cols-2 gap-2.5 sm:grid-cols-[repeat(auto-fill,minmax(11.5rem,1fr))]">
                {units.map((unit) => (
                  <li key={unit.id}>
                    <UnitCard
                      unit={unit}
                      roomType={roomTypes.get(unit.room_type_id)}
                      date={date}
                      words={words}
                      canBook={canBook}
                      onBook={() => openNew({ roomTypeId: unit.room_type_id, roomId: unit.id, checkIn: date })}
                      onOpen={(id) => openDetails(id)}
                    />
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
      {dialogs}
    </div>
  );
}

function UnitCard({
  unit,
  roomType,
  date,
  words,
  canBook,
  onBook,
  onOpen,
}: {
  unit: PropertyMapUnit;
  roomType: PropertyMapRoomType | undefined;
  date: string;
  words: Terms;
  canBook: boolean;
  onBook: () => void;
  onOpen: (reservationId: string) => void;
}) {
  const style = STATUS[unit.status];
  const stay = unit.reservation;

  const body = (
    <>
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-1", style.edge)} />
      <span className="flex items-start justify-between gap-2">
        <span className="text-[15px] font-semibold leading-tight tabular-nums">{unit.room_number}</span>
        {roomType && (
          <span className="rounded bg-card/80 px-1.5 py-0.5 text-[10.5px] font-semibold tracking-wide text-muted-foreground ring-1 ring-inset ring-border">
            {roomType.code}
          </span>
        )}
      </span>
      <CardDetail unit={unit} stay={stay} roomType={roomType} date={date} style={style} />
    </>
  );
  const base = "relative flex h-full min-h-[5.5rem] w-full flex-col justify-between gap-2 overflow-hidden rounded-lg border py-2.5 pl-3.5 pr-2.5 text-left";

  if (unit.status === "out_of_order") {
    return (
      <div className={cn(base, style.card)} title={`Out of order. Put it back in service in Settings, Inventory.`}>
        {body}
      </div>
    );
  }
  const action = stay
    ? () => onOpen(stay.id)
    : canBook
      ? onBook
      : undefined;
  if (!action) return <div className={cn(base, style.card)}>{body}</div>;

  const label = stay
    ? `${words.unit} ${unit.room_number}, ${style.label}: ${stay.guest_name}. Open the reservation.`
    : `${words.unit} ${unit.room_number}, available. New reservation.`;
  return (
    <button
      type="button"
      onClick={action}
      aria-label={label}
      className={cn(
        base,
        style.card,
        "outline-none transition-[transform,box-shadow,background-color,border-color] duration-150 hover:-translate-y-px hover:shadow-lift focus-visible:ring-2 focus-visible:ring-ring",
      )}
    >
      {body}
    </button>
  );
}

function CardDetail({
  unit,
  stay,
  roomType,
  date,
  style,
}: {
  unit: PropertyMapUnit;
  stay: TapeChartReservation | null;
  roomType: PropertyMapRoomType | undefined;
  date: string;
  style: StatusStyle;
}) {
  if (unit.status === "out_of_order") {
    return (
      <span className={cn("flex items-center gap-1.5 text-xs font-medium", style.text)}>
        <Wrench className="size-3.5 text-rose-500" />
        Out of order
      </span>
    );
  }
  if (!stay) {
    return (
      <span className="block">
        <span className={cn("block text-xs font-medium", style.text)}>Available</span>
        {roomType && (
          <span className="block text-[12.5px] text-muted-foreground">
            <span className="font-medium text-foreground">{formatMoney(roomType.base_rate)}</span> / night
          </span>
        )}
      </span>
    );
  }
  if (unit.status === "occupied") {
    const dueOut = stay.check_out_date === date;
    return (
      <span className="block min-w-0">
        <span className="block truncate text-[13px] font-medium">{stay.guest_name}</span>
        <span className={cn("flex items-center gap-1 text-xs", style.text)}>
          <LogOut className="size-3" />
          {dueOut ? "Due out today" : `Out ${format(fromIso(stay.check_out_date), "d MMM")}`}
        </span>
      </span>
    );
  }
  const source = SOURCE_STYLES[stay.source];
  const arriving = stay.check_in_date === date;
  return (
    <span className="block min-w-0">
      <span className="block truncate text-[13px] font-medium">{stay.guest_name}</span>
      <span className="mt-0.5 flex min-w-0 items-center gap-1.5 text-xs">
        <span className={cn("flex shrink-0 items-center gap-1", style.text)}>
          {arriving && <LogIn className="size-3" />}
          {arriving ? "Arriving" : "Reserved"}
        </span>
        <span className="flex min-w-0 items-center gap-1 rounded-full bg-card/90 px-1.5 py-px text-[10.5px] font-medium text-foreground ring-1 ring-inset ring-border">
          <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", source.accent)} />
          <span className="truncate">{source.label}</span>
        </span>
      </span>
    </span>
  );
}

function UnassignedBanner({
  stays,
  words,
  roomTypes,
  onOpen,
}: {
  stays: TapeChartReservation[];
  words: Terms;
  roomTypes: Map<string, PropertyMapRoomType>;
  onOpen: (reservationId: string) => void;
}) {
  return (
    <section
      aria-label={`Bookings that need a ${words.unitLower}`}
      className="flex flex-col gap-2.5 rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-3 text-amber-950 sm:flex-row sm:items-center"
    >
      <p className="flex shrink-0 items-center gap-2 text-[13px] font-medium">
        <DoorOpen className="size-4 text-amber-600" />
        {stays.length} {stays.length === 1 ? "booking needs" : "bookings need"} a {words.unitLower}:
      </p>
      <ul className="flex flex-wrap gap-1.5">
        {stays.map((stay) => (
          <li key={stay.id}>
            <button
              type="button"
              onClick={() => onOpen(stay.id)}
              className="flex items-center gap-1.5 rounded-full border border-amber-300 bg-card px-2.5 py-1 text-xs font-medium outline-none transition-colors hover:bg-amber-100 focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span aria-hidden className={cn("size-1.5 rounded-full", SOURCE_STYLES[stay.source].accent)} />
              {stay.guest_name}
              <span className="text-muted-foreground">· {roomTypes.get(stay.room_type_id)?.code ?? "?"}</span>
              <span className="text-amber-700">Assign</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
