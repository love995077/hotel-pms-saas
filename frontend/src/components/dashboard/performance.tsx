"use client";

import { format } from "date-fns";
import { ArrowDownRight, ArrowUpRight, BarChart3, CircleAlert, Minus, Table2 } from "lucide-react";
import { useId, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/field";
import { fromIso } from "@/lib/dates";
import { useDashboardStats } from "@/lib/queries";
import type { DashboardStats, DayPerformance } from "@/lib/types";
import { cn, formatMoney } from "@/lib/utils";

// Chart marks use the theme's primary hue; text stays in the text tokens.
const SERIES = "rgb(var(--primary))";
const GRID = "rgb(var(--border))";
const AXIS_TEXT = "rgb(var(--muted-foreground))";

const compact = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });

/** ₹45K, ₹1.2L, ₹3Cr: short enough for an axis tick. */
function compactMoney(value: number): string {
  return `₹${compact.format(value)}`;
}

const percent = (value: string | number) => `${Number(value).toFixed(Number(value) % 1 === 0 ? 0 : 1)}%`;

interface Delta {
  /** Positive is up. */
  change: number;
  label: string;
}

/** How today compares with the same figure over the period; null when there is nothing to compare with. */
function relativeDelta(today: number, baseline: number): Delta | null {
  if (baseline <= 0) return null;
  const change = ((today - baseline) / baseline) * 100;
  return { change, label: `${Math.abs(change).toFixed(Math.abs(change) >= 10 ? 0 : 1)}%` };
}

export function Performance() {
  const { data, isPending, isError, error, refetch } = useDashboardStats();

  if (isError) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-xl border border-border bg-card px-6 py-10 text-center shadow-soft">
        <CircleAlert className="size-6 text-destructive" />
        <p className="text-sm text-muted-foreground">{error.message}</p>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          Try again
        </Button>
      </div>
    );
  }

  return (
    <>
      <KpiRow stats={data} loading={isPending} />
      {/* A hotel with no rooms has nothing to chart; the tape chart below points to the set-up page. */}
      {(isPending || data.today.rooms_available > 0) && <Trend stats={data} loading={isPending} />}
    </>
  );
}

// --- KPI tiles ------------------------------------------------------------------

function KpiRow({ stats, loading }: { stats: DashboardStats | undefined; loading: boolean }) {
  const today = stats?.today;
  const period = stats?.period;
  const trend = stats?.trend ?? [];
  const days = trend.length;
  const showMoney = loading || stats?.can_view_revenue;

  const occupancyChange = today && period ? Number(today.occupancy_pct) - Number(period.occupancy_pct) : 0;

  return (
    <div className={cn("grid gap-3 lg:gap-4", showMoney && "grid-cols-2 lg:grid-cols-4")}>
      <Kpi
        label="Occupancy tonight"
        loading={loading}
        value={today ? percent(today.occupancy_pct) : ""}
        detail={today ? `${today.rooms_sold} of ${today.rooms_available} rooms sold` : ""}
        delta={
          period && period.rooms_sold > 0
            ? { change: occupancyChange, label: `${Math.abs(occupancyChange).toFixed(1)} pts` }
            : null
        }
        comparison={`${days}-day average`}
        spark={trend.map((day) => Number(day.occupancy_pct))}
        meter={today ? Number(today.occupancy_pct) / 100 : undefined}
      />
      {showMoney && (
        <>
          <Kpi
            label="Room revenue today"
            tag={today?.is_projected ? "Expected" : undefined}
            tagTitle="Tonight's room charges are posted by the night audit. Until then this is the booked rate of the rooms occupied tonight."
            loading={loading}
            value={today ? formatMoney(today.room_revenue ?? 0) : ""}
            detail={
              today && Number(today.other_revenue) > 0
                ? `plus ${formatMoney(today.other_revenue ?? 0)} in extras, before GST`
                : "before GST"
            }
            delta={
              today && period && days > 0
                ? relativeDelta(Number(today.room_revenue), Number(period.room_revenue) / days)
                : null
            }
            comparison={`${days}-day daily average`}
            spark={trend.map((day) => Number(day.room_revenue))}
          />
          <Kpi
            label="ADR"
            labelTitle="Average daily rate: room revenue divided by rooms sold"
            loading={loading}
            value={today ? formatMoney(today.adr ?? 0) : ""}
            detail="average rate per room sold"
            delta={today && period ? relativeDelta(Number(today.adr), Number(period.adr)) : null}
            comparison={`${days}-day ADR`}
            spark={trend.map((day) => Number(day.adr))}
          />
          <Kpi
            label="RevPAR"
            labelTitle="Revenue per available room: room revenue divided by all rooms, sold or not"
            loading={loading}
            value={today ? formatMoney(today.revpar ?? 0) : ""}
            detail="revenue per available room"
            delta={today && period ? relativeDelta(Number(today.revpar), Number(period.revpar)) : null}
            comparison={`${days}-day RevPAR`}
            spark={trend.map((day) => Number(day.revpar))}
          />
        </>
      )}
    </div>
  );
}

function Kpi({
  label,
  labelTitle,
  tag,
  tagTitle,
  value,
  detail,
  delta,
  comparison,
  spark,
  meter,
  loading,
}: {
  label: string;
  labelTitle?: string;
  tag?: string;
  tagTitle?: string;
  value: string;
  detail: string;
  delta: Delta | null;
  comparison: string;
  spark: number[];
  /** 0-1, drawn as a thin meter under the value. */
  meter?: number;
  loading: boolean;
}) {
  const direction = !delta || Math.abs(delta.change) < 0.05 ? "flat" : delta.change > 0 ? "up" : "down";
  const DeltaIcon = direction === "up" ? ArrowUpRight : direction === "down" ? ArrowDownRight : Minus;

  return (
    <div className="relative overflow-hidden rounded-xl border border-border bg-card p-4 shadow-soft transition-shadow duration-200 hover:shadow-lift sm:p-5">
      <div className="flex items-center gap-2">
        <p className="text-[13px] font-medium text-muted-foreground" title={labelTitle}>
          {labelTitle ? <abbr className="cursor-help no-underline">{label}</abbr> : label}
        </p>
        {tag && (
          <span
            title={tagTitle}
            className="cursor-help rounded-full bg-accent px-1.5 py-0.5 text-[10.5px] font-medium text-accent-foreground"
          >
            {tag}
          </span>
        )}
      </div>

      {loading ? (
        <div className="mt-3 h-9 w-28 animate-pulse rounded-md bg-muted" />
      ) : (
        <p className="mt-2 text-[30px] font-semibold leading-none tracking-tight tabular-nums">{value}</p>
      )}
      {meter !== undefined && (
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-primary transition-[width] duration-500 ease-out"
            style={{ width: `${Math.min(Math.max(meter, 0), 1) * 100}%` }}
          />
        </div>
      )}
      <p className={cn("text-xs text-muted-foreground", meter === undefined ? "mt-2" : "mt-1.5")}>
        {loading ? " " : detail}
      </p>

      <div className="mt-3 flex items-end justify-between gap-3 border-t border-border/70 pt-3">
        {loading ? (
          <div className="h-4 w-32 animate-pulse rounded bg-muted" />
        ) : delta ? (
          <p className="flex min-w-0 flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
            <span
              className={cn(
                "flex items-center gap-0.5 rounded-full px-1.5 py-0.5 font-medium tabular-nums ring-1 ring-inset",
                direction === "up" && "bg-emerald-50 text-emerald-700 ring-emerald-200",
                direction === "down" && "bg-rose-50 text-rose-700 ring-rose-200",
                direction === "flat" && "bg-muted text-muted-foreground ring-border",
              )}
            >
              <DeltaIcon className="size-3" strokeWidth={2.25} />
              {direction === "flat" ? "Level" : `${direction === "up" ? "Up" : "Down"} ${delta.label}`}
            </span>
            <span className="truncate">vs {comparison}</span>
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">No history to compare with yet</p>
        )}
        <Sparkline values={spark} />
      </div>
    </div>
  );
}

/** The shape of the last few weeks, without axes: a hint, not a chart to read values from. */
function Sparkline({ values }: { values: number[] }) {
  const gradient = useId();
  const max = Math.max(...values, 0);
  if (values.length < 2 || max <= 0) return null;
  const width = 84;
  const height = 26;
  const points = values.map((value, index) => {
    const x = (index / (values.length - 1)) * width;
    const y = height - 2 - (value / max) * (height - 4);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden className="shrink-0">
      <defs>
        <linearGradient id={gradient} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={SERIES} stopOpacity={0.18} />
          <stop offset="100%" stopColor={SERIES} stopOpacity={0} />
        </linearGradient>
      </defs>
      <polygon points={`0,${height} ${points.join(" ")} ${width},${height}`} fill={`url(#${gradient})`} />
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke={SERIES}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

// --- 30-day trend ---------------------------------------------------------------

interface Point {
  date: string;
  revenue: number;
  occupancy: number;
  day: DayPerformance;
}

function Trend({ stats, loading }: { stats: DashboardStats | undefined; loading: boolean }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  // The two charts move their crosshairs together; only the one under the pointer shows the readout.
  const [hovered, setHovered] = useState<"revenue" | "occupancy">("occupancy");
  const readout = (chart: "revenue" | "occupancy") =>
    hovered === chart ? <TrendTooltip showMoney={showMoney} /> : () => null;
  const showMoney = stats?.can_view_revenue ?? false;
  const period = stats?.period;
  const points: Point[] = (stats?.trend ?? []).map((day) => ({
    date: day.date,
    revenue: Number(day.room_revenue ?? 0),
    occupancy: Number(day.occupancy_pct),
    day,
  }));
  const days = points.length || 30;
  const hasHistory = points.some((point) => point.day.rooms_sold > 0 || point.revenue > 0);

  return (
    <section className="overflow-hidden rounded-xl border border-border bg-card shadow-soft">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-border px-4 py-3.5 sm:px-5">
        <div className="mr-auto">
          <h2 className="text-[15px] font-semibold leading-tight">Last {days} days</h2>
          <p className="mt-0.5 text-[13px] text-muted-foreground">
            {points.length > 0
              ? `${format(fromIso(points[0].date), "d MMM")} – ${format(fromIso(points[points.length - 1].date), "d MMM yyyy")}`
              : " "}
          </p>
        </div>
        {period && (
          <dl className="flex flex-wrap gap-x-6 gap-y-2">
            {showMoney && <Figure label="Room revenue" value={formatMoney(period.room_revenue ?? 0)} />}
            <Figure label="Occupancy" value={percent(period.occupancy_pct)} />
            {showMoney && <Figure label="ADR" value={formatMoney(period.adr ?? 0)} />}
            {showMoney && <Figure label="RevPAR" value={formatMoney(period.revpar ?? 0)} />}
          </dl>
        )}
        <Segmented
          label="View"
          value={view}
          onChange={setView}
          options={[
            {
              value: "chart",
              label: (
                <>
                  <BarChart3 className="size-3.5" /> Chart
                </>
              ),
            },
            {
              value: "table",
              label: (
                <>
                  <Table2 className="size-3.5" /> Table
                </>
              ),
            },
          ]}
        />
      </div>

      {loading ? (
        <div className="space-y-4 p-5" aria-busy="true" aria-label="Loading performance">
          <div className="h-44 animate-pulse rounded-lg bg-muted" />
          <div className="h-32 animate-pulse rounded-lg bg-muted" />
        </div>
      ) : view === "table" ? (
        <TrendTable points={points} showMoney={showMoney} />
      ) : (
        <div className="relative px-2 pb-3 pt-4 sm:px-4">
          {/* Two measures on two scales get two charts on a shared time axis, never one chart with two y-axes. */}
          {showMoney && (
            <ChartBlock title="Room revenue" subtitle="per night, before GST">
              <ResponsiveContainer width="100%" height={190}>
                <BarChart
                  data={points}
                  syncId="performance"
                  margin={{ top: 6, right: 12, bottom: 0, left: 4 }}
                  onMouseEnter={() => setHovered("revenue")}
                >
                  <CartesianGrid vertical={false} stroke={GRID} />
                  <XAxis dataKey="date" hide />
                  <YAxis
                    width={52}
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: AXIS_TEXT, fontSize: 11 }}
                    tickFormatter={compactMoney}
                    allowDecimals={false}
                  />
                  <Tooltip
                    cursor={{ fill: "rgb(var(--accent))" }}
                    content={readout("revenue")}
                    isAnimationActive={false}
                  />
                  <Bar
                    dataKey="revenue"
                    name="Room revenue"
                    fill={SERIES}
                    radius={[4, 4, 0, 0]}
                    maxBarSize={24}
                    isAnimationActive={false}
                  />
                </BarChart>
              </ResponsiveContainer>
            </ChartBlock>
          )}
          <ChartBlock title="Occupancy" subtitle="rooms sold as a share of rooms available">
            <ResponsiveContainer width="100%" height={showMoney ? 150 : 220}>
              <AreaChart
                data={points}
                syncId="performance"
                margin={{ top: 6, right: 12, bottom: 0, left: 4 }}
                onMouseEnter={() => setHovered("occupancy")}
              >
                <CartesianGrid vertical={false} stroke={GRID} />
                {/* Band scale, like the bars above, so a day sits at the same x in both charts. */}
                <XAxis
                  dataKey="date"
                  scale="band"
                  tickLine={false}
                  axisLine={{ stroke: GRID }}
                  tick={{ fill: AXIS_TEXT, fontSize: 11 }}
                  tickFormatter={(value: string) => format(fromIso(value), "d MMM")}
                  minTickGap={36}
                  tickMargin={8}
                />
                <YAxis
                  width={52}
                  domain={[0, 100]}
                  ticks={[0, 50, 100]}
                  tickLine={false}
                  axisLine={false}
                  tick={{ fill: AXIS_TEXT, fontSize: 11 }}
                  tickFormatter={(value: number) => `${value}%`}
                />
                <Tooltip
                  cursor={{ stroke: AXIS_TEXT, strokeWidth: 1 }}
                  content={readout("occupancy")}
                  isAnimationActive={false}
                />
                <Area
                  type="monotone"
                  dataKey="occupancy"
                  name="Occupancy"
                  stroke={SERIES}
                  strokeWidth={2}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  fill={SERIES}
                  fillOpacity={0.1}
                  dot={false}
                  activeDot={{ r: 4, fill: SERIES, stroke: "rgb(var(--card))", strokeWidth: 2 }}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </ChartBlock>

          {!hasHistory && (
            <p className="pointer-events-none absolute inset-x-0 top-1/2 mx-auto w-fit max-w-[80%] -translate-y-1/2 rounded-lg border border-border bg-card/95 px-4 py-2.5 text-center text-[13px] text-muted-foreground shadow-soft">
              No history yet. Figures appear here once guests have stayed and the night audit has run.
            </p>
          )}
        </div>
      )}
    </section>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] text-muted-foreground">{label}</dt>
      <dd className="text-[15px] font-semibold leading-tight tabular-nums">{value}</dd>
    </div>
  );
}

function ChartBlock({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <figure className="mb-1">
      <figcaption className="mb-1 flex items-baseline gap-2 px-2 sm:px-1">
        <span className="text-[13px] font-medium">{title}</span>
        <span className="text-xs text-muted-foreground">{subtitle}</span>
      </figcaption>
      {children}
    </figure>
  );
}

/** One readout for both charts: the day, then every figure for it, values first. */
function TrendTooltip({
  active,
  payload,
  showMoney,
}: {
  active?: boolean;
  payload?: readonly { payload: Point }[];
  showMoney: boolean;
}) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  const { day } = point;
  return (
    <div className="min-w-44 rounded-lg border border-border bg-popover px-3 py-2.5 text-popover-foreground shadow-lift">
      <p className="text-xs text-muted-foreground">{format(fromIso(point.date), "EEEE, d MMM yyyy")}</p>
      <dl className="mt-1.5 space-y-1 text-[13px]">
        {showMoney && <Readout value={formatMoney(day.room_revenue ?? 0)} label="room revenue" />}
        <Readout
          value={percent(day.occupancy_pct)}
          label={`occupancy · ${day.rooms_sold} of ${day.rooms_available} rooms`}
        />
        {showMoney && <Readout value={formatMoney(day.adr ?? 0)} label="ADR" />}
        {showMoney && <Readout value={formatMoney(day.revpar ?? 0)} label="RevPAR" />}
      </dl>
    </div>
  );
}

function Readout({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <dd className="font-semibold tabular-nums">{value}</dd>
      <dt className="text-xs text-muted-foreground">{label}</dt>
    </div>
  );
}

function TrendTable({ points, showMoney }: { points: Point[]; showMoney: boolean }) {
  return (
    <div className="scroll-slim max-h-[23rem] overflow-auto">
      <table className="w-full min-w-[560px] text-left text-[13px]">
        <thead className="sticky top-0 bg-card text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
          <tr className="border-b border-border">
            <th className="px-4 py-2.5 font-medium sm:px-5">Date</th>
            <th className="px-4 py-2.5 text-right font-medium">Rooms sold</th>
            <th className="px-4 py-2.5 text-right font-medium">Occupancy</th>
            {showMoney && (
              <>
                <th className="px-4 py-2.5 text-right font-medium">Room revenue</th>
                <th className="px-4 py-2.5 text-right font-medium">ADR</th>
                <th className="px-4 py-2.5 text-right font-medium sm:px-5">RevPAR</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {/* Newest first: the most recent night is what people look for. */}
          {[...points].reverse().map(({ date, day }) => (
            <tr key={date} className="border-b border-border/70 last:border-b-0 hover:bg-accent/40">
              <td className="whitespace-nowrap px-4 py-2 sm:px-5">{format(fromIso(date), "EEE, d MMM")}</td>
              <td className="px-4 py-2 text-right tabular-nums">
                {day.rooms_sold} <span className="text-muted-foreground">of {day.rooms_available}</span>
              </td>
              <td className="px-4 py-2 text-right tabular-nums">{percent(day.occupancy_pct)}</td>
              {showMoney && (
                <>
                  <td className="px-4 py-2 text-right tabular-nums">{formatMoney(day.room_revenue ?? 0)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{formatMoney(day.adr ?? 0)}</td>
                  <td className="px-4 py-2 text-right tabular-nums sm:px-5">{formatMoney(day.revpar ?? 0)}</td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
