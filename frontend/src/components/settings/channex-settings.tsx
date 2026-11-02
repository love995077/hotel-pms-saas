"use client";

import { format } from "date-fns";
import {
  ArrowLeftRight,
  Cable,
  CircleAlert,
  CircleCheck,
  LoaderCircle,
  Pencil,
  PlugZap,
  RefreshCw,
  ShieldAlert,
  Webhook,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { EVENT_STATUS } from "@/components/settings/channel-connections";
import { Button } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FormError, SubmitButton } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  useChannelConnections,
  useChannelEvents,
  useChannexMappings,
  useCreateChannexConnection,
  useRoomTypes,
  useSaveChannexMappings,
  useSyncChannel,
  useTestOutbound,
  useUpdateChannelConnection,
} from "@/lib/queries";
import { SOURCE_STYLES } from "@/lib/sources";
import type {
  BookingSource,
  ChannelConnection,
  ChannelConnectionCreated,
  ChannexMapping,
  ChannexMappingInput,
  RoomType,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const WEBHOOK_PATH = "/api/v1/webhooks/channex";
// Channex ids are UUIDs; the API accepts letters, digits and hyphens.
const CHANNEX_ID = /^[A-Za-z0-9-]{1,64}$/;
const ID_HINT = "e.g. 8faff15f-c399-4c5b-a976-2fffad33d36c";

function useWebhookUrl(): string {
  // The origin is only known in the browser; rendering it on the server would not match.
  const [origin, setOrigin] = useState("");
  useEffect(() => setOrigin(window.location.origin), []);
  return origin + WEBHOOK_PATH;
}

export function ChannexSettings() {
  const connections = useChannelConnections(true);
  const connection = connections.data?.find((c) => c.provider === "channex");
  // Kept here, not in the connect form: once the connection exists the form is
  // replaced, and the one-time secret must stay on screen until it is saved.
  const [created, setCreated] = useState<ChannelConnectionCreated | null>(null);

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Channex</h2>
        <p className="mt-1 max-w-prose text-sm text-muted-foreground">
          Two-way sync with Channex.io: OTA bookings arrive as reservations, and availability is sent to Channex
          whenever a booking changes what you can sell.
        </p>
      </div>

      {connections.isPending ? (
        <div className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-soft" aria-busy="true">
          <div className="h-10 animate-pulse rounded-md bg-muted" />
          <div className="h-24 animate-pulse rounded-md bg-muted" />
        </div>
      ) : connections.isError ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-border bg-card px-6 py-12 text-center shadow-soft">
          <CircleAlert className="size-6 text-destructive" />
          <p className="text-sm text-muted-foreground">{connections.error.message}</p>
          <Button variant="outline" size="sm" onClick={() => connections.refetch()}>
            Try again
          </Button>
        </div>
      ) : connection === undefined ? (
        <ConnectChannex onCreated={setCreated} />
      ) : (
        <>
          <ConnectionCard connection={connection} />
          <RoomMappings connection={connection} />
          <ChannexDeliveries connectionId={connection.id} />
        </>
      )}

      {created && <CredentialsDialog created={created} onClose={() => setCreated(null)} />}
    </div>
  );
}

// --- connecting ------------------------------------------------------------------------

function ConnectChannex({ onCreated }: { onCreated: (created: ChannelConnectionCreated) => void }) {
  const create = useCreateChannexConnection();
  const [propertyId, setPropertyId] = useState("");
  const trimmed = propertyId.trim();
  const invalid = trimmed !== "" && !CHANNEX_ID.test(trimmed);

  return (
    <section className="rounded-xl border border-border bg-card shadow-soft">
      <div className="flex flex-col items-center px-6 pb-2 pt-10 text-center">
        <span className="flex size-12 items-center justify-center rounded-xl bg-accent text-accent-foreground">
          <Cable className="size-6" strokeWidth={1.75} />
        </span>
        <h3 className="mt-4 text-base font-semibold">Connect your Channex property</h3>
        <p className="mt-1.5 max-w-md text-sm text-muted-foreground">
          Paste the property ID from your Channex dashboard. You will then get the two webhook headers to add in
          Channex, and can map your room types.
        </p>
      </div>
      <form
        className="mx-auto max-w-md space-y-4 px-6 pb-8 pt-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (invalid || trimmed === "") return;
          create.mutate({ name: "Channex", external_property_id: trimmed }, { onSuccess: onCreated });
        }}
      >
        <FormError message={create.error?.message} />
        <Field
          label="Channex property ID"
          hint={invalid ? undefined : ID_HINT}
          error={invalid ? "Use the ID exactly as Channex shows it: letters, digits and hyphens." : null}
        >
          {(field) => (
            <Input
              {...field}
              value={propertyId}
              onChange={(event) => setPropertyId(event.target.value)}
              maxLength={64}
              spellCheck={false}
              autoComplete="off"
              required
              className="font-mono text-[13px]"
            />
          )}
        </Field>
        <SubmitButton pending={create.isPending} className="w-full" disabled={invalid}>
          <PlugZap className="size-4" />
          Connect Channex
        </SubmitButton>
      </form>
    </section>
  );
}

function CredentialsDialog({ created, onClose }: { created: ChannelConnectionCreated; onClose: () => void }) {
  const webhookUrl = useWebhookUrl();
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        // Only the explicit button closes it: the token cannot be shown again.
        onInteractOutside={(event) => event.preventDefault()}
        onEscapeKeyDown={(event) => event.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>Add this webhook in Channex</DialogTitle>
          <DialogDescription>
            In Channex, open Settings → Webhooks and create one with these values.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div className="flex items-start gap-2.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-[13px] text-amber-900">
            <ShieldAlert className="mt-px size-4 shrink-0" />
            This is the only time the token is shown. Copy it into Channex now.
          </div>
          <Secret label="Callback URL" value={webhookUrl} />
          <Secret label="Header X-Channex-Key" value={created.key_id} />
          <Secret label="Header X-Channex-Token" value={created.signing_secret} />
          <p className="text-[13px] text-muted-foreground">
            Event mask <code className="rounded bg-muted px-1 font-mono text-xs">booking</code>, with &ldquo;Send
            data&rdquo; switched on.
          </p>
        </DialogBody>
        <DialogFooter>
          <Button onClick={onClose}>I&apos;ve added it in Channex</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Secret({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[13px] font-medium">{label}</p>
      <div className="mt-2 flex items-center gap-2 rounded-lg border border-border bg-muted/50 py-1.5 pl-3 pr-1.5">
        <code className="min-w-0 flex-1 break-all font-mono text-[12.5px] leading-snug">{value}</code>
        <CopyButton value={value} label={label.toLowerCase()} />
      </div>
    </div>
  );
}

// --- the connection ------------------------------------------------------------------

function ConnectionCard({ connection }: { connection: ChannelConnection }) {
  const update = useUpdateChannelConnection();
  const test = useTestOutbound();
  const sync = useSyncChannel();
  const [editing, setEditing] = useState(false);
  const webhookUrl = useWebhookUrl();

  const toggle = () =>
    update.mutate(
      { id: connection.id, changes: { is_active: !connection.is_active } },
      {
        onSuccess: (saved) => toast.success(saved.is_active ? "Channex sync enabled" : "Channex sync paused"),
        onError: (error) => toast.error(error.message),
      },
    );

  return (
    <section aria-label="Channex connection" className="rounded-xl border border-border bg-card shadow-soft">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3 p-4 sm:p-5">
        <span
          className={cn(
            "flex size-10 shrink-0 items-center justify-center rounded-lg",
            connection.is_active ? "bg-accent text-accent-foreground" : "bg-muted text-muted-foreground",
          )}
        >
          <Cable className="size-5" strokeWidth={1.75} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium">Channex property</p>
            <span
              className={cn(
                "shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset",
                connection.is_active
                  ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
                  : "bg-slate-100 text-slate-600 ring-slate-200",
              )}
            >
              {connection.is_active ? "Active" : "Paused"}
            </span>
          </div>
          {!editing && (
            <div className="mt-0.5 flex items-center gap-1">
              <code className="truncate font-mono text-xs text-muted-foreground">
                {connection.external_property_id}
              </code>
              <CopyButton value={connection.external_property_id ?? ""} label="property ID" className="size-6" />
              <Button
                variant="ghost"
                size="icon"
                className="size-6"
                aria-label="Change property ID"
                onClick={() => setEditing(true)}
              >
                <Pencil className="size-3" />
              </Button>
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={test.isPending}
            onClick={() => test.mutate(connection.id)}
            title="Check that the API key can see this property"
          >
            {test.isPending ? <LoaderCircle className="size-3.5 animate-spin" /> : <PlugZap className="size-3.5" />}
            Test connection
          </Button>
          <Button
            size="sm"
            disabled={sync.isPending || !connection.is_active}
            title={connection.is_active ? "Send Channex availability for the coming weeks" : "Enable sync first"}
            onClick={() =>
              sync.mutate(connection.id, {
                onSuccess: ({ room_types_queued }) =>
                  toast.success("Sync queued", {
                    description: `Availability for ${room_types_queued} room type${room_types_queued === 1 ? "" : "s"} is being sent to Channex.`,
                  }),
                onError: (error) => toast.error(error.message),
              })
            }
          >
            <RefreshCw className={cn("size-3.5", sync.isPending && "animate-spin")} />
            Sync now
          </Button>
          <Button variant="outline" size="sm" disabled={update.isPending} onClick={toggle}>
            {connection.is_active ? "Pause" : "Enable"}
          </Button>
        </div>
      </div>

      {editing && <PropertyIdForm connection={connection} onDone={() => setEditing(false)} />}

      <div className="space-y-2 border-t border-border/70 px-4 py-3 text-xs sm:px-5">
        <PushStatus connection={connection} />
        {(test.data || test.isError) && (
          <p
            role="status"
            className={cn(
              "flex items-start gap-1.5 rounded-md border px-2.5 py-2 animate-in fade-in-0 slide-in-from-top-1",
              test.data?.ok
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border-destructive/20 bg-destructive/5 text-destructive",
            )}
          >
            {test.data?.ok ? (
              <CircleCheck className="mt-px size-3.5 shrink-0" />
            ) : (
              <CircleAlert className="mt-px size-3.5 shrink-0" />
            )}
            <span>
              {test.data
                ? `Test ${test.data.ok ? "succeeded" : "failed"}: ${test.data.detail} (${test.data.duration_ms} ms)`
                : test.error?.message}
            </span>
          </p>
        )}
      </div>

      <div className="border-t border-border/70 p-4 sm:p-5">
        <h3 className="flex items-center gap-2 text-[15px] font-semibold">
          <Webhook className="size-4 text-muted-foreground" />
          Channex webhook
        </h3>
        <p className="mt-1 text-[13px] text-muted-foreground">
          Bookings arrive through a webhook you create in Channex (Settings → Webhooks) with these values.
        </p>
        <dl className="mt-3 space-y-2.5 text-[13px]">
          <WebhookValue term="Callback URL">
            <code className="min-w-0 truncate font-mono text-[12.5px]">{webhookUrl}</code>
            <CopyButton value={webhookUrl} label="webhook URL" className="size-6" />
          </WebhookValue>
          <WebhookValue term="Event mask">
            <code className="font-mono text-[12.5px]">booking</code>
            <span className="text-muted-foreground">, with &ldquo;Send data&rdquo; on</span>
          </WebhookValue>
          <WebhookValue term="Header X-Channex-Key">
            <code className="min-w-0 truncate font-mono text-[12.5px]">{connection.key_id}</code>
            <CopyButton value={connection.key_id} label="key" className="size-6" />
          </WebhookValue>
          <WebhookValue term="Header X-Channex-Token">
            <span className="text-muted-foreground">The token shown once when you connected Channex.</span>
          </WebhookValue>
        </dl>
      </div>
    </section>
  );
}

function WebhookValue({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
      <dt className="shrink-0 font-medium sm:w-48">{term}</dt>
      <dd className="flex min-w-0 items-center gap-1">{children}</dd>
    </div>
  );
}

function PushStatus({ connection }: { connection: ChannelConnection }) {
  if (!connection.is_active) {
    return (
      <p className="text-muted-foreground">
        Sync is paused: Channex receives no updates and its bookings are refused.
      </p>
    );
  }
  if (connection.last_push_at === null) {
    return (
      <p className="text-muted-foreground">
        Nothing has been sent to Channex yet. Map your room types, then press Sync now.
      </p>
    );
  }
  return (
    <p
      className={cn(
        "flex items-start gap-1.5",
        connection.last_push_ok ? "text-muted-foreground" : "text-destructive",
      )}
    >
      {connection.last_push_ok ? (
        <CircleCheck className="mt-px size-3.5 shrink-0 text-emerald-600" />
      ) : (
        <CircleAlert className="mt-px size-3.5 shrink-0" />
      )}
      <span>
        Last update to Channex {format(new Date(connection.last_push_at), "d MMM, HH:mm")}:{" "}
        {connection.last_push_detail ?? (connection.last_push_ok ? "Accepted" : "Failed")}
        {!connection.last_push_ok && ". It is retried automatically for about two hours."}
      </span>
    </p>
  );
}

function PropertyIdForm({ connection, onDone }: { connection: ChannelConnection; onDone: () => void }) {
  const update = useUpdateChannelConnection();
  const [value, setValue] = useState(connection.external_property_id ?? "");
  const trimmed = value.trim();
  const invalid = !CHANNEX_ID.test(trimmed);

  return (
    <form
      className="border-t border-border/70 bg-muted/40 px-4 py-3 sm:px-5"
      onSubmit={(event) => {
        event.preventDefault();
        if (invalid) return;
        update.mutate(
          { id: connection.id, changes: { external_property_id: trimmed } },
          {
            onSuccess: () => {
              toast.success("Property ID changed", { description: "Press Sync now to update the new property." });
              onDone();
            },
          },
        );
      }}
    >
      <label htmlFor="channex-property" className="text-[13px] font-medium">
        Channex property ID
      </label>
      <div className="mt-2 flex flex-wrap gap-2">
        <Input
          id="channex-property"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          maxLength={64}
          spellCheck={false}
          autoComplete="off"
          autoFocus
          aria-invalid={invalid || update.isError}
          className="h-9 min-w-0 flex-1 basis-64 font-mono text-[12.5px]"
        />
        <SubmitButton pending={update.isPending} size="sm" className="h-9" disabled={invalid}>
          Save
        </SubmitButton>
        <Button type="button" variant="ghost" size="sm" className="h-9" onClick={onDone}>
          Cancel
        </Button>
      </div>
      <p className={cn("mt-2 text-xs", update.isError ? "text-destructive" : "text-muted-foreground")}>
        {update.isError
          ? update.error.message
          : "Change this when you move from the Channex staging property to your live one. Room type mappings are kept."}
      </p>
    </form>
  );
}

// --- room type mapping ---------------------------------------------------------------

interface Draft {
  roomType: string;
  ratePlan: string;
}

function RoomMappings({ connection }: { connection: ChannelConnection }) {
  const roomTypes = useRoomTypes();
  const mappings = useChannexMappings(connection.id);

  return (
    <section
      aria-label="Room type mapping"
      className="overflow-hidden rounded-xl border border-border bg-card shadow-soft"
    >
      <div className="border-b border-border px-4 py-3 sm:px-5">
        <h3 className="flex items-center gap-2 text-[15px] font-semibold leading-tight">
          <ArrowLeftRight className="size-4 text-muted-foreground" />
          Room type mapping
        </h3>
        <p className="mt-1 max-w-prose text-[13px] text-muted-foreground">
          Which Channex room type each of your room types is sold as. Unmapped room types are not sent to Channex,
          and Channex bookings for an unmapped Channex room type are refused.
        </p>
      </div>
      {roomTypes.isPending || mappings.isPending ? (
        <div className="space-y-3 p-5" aria-busy="true" aria-label="Loading room types">
          <div className="h-10 animate-pulse rounded-md bg-muted" />
          <div className="h-10 animate-pulse rounded-md bg-muted" />
        </div>
      ) : roomTypes.isError || mappings.isError ? (
        <p className="px-5 py-8 text-center text-sm text-muted-foreground">
          {(roomTypes.error ?? mappings.error)?.message}
        </p>
      ) : roomTypes.data.length === 0 ? (
        <p className="px-5 py-10 text-center text-sm text-muted-foreground">
          Add room types in the Inventory tab first, then map them here.
        </p>
      ) : (
        // Remounted when the saved mappings change, so the form starts from them.
        <MappingForm
          key={mappings.data.map((m) => `${m.id}:${m.channex_room_type_id}:${m.channex_rate_plan_id}`).join("|")}
          connectionId={connection.id}
          roomTypes={roomTypes.data}
          saved={mappings.data}
        />
      )}
    </section>
  );
}

function MappingForm({
  connectionId,
  roomTypes,
  saved,
}: {
  connectionId: string;
  roomTypes: RoomType[];
  saved: ChannexMapping[];
}) {
  const save = useSaveChannexMappings(connectionId);
  const initial = useMemo(() => {
    const byRoomType = new Map(saved.map((m) => [m.room_type_id, m]));
    return Object.fromEntries(
      roomTypes.map((rt) => {
        const mapping = byRoomType.get(rt.id);
        return [
          rt.id,
          { roomType: mapping?.channex_room_type_id ?? "", ratePlan: mapping?.channex_rate_plan_id ?? "" },
        ];
      }),
    ) as Record<string, Draft>;
  }, [roomTypes, saved]);
  const [draft, setDraft] = useState(initial);

  const set = (roomTypeId: string, change: Partial<Draft>) =>
    setDraft((current) => ({ ...current, [roomTypeId]: { ...current[roomTypeId], ...change } }));

  const errors = useMemo(() => validate(draft), [draft]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial);
  const mappedCount = Object.values(draft).filter((d) => d.roomType.trim() !== "").length;

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (Object.keys(errors).length > 0) return;
    const body: ChannexMappingInput[] = Object.entries(draft)
      .filter(([, d]) => d.roomType.trim() !== "")
      .map(([roomTypeId, d]) => ({
        room_type_id: roomTypeId,
        channex_room_type_id: d.roomType.trim(),
        channex_rate_plan_id: d.ratePlan.trim() || null,
      }));
    save.mutate(body, {
      onSuccess: (result) =>
        toast.success("Mapping saved", {
          description: `${result.length} room type${result.length === 1 ? "" : "s"} mapped. Press Sync now to send Channex the current availability.`,
        }),
    });
  };

  return (
    <form onSubmit={submit}>
      <div
        aria-hidden="true"
        className="hidden gap-3 border-b border-border/70 bg-muted/40 px-5 py-2 text-xs font-medium text-muted-foreground sm:grid sm:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)_minmax(0,1.2fr)]"
      >
        <span>Room type</span>
        <span>Channex room type ID</span>
        <span>Channex rate plan ID (optional)</span>
      </div>
      <ul className="divide-y divide-border/70">
        {roomTypes.map((rt) => {
          const row = draft[rt.id];
          const error = errors[rt.id];
          return (
            <li
              key={rt.id}
              className="grid gap-2 px-4 py-3 sm:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)_minmax(0,1.2fr)] sm:items-start sm:gap-3 sm:px-5"
            >
              <div className="min-w-0 sm:pt-2">
                <p className="truncate text-sm font-medium">
                  {rt.name}
                  {!rt.is_active && (
                    <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 ring-1 ring-inset ring-slate-200">
                      Inactive
                    </span>
                  )}
                </p>
                <p className="text-xs text-muted-foreground">
                  {rt.code} · up to {rt.max_occupancy} guest{rt.max_occupancy === 1 ? "" : "s"}
                </p>
              </div>
              <div>
                <label htmlFor={`cx-rt-${rt.id}`} className="mb-1 block text-xs text-muted-foreground sm:sr-only">
                  Channex room type ID for {rt.name}
                </label>
                <Input
                  id={`cx-rt-${rt.id}`}
                  value={row.roomType}
                  onChange={(event) => set(rt.id, { roomType: event.target.value })}
                  placeholder="Not sent to Channex"
                  maxLength={64}
                  spellCheck={false}
                  autoComplete="off"
                  aria-invalid={Boolean(error?.roomType)}
                  aria-describedby={error?.roomType ? `cx-rt-${rt.id}-error` : undefined}
                  className="h-9 font-mono text-[12.5px] placeholder:font-sans"
                />
                {error?.roomType && (
                  <p id={`cx-rt-${rt.id}-error`} className="mt-1 text-xs text-destructive">
                    {error.roomType}
                  </p>
                )}
              </div>
              <div>
                <label htmlFor={`cx-rp-${rt.id}`} className="mb-1 block text-xs text-muted-foreground sm:sr-only">
                  Channex rate plan ID for {rt.name} (optional)
                </label>
                <Input
                  id={`cx-rp-${rt.id}`}
                  value={row.ratePlan}
                  onChange={(event) => set(rt.id, { ratePlan: event.target.value })}
                  placeholder="Rates managed in Channex"
                  maxLength={64}
                  spellCheck={false}
                  autoComplete="off"
                  aria-invalid={Boolean(error?.ratePlan)}
                  aria-describedby={error?.ratePlan ? `cx-rp-${rt.id}-error` : undefined}
                  className="h-9 font-mono text-[12.5px] placeholder:font-sans"
                />
                {error?.ratePlan && (
                  <p id={`cx-rp-${rt.id}-error`} className="mt-1 text-xs text-destructive">
                    {error.ratePlan}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      <div className="space-y-3 border-t border-border bg-muted/30 px-4 py-3 sm:px-5">
        <FormError message={save.error?.message} />
        <div className="flex flex-wrap items-center gap-3">
          <p className="mr-auto max-w-prose text-xs text-muted-foreground">
            With a rate plan set, Sync now also sends that room type&apos;s base rate, in your hotel&apos;s currency, to
            the plan. Leave it empty if you price rooms in Channex, or if the plan uses another currency.
          </p>
          <span className="text-xs tabular-nums text-muted-foreground">
            {mappedCount} of {roomTypes.length} mapped
          </span>
          {dirty && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setDraft(initial);
                save.reset();
              }}
            >
              Discard
            </Button>
          )}
          <SubmitButton pending={save.isPending} size="sm" disabled={!dirty || Object.keys(errors).length > 0}>
            Save mapping
          </SubmitButton>
        </div>
      </div>
    </form>
  );
}

/** Problems that would make the API refuse the mapping, keyed by our room type id. */
function validate(draft: Record<string, Draft>): Record<string, { roomType?: string; ratePlan?: string }> {
  const errors: Record<string, { roomType?: string; ratePlan?: string }> = {};
  const seen = new Map<string, string>();
  for (const [roomTypeId, d] of Object.entries(draft)) {
    const roomType = d.roomType.trim();
    const ratePlan = d.ratePlan.trim();
    if (roomType !== "" && !CHANNEX_ID.test(roomType)) {
      errors[roomTypeId] = { roomType: "Letters, digits and hyphens only." };
    } else if (roomType !== "" && seen.has(roomType)) {
      errors[roomTypeId] = { roomType: "Already mapped to another room type." };
    } else if (roomType !== "") {
      seen.set(roomType, roomTypeId);
    }
    if (ratePlan !== "" && roomType === "") {
      errors[roomTypeId] = { ...errors[roomTypeId], ratePlan: "Set the Channex room type first." };
    } else if (ratePlan !== "" && !CHANNEX_ID.test(ratePlan)) {
      errors[roomTypeId] = { ...errors[roomTypeId], ratePlan: "Letters, digits and hyphens only." };
    }
  }
  return errors;
}

// --- deliveries ----------------------------------------------------------------------

function ChannexDeliveries({ connectionId }: { connectionId: string }) {
  const events = useChannelEvents(true);
  const mine = events.data?.filter((event) => event.connection_id === connectionId);

  return (
    <section
      aria-label="Channex bookings received"
      className="overflow-hidden rounded-xl border border-border bg-card shadow-soft"
    >
      <div className="border-b border-border px-4 py-3 sm:px-5">
        <h3 className="text-[15px] font-semibold leading-tight">Bookings received</h3>
        <p className="mt-0.5 text-[13px] text-muted-foreground">Recent Channex webhook calls, newest first.</p>
      </div>
      {events.isPending ? (
        <div className="space-y-3 p-5" aria-busy="true" aria-label="Loading deliveries">
          <div className="h-8 animate-pulse rounded-md bg-muted" />
        </div>
      ) : events.isError ? (
        <p className="px-5 py-8 text-center text-sm text-muted-foreground">{events.error.message}</p>
      ) : mine === undefined || mine.length === 0 ? (
        <p className="px-5 py-10 text-center text-sm text-muted-foreground">
          Nothing received yet. Bookings appear here as soon as Channex sends one.
        </p>
      ) : (
        <ul className="divide-y divide-border/70">
          {mine.map((event) => (
            <li key={event.id} className="flex items-start gap-3 px-4 py-3 sm:px-5">
              <span
                className={cn(
                  "mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium capitalize ring-1 ring-inset",
                  EVENT_STATUS[event.status] ?? EVENT_STATUS.duplicate,
                )}
              >
                {event.status}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium">
                  {event.event_type.replace(/_/g, " ")}
                  <span className="font-normal text-muted-foreground">
                    {" "}
                    · {SOURCE_STYLES[event.channel as BookingSource]?.label ?? event.channel}
                  </span>
                </p>
                <p className="mt-0.5 truncate text-xs text-muted-foreground">
                  <span className="font-mono">{event.external_booking_id}</span>
                  {event.detail ? ` · ${event.detail}` : ""}
                </p>
              </div>
              <time dateTime={event.received_at} className="shrink-0 text-xs tabular-nums text-muted-foreground">
                {format(new Date(event.received_at), "d MMM, HH:mm")}
              </time>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
