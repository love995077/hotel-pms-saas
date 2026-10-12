"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FormError, Segmented, SubmitButton, Textarea } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { formatStay, nightsBetween } from "@/lib/dates";
import { useCreateGuest, useGuestReservations, useUpdateGuest } from "@/lib/queries";
import { SOURCE_STYLES, STATUS_CHIP, STATUS_LABELS } from "@/lib/sources";
import type { Guest, GuestInput } from "@/lib/types";
import { cn, formatMoney } from "@/lib/utils";

const EMPTY: GuestInput = {
  first_name: "",
  last_name: "",
  email: null,
  phone: null,
  id_document_type: null,
  id_document_number: null,
  nationality: null,
  address: null,
  city: null,
  state: null,
  country: null,
  company_name: null,
  gstin: null,
};

const ID_TYPES = ["Aadhaar", "Passport", "Driving licence", "Voter ID", "PAN"];

type TextField = Exclude<keyof GuestInput, "first_name" | "last_name">;

/** Create a guest (guest === null) or view and edit one. */
export function GuestDialog({
  guest,
  canEdit,
  onClose,
  onOpenReservation,
}: {
  guest: Guest | null;
  canEdit: boolean;
  onClose: () => void;
  onOpenReservation: (reservationId: string) => void;
}) {
  const create = useCreateGuest();
  const update = useUpdateGuest();
  const mutation = guest ? update : create;
  const stays = useGuestReservations(guest?.id ?? null);

  const [tab, setTab] = useState<"profile" | "stays">("profile");
  const [values, setValues] = useState<GuestInput>(() => {
    if (!guest) return EMPTY;
    const initial = { ...EMPTY };
    for (const key of Object.keys(EMPTY) as (keyof GuestInput)[]) (initial[key] as string | null) = guest[key];
    return initial;
  });
  const [submitted, setSubmitted] = useState(false);

  const set = (key: keyof GuestInput) => (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setValues((current) => ({ ...current, [key]: event.target.value }));
  const text = (key: TextField) => ({ value: values[key] ?? "", onChange: set(key), disabled: !canEdit });

  const gstin = (values.gstin ?? "").trim();
  const gstinError = gstin !== "" && gstin.length !== 15 ? "A GSTIN has exactly 15 characters." : null;

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    if (gstinError) return;
    // Blank optional fields are stored as null, not as empty strings.
    const input = { ...values };
    for (const key of Object.keys(EMPTY) as (keyof GuestInput)[]) {
      const trimmed = (input[key] ?? "").trim();
      (input[key] as string | null) = trimmed === "" && key !== "first_name" && key !== "last_name" ? null : trimmed;
    }
    if (input.gstin) input.gstin = input.gstin.toUpperCase();
    const onSuccess = (saved: Guest) => {
      toast.success(guest ? "Guest profile updated" : `${saved.first_name} ${saved.last_name} added`);
      onClose();
    };
    if (guest) update.mutate({ id: guest.id, changes: input }, { onSuccess });
    else create.mutate(input, { onSuccess });
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl">
        <form onSubmit={onSubmit} className="flex min-h-0 flex-col">
          <DialogHeader>
            <DialogTitle>{guest ? `${guest.first_name} ${guest.last_name}` : "Add a guest"}</DialogTitle>
            <DialogDescription>
              {guest ? "Contact details, identity and stays at this hotel." : "Create a profile to book stays against."}
            </DialogDescription>
            {guest && (
              <Segmented
                label="Section"
                value={tab}
                onChange={setTab}
                className="mt-3 self-start"
                options={[
                  { value: "profile", label: "Profile" },
                  { value: "stays", label: `Stays${stays.data ? ` (${stays.data.length})` : ""}` },
                ]}
              />
            )}
          </DialogHeader>

          <DialogBody className="min-h-64">
            {tab === "stays" ? (
              stays.isPending ? (
                <div className="space-y-3" aria-busy="true" aria-label="Loading stays">
                  {Array.from({ length: 3 }, (_, index) => (
                    <div key={index} className="h-12 animate-pulse rounded-md bg-muted" />
                  ))}
                </div>
              ) : stays.isError ? (
                <FormError message={stays.error.message} />
              ) : stays.data.length === 0 ? (
                <p className="rounded-lg border border-dashed border-input px-4 py-10 text-center text-[13px] text-muted-foreground">
                  No stays yet.
                </p>
              ) : (
                <ul className="divide-y divide-border/70 overflow-hidden rounded-lg border border-border">
                  {[...stays.data].reverse().map((stay) => {
                    const nights = nightsBetween(stay.check_in_date, stay.check_out_date);
                    return (
                      <li key={stay.id}>
                        <button
                          type="button"
                          onClick={() => onOpenReservation(stay.id)}
                          className="flex w-full items-center gap-3 px-3.5 py-3 text-left transition-colors hover:bg-accent/50"
                        >
                          <span aria-hidden className={cn("size-2 shrink-0 rounded-full", SOURCE_STYLES[stay.source].accent)} />
                          <span className="min-w-0 flex-1">
                            <span className="block text-[13px] font-medium">
                              {formatStay(stay.check_in_date, stay.check_out_date)}
                              <span className="font-normal text-muted-foreground">
                                {" "}
                                · {nights} night{nights === 1 ? "" : "s"} · {formatMoney(stay.rate_per_night)}
                              </span>
                            </span>
                            <span className="block font-mono text-[11px] tracking-wide text-muted-foreground">
                              {stay.confirmation_number} · {SOURCE_STYLES[stay.source].label}
                            </span>
                          </span>
                          <span
                            className={cn(
                              "shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset",
                              STATUS_CHIP[stay.status],
                            )}
                          >
                            {STATUS_LABELS[stay.status]}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )
            ) : (
              <div className="space-y-5">
                <FormError message={mutation.error?.message} />

                <Section title="Contact">
                  <Field label="First name">
                    {(field) => (
                      <Input
                        {...field}
                        value={values.first_name}
                        onChange={set("first_name")}
                        disabled={!canEdit}
                        maxLength={100}
                        autoFocus={!guest}
                        required
                      />
                    )}
                  </Field>
                  <Field label="Last name">
                    {(field) => (
                      <Input
                        {...field}
                        value={values.last_name}
                        onChange={set("last_name")}
                        disabled={!canEdit}
                        maxLength={100}
                        required
                      />
                    )}
                  </Field>
                  <Field label="Phone">{(field) => <Input {...field} {...text("phone")} type="tel" maxLength={32} />}</Field>
                  <Field label="Email">{(field) => <Input {...field} {...text("email")} type="email" />}</Field>
                </Section>

                <Section title="Identity">
                  <Field label="ID document">
                    {(field) => (
                      <>
                        <Input {...field} {...text("id_document_type")} list="guest-id-types" maxLength={50} placeholder="Aadhaar, Passport…" />
                        <datalist id="guest-id-types">
                          {ID_TYPES.map((type) => (
                            <option key={type} value={type} />
                          ))}
                        </datalist>
                      </>
                    )}
                  </Field>
                  <Field label="Document number">
                    {(field) => <Input {...field} {...text("id_document_number")} maxLength={100} />}
                  </Field>
                  <Field label="Nationality">
                    {(field) => <Input {...field} {...text("nationality")} maxLength={100} placeholder="Indian" />}
                  </Field>
                </Section>

                <Section title="Address">
                  <Field label="Street address" className="sm:col-span-2">
                    {(field) => <Textarea {...field} {...text("address")} rows={2} />}
                  </Field>
                  <Field label="City">{(field) => <Input {...field} {...text("city")} maxLength={100} />}</Field>
                  <Field label="State">{(field) => <Input {...field} {...text("state")} maxLength={100} />}</Field>
                  <Field label="Country">{(field) => <Input {...field} {...text("country")} maxLength={100} />}</Field>
                </Section>

                <Section title="Company billing">
                  <Field label="Company name">
                    {(field) => <Input {...field} {...text("company_name")} maxLength={200} />}
                  </Field>
                  <Field label="GSTIN" hint="For a B2B tax invoice." error={submitted ? gstinError : null}>
                    {(field) => (
                      <Input
                        {...field}
                        {...text("gstin")}
                        maxLength={15}
                        autoCapitalize="characters"
                        spellCheck={false}
                        className="font-mono uppercase placeholder:font-sans placeholder:normal-case"
                        placeholder="15 characters"
                      />
                    )}
                  </Field>
                </Section>
              </div>
            )}
          </DialogBody>

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                {canEdit && tab === "profile" ? "Cancel" : "Close"}
              </Button>
            </DialogClose>
            {canEdit && tab === "profile" && (
              <SubmitButton pending={mutation.isPending}>{guest ? "Save changes" : "Add guest"}</SubmitButton>
            )}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section aria-label={title}>
      <h3 className="mb-3 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">{title}</h3>
      <div className="grid gap-3 sm:grid-cols-2">{children}</div>
    </section>
  );
}
