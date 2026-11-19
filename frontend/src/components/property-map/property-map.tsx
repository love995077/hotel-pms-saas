"use client";

import { addDays, format, isSameDay } from "date-fns";
import {
  ArrowRight,
  BedDouble,
  Building2,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  DoorOpen,
  Layers,
  LoaderCircle,
  LogIn,
  LogOut,
  MapPin,
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
import { compareGroups, kindTerms, unitGroup, useTerms } from "@/lib/terminology";
import type { PropertyMapRoomType, PropertyMapUnit, TapeChartReservation, UnitStatus } from "@/lib/types";
import { cn, formatMoney } from "@/lib/utils";

const byNumber = new Intl.Collator("en", { numeric: true });

interface StatusStyle {
  label: string;
  dot: string;
  pill: string;
  pillActive: string;
  /** The bold bar along the top of a tile, and its segment in a floor's occupancy bar. */
  bar: string;
  tile: string;
  icon: string;
  chip: string;
  text: string;
}

const STATUS: Record<UnitStatus, StatusStyle> = {
  available: {
    label: "Available",
    dot: "bg-emerald-500",
    pill: "border-emerald-200 bg-emerald-50 text-emerald-800 hover:bg-emerald-100",
    pillActive: "border-emerald-500 bg-emerald-100 text-emerald-900 ring-1 ring-emerald-500",
    bar: "bg-emerald-500",
    tile: "border-emerald-200/80 bg-white hover:border-emerald-300",
    icon: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    chip: "bg-emerald-50 text-emerald-800 ring-emerald-200",
    text: "text-emerald-800",
  },
  occupied: {
    label: "Occupied / In-house",
    dot: "bg-blue-500",
    pill: "border-blue-200 bg-blue-50 text-blue-800 hover:bg-blue-100",
    pillActive: "border-blue-500 bg-blue-100 text-blue-900 ring-1 ring-blue-500",
    bar: "bg-blue-500",
    tile: "border-blue-200 bg-blue-50/60 hover:border-blue-300",
    icon: "bg-blue-100 text-blue-700 ring-blue-200",
    chip: "bg-blue-100 text-blue-800 ring-blue-200",
    text: "text-blue-800",
  },
  reserved: {
    label: "Reserved / Arriving",
    dot: "bg-amber-500",
    pill: "border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100",
    pillActive: "border-amber-500 bg-amber-100 text-amber-900 ring-1 ring-amber-500",
    bar: "bg-amber-500",
    tile: "border-amber-200 bg-amber-50/60 hover:border-amber-300",
    icon: "bg-amber-100 text-amber-700 ring-amber-200",
    chip: "bg-amber-100 text-amber-800 ring-amber-200",
    text: "text-amber-800",
  },
  out_of_order: {
    label: "Maintenance",
    dot: "bg-rose-500",
    pill: "border-rose-200 bg-rose-50 text-rose-800 hover:bg-rose-100",
    pillActive: "border-rose-500 bg-rose-100 text-rose-900 ring-1 ring-rose-500",
    bar: "bg-rose-500",
    tile: "border-dashed border-slate-300 bg-slate-50",
    icon: "bg-slate-100 text-slate-500 ring-slate-200",
    chip: "bg-rose-50 text-rose-700 ring-rose-200",
    text: "text-slate-600",
  },
};

const STATUS_ORDER: UnitStatus[] = ["available", "occupied", "reserved", "out_of_order"];

/** The architectural dot grid inside a floor, drawn from a theme token. */
const FLOOR_PLAN_GRID: React.CSSProperties = {
  backgroundImage: "radial-gradient(rgb(var(--input)) 1px, transparent 1px)",
  backgroundSize: "16px 16px",
};

function emptyCounts(): Record<UnitStatus, number> {
  return { available: 0, occupied: 0, reserved: 0, out_of_order: 0 };
}

export function PropertyMap() {
  const words = useTerms();
  const canBook = can(useCurrentUser().data?.role, "frontOffice");
  const { dialogs, openNew, openDetails } = useReservationDialogs();

  const [day, setDay] = useState(today);
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<UnitStatus | null>(null);
  const [floorFilter, setFloorFilter] = useState<string | null>(null);

  const date = toIso(day);
  const isToday = isSameDay(day, today());
  const { data, isPending, isError, error, isFetching, refetch } = usePropertyMap(date);

  const roomTypes = useMemo(
    () => new Map((data?.room_types ?? []).map((roomType) => [roomType.id, roomType])),
    [data],
  );

  // Every floor of the chosen unit type, in building order, whatever the other filters.
  const floors = useMemo(() => {
    const grouped = new Map<string, PropertyMapUnit[]>();
    for (const unit of data?.units ?? []) {
      if (typeFilter !== "" && unit.room_type_id !== typeFilter) continue;
      const name = unitGroup(unit);
      grouped.set(name, [...(grouped.get(name) ?? []), unit]);
    }
    return Array.from(grouped.entries())
      .sort(([a], [b]) => compareGroups(a, b))
      .map(([name, units]) => ({
        name,
        units: [...units].sort((a, b) => byNumber.compare(a.room_number, b.room_number)),
      }));
  }, [data, typeFilter]);

  // A floor that no longer exists (another date, another type) falls back to all floors.
  const activeFloor = floorFilter !== null && floors.some((floor) => floor.name === floorFilter) ? floorFilter : null;
  const inScope = floors.filter((floor) => activeFloor === null || floor.name === activeFloor);
  const counts = emptyCounts();
  for (const floor of inScope) for (const unit of floor.units) counts[unit.status] += 1;
  const visible = inScope
    .map((floor) => ({ ...floor, shown: floor.units.filter((unit) => statusFilter === null || unit.status === statusFilter) }))
    .filter((floor) => floor.shown.length > 0);
  const unassigned = (data?.unassigned ?? []).filter((stay) => typeFilter === "" || stay.room_type_id === typeFilter);
  const totalUnits = floors.reduce((sum, floor) => sum + floor.units.length, 0);

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
              {isToday ? "Today. " : ""}Who is where on this night, floor by floor.
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
            className="h-8 w-full text-[13px] sm:w-56"
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

        {floors.length > 1 && (
          <div className="-mx-3.5 border-t border-border px-3.5 pt-3 sm:-mx-4 sm:px-4">
            <div role="tablist" aria-label="Jump to a floor or zone" className="scroll-slim flex gap-1.5 overflow-x-auto pb-0.5">
              <FloorTab active={activeFloor === null} onClick={() => setFloorFilter(null)} count={totalUnits}>
                <Building2 className="size-3.5" />
                All floors
              </FloorTab>
              {floors.map((floor) => (
                <FloorTab
                  key={floor.name}
                  active={activeFloor === floor.name}
                  onClick={() => setFloorFilter(floor.name)}
                  count={floor.units.length}
                >
                  {floor.name}
                </FloorTab>
              ))}
            </div>
          </div>
        )}
      </section>

      {unassigned.length > 0 && <UnassignedBanner stays={unassigned} roomTypes={roomTypes} onOpen={openDetails} />}

      {isError ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-border bg-card px-6 py-16 text-center shadow-soft">
          <CircleAlert className="size-6 text-destructive" />
          <p className="text-sm text-muted-foreground">{error.message}</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      ) : isPending ? (
        <div className="space-y-4" aria-busy="true" aria-label="Loading property map">
          {Array.from({ length: 2 }, (_, index) => (
            <div key={index} className="h-56 animate-pulse rounded-xl border border-border bg-card" />
          ))}
        </div>
      ) : data.units.length === 0 ? (
        <div className="flex flex-col items-center rounded-xl border border-dashed border-input bg-card px-6 py-16 text-center shadow-soft">
          <BedDouble className="size-6 text-muted-foreground" strokeWidth={1.75} />
          <p className="mt-3 text-sm font-medium">No {words.unitsLower} yet</p>
          <p className="mt-1 max-w-sm text-[13px] text-muted-foreground">
            Add {words.unitTypes.toLowerCase()} and {words.unitsLower} in Settings, and they will appear here floor by
            floor.
          </p>
          <Button asChild variant="outline" size="sm" className="mt-4">
            <Link href="/settings">
              Open settings <ArrowRight className="size-3.5" />
            </Link>
          </Button>
        </div>
      ) : visible.length === 0 ? (
        <p className="rounded-xl border border-border bg-card px-6 py-10 text-center text-sm text-muted-foreground shadow-soft">
          No {words.unitsLower} match these filters.
        </p>
      ) : (
        <div className="space-y-5">
          {visible.map((floor) => (
            <FloorWing
              key={floor.name}
              name={floor.name}
              units={floor.units}
              shown={floor.shown}
              roomTypes={roomTypes}
              date={date}
              canBook={canBook}
              onBook={(unit) => openNew({ roomTypeId: unit.room_type_id, roomId: unit.id, checkIn: date })}
              onOpen={openDetails}
            />
          ))}
        </div>
      )}
      {dialogs}
    </div>
  );
}

function FloorTab({
  active,
  onClick,
  count,
  children,
}: {
  active: boolean;
  onClick: () => void;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 py-1.5 text-[13px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
        active
          ? "bg-primary text-primary-foreground shadow-soft"
          : "bg-muted text-muted-foreground hover:bg-accent hover:text-foreground",
      )}
    >
      {children}
      <span className={cn("tabular-nums", active ? "text-primary-foreground/75" : "text-muted-foreground/80")}>
        {count}
      </span>
    </button>
  );
}

/** One floor or zone, drawn as a blueprint: header bar with occupancy, units on a dot grid. */
function FloorWing({
  name,
  units,
  shown,
  roomTypes,
  date,
  canBook,
  onBook,
  onOpen,
}: {
  name: string;
  units: PropertyMapUnit[];
  shown: PropertyMapUnit[];
  roomTypes: Map<string, PropertyMapRoomType>;
  date: string;
  canBook: boolean;
  onBook: (unit: PropertyMapUnit) => void;
  onOpen: (reservationId: string) => void;
}) {
  const counts = emptyCounts();
  for (const unit of units) counts[unit.status] += 1;
  const isFloor = name === "Ground floor" || /^Floor \d+$/.test(name);
  const Icon = isFloor ? Layers : MapPin;
  // Counted per kind, so a mixed floor reads "3 rooms · 6 beds".
  const perKind = new Map<string, { one: string; many: string; count: number }>();
  for (const unit of units) {
    const kind = kindTerms(roomTypes.get(unit.room_type_id)?.unit_kind);
    const entry = perKind.get(kind.unit) ?? { one: kind.unitLower, many: kind.unitsLower, count: 0 };
    entry.count += 1;
    perKind.set(kind.unit, entry);
  }
  const summary = Array.from(perKind.values())
    .map((entry) => `${entry.count} ${entry.count === 1 ? entry.one : entry.many}`)
    .join(" · ");

  return (
    <section aria-label={name} className="overflow-hidden rounded-xl border border-border bg-card shadow-soft">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2.5 border-b border-border bg-muted/60 px-3.5 py-3 sm:px-4">
        <div className="mr-auto flex min-w-0 items-center gap-2.5">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-soft">
            <Icon className="size-[18px]" strokeWidth={1.75} />
          </span>
          <div className="min-w-0">
            <h3 className="truncate text-[15px] font-semibold leading-tight">{name}</h3>
            <p className="text-xs text-muted-foreground">
              {summary}
              {counts.available > 0 && ` · ${counts.available} available`}
            </p>
          </div>
        </div>
        <OccupancyBar counts={counts} total={units.length} />
      </header>

      <div className="p-3 sm:p-4" style={FLOOR_PLAN_GRID}>
        <ul className="grid grid-cols-2 gap-2.5 sm:grid-cols-[repeat(auto-fill,minmax(12.5rem,1fr))] sm:gap-3">
          {shown.map((unit) => (
            <li key={unit.id}>
              <UnitTile
                unit={unit}
                roomType={roomTypes.get(unit.room_type_id)}
                date={date}
                canBook={canBook}
                onBook={() => onBook(unit)}
                onOpen={onOpen}
              />
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function OccupancyBar({ counts, total }: { counts: Record<UnitStatus, number>; total: number }) {
  const segments: UnitStatus[] = ["occupied", "reserved", "out_of_order", "available"];
  return (
    <div className="flex w-full items-center gap-3 sm:w-auto">
      <div className="min-w-0 flex-1 sm:w-40 sm:flex-none">
        <div
          className="flex h-2 overflow-hidden rounded-full bg-muted ring-1 ring-inset ring-border"
          role="img"
          aria-label={`${counts.occupied} occupied, ${counts.reserved} reserved, ${counts.out_of_order} out of order, ${counts.available} available`}
        >
          {segments.map((status) =>
            counts[status] > 0 ? (
              <span
                key={status}
                className={cn("h-full", STATUS[status].bar, status === "available" && "opacity-35")}
                style={{ width: `${(counts[status] / Math.max(total, 1)) * 100}%` }}
              />
            ) : null,
          )}
        </div>
      </div>
      <span className="shrink-0 rounded-full bg-card px-2.5 py-0.5 text-xs font-semibold tabular-nums ring-1 ring-inset ring-border">
        {counts.occupied} / {total} occupied
        {counts.reserved > 0 && <span className="font-medium text-amber-700"> · {counts.reserved} reserved</span>}
      </span>
    </div>
  );
}

function statusChip(unit: PropertyMapUnit, date: string): string {
  if (unit.status === "out_of_order") return "Out of order";
  if (unit.status === "occupied") return unit.reservation?.check_out_date === date ? "Due out" : "In-house";
  if (unit.status === "reserved") return unit.reservation?.check_in_date === date ? "Arriving" : "Reserved";
  return "Available";
}

function UnitTile({
  unit,
  roomType,
  date,
  canBook,
  onBook,
  onOpen,
}: {
  unit: PropertyMapUnit;
  roomType: PropertyMapRoomType | undefined;
  date: string;
  canBook: boolean;
  onBook: () => void;
  onOpen: (reservationId: string) => void;
}) {
  const style = STATUS[unit.status];
  const kind = kindTerms(roomType?.unit_kind);
  const KindIcon = unit.status === "out_of_order" ? Wrench : kind.icon;
  const stay = unit.reservation;
  const chip = statusChip(unit, date);

  const body = (
    <>
      <span aria-hidden className={cn("absolute inset-x-0 top-0 h-1.5", style.bar)} />
      <span className="flex items-start gap-2.5">
        <span
          className={cn("flex size-9 shrink-0 items-center justify-center rounded-lg ring-1 ring-inset", style.icon)}
          title={kind.label}
        >
          <KindIcon className="size-[18px]" strokeWidth={1.75} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-xl font-bold leading-none tracking-tight tabular-nums">{unit.room_number}</span>
          <span className="mt-1 block truncate text-[11px] text-muted-foreground">{kind.unit}</span>
        </span>
        {roomType && (
          <span className="shrink-0 rounded-md bg-card px-1.5 py-0.5 text-[10.5px] font-semibold tracking-wide text-muted-foreground ring-1 ring-inset ring-border">
            {roomType.code}
          </span>
        )}
      </span>

      <span className="flex min-w-0 flex-col gap-1.5">
        <span
          className={cn(
            "inline-flex w-fit items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset",
            style.chip,
          )}
        >
          <span aria-hidden className={cn("size-1.5 rounded-full", style.dot)} />
          {chip}
        </span>
        <TileDetail unit={unit} stay={stay} roomType={roomType} date={date} style={style} />
      </span>
    </>
  );
  const base =
    "relative flex h-full min-h-[8.25rem] w-full flex-col justify-between gap-3 overflow-hidden rounded-xl border px-3 pb-3 pt-4 text-left shadow-[0_1px_2px_rgb(26_33_55/0.06)]";

  if (unit.status === "out_of_order") {
    return (
      <div className={cn(base, style.tile)} title="Out of order. Put it back in service in Settings, Inventory.">
        {body}
      </div>
    );
  }
  const action = stay ? () => onOpen(stay.id) : canBook ? onBook : undefined;
  if (!action) return <div className={cn(base, style.tile)}>{body}</div>;

  const label = stay
    ? `${kind.unit} ${unit.room_number}, ${chip}: ${stay.guest_name}. Open the reservation.`
    : `${kind.unit} ${unit.room_number}, available. New reservation.`;
  return (
    <button
      type="button"
      onClick={action}
      aria-label={label}
      className={cn(
        base,
        style.tile,
        "outline-none transition-[transform,box-shadow,border-color] duration-150 hover:-translate-y-0.5 hover:shadow-lift focus-visible:ring-2 focus-visible:ring-ring",
      )}
    >
      {body}
    </button>
  );
}

function TileDetail({
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
    return <span className={cn("block text-[12.5px]", style.text)}>Under maintenance</span>;
  }
  if (!stay) {
    return roomType ? (
      <span className="block text-[13px] text-muted-foreground">
        <span className="font-semibold text-foreground">{formatMoney(roomType.base_rate)}</span> / night
      </span>
    ) : null;
  }
  if (unit.status === "occupied") {
    const dueOut = stay.check_out_date === date;
    return (
      <span className="block min-w-0">
        <span className="block truncate text-[13.5px] font-semibold">{stay.guest_name}</span>
        <span className={cn("mt-0.5 flex items-center gap-1 text-xs", style.text)}>
          <LogOut className="size-3" />
          {dueOut ? "Checks out today" : `Out ${format(fromIso(stay.check_out_date), "d MMM")}`}
        </span>
      </span>
    );
  }
  const source = SOURCE_STYLES[stay.source];
  const arriving = stay.check_in_date === date;
  return (
    <span className="block min-w-0">
      <span className="block truncate text-[13.5px] font-semibold">{stay.guest_name}</span>
      <span className="mt-0.5 flex min-w-0 items-center gap-1.5 text-xs">
        {arriving ? (
          <LogIn className={cn("size-3 shrink-0", style.text)} />
        ) : (
          <span className={cn("shrink-0", style.text)}>to {format(fromIso(stay.check_out_date), "d MMM")}</span>
        )}
        <span className="flex min-w-0 items-center gap-1 rounded-full bg-card px-1.5 py-px text-[10.5px] font-medium text-foreground ring-1 ring-inset ring-border">
          <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", source.accent)} />
          <span className="truncate">{source.label}</span>
        </span>
      </span>
    </span>
  );
}

function UnassignedBanner({
  stays,
  roomTypes,
  onOpen,
}: {
  stays: TapeChartReservation[];
  roomTypes: Map<string, PropertyMapRoomType>;
  onOpen: (reservationId: string) => void;
}) {
  return (
    <section
      aria-label="Bookings that need a unit assigned"
      className="flex flex-col gap-2.5 rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-3 text-amber-950 sm:flex-row sm:items-center"
    >
      <p className="flex shrink-0 items-center gap-2 text-[13px] font-medium">
        <DoorOpen className="size-4 text-amber-600" />
        {stays.length} {stays.length === 1 ? "booking needs" : "bookings need"} assigning:
      </p>
      <ul className="flex flex-wrap gap-1.5">
        {stays.map((stay) => {
          const roomType = roomTypes.get(stay.room_type_id);
          return (
            <li key={stay.id}>
              <button
                type="button"
                onClick={() => onOpen(stay.id)}
                className="flex items-center gap-1.5 rounded-full border border-amber-300 bg-card px-2.5 py-1 text-xs font-medium outline-none transition-colors hover:bg-amber-100 focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span aria-hidden className={cn("size-1.5 rounded-full", SOURCE_STYLES[stay.source].accent)} />
                {stay.guest_name}
                <span className="text-muted-foreground">· {roomType?.code ?? "?"}</span>
                <span className="text-amber-700">Assign {kindTerms(roomType?.unit_kind).unitLower}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
