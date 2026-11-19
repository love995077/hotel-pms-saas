"use client";

import { format } from "date-fns";
import { BedDouble, CalendarDays, DoorOpen, IndianRupee, Users } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatStay, fromIso, nightsBetween } from "@/lib/dates";
import { SOURCE_STYLES, STATUS_CHIP, STATUS_LABELS } from "@/lib/sources";
import type { TapeChartReservation } from "@/lib/types";
import { cn, formatMoney } from "@/lib/utils";

export interface BlockGeometry {
  /** Position and size as fractions (0-1) of the visible date track, on whole night columns. */
  left: number;
  width: number;
  /** Nights of the stay inside the visible window. */
  visibleNights: number;
  /** The stay starts before / ends after the visible window. */
  clippedStart: boolean;
  clippedEnd: boolean;
}

/** Gap between a card and its column edges, so back-to-back stays read as two cards. */
const INSET = 3;

interface ReservationBlockProps {
  reservation: TapeChartReservation;
  geometry: BlockGeometry;
  roomLabel: string;
  roomTypeCode: string;
  /** Shown on the unassigned row: the stay still needs a room number. */
  unassigned?: boolean;
  /** The property's word for a unit, mid-sentence: "room", "bed". */
  unitLower?: string;
  onOpen: () => void;
}

export function ReservationBlock({
  reservation,
  geometry,
  roomLabel,
  roomTypeCode,
  unassigned = false,
  unitLower = "room",
  onOpen,
}: ReservationBlockProps) {
  const source = SOURCE_STYLES[reservation.source];
  // Only a stay that will still arrive needs a room; a cancelled one does not.
  const needsRoom = unassigned && reservation.status === "confirmed";
  const nights = nightsBetween(reservation.check_in_date, reservation.check_out_date);
  const guests =
    `${reservation.adults} adult${reservation.adults === 1 ? "" : "s"}` +
    (reservation.children > 0
      ? `, ${reservation.children} child${reservation.children === 1 ? "" : "ren"}`
      : "");

  // A clipped side runs to the edge of the track, showing the stay continues.
  const insetLeft = geometry.clippedStart ? 0 : INSET;
  const insetRight = geometry.clippedEnd ? 0 : INSET;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onOpen}
          aria-label={`${reservation.guest_name}, ${formatStay(reservation.check_in_date, reservation.check_out_date)}, ${source.label}, ${STATUS_LABELS[reservation.status]}${needsRoom ? `, needs a ${unitLower}: open to assign one` : ""}`}
          style={{
            left: `calc(${geometry.left * 100}% + ${insetLeft}px)`,
            width: `calc(${geometry.width * 100}% - ${insetLeft + insetRight}px)`,
          }}
          className="group/block absolute inset-y-[5px] z-10 min-w-0 outline-none focus-visible:z-20 focus-visible:ring-0"
        >
          <span
            className={cn(
              "relative flex h-full min-w-0 items-center gap-1.5 overflow-hidden border pl-2.5 pr-1.5 text-left",
              "shadow-[0_1px_2px_rgb(15_23_42/0.08),0_1px_1px_rgb(15_23_42/0.04)]",
              "transition-[transform,box-shadow,background-color] duration-150 ease-out",
              "group-hover/block:-translate-y-px group-hover/block:shadow-lift",
              "group-focus-visible/block:ring-2 group-focus-visible/block:ring-ring",
              source.block,
              geometry.clippedStart ? "border-l-0 pl-2" : "rounded-l-md",
              geometry.clippedEnd ? "border-r-0" : "rounded-r-md",
              reservation.status === "checked_out" && "opacity-60 saturate-50",
              (reservation.status === "cancelled" || reservation.status === "no_show") &&
                "border-dashed opacity-50",
            )}
          >
            {!geometry.clippedStart && (
              <span aria-hidden className={cn("absolute inset-y-0 left-0 w-[3px]", source.accent)} />
            )}
            <span className="flex min-w-0 flex-1 flex-col justify-center leading-tight">
              <span className="flex min-w-0 items-center gap-1">
                {reservation.status === "checked_in" && (
                  <span
                    aria-hidden
                    className="size-1.5 shrink-0 rounded-full bg-emerald-500 ring-2 ring-white"
                  />
                )}
                <span className="min-w-0 truncate text-[12px] font-semibold">{reservation.guest_name}</span>
              </span>
              {geometry.visibleNights >= 2 && (
                <span className="mt-0.5 min-w-0 truncate text-[10.5px] font-medium opacity-70">
                  {nights} night{nights === 1 ? "" : "s"} · {source.label}
                </span>
              )}
            </span>
            {needsRoom && (
              <span
                aria-hidden
                className="flex size-4 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-700 ring-1 ring-inset ring-amber-300"
              >
                <DoorOpen className="size-2.5" strokeWidth={2.25} />
              </span>
            )}
          </span>
        </button>
      </TooltipTrigger>

      <TooltipContent side="top" align="start" className="w-64 p-0">
        <div className="flex items-start justify-between gap-3 border-b border-border px-3.5 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold leading-tight">{reservation.guest_name}</p>
            <p className="mt-1 font-mono text-[11px] tracking-wide text-muted-foreground">
              {reservation.confirmation_number}
            </p>
          </div>
          <span
            className={cn(
              "shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset",
              STATUS_CHIP[reservation.status],
            )}
          >
            {STATUS_LABELS[reservation.status]}
          </span>
        </div>

        <dl className="space-y-2 px-3.5 py-3 text-[12.5px]">
          <Detail icon={<CalendarDays className="size-3.5" />}>
            {format(fromIso(reservation.check_in_date), "EEE d MMM")} →{" "}
            {format(fromIso(reservation.check_out_date), "EEE d MMM")}
            <span className="text-muted-foreground">
              {" "}
              · {nights} night{nights === 1 ? "" : "s"}
            </span>
          </Detail>
          <Detail icon={<BedDouble className="size-3.5" />}>
            <span className={cn(needsRoom && "font-medium text-amber-700")}>{roomLabel}</span>
            <span className="text-muted-foreground"> · {roomTypeCode}</span>
          </Detail>
          <Detail icon={<Users className="size-3.5" />}>{guests}</Detail>
          <Detail icon={<IndianRupee className="size-3.5" />}>
            {formatMoney(reservation.rate_per_night)}
            <span className="text-muted-foreground"> per night</span>
          </Detail>
        </dl>

        <div className="flex items-center gap-2 border-t border-border bg-muted/50 px-3.5 py-2 text-[11.5px] text-muted-foreground">
          <span aria-hidden className={cn("size-2 rounded-full", source.accent)} />
          Booked via <span className="font-medium text-foreground">{source.label}</span>
          <span className={cn("ml-auto", needsRoom && "font-medium text-amber-700")}>
            {needsRoom ? `Click to assign a ${unitLower}` : "Click to open"}
          </span>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

function Detail({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2.5">
      <dt className="text-muted-foreground">{icon}</dt>
      <dd className="min-w-0 truncate">{children}</dd>
    </div>
  );
}
