import { useHotel } from "@/lib/queries";
import type { PropertyType } from "@/lib/types";

/** The words the UI uses for a sellable unit and the groups units sit in. */
export interface Terms {
  /** "Room", "Bed", "Flat": a label or the start of a sentence. */
  unit: string;
  units: string;
  /** Mid-sentence forms: "assign a room". */
  unitLower: string;
  unitsLower: string;
  /** What a room type is called here: "Room type", "Bed type". */
  unitType: string;
  unitTypes: string;
  /** What units are grouped by: "Floor", "Dormitory". */
  group: string;
  /** Short form used for derived group names: "Floor 1", "Dorm 1". */
  groupShort: string;
}

interface PropertyTypeOption {
  value: PropertyType;
  label: string;
  description: string;
  terms: Terms;
}

function terms(
  unit: string,
  units: string,
  unitType: string,
  unitTypes: string,
  group: string,
  groupShort: string,
): Terms {
  return {
    unit,
    units,
    unitLower: unit.toLowerCase(),
    unitsLower: units.toLowerCase(),
    unitType,
    unitTypes,
    group,
    groupShort,
  };
}

export const PROPERTY_TYPES: readonly PropertyTypeOption[] = [
  {
    value: "hotel",
    label: "Hotel",
    description: "Rooms on floors",
    terms: terms("Room", "Rooms", "Room type", "Room types", "Floor", "Floor"),
  },
  {
    value: "resort",
    label: "Resort",
    description: "Villas and cottages in zones",
    terms: terms("Villa / Cottage", "Villas / Cottages", "Villa type", "Villa types", "Zone", "Zone"),
  },
  {
    value: "hostel",
    label: "Hostel",
    description: "Beds in dormitories",
    terms: terms("Bed", "Beds", "Bed type", "Bed types", "Dormitory", "Dorm"),
  },
  {
    value: "apartment",
    label: "Serviced Flat / Apartment",
    description: "Flats in blocks or towers",
    terms: terms("Flat", "Flats", "Flat type", "Flat types", "Block / Tower", "Block"),
  },
  {
    value: "villa",
    label: "Villa",
    description: "Suites and villas by area",
    terms: terms("Suite / Villa", "Suites / Villas", "Unit type", "Unit types", "Area", "Area"),
  },
];

const BY_TYPE = new Map(PROPERTY_TYPES.map((option) => [option.value, option]));

/** A property that has not chosen yet is treated as a hotel. */
export function termsFor(propertyType: PropertyType | null | undefined): Terms {
  return (BY_TYPE.get(propertyType ?? "hotel") ?? PROPERTY_TYPES[0]).terms;
}

export function propertyTypeLabel(propertyType: PropertyType | null | undefined): string {
  return (BY_TYPE.get(propertyType ?? "hotel") ?? PROPERTY_TYPES[0]).label;
}

/** The current property's words. Falls back to hotel terms while the profile loads. */
export function useTerms(): Terms {
  return termsFor(useHotel().data?.property_type);
}

/**
 * The group a unit belongs to: its own floor/zone if set, otherwise derived
 * from a numeric unit number (101 → "Floor 1", 1204 → "Floor 12"), else "Main".
 */
export function unitGroup(unit: { room_number: string; floor_or_zone: string | null }, words: Terms): string {
  const own = unit.floor_or_zone?.trim();
  // A bare number ("1", as older data stored floors) reads as "Floor 1".
  if (own && !/^\d+$/.test(own)) return own;
  const match = own ? [own, own] : /^(\d{1,2})\d{2}$/.exec(unit.room_number.trim());
  if (!match) return "Main";
  const level = Number(match[1]);
  if (level === 0 && words.groupShort === "Floor") return "Ground floor";
  return `${words.groupShort} ${level}`;
}
