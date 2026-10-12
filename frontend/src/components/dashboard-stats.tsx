"use client";

import { addDays } from "date-fns";
import { BedDouble, DoorOpen, LogIn } from "lucide-react";

import { toIso, today } from "@/lib/dates";
import { useTapeChart } from "@/lib/queries";
import { cn } from "@/lib/utils";

interface Stat {
  label: string;
  value: string;
  hint: string;
  icon: React.ReactNode;
  tint: string;
}

/** What the front desk has to do today. Occupancy and revenue live in the KPI row above. */
export function DashboardStats() {
  const now = today();
  const todayIso = toIso(now);
  // Yesterday is included so that stays leaving today are in the result.
  const { data, isPending } = useTapeChart(toIso(addDays(now, -1)), toIso(addDays(now, 1)));

  const reservations = data?.reservations ?? [];
  const arrivals = reservations.filter((r) => r.check_in_date === todayIso);
  const departures = reservations.filter((r) => r.check_out_date === todayIso);
  const inHouse = reservations.filter((r) => r.status === "checked_in");

  const stats: Stat[] = [
    {
      label: "Arrivals today",
      value: String(arrivals.length),
      hint: `${arrivals.filter((r) => r.status === "confirmed").length} still to check in`,
      icon: <LogIn className="size-4" />,
      tint: "bg-blue-50 text-blue-700",
    },
    {
      label: "Departures today",
      value: String(departures.length),
      hint: `${departures.filter((r) => r.status === "checked_in").length} still to check out`,
      icon: <DoorOpen className="size-4" />,
      tint: "bg-amber-50 text-amber-700",
    },
    {
      label: "In house",
      value: String(inHouse.length),
      hint: "stays checked in right now",
      icon: <BedDouble className="size-4" />,
      tint: "bg-emerald-50 text-emerald-700",
    },
  ];

  return (
    <div className="grid gap-3 sm:grid-cols-3 lg:gap-4">
      {stats.map((stat) => (
        <div
          key={stat.label}
          className="flex items-center gap-3.5 rounded-xl border border-border bg-card px-4 py-3.5 shadow-soft transition-shadow duration-200 hover:shadow-lift"
        >
          <span className={cn("flex size-10 shrink-0 items-center justify-center rounded-lg", stat.tint)}>
            {stat.icon}
          </span>
          <div className="min-w-0">
            <p className="text-[13px] font-medium text-muted-foreground">{stat.label}</p>
            <p className="mt-0.5 flex items-baseline gap-2">
              {isPending ? (
                <span className="inline-block h-6 w-8 animate-pulse rounded bg-muted" />
              ) : (
                <span className="text-2xl font-semibold leading-none tracking-tight tabular-nums">{stat.value}</span>
              )}
              <span className="truncate text-xs text-muted-foreground">{isPending ? "" : stat.hint}</span>
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
