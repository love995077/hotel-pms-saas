"use client";

import { addDays, differenceInCalendarDays, format, isSameDay, isWeekend } from "date-fns";
import { ChevronDown, ChevronLeft, ChevronRight, CircleAlert, LoaderCircle, Plus } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { useReservationDialogs } from "@/components/reservations/reservation-dialogs";
import { ReservationBlock, type BlockGeometry } from "@/components/tape-chart/reservation-block";
import { Button } from "@/components/ui/button";
import { daysFrom, fromIso, toIso, today } from "@/lib/dates";
import { useCurrentUser, useTapeChart } from "@/lib/queries";
import { can } from "@/lib/roles";
import { SOURCE_STYLES } from "@/lib/sources";
import type { BookingSource, TapeChartReservation, TapeChartRoom, TapeChartRoomType } from "@/lib/types";
import { cn } from "@/lib/utils";

const LABEL_WIDTH = 188;
const MIN_DAY_WIDTH = 56;
const ROW_HEIGHT = 44;
const SPANS = [14, 21, 30] as const;

/** Where a stay sits on the visible track, or null if it is entirely outside it. */
function geometryFor(
  reservation: TapeChartReservation,
  windowStart: Date,
  days: number,
): BlockGeometry | null {
  // A stay runs from the middle of the arrival day to the middle of the
  // departure day, so a departure and an arrival can share one cell.
  const start = differenceInCalendarDays(fromIso(reservation.check_in_date), windowStart) + 0.5;
  const end = differenceInCalendarDays(fromIso(reservation.check_out_date), windowStart) + 0.5;
  const left = Math.max(start, 0);
  const right = Math.min(end, days);
  if (right <= left) return null;
  return {
    left: left / days,
    width: (right - left) / days,
    clippedStart: start < 0,
    clippedEnd: end > days,
  };
}

/** Pack overlapping stays into as few rows as possible. */
function packIntoLanes(reservations: TapeChartReservation[]): TapeChartReservation[][] {
  const lanes: TapeChartReservation[][] = [];
  const sorted = [...reservations].sort((a, b) => a.check_in_date.localeCompare(b.check_in_date));
  for (const reservation of sorted) {
    const lane = lanes.find(
      (candidate) => candidate[candidate.length - 1].check_out_date <= reservation.check_in_date,
    );
    if (lane) lane.push(reservation);
    else lanes.push([reservation]);
  }
  return lanes;
}

export function TapeChart() {
  const [windowStart, setWindowStart] = useState(() => addDays(today(), -2));
  const [span, setSpan] = useState<(typeof SPANS)[number]>(14);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const { dialogs, openNew, openDetails } = useReservationDialogs();
  const canBook = can(useCurrentUser().data?.role, "frontOffice");

  const windowEnd = addDays(windowStart, span);
  const { data, isPending, isError, error, isFetching, refetch } = useTapeChart(
    toIso(windowStart),
    toIso(windowEnd),
  );

  const days = useMemo(() => daysFrom(windowStart, span), [windowStart, span]);
  const now = today();

  const byRoom = useMemo(() => {
    const assigned = new Map<string, TapeChartReservation[]>();
    const unassigned = new Map<string, TapeChartReservation[]>();
    for (const reservation of data?.reservations ?? []) {
      const [map, key] = reservation.room_id
        ? [assigned, reservation.room_id]
        : [unassigned, reservation.room_type_id];
      map.set(key, [...(map.get(key) ?? []), reservation]);
    }
    return { assigned, unassigned };
  }, [data]);

  const sourcesInView = useMemo(() => {
    const present = new Set<BookingSource>();
    for (const reservation of data?.reservations ?? []) present.add(reservation.source);
    return (Object.keys(SOURCE_STYLES) as BookingSource[]).filter((source) => present.has(source));
  }, [data]);

  const toggleGroup = (id: string) =>
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const trackStyle = { gridTemplateColumns: `repeat(${span}, minmax(0, 1fr))` };

  // The day grid behind a row. With `onPick`, days from today onwards are
  // buttons that start a booking on that day.
  const cells = (onPick?: (day: Date) => void, label?: string) => (
    <div className="absolute inset-0 grid" style={trackStyle} aria-hidden={onPick ? undefined : true}>
      {days.map((day) => {
        const className = cn(
          "border-r border-border/70 last:border-r-0",
          isWeekend(day) && "bg-muted/45",
          isSameDay(day, now) && "bg-primary/[0.06]",
        );
        return onPick && day >= now ? (
          <button
            key={day.toISOString()}
            type="button"
            aria-label={`New reservation, ${label}, ${format(day, "d MMMM")}`}
            onClick={() => onPick(day)}
            className={cn(
              className,
              "group/cell flex items-center justify-center outline-none transition-colors hover:bg-primary/10 focus-visible:bg-primary/10 focus-visible:ring-inset focus-visible:ring-offset-0",
            )}
          >
            <Plus className="size-3.5 text-primary opacity-0 transition-opacity group-hover/cell:opacity-100 group-focus-visible/cell:opacity-100" />
          </button>
        ) : (
          <div key={day.toISOString()} className={className} />
        );
      })}
    </div>
  );

  const roomRow = (
    key: string,
    label: React.ReactNode,
    reservations: TapeChartReservation[],
    roomLabel: string,
    roomType: TapeChartRoomType,
    room: TapeChartRoom | null,
  ) => (
    <div key={key} className="group/row relative flex border-b border-border/70" style={{ height: ROW_HEIGHT }}>
      <div
        className="sticky left-0 z-20 flex shrink-0 items-center border-r border-border bg-card px-4 text-[13px] transition-colors group-hover/row:bg-accent/60"
        style={{ width: LABEL_WIDTH }}
      >
        {label}
      </div>
      <div className="relative min-w-0 flex-1 transition-colors group-hover/row:bg-accent/25">
        {cells(
          canBook
            ? (day) => openNew({ roomTypeId: roomType.id, roomId: room?.id, checkIn: toIso(day) })
            : undefined,
          room ? roomLabel : `${roomType.name}, no room assigned`,
        )}
        {reservations.map((reservation) => {
          const geometry = geometryFor(reservation, windowStart, span);
          return geometry ? (
            <ReservationBlock
              key={reservation.id}
              reservation={reservation}
              geometry={geometry}
              roomLabel={roomLabel}
              roomTypeCode={roomType.code}
              onOpen={() => openDetails(reservation.id)}
            />
          ) : null;
        })}
      </div>
    </div>
  );

  return (
    <section className="overflow-hidden rounded-xl border border-border bg-card shadow-soft">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3 border-b border-border px-4 py-3 sm:px-5">
        <div className="mr-auto min-w-0">
          <h2 className="flex items-center gap-2 text-[15px] font-semibold leading-tight">
            Tape chart
            {isFetching && !isPending && (
              <LoaderCircle className="size-3.5 animate-spin text-muted-foreground" aria-label="Refreshing" />
            )}
          </h2>
          <p className="mt-0.5 text-[13px] text-muted-foreground">
            {format(windowStart, "d MMM")} – {format(addDays(windowEnd, -1), "d MMM yyyy")}
          </p>
        </div>

        <div className="flex rounded-lg bg-muted p-0.5" role="group" aria-label="Days shown">
          {SPANS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setSpan(option)}
              aria-pressed={span === option}
              className={cn(
                "rounded-md px-2.5 py-1 text-[12.5px] font-medium transition-[background-color,color,box-shadow] duration-150",
                span === option
                  ? "bg-card text-foreground shadow-soft"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {option} days
            </button>
          ))}
        </div>

        {canBook && data && data.room_types.length > 0 && (
          <Button size="sm" onClick={() => openNew()}>
            <Plus className="size-3.5" />
            New reservation
          </Button>
        )}

        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon"
            aria-label="Previous week"
            onClick={() => setWindowStart((current) => addDays(current, -7))}
          >
            <ChevronLeft className="size-4" />
          </Button>
          <Button variant="outline" size="sm" onClick={() => setWindowStart(addDays(today(), -2))}>
            Today
          </Button>
          <Button
            variant="outline"
            size="icon"
            aria-label="Next week"
            onClick={() => setWindowStart((current) => addDays(current, 7))}
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
      </div>

      {/* Chart */}
      {isPending ? (
        <ChartSkeleton />
      ) : isError ? (
        <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
          <CircleAlert className="size-6 text-destructive" />
          <p className="text-sm text-muted-foreground">{error.message}</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      ) : data.room_types.length === 0 ? (
        <div className="px-6 py-16 text-center">
          <p className="text-sm font-medium">No rooms yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Add room types and rooms, and they will appear here.
          </p>
          <Button asChild variant="outline" size="sm" className="mt-4">
            <Link href="/settings">Set up inventory</Link>
          </Button>
        </div>
      ) : (
        <div className="scroll-slim max-h-[calc(100dvh-21rem)] min-h-[20rem] overflow-auto">
          <div style={{ minWidth: LABEL_WIDTH + span * MIN_DAY_WIDTH }}>
            {/* Date header: sticks to the top; its corner also sticks to the left. */}
            <div className="sticky top-0 z-30 flex border-b border-border bg-card">
              <div
                className="sticky left-0 z-40 flex shrink-0 items-end border-r border-border bg-card px-4 pb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground"
                style={{ width: LABEL_WIDTH }}
              >
                Room
              </div>
              <div className="grid min-w-0 flex-1" style={trackStyle}>
                {days.map((day, index) => {
                  const isToday = isSameDay(day, now);
                  return (
                    <div
                      key={day.toISOString()}
                      className={cn(
                        "flex flex-col items-center gap-0.5 border-r border-border/70 py-2 last:border-r-0",
                        isWeekend(day) && "bg-muted/45",
                        isToday && "bg-primary/[0.06]",
                      )}
                    >
                      <span
                        className={cn(
                          "text-[10.5px] font-medium uppercase tracking-wide",
                          isToday ? "text-primary" : "text-muted-foreground",
                        )}
                      >
                        {format(day, "EEE")}
                      </span>
                      <span
                        className={cn(
                          "flex size-6 items-center justify-center rounded-full text-[13px] font-semibold tabular-nums",
                          isToday && "bg-primary text-primary-foreground",
                        )}
                      >
                        {format(day, "d")}
                      </span>
                      <span className="h-3 text-[10px] leading-3 text-muted-foreground">
                        {index === 0 || day.getDate() === 1 ? format(day, "MMM") : ""}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {data.room_types.map((roomType) => {
              const isCollapsed = collapsed.has(roomType.id);
              const lanes = packIntoLanes(byRoom.unassigned.get(roomType.id) ?? []);
              return (
                <div key={roomType.id}>
                  {/* Room type row: name on the left, rooms free per night across. */}
                  <div className="relative flex border-b border-border bg-muted/60" style={{ height: 36 }}>
                    <button
                      type="button"
                      onClick={() => toggleGroup(roomType.id)}
                      aria-expanded={!isCollapsed}
                      className="sticky left-0 z-20 flex shrink-0 items-center gap-2 border-r border-border bg-muted px-3 text-left text-[13px] font-semibold outline-none hover:bg-accent focus-visible:ring-inset focus-visible:ring-offset-0"
                      style={{ width: LABEL_WIDTH }}
                    >
                      <ChevronDown
                        className={cn(
                          "size-4 shrink-0 text-muted-foreground transition-transform duration-200",
                          isCollapsed && "-rotate-90",
                        )}
                      />
                      <span className="truncate">{roomType.name}</span>
                      <span className="ml-auto rounded bg-card px-1.5 py-0.5 text-[10.5px] font-medium text-muted-foreground ring-1 ring-inset ring-border">
                        {roomType.code}
                      </span>
                    </button>
                    <div className="grid min-w-0 flex-1" style={trackStyle}>
                      {roomType.availability.map((night) => (
                        <div
                          key={night.date}
                          title={`${night.available} of ${night.total_rooms} free on ${format(fromIso(night.date), "d MMM")}`}
                          className="flex items-center justify-center border-r border-border/70 last:border-r-0"
                        >
                          <span
                            className={cn(
                              "min-w-6 rounded-full px-1.5 py-0.5 text-center text-[11px] font-semibold tabular-nums",
                              night.available <= 0
                                ? "bg-rose-100 text-rose-700"
                                : night.available / Math.max(night.total_rooms, 1) <= 0.25
                                  ? "bg-amber-100 text-amber-800"
                                  : "text-muted-foreground",
                            )}
                          >
                            {Math.max(night.available, 0)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {!isCollapsed && (
                    <>
                      {roomType.rooms.map((room) =>
                        roomRow(
                          room.id,
                          <>
                            <span className="font-medium tabular-nums">{room.room_number}</span>
                            {room.floor && (
                              <span className="ml-2 text-xs text-muted-foreground">Floor {room.floor}</span>
                            )}
                          </>,
                          byRoom.assigned.get(room.id) ?? [],
                          `Room ${room.room_number}`,
                          roomType,
                          room,
                        ),
                      )}
                      {lanes.map((lane, index) =>
                        roomRow(
                          `${roomType.id}-unassigned-${index}`,
                          index === 0 ? (
                            <span className="rounded border border-dashed border-input px-1.5 py-0.5 text-xs text-muted-foreground">
                              Unassigned
                            </span>
                          ) : null,
                          lane,
                          "No room assigned yet",
                          roomType,
                          null,
                        ),
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Legend */}
      {sourcesInView.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border bg-muted/40 px-4 py-2.5 text-xs text-muted-foreground sm:px-5">
          {sourcesInView.map((source) => (
            <span key={source} className="flex items-center gap-1.5">
              <span aria-hidden className={cn("size-2.5 rounded-[3px]", SOURCE_STYLES[source].accent)} />
              {SOURCE_STYLES[source].label}
            </span>
          ))}
          <span className="ml-auto flex items-center gap-1.5">
            <span aria-hidden className="size-1.5 rounded-full bg-emerald-500" />
            In house
          </span>
        </div>
      )}
      {dialogs}
    </section>
  );
}

function ChartSkeleton() {
  return (
    <div className="space-y-px p-4" aria-busy="true" aria-label="Loading tape chart">
      {Array.from({ length: 8 }, (_, index) => (
        <div key={index} className="flex items-center gap-3 py-1.5">
          <div className="h-7 w-40 animate-pulse rounded-md bg-muted" />
          <div
            className="h-7 animate-pulse rounded-md bg-muted"
            style={{ width: `${30 + ((index * 37) % 55)}%`, animationDelay: `${index * 60}ms` }}
          />
        </div>
      ))}
    </div>
  );
}
