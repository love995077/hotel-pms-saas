import { addDays, differenceInCalendarDays, format, parseISO } from "date-fns";

/** "YYYY-MM-DD" in local time, the format the API expects. */
export function toIso(date: Date): string {
  return format(date, "yyyy-MM-dd");
}

export function fromIso(value: string): Date {
  return parseISO(value);
}

export function today(): Date {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

/** Consecutive days starting at `start`. */
export function daysFrom(start: Date, count: number): Date[] {
  return Array.from({ length: count }, (_, index) => addDays(start, index));
}

export function nightsBetween(checkIn: string, checkOut: string): number {
  return differenceInCalendarDays(fromIso(checkOut), fromIso(checkIn));
}

export function formatStay(checkIn: string, checkOut: string): string {
  return `${format(fromIso(checkIn), "d MMM")} → ${format(fromIso(checkOut), "d MMM")}`;
}
