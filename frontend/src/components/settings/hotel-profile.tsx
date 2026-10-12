"use client";

import { CircleAlert, CircleCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Field, FormError, SubmitButton, Textarea } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useHotel, useUpdateHotel } from "@/lib/queries";
import type { Hotel, HotelInput } from "@/lib/types";

const GSTIN_PATTERN = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;

const STATES = [
  "Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh",
  "Chhattisgarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa", "Gujarat", "Haryana",
  "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep",
  "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Puducherry",
  "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
  "West Bengal",
]; // prettier-ignore

const FIELDS = ["name", "gstin", "address", "city", "state", "postal_code", "phone", "email"] as const;

export function HotelProfile() {
  const hotel = useHotel();

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Hotel profile</h2>
        <p className="mt-1 max-w-prose text-sm text-muted-foreground">
          These details are printed at the top of every invoice. A GST tax invoice needs your GSTIN, address and state.
        </p>
      </div>

      {hotel.isPending ? (
        <div
          className="h-96 animate-pulse rounded-xl border border-border bg-card"
          aria-busy="true"
          aria-label="Loading hotel profile"
        />
      ) : hotel.isError ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-border bg-card px-6 py-16 text-center shadow-soft">
          <CircleAlert className="size-6 text-destructive" />
          <p className="text-sm text-muted-foreground">{hotel.error.message}</p>
          <Button variant="outline" size="sm" onClick={() => hotel.refetch()}>
            Try again
          </Button>
        </div>
      ) : (
        // Keyed on the saved version so the form picks up what the server stored.
        <ProfileForm key={hotel.data.updated_at} hotel={hotel.data} />
      )}
    </div>
  );
}

function ProfileForm({ hotel }: { hotel: Hotel }) {
  const update = useUpdateHotel();
  const [values, setValues] = useState<Record<(typeof FIELDS)[number], string>>(
    () =>
      Object.fromEntries(FIELDS.map((field) => [field, hotel[field] ?? ""])) as Record<(typeof FIELDS)[number], string>,
  );
  const [submitted, setSubmitted] = useState(false);

  const bind = (field: (typeof FIELDS)[number]) => ({
    value: values[field],
    onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setValues((current) => ({ ...current, [field]: event.target.value })),
  });

  const gstin = values.gstin.trim().toUpperCase();
  const gstinError =
    gstin !== "" && !GSTIN_PATTERN.test(gstin) ? "Enter the 15-character GSTIN exactly as on your certificate." : null;
  const dirty = FIELDS.some((field) => values[field].trim() !== (hotel[field] ?? ""));
  const missing = [!hotel.gstin && "GSTIN", !hotel.address && "address", !hotel.state && "state"].filter(Boolean);

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    if (gstinError) return;
    const changes: HotelInput = {
      name: values.name.trim(),
      gstin: gstin || null,
      address: values.address.trim() || null,
      city: values.city.trim() || null,
      state: values.state.trim() || null,
      postal_code: values.postal_code.trim() || null,
      phone: values.phone.trim() || null,
      email: values.email.trim() || null,
    };
    update.mutate(changes, { onSuccess: () => toast.success("Hotel profile saved") });
  }

  return (
    <form onSubmit={onSubmit} className="overflow-hidden rounded-xl border border-border bg-card shadow-soft">
      <div className="space-y-5 p-4 sm:p-6">
        {missing.length > 0 ? (
          <p className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-[13px] text-amber-900">
            <CircleAlert className="mt-px size-4 shrink-0" />
            Invoices are missing your {missing.join(", ").replace(/, ([^,]*)$/, " and $1")}. Add{" "}
            {missing.length === 1 ? "it" : "them"} before issuing tax invoices.
          </p>
        ) : (
          <p className="flex items-center gap-2 text-[13px] text-emerald-700">
            <CircleCheck className="size-4" />
            Your invoices carry everything a GST tax invoice needs about the supplier.
          </p>
        )}
        <FormError message={update.error?.message} />

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Hotel name" hint="The legal or trade name to print on invoices.">
            {(field) => <Input {...field} {...bind("name")} minLength={2} maxLength={200} required />}
          </Field>
          <Field
            label="GSTIN"
            error={submitted ? gstinError : null}
            hint="Leave empty if the hotel is not GST-registered."
          >
            {(field) => (
              <Input
                {...field}
                {...bind("gstin")}
                maxLength={15}
                placeholder="08AAACH7409R1ZZ"
                autoCapitalize="characters"
                spellCheck={false}
                className="font-mono uppercase placeholder:font-sans placeholder:normal-case"
              />
            )}
          </Field>
          <Field label="Address" className="sm:col-span-2">
            {(field) => (
              <Textarea
                {...field}
                {...bind("address")}
                rows={2}
                maxLength={500}
                placeholder="Building, street, locality"
              />
            )}
          </Field>
          <Field label="City">{(field) => <Input {...field} {...bind("city")} maxLength={100} />}</Field>
          <Field label="State" hint="Printed as the place of supply.">
            {(field) => (
              <>
                <Input {...field} {...bind("state")} maxLength={100} list="indian-states" autoComplete="off" />
                <datalist id="indian-states">
                  {STATES.map((state) => (
                    <option key={state} value={state} />
                  ))}
                </datalist>
              </>
            )}
          </Field>
          <Field label="PIN code">
            {(field) => <Input {...field} {...bind("postal_code")} maxLength={10} inputMode="numeric" />}
          </Field>
          <Field label="Phone">{(field) => <Input {...field} {...bind("phone")} type="tel" maxLength={32} />}</Field>
          <Field label="Accounts email" className="sm:col-span-2">
            {(field) => <Input {...field} {...bind("email")} type="email" placeholder="accounts@yourhotel.com" />}
          </Field>
        </div>
      </div>

      <div className="flex items-center justify-end gap-2 border-t border-border bg-muted/40 px-4 py-3.5 sm:px-6">
        <p className="mr-auto text-xs text-muted-foreground">
          Hotel code <span className="font-mono text-foreground">{hotel.slug}</span> can&apos;t be changed.
        </p>
        <SubmitButton pending={update.isPending} disabled={!dirty}>
          Save profile
        </SubmitButton>
      </div>
    </form>
  );
}
