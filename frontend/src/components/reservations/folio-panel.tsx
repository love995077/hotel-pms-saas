"use client";

import { format } from "date-fns";
import { Banknote, CircleCheck, FileDown, Info, LoaderCircle, Lock, Plus, ReceiptText, Undo2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Field, FormError, Select, SubmitButton } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { fromIso, nightsBetween } from "@/lib/dates";
import {
  useDownloadInvoice,
  useOpenFolio,
  usePostCharge,
  usePostPayment,
  useReverseTransaction,
} from "@/lib/queries";
import type { Folio, FolioTransaction, PaymentMethod, Reservation } from "@/lib/types";
import { cn, formatAmount } from "@/lib/utils";

const MONEY_PATTERN = /^\d{1,10}(\.\d{1,2})?$/;

// A starting point for each kind of extra; staff can change the rate before posting.
const CHARGE_PRESETS = [
  { label: "Room service", gst: "5" },
  { label: "Restaurant", gst: "5" },
  { label: "Laundry", gst: "18" },
  { label: "Minibar", gst: "18" },
  { label: "Other", gst: "0" },
] as const;
const GST_RATES = ["0", "5", "18"] as const;

const PAYMENT_METHODS: readonly { value: PaymentMethod; label: string }[] = [
  { value: "cash", label: "Cash" },
  { value: "card", label: "Card" },
  { value: "upi", label: "UPI" },
  { value: "bank_transfer", label: "Bank transfer" },
  { value: "cheque", label: "Cheque" },
  { value: "other", label: "Other" },
];

interface FolioPanelProps {
  reservation: Reservation;
  /** null: no folio has been opened for this reservation yet. */
  folio: Folio | null;
  canBill: boolean;
  canReverse: boolean;
}

export function FolioPanel({ reservation, folio, canBill, canReverse }: FolioPanelProps) {
  const openFolio = useOpenFolio();

  if (folio === null) {
    const released = reservation.status === "cancelled" || reservation.status === "no_show";
    return (
      <div className="flex flex-col items-center rounded-lg border border-dashed border-input px-6 py-10 text-center">
        <span className="flex size-11 items-center justify-center rounded-xl bg-accent text-accent-foreground">
          <ReceiptText className="size-5" strokeWidth={1.75} />
        </span>
        <h3 className="mt-3 text-sm font-semibold">No folio yet</h3>
        <p className="mt-1 max-w-xs text-[13px] text-muted-foreground">
          {released
            ? "This reservation was released before a folio was opened."
            : "The folio opens automatically at check-in. Open it now to take an advance payment."}
        </p>
        <FormError className="mt-3" message={openFolio.error?.message} />
        {canBill && !released && (
          <Button
            variant="outline"
            size="sm"
            className="mt-4"
            disabled={openFolio.isPending}
            onClick={() => openFolio.mutate(reservation.id)}
          >
            Open folio
          </Button>
        )}
      </div>
    );
  }

  return <OpenedFolio reservation={reservation} folio={folio} canBill={canBill} canReverse={canReverse} />;
}

function OpenedFolio({ reservation, folio, canBill, canReverse }: FolioPanelProps & { folio: Folio }) {
  const [form, setForm] = useState<"charge" | "payment" | null>(null);
  const download = useDownloadInvoice();
  const balance = Number(folio.balance);
  const isOpen = folio.status === "open";

  const reversedIds = new Set(folio.transactions.map((line) => line.reverses_transaction_id).filter(Boolean));
  const nightsPosted = folio.transactions.filter(
    (line) => line.category === "room_charge" && line.reverses_transaction_id === null && !reversedIds.has(line.id),
  ).length;
  const nights = nightsBetween(reservation.check_in_date, reservation.check_out_date);

  // The API's debit and credit totals count a reversal as a credit (or debit) in
  // its own right. Staff think in net terms, so a reversed line is taken off
  // the side it was first posted to. The balance always comes from the API.
  let charges = 0;
  let payments = 0;
  for (const line of folio.transactions) {
    const signed = Number(line.total_amount) * (line.entry_type === "debit" ? 1 : -1);
    if (line.category === "payment") payments -= signed;
    else charges += signed;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <p className="font-mono text-xs tracking-wide text-muted-foreground">
          {folio.folio_number}
          {folio.invoice_number && <span className="text-foreground"> · {folio.invoice_number}</span>}
        </p>
        {!isOpen && (
          <span className="flex items-center gap-1.5 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 ring-1 ring-inset ring-slate-200">
            <Lock className="size-3" />
            Closed{folio.closed_at ? ` ${format(new Date(folio.closed_at), "d MMM yyyy")}` : ""}
          </span>
        )}
        {canBill && (
          <Button
            variant="outline"
            size="sm"
            className="ml-auto"
            // An invoice needs at least one charge that has not been reversed.
            disabled={download.isPending || charges <= 0}
            title={
              charges <= 0
                ? "Nothing has been charged yet"
                : isOpen
                  ? "The tax invoice is issued once the folio is settled and closed"
                  : undefined
            }
            onClick={() =>
              download.mutate(folio, {
                onSuccess: (file) => toast.success("Invoice downloaded", { description: file.filename }),
                onError: (error) => toast.error(error.message),
              })
            }
          >
            {download.isPending ? (
              <LoaderCircle className="size-3.5 animate-spin" />
            ) : (
              <FileDown className="size-3.5" />
            )}
            {isOpen ? "Download pro forma" : "Download invoice"}
          </Button>
        )}
      </div>

      <dl className="grid grid-cols-3 gap-2.5">
        <Total label="Charges" value={formatAmount(charges)} />
        <Total label="Payments" value={formatAmount(payments)} />
        <Total
          label={balance < 0 ? "Refund due" : "Balance due"}
          value={formatAmount(Math.abs(balance))}
          tone={balance !== 0 ? "due" : folio.transactions.length > 0 ? "settled" : undefined}
        />
      </dl>

      {isOpen && nightsPosted < nights && (
        <p className="flex items-start gap-2 rounded-lg bg-accent/50 px-3 py-2.5 text-xs leading-snug text-accent-foreground">
          <Info className="mt-px size-3.5 shrink-0" />
          Room charges are posted by the night audit, one night at a time: {nightsPosted} of {nights} night
          {nights === 1 ? "" : "s"} posted so far.
        </p>
      )}

      {isOpen && canBill && (
        <div>
          <div className="flex gap-2">
            <Button
              variant={form === "charge" ? "default" : "outline"}
              size="sm"
              onClick={() => setForm(form === "charge" ? null : "charge")}
            >
              <Plus className="size-3.5" />
              Add charge
            </Button>
            <Button
              variant={form === "payment" ? "default" : "outline"}
              size="sm"
              onClick={() => setForm(form === "payment" ? null : "payment")}
            >
              <Banknote className="size-3.5" />
              Take payment
            </Button>
          </div>
          {form === "charge" && <ChargeForm folioId={folio.id} onDone={() => setForm(null)} />}
          {form === "payment" && (
            // Remounted when the balance changes so the suggested amount is always current.
            <PaymentForm key={folio.balance} folioId={folio.id} balance={balance} onDone={() => setForm(null)} />
          )}
        </div>
      )}

      {folio.transactions.length === 0 ? (
        <p className="rounded-lg border border-dashed border-input px-4 py-6 text-center text-[13px] text-muted-foreground">
          Nothing has been posted to this folio yet.
        </p>
      ) : (
        <ul className="divide-y divide-border/70 overflow-hidden rounded-lg border border-border">
          {folio.transactions.map((line) => (
            <Line
              key={line.id}
              line={line}
              reversed={reversedIds.has(line.id)}
              canReverse={isOpen && canReverse}
              folioId={folio.id}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function Total({ label, value, tone }: { label: string; value: string; tone?: "settled" | "due" }) {
  return (
    <div
      className={cn(
        "rounded-lg border px-3 py-2.5",
        tone === "due"
          ? "border-amber-200 bg-amber-50"
          : tone === "settled"
            ? "border-emerald-200 bg-emerald-50"
            : "border-border bg-card",
      )}
    >
      <dt
        className={cn(
          "flex items-center gap-1 text-[11.5px]",
          tone === "due" ? "text-amber-800" : tone === "settled" ? "text-emerald-700" : "text-muted-foreground",
        )}
      >
        {tone === "settled" && <CircleCheck className="size-3" />}
        {tone === "settled" ? "Settled" : label}
      </dt>
      <dd className="mt-0.5 truncate text-[15px] font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function Line({
  line,
  reversed,
  canReverse,
  folioId,
}: {
  line: FolioTransaction;
  reversed: boolean;
  canReverse: boolean;
  folioId: string;
}) {
  const reverse = useReverseTransaction(folioId);
  const [reversing, setReversing] = useState(false);
  const [reason, setReason] = useState("");

  const isCredit = line.entry_type === "credit";
  const isReversal = line.reverses_transaction_id !== null;
  const tax = Number(line.cgst_amount) + Number(line.sgst_amount);
  const method = PAYMENT_METHODS.find((option) => option.value === line.payment_method)?.label;
  const detail = [
    format(fromIso(line.business_date), "d MMM"),
    line.category === "payment" && !isReversal ? method : null,
    line.reference,
    tax > 0 ? `incl. GST ${Number(line.gst_rate)}% ${formatAmount(tax)}` : null,
  ].filter(Boolean);

  return (
    <li className={cn("px-3.5 py-2.5", (reversed || isReversal) && "bg-muted/40")}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className={cn("text-[13px] font-medium leading-snug", reversed && "text-muted-foreground line-through")}>
            {line.description}
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {detail.join(" · ")}
            {reversed && <span className="ml-1.5 font-medium text-foreground/70">Reversed</span>}
          </p>
        </div>
        <p
          className={cn(
            "shrink-0 text-[13px] font-semibold tabular-nums",
            isCredit ? "text-emerald-700" : "text-foreground",
            reversed && "text-muted-foreground line-through",
          )}
        >
          {isCredit ? "−" : ""}
          {formatAmount(line.total_amount)}
        </p>
        {canReverse && !reversed && !isReversal && (
          <button
            type="button"
            title="Reverse this line"
            aria-label={`Reverse ${line.description}`}
            onClick={() => setReversing(!reversing)}
            className="-mr-1 flex size-6 shrink-0 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
          >
            <Undo2 className="size-3.5" />
          </button>
        )}
      </div>

      {reversing && (
        <form
          className="mt-2.5 space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            reverse.mutate(
              { transactionId: line.id, reason: reason.trim() },
              {
                onSuccess: () => {
                  toast.success("Line reversed");
                  setReversing(false);
                },
              },
            );
          }}
        >
          <FormError message={reverse.error?.message} />
          <div className="flex gap-2">
            <Input
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Reason for the reversal"
              aria-label="Reason for the reversal"
              minLength={3}
              maxLength={300}
              className="h-9"
              autoFocus
              required
            />
            <SubmitButton pending={reverse.isPending} size="sm" className="h-9 shrink-0">
              Reverse
            </SubmitButton>
          </div>
          <p className="text-xs text-muted-foreground">
            The original line stays on the ledger; a matching opposite line is added.
          </p>
        </form>
      )}
    </li>
  );
}

function ChargeForm({ folioId, onDone }: { folioId: string; onDone: () => void }) {
  const postCharge = usePostCharge(folioId);
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [gstRate, setGstRate] = useState<string>("5");
  const [submitted, setSubmitted] = useState(false);

  const amountError = MONEY_PATTERN.test(amount.trim()) && Number(amount) > 0 ? null : "Enter an amount above zero.";

  return (
    <form
      className="mt-3 space-y-3 rounded-lg border border-border bg-muted/40 p-3.5 animate-in fade-in-0 slide-in-from-top-1"
      onSubmit={(event) => {
        event.preventDefault();
        setSubmitted(true);
        if (amountError) return;
        postCharge.mutate(
          { description: description.trim(), amount: amount.trim(), gst_rate: gstRate },
          {
            onSuccess: (line) => {
              toast.success(`${line.description} charged`, { description: formatAmount(line.total_amount) });
              onDone();
            },
          },
        );
      }}
    >
      <FormError message={postCharge.error?.message} />
      <div className="flex flex-wrap gap-1.5">
        {CHARGE_PRESETS.map((preset) => (
          <button
            key={preset.label}
            type="button"
            onClick={() => {
              setDescription(preset.label === "Other" ? "" : preset.label);
              setGstRate(preset.gst);
            }}
            className={cn(
              "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
              description === preset.label
                ? "border-primary bg-primary text-primary-foreground"
                : "border-input bg-card text-muted-foreground hover:border-ring/60 hover:text-foreground",
            )}
          >
            {preset.label}
          </button>
        ))}
      </div>
      <Field label="Description">
        {(field) => (
          <Input
            {...field}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Room service: dinner for two"
            maxLength={500}
            required
          />
        )}
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Amount before tax" error={submitted ? amountError : null}>
          {(field) => (
            <Input
              {...field}
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="0.00"
              inputMode="decimal"
              required
            />
          )}
        </Field>
        <Field label="GST rate">
          {(field) => (
            <Select {...field} value={gstRate} onChange={(event) => setGstRate(event.target.value)}>
              {GST_RATES.map((rate) => (
                <option key={rate} value={rate}>
                  {rate}%
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onDone}>
          Cancel
        </Button>
        <SubmitButton pending={postCharge.isPending} size="sm">
          Post charge
        </SubmitButton>
      </div>
    </form>
  );
}

function PaymentForm({ folioId, balance, onDone }: { folioId: string; balance: number; onDone: () => void }) {
  const postPayment = usePostPayment(folioId);
  const [amount, setAmount] = useState(balance > 0 ? balance.toFixed(2) : "");
  const [method, setMethod] = useState<PaymentMethod>("upi");
  const [reference, setReference] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const amountError = MONEY_PATTERN.test(amount.trim()) && Number(amount) > 0 ? null : "Enter an amount above zero.";

  return (
    <form
      className="mt-3 space-y-3 rounded-lg border border-border bg-muted/40 p-3.5 animate-in fade-in-0 slide-in-from-top-1"
      onSubmit={(event) => {
        event.preventDefault();
        setSubmitted(true);
        if (amountError) return;
        postPayment.mutate(
          { amount: amount.trim(), payment_method: method, reference: reference.trim() || null },
          {
            onSuccess: (line) => {
              toast.success("Payment recorded", { description: formatAmount(line.total_amount) });
              onDone();
            },
          },
        );
      }}
    >
      <FormError message={postPayment.error?.message} />
      <div className="grid grid-cols-2 gap-3">
        <Field label="Amount received" error={submitted ? amountError : null}>
          {(field) => (
            <Input
              {...field}
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="0.00"
              inputMode="decimal"
              autoFocus
              required
            />
          )}
        </Field>
        <Field label="Method">
          {(field) => (
            <Select {...field} value={method} onChange={(event) => setMethod(event.target.value as PaymentMethod)}>
              {PAYMENT_METHODS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      <Field label="Reference (optional)">
        {(field) => (
          <Input
            {...field}
            value={reference}
            onChange={(event) => setReference(event.target.value)}
            placeholder="UPI or card transaction id"
            maxLength={100}
          />
        )}
      </Field>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onDone}>
          Cancel
        </Button>
        <SubmitButton pending={postPayment.isPending} size="sm">
          Record payment
        </SubmitButton>
      </div>
    </form>
  );
}
