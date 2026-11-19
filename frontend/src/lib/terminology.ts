import { BedSingle, Building, DoorClosed, House, type LucideIcon } from "lucide-react";

import { useHotel } from "@/lib/queries";
import type { PropertyType, UnitKind } from "@/lib/types";

/**
 * Property-wide words, for text about the whole inventory ("Add a room type",
 * "Sellable rooms"). A single unit is labelled by its room type's kind instead
 * (see `kindTerms`), because one property can mix private rooms and dorm beds.
 */
export interface Terms {
  unit: string;
  units: string;
  unitLower: string;
  unitsLower: string;
  unitType: string;
  unitTypes: string;
  /** Placeholder for the floor / zone field. */
  groupExample: string;
}

interface PropertyTypeOption {
  value: PropertyType;
  label: string;
  description: string;
  defaultKind: UnitKind;
  terms: Terms;
}

function terms(unit: string, units: string, unitType: string, unitTypes: string, groupExample: string): Terms {
  return {
    unit,
    units,
    unitLower: unit.toLowerCase(),
    unitsLower: units.toLowerCase(),
    unitType,
    unitTypes,
    groupExample,
  };
}

export const PROPERTY_TYPES: readonly PropertyTypeOption[] = [
  {
    value: "hotel",
    label: "Hotel",
    description: "Rooms on floors",
    defaultKind: "room",
    terms: terms("Room", "Rooms", "Room type", "Room types", "1st Floor"),
  },
  {
    value: "resort",
    label: "Resort",
    description: "Villas, cottages and rooms",
    defaultKind: "villa",
    terms: terms("Unit", "Units", "Unit type", "Unit types", "Poolside Wing"),
  },
  {
    value: "hostel",
    label: "Hostel",
    description: "Dorm beds and private rooms",
    defaultKind: "room",
    terms: terms("Room / bed", "Rooms & beds", "Room / bed type", "Room / bed types", "Dormitory A"),
  },
  {
    value: "apartment",
    label: "Serviced Flat / Apartment",
    description: "Flats in blocks or towers",
    defaultKind: "flat",
    terms: terms("Flat", "Flats", "Flat type", "Flat types", "Tower B"),
  },
  {
    value: "villa",
    label: "Villa",
    description: "Suites and villas by area",
    defaultKind: "villa",
    terms: terms("Unit", "Units", "Unit type", "Unit types", "Garden Area"),
  },
];

const BY_TYPE = new Map(PROPERTY_TYPES.map((option) => [option.value, option]));

function option(propertyType: PropertyType | null | undefined): PropertyTypeOption {
  return BY_TYPE.get(propertyType ?? "hotel") ?? PROPERTY_TYPES[0];
}

/** A property that has not chosen yet is treated as a hotel. */
export function termsFor(propertyType: PropertyType | null | undefined): Terms {
  return option(propertyType).terms;
}

export function propertyTypeLabel(propertyType: PropertyType | null | undefined): string {
  return option(propertyType).label;
}

/** What a new room type is preselected as. Mirrors `default_unit_kind` on the server. */
export function defaultUnitKind(propertyType: PropertyType | null | undefined): UnitKind {
  return option(propertyType).defaultKind;
}

/** The current property's words. Falls back to hotel terms while the profile loads. */
export function useTerms(): Terms {
  return termsFor(useHotel().data?.property_type);
}

// --- per room type: what one unit is ------------------------------------------

export interface KindTerms {
  /** Shown when choosing a kind: "Private room", "Dorm bed". */
  label: string;
  unit: string;
  units: string;
  unitLower: string;
  unitsLower: string;
  icon: LucideIcon;
}

function kind(label: string, unit: string, units: string, icon: LucideIcon): KindTerms {
  return { label, unit, units, unitLower: unit.toLowerCase(), unitsLower: units.toLowerCase(), icon };
}

export const UNIT_KINDS: Record<UnitKind, KindTerms> = {
  room: kind("Private room", "Room", "Rooms", DoorClosed),
  dorm_bed: kind("Dorm bed", "Bed", "Beds", BedSingle),
  villa: kind("Villa / cottage", "Villa", "Villas", House),
  flat: kind("Flat / apartment", "Flat", "Flats", Building),
};

export const UNIT_KIND_ORDER: readonly UnitKind[] = ["room", "dorm_bed", "villa", "flat"];

export function kindTerms(unitKind: UnitKind | null | undefined): KindTerms {
  return UNIT_KINDS[unitKind ?? "room"];
}

// --- floors and zones ----------------------------------------------------------

/**
 * The floor or zone a unit sits in: the owner's own name if set ("Dormitory A",
 * "Poolside Wing"), otherwise derived from a numeric unit number whatever the
 * property type (101 → "Floor 1", 1204 → "Floor 12", 012 → "Ground floor"),
 * otherwise "Main". A bare number as the name ("1", as older data stored
 * floors) reads as "Floor 1".
 */
export function unitGroup(unit: { room_number: string; floor_or_zone: string | null }): string {
  const own = unit.floor_or_zone?.trim();
  if (own && !/^\d+$/.test(own)) return own;
  const level = own ? own : /^(\d{1,2})\d{2}$/.exec(unit.room_number.trim())?.[1];
  if (level === undefined) return "Main";
  return Number(level) === 0 ? "Ground floor" : `Floor ${Number(level)}`;
}

const byNumber = new Intl.Collator("en", { numeric: true });

/** Floors in building order (ground floor first), then named zones, then "Main". */
export function compareGroups(a: string, b: string): number {
  const rank = (name: string) => (name === "Ground floor" ? 0 : /^Floor \d+$/.test(name) ? 1 : name === "Main" ? 3 : 2);
  return rank(a) - rank(b) || byNumber.compare(a, b);
}
