"use client";

import { format } from "date-fns";
import {
  ArrowUpFromLine,
  CircleAlert,
  CircleCheck,
  KeyRound,
  LoaderCircle,
  Plus,
  RefreshCw,
  Send,
  ShieldAlert,
  Webhook,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
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
import { Field, FormError, SubmitButton } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  useChannelConnections,
  useChannelEvents,
  useCreateChannelConnection,
  useSyncChannel,
  useTestOutbound,
  useUpdateChannelConnection,
} from "@/lib/queries";
import { SOURCE_STYLES } from "@/lib/sources";
import type { BookingSource, ChannelConnection, ChannelConnectionCreated } from "@/lib/types";
import { cn } from "@/lib/utils";

const WEBHOOK_PATH = "/api/v1/webhooks/channel-manager";

const EVENT_STATUS: Record<string, string> = {
  processed: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  duplicate: "bg-slate-100 text-slate-600 ring-slate-200",
  rejected: "bg-rose-50 text-rose-700 ring-rose-200",
};

export function ChannelConnections() {
  const connections = useChannelConnections(true);
  const events = useChannelEvents(true);
  const [creating, setCreating] = useState(false);

  // The origin is only known in the browser; rendering it on the server would not match.
  const [origin, setOrigin] = useState("");
  useEffect(() => setOrigin(window.location.origin), []);
  const webhookUrl = origin + WEBHOOK_PATH;

  const names = new Map(connections.data?.map((connection) => [connection.id, connection.name]));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-4">
        <div className="mr-auto">
          <h2 className="text-xl font-semibold tracking-tight">Channel manager</h2>
          <p className="mt-1 max-w-prose text-sm text-muted-foreground">
            API keys for two-way sync: your channel manager sends OTA bookings in, and availability is pushed back out
            whenever it changes.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus className="size-4" />
          Generate API key
        </Button>
      </div>

      {/* Keys */}
      <section aria-label="API keys" className="overflow-hidden rounded-xl border border-border bg-card shadow-soft">
        {connections.isPending ? (
          <div className="space-y-3 p-5" aria-busy="true" aria-label="Loading API keys">
            {Array.from({ length: 2 }, (_, index) => (
              <div key={index} className="h-10 animate-pulse rounded-md bg-muted" />
            ))}
          </div>
        ) : connections.isError ? (
          <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
            <CircleAlert className="size-6 text-destructive" />
            <p className="text-sm text-muted-foreground">{connections.error.message}</p>
            <Button variant="outline" size="sm" onClick={() => connections.refetch()}>
              Try again
            </Button>
          </div>
        ) : connections.data.length === 0 ? (
          <div className="flex flex-col items-center px-6 py-14 text-center">
            <span className="flex size-12 items-center justify-center rounded-xl bg-accent text-accent-foreground">
              <KeyRound className="size-6" strokeWidth={1.75} />
            </span>
            <h3 className="mt-4 text-base font-semibold">No API keys yet</h3>
            <p className="mt-1.5 max-w-sm text-sm text-muted-foreground">
              Generate a key and give it to your channel manager. Each key has its own signing secret and can be
              switched off on its own.
            </p>
            <Button className="mt-5" onClick={() => setCreating(true)}>
              <Plus className="size-4" />
              Generate your first key
            </Button>
          </div>
        ) : (
          <ul className="divide-y divide-border/70">
            {connections.data.map((connection) => (
              <ConnectionRow key={connection.id} connection={connection} />
            ))}
          </ul>
        )}
      </section>

      {/* How to connect */}
      <section
        aria-label="Integration details"
        className="rounded-xl border border-border bg-card p-4 shadow-soft sm:p-5"
      >
        <h3 className="flex items-center gap-2 text-[15px] font-semibold">
          <Webhook className="size-4 text-muted-foreground" />
          Webhook endpoint
        </h3>
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-border bg-muted/50 py-1.5 pl-3 pr-1.5">
          <span className="rounded bg-card px-1.5 py-0.5 text-[11px] font-semibold text-accent-foreground ring-1 ring-inset ring-border">
            POST
          </span>
          <code className="min-w-0 flex-1 truncate font-mono text-[12.5px]">{webhookUrl}</code>
          <CopyButton value={webhookUrl} label="webhook URL" />
        </div>
        <p className="mt-4 text-[13px] text-muted-foreground">
          Every request must carry three headers. Availability pushes sent to your outbound URL carry the same three,
          signed with the same secret, so the receiver can verify them the same way.
        </p>
        <dl className="mt-2 space-y-2 text-[13px]">
          {[
            ["X-Channel-Key", "The key ID shown above."],
            ["X-Channel-Timestamp", "The current Unix time in seconds."],
            [
              "X-Channel-Signature",
              '"sha256=" followed by the hex HMAC-SHA256 of "<timestamp>.<raw body>", keyed with the signing secret.',
            ],
          ].map(([header, meaning]) => (
            <div key={header} className="flex flex-col gap-1 sm:flex-row sm:gap-3">
              <dt className="shrink-0 sm:w-52">
                <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{header}</code>
              </dt>
              <dd className="text-muted-foreground">{meaning}</dd>
            </div>
          ))}
        </dl>
      </section>

      {/* Deliveries */}
      <section
        aria-label="Recent deliveries"
        className="overflow-hidden rounded-xl border border-border bg-card shadow-soft"
      >
        <div className="border-b border-border px-4 py-3 sm:px-5">
          <h3 className="text-[15px] font-semibold leading-tight">Recent deliveries</h3>
          <p className="mt-0.5 text-[13px] text-muted-foreground">The last 15 webhook calls, newest first.</p>
        </div>
        {events.isPending ? (
          <div className="space-y-3 p-5" aria-busy="true" aria-label="Loading deliveries">
            <div className="h-8 animate-pulse rounded-md bg-muted" />
            <div className="h-8 animate-pulse rounded-md bg-muted" />
          </div>
        ) : events.isError ? (
          <p className="px-5 py-8 text-center text-sm text-muted-foreground">{events.error.message}</p>
        ) : events.data.length === 0 ? (
          <p className="px-5 py-10 text-center text-sm text-muted-foreground">
            Nothing received yet. Deliveries appear here as soon as your channel manager sends one.
          </p>
        ) : (
          <ul className="divide-y divide-border/70">
            {events.data.map((event) => (
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
                    {event.event_type}
                    <span className="font-normal text-muted-foreground">
                      {" "}
                      · {SOURCE_STYLES[event.channel as BookingSource]?.label ?? event.channel} ·{" "}
                      <span className="font-mono text-xs">{event.external_booking_id}</span>
                    </span>
                  </p>
                  <p className="mt-0.5 truncate text-xs text-muted-foreground">
                    {names.get(event.connection_id) ?? "Unknown key"}
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

      {creating && <CreateKeyDialog onClose={() => setCreating(false)} />}
    </div>
  );
}

function ConnectionRow({ connection }: { connection: ChannelConnection }) {
  const update = useUpdateChannelConnection();
  const toggle = () =>
    update.mutate(
      { id: connection.id, changes: { is_active: !connection.is_active } },
      {
        onSuccess: (saved) => toast.success(saved.is_active ? `${saved.name} enabled` : `${saved.name} disabled`),
        onError: (error) => toast.error(error.message),
      },
    );

  return (
    <li className="px-4 py-3.5 sm:px-5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <span
          className={cn(
            "flex size-9 shrink-0 items-center justify-center rounded-lg",
            connection.is_active ? "bg-accent text-accent-foreground" : "bg-muted text-muted-foreground",
          )}
        >
          <KeyRound className="size-[18px]" strokeWidth={1.75} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className={cn("truncate text-sm font-medium", !connection.is_active && "text-muted-foreground")}>
              {connection.name}
            </p>
            <span
              className={cn(
                "shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset",
                connection.is_active
                  ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
                  : "bg-slate-100 text-slate-600 ring-slate-200",
              )}
            >
              {connection.is_active ? "Active" : "Disabled"}
            </span>
          </div>
          <div className="mt-0.5 flex items-center gap-1">
            <code className="truncate font-mono text-xs text-muted-foreground">{connection.key_id}</code>
            <CopyButton value={connection.key_id} label="key ID" className="size-6" />
            <span className="hidden text-xs text-muted-foreground sm:inline">
              · Created {format(new Date(connection.created_at), "d MMM yyyy")}
            </span>
          </div>
        </div>
        <Button variant="outline" size="sm" disabled={update.isPending} onClick={toggle}>
          {connection.is_active ? "Disable" : "Enable"}
        </Button>
      </div>
      {/* Keyed on the saved URL so the field resets when it changes on the server. */}
      <OutboundSync key={connection.outbound_url ?? ""} connection={connection} />
    </li>
  );
}

function OutboundSync({ connection }: { connection: ChannelConnection }) {
  const update = useUpdateChannelConnection();
  const test = useTestOutbound();
  const sync = useSyncChannel();
  const [url, setUrl] = useState(connection.outbound_url ?? "");

  const saved = connection.outbound_url ?? "";
  const dirty = url.trim() !== saved;
  const configured = saved !== "";

  const save = (event: React.FormEvent) => {
    event.preventDefault();
    test.reset();
    update.mutate(
      { id: connection.id, changes: { outbound_url: url.trim() || null } },
      {
        onSuccess: (result) =>
          toast.success(result.outbound_url ? "Outbound URL saved" : "Outbound sync turned off", {
            description: result.outbound_url ? "Send a test to check it is reachable." : undefined,
          }),
      },
    );
  };

  return (
    <form onSubmit={save} className="mt-3 rounded-lg border border-border bg-muted/40 p-3 sm:ml-[3.25rem]">
      <label
        htmlFor={`outbound-${connection.id}`}
        className="flex items-center gap-1.5 text-[13px] font-medium leading-none"
      >
        <ArrowUpFromLine className="size-3.5 text-muted-foreground" />
        Outbound webhook URL
      </label>
      <div className="mt-2 flex flex-wrap gap-2">
        <Input
          id={`outbound-${connection.id}`}
          type="url"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="https://your-channel-manager.com/webhooks/availability"
          maxLength={2048}
          spellCheck={false}
          autoComplete="off"
          aria-invalid={update.isError}
          aria-describedby={`outbound-${connection.id}-status`}
          className="h-9 min-w-0 flex-1 basis-64 font-mono text-[12.5px] placeholder:font-sans"
        />
        {dirty ? (
          <>
            <SubmitButton pending={update.isPending} size="sm" className="h-9">
              {url.trim() === "" ? "Remove" : "Save"}
            </SubmitButton>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-9"
              onClick={() => {
                setUrl(saved);
                update.reset();
              }}
            >
              Cancel
            </Button>
          </>
        ) : (
          configured && (
            <>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-9"
                disabled={test.isPending}
                onClick={() => test.mutate(connection.id)}
              >
                {test.isPending ? <LoaderCircle className="size-3.5 animate-spin" /> : <Send className="size-3.5" />}
                Send test
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-9"
                disabled={sync.isPending || !connection.is_active}
                title={connection.is_active ? "Push all availability for the coming weeks" : "Enable this key first"}
                onClick={() =>
                  sync.mutate(connection.id, {
                    onSuccess: ({ room_types_queued }) =>
                      toast.success("Sync queued", {
                        description: `Availability for ${room_types_queued} room type${room_types_queued === 1 ? "" : "s"} is being pushed.`,
                      }),
                    onError: (error) => toast.error(error.message),
                  })
                }
              >
                <RefreshCw className={cn("size-3.5", sync.isPending && "animate-spin")} />
                Sync now
              </Button>
            </>
          )
        )}
      </div>

      <div id={`outbound-${connection.id}-status`} className="mt-2 space-y-2 text-xs">
        {update.isError ? (
          <p role="alert" className="text-destructive">
            {update.error.message}
          </p>
        ) : !configured ? (
          <p className="text-muted-foreground">
            Optional. Leave empty and this key only receives bookings. Add your channel manager&apos;s https endpoint
            and availability is pushed to it whenever a booking changes what you can sell.
          </p>
        ) : !connection.is_active ? (
          <p className="text-muted-foreground">Pushes are paused while this key is disabled.</p>
        ) : connection.last_push_at === null ? (
          <p className="text-muted-foreground">Nothing has been pushed to this URL yet.</p>
        ) : (
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
              Last push {format(new Date(connection.last_push_at), "d MMM, HH:mm")}:{" "}
              {connection.last_push_detail ?? (connection.last_push_ok ? "Delivered" : "Failed")}
              {!connection.last_push_ok && ". It is retried automatically for about two hours."}
            </span>
          </p>
        )}

        {(test.data || test.isError) && !dirty && (
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
    </form>
  );
}

function CreateKeyDialog({ onClose }: { onClose: () => void }) {
  const create = useCreateChannelConnection();
  const [name, setName] = useState("");
  const [created, setCreated] = useState<ChannelConnectionCreated | null>(null);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        // Once the secret is on screen, only the explicit button closes the dialog:
        // a stray click outside would lose a secret that cannot be shown again.
        onInteractOutside={(event) => created && event.preventDefault()}
        onEscapeKeyDown={(event) => created && event.preventDefault()}
      >
        {created ? (
          <>
            <DialogHeader>
              <DialogTitle>Save your signing secret</DialogTitle>
              <DialogDescription>
                Give both values to your channel manager for &ldquo;
                {created.name}&rdquo;.
              </DialogDescription>
            </DialogHeader>
            <DialogBody className="space-y-4">
              <div className="flex items-start gap-2.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-[13px] text-amber-900">
                <ShieldAlert className="mt-px size-4 shrink-0" />
                This is the only time the signing secret is shown. Copy it now and store it somewhere safe. If it is
                lost, disable this key and generate a new one.
              </div>
              <Secret label="Key ID" value={created.key_id} />
              <Secret label="Signing secret" value={created.signing_secret} />
            </DialogBody>
            <DialogFooter>
              <Button onClick={onClose}>I&apos;ve saved the secret</Button>
            </DialogFooter>
          </>
        ) : (
          <form
            className="flex min-h-0 flex-col"
            onSubmit={(event) => {
              event.preventDefault();
              create.mutate(name.trim(), { onSuccess: setCreated });
            }}
          >
            <DialogHeader>
              <DialogTitle>Generate an API key</DialogTitle>
              <DialogDescription>
                Name it after the system that will use it, so you can tell keys apart later.
              </DialogDescription>
            </DialogHeader>
            <DialogBody>
              <FormError className="mb-4" message={create.error?.message} />
              <Field label="Name">
                {(field) => (
                  <Input
                    {...field}
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="Channel manager – production"
                    maxLength={100}
                    autoFocus
                    required
                  />
                )}
              </Field>
            </DialogBody>
            <DialogFooter>
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  Cancel
                </Button>
              </DialogClose>
              <SubmitButton pending={create.isPending}>Generate key</SubmitButton>
            </DialogFooter>
          </form>
        )}
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
