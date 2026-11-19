import type { BookingSource, ReservationStatus } from "@/lib/types";

interface SourceStyle {
  label: string;
  /** Soft tint, border and text for a tape chart booking card. */
  block: string;
  /** Solid accent used for the block's leading bar and legend dot. */
  accent: string;
}

// Full class names are spelled out so Tailwind's scanner keeps them. Own channels
// (direct, walk-in) are green, Booking.com blue, Airbnb violet; the rest each get a hue.
export const SOURCE_STYLES: Record<BookingSource, SourceStyle> = {
  direct: {
    label: "Direct",
    block: "bg-emerald-50 border-emerald-200 text-emerald-950 hover:bg-emerald-100",
    accent: "bg-emerald-500",
  },
  walk_in: {
    label: "Walk-in",
    block: "bg-green-50 border-green-200 text-green-950 hover:bg-green-100",
    accent: "bg-green-600",
  },
  phone: {
    label: "Phone",
    block: "bg-cyan-50 border-cyan-200 text-cyan-950 hover:bg-cyan-100",
    accent: "bg-cyan-500",
  },
  website: {
    label: "Website",
    block: "bg-sky-50 border-sky-200 text-sky-950 hover:bg-sky-100",
    accent: "bg-sky-500",
  },
  booking_com: {
    label: "Booking.com",
    block: "bg-blue-50 border-blue-200 text-blue-950 hover:bg-blue-100",
    accent: "bg-blue-600",
  },
  makemytrip: {
    label: "MakeMyTrip",
    block: "bg-rose-50 border-rose-200 text-rose-950 hover:bg-rose-100",
    accent: "bg-rose-500",
  },
  goibibo: {
    label: "Goibibo",
    block: "bg-orange-50 border-orange-200 text-orange-950 hover:bg-orange-100",
    accent: "bg-orange-500",
  },
  agoda: {
    label: "Agoda",
    block: "bg-fuchsia-50 border-fuchsia-200 text-fuchsia-950 hover:bg-fuchsia-100",
    accent: "bg-fuchsia-500",
  },
  expedia: {
    label: "Expedia",
    block: "bg-amber-50 border-amber-200 text-amber-950 hover:bg-amber-100",
    accent: "bg-amber-500",
  },
  airbnb: {
    label: "Airbnb",
    block: "bg-violet-50 border-violet-200 text-violet-950 hover:bg-violet-100",
    accent: "bg-violet-500",
  },
  corporate: {
    label: "Corporate",
    block: "bg-teal-50 border-teal-200 text-teal-950 hover:bg-teal-100",
    accent: "bg-teal-600",
  },
  travel_agent: {
    label: "Travel agent",
    block: "bg-lime-50 border-lime-200 text-lime-950 hover:bg-lime-100",
    accent: "bg-lime-600",
  },
  other: {
    label: "Other",
    block: "bg-slate-50 border-slate-200 text-slate-950 hover:bg-slate-100",
    accent: "bg-slate-500",
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
