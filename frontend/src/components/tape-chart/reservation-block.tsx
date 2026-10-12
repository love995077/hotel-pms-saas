"use client";

import { BedDouble, CalendarDays, IndianRupee, Users } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatStay, nightsBetween } from "@/lib/dates";
import { SOURCE_STYLES, STATUS_CHIP, STATUS_LABELS } from "@/lib/sources";
import type { TapeChartReservation } from "@/lib/types";
import { cn, formatMoney } from "@/lib/utils";

export interface BlockGeometry {
  /** Position and size as fractions (0-1) of the visible date track. */
  left: number;
  width: number;
  /** The stay starts before / ends after the visible window. */
  clippedStart: boolean;
  clippedEnd: boolean;
}

interface ReservationBlockProps {
  reservation: TapeChartReservation;
  geometry: BlockGeometry;
  roomLabel: string;
  roomTypeCode: string;
  onOpen: () => void;
}

export function ReservationBlock({ reservation, geometry, roomLabel, roomTypeCode, onOpen }: ReservationBlockProps) {
  const source = SOURCE_STYLES[reservation.source];
  const nights = nightsBetween(reservation.check_in_date, reservation.check_out_date);
  const guests =
    `${reservation.adults} adult${reservation.adults === 1 ? "" : "s"}` +
    (reservation.children > 0
      ? `, ${reservation.children} child${reservation.children === 1 ? "" : "ren"}`
      : "");

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onOpen}
          aria-label={`${reservation.guest_name}, ${formatStay(reservation.check_in_date, reservation.check_out_date)}, ${source.label}, ${STATUS_LABELS[reservation.status]}`}
          style={{ left: `${geometry.left * 100}%`, width: `${geometry.width * 100}%` }}
          className="group/block absolute inset-y-[5px] z-10 px-px outline-none focus-visible:z-20 focus-visible:ring-0"
        >
          <span
            className={cn(
              "relative flex h-full items-center gap-1.5 overflow-hidden border pl-3 pr-2 text-left text-xs font-medium shadow-[0_1px_1px_rgb(26_33_55/0.06)]",
              "transition-[transform,box-shadow,background-color] duration-150 ease-out",
              "group-hover/block:-translate-y-px group-hover/block:shadow-lift",
              "group-focus-visible/block:ring-2 group-focus-visible/block:ring-ring",
              source.block,
              !geometry.clippedStart && "rounded-l-lg",
              !geometry.clippedEnd && "rounded-r-lg",
              geometry.clippedStart && "border-l-0",
              geometry.clippedEnd && "border-r-0",
              reservation.status === "checked_out" && "opacity-55",
              (reservation.status === "cancelled" || reservation.status === "no_show") &&
                "border-dashed opacity-50",
            )}
          >
            <span aria-hidden className={cn("absolute inset-y-0 left-0 w-1", source.accent)} />
            {reservation.status === "checked_in" && (
              <span
                aria-hidden
                className="size-1.5 shrink-0 rounded-full bg-emerald-500 ring-2 ring-white/70"
              />
            )}
            <span className="truncate">{reservation.guest_name}</span>
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
            {formatStay(reservation.check_in_date, reservation.check_out_date)}
            <span className="text-muted-foreground">
              {" "}
              · {nights} night{nights === 1 ? "" : "s"}
            </span>
          </Detail>
          <Detail icon={<BedDouble className="size-3.5" />}>
            {roomLabel}
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
          <span className="ml-auto">Click to open</span>
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
