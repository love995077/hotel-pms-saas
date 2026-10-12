import type { BookingSource, ReservationStatus } from "@/lib/types";

interface SourceStyle {
  label: string;
  /** Soft fill, border and text for a reservation block or chip. */
  block: string;
  /** Solid accent used for the block's leading bar and legend dot. */
  accent: string;
}

// Full class names are spelled out so Tailwind's scanner keeps them.
export const SOURCE_STYLES: Record<BookingSource, SourceStyle> = {
  direct: {
    label: "Direct",
    block: "bg-indigo-100 border-indigo-200 text-indigo-950 hover:bg-indigo-200/80",
    accent: "bg-indigo-500",
  },
  walk_in: {
    label: "Walk-in",
    block: "bg-slate-200 border-slate-300 text-slate-900 hover:bg-slate-300/80",
    accent: "bg-slate-500",
  },
  phone: {
    label: "Phone",
    block: "bg-cyan-100 border-cyan-200 text-cyan-950 hover:bg-cyan-200/80",
    accent: "bg-cyan-500",
  },
  website: {
    label: "Website",
    block: "bg-violet-100 border-violet-200 text-violet-950 hover:bg-violet-200/80",
    accent: "bg-violet-500",
  },
  booking_com: {
    label: "Booking.com",
    block: "bg-blue-100 border-blue-200 text-blue-950 hover:bg-blue-200/80",
    accent: "bg-blue-600",
  },
  makemytrip: {
    label: "MakeMyTrip",
    block: "bg-rose-100 border-rose-200 text-rose-950 hover:bg-rose-200/80",
    accent: "bg-rose-500",
  },
  goibibo: {
    label: "Goibibo",
    block: "bg-orange-100 border-orange-200 text-orange-950 hover:bg-orange-200/80",
    accent: "bg-orange-500",
  },
  agoda: {
    label: "Agoda",
    block: "bg-fuchsia-100 border-fuchsia-200 text-fuchsia-950 hover:bg-fuchsia-200/80",
    accent: "bg-fuchsia-500",
  },
  expedia: {
    label: "Expedia",
    block: "bg-amber-100 border-amber-200 text-amber-950 hover:bg-amber-200/80",
    accent: "bg-amber-500",
  },
  airbnb: {
    label: "Airbnb",
    block: "bg-pink-100 border-pink-200 text-pink-950 hover:bg-pink-200/80",
    accent: "bg-pink-500",
  },
  corporate: {
    label: "Corporate",
    block: "bg-teal-100 border-teal-200 text-teal-950 hover:bg-teal-200/80",
    accent: "bg-teal-600",
  },
  travel_agent: {
    label: "Travel agent",
    block: "bg-lime-100 border-lime-200 text-lime-950 hover:bg-lime-200/80",
    accent: "bg-lime-600",
  },
  other: {
    label: "Other",
    block: "bg-zinc-200 border-zinc-300 text-zinc-900 hover:bg-zinc-300/80",
    accent: "bg-zinc-500",
  },
};

export const STATUS_LABELS: Record<ReservationStatus, string> = {
  confirmed: "Confirmed",
  checked_in: "In house",
  checked_out: "Checked out",
  cancelled: "Cancelled",
  no_show: "No-show",
};

export const STATUS_CHIP: Record<ReservationStatus, string> = {
  confirmed: "bg-blue-50 text-blue-700 ring-blue-200",
  checked_in: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  checked_out: "bg-slate-100 text-slate-600 ring-slate-200",
  cancelled: "bg-rose-50 text-rose-700 ring-rose-200",
  no_show: "bg-amber-50 text-amber-800 ring-amber-200",
};
