"use client";

import { BedSingle, Building, Hotel, House, TreePalm, type LucideIcon } from "lucide-react";

import { PROPERTY_TYPES } from "@/lib/terminology";
import type { PropertyType } from "@/lib/types";
import { cn } from "@/lib/utils";

const ICONS: Record<PropertyType, LucideIcon> = {
  hotel: Hotel,
  resort: TreePalm,
  hostel: BedSingle,
  apartment: Building,
  villa: House,
};

/** Radio cards for the five property types. Native radios, so arrow keys work. */
export function PropertyTypePicker({
  value,
  onChange,
  name = "property-type",
  className,
}: {
  value: PropertyType | null;
  onChange: (value: PropertyType) => void;
  name?: string;
  className?: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label="Property type"
      className={cn("grid grid-cols-2 gap-2 sm:grid-cols-3", className)}
    >
      {PROPERTY_TYPES.map((option) => {
        const Icon = ICONS[option.value];
        const checked = value === option.value;
        return (
          <label
            key={option.value}
            className={cn(
              "relative flex cursor-pointer items-start gap-2.5 rounded-lg border bg-card px-3 py-2.5 transition-[border-color,box-shadow,background-color] duration-150",
              "has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring",
              checked ? "border-primary bg-primary/5 shadow-soft" : "border-border hover:border-input hover:bg-accent/40",
            )}
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={checked}
              onChange={() => onChange(option.value)}
              className="sr-only"
            />
            <span
              className={cn(
                "mt-px flex size-7 shrink-0 items-center justify-center rounded-md",
                checked ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
              )}
            >
              <Icon className="size-4" strokeWidth={1.75} />
            </span>
            <span className="min-w-0">
              <span className="block text-[13px] font-medium leading-tight">{option.label}</span>
              <span className="mt-0.5 block text-[11.5px] leading-snug text-muted-foreground">{option.description}</span>
            </span>
          </label>
        );
      })}
    </div>
  );
}
