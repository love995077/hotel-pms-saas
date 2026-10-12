"use client";

import { BedDouble, CircleAlert, DoorOpen, Layers, Lock, Pencil, Plus, Trash2, Users } from "lucide-react";
import { useMemo, useState } from "react";

import { AddRoomsDialog, DeleteDialog, EditRoomDialog, RoomTypeDialog } from "@/components/inventory/inventory-dialogs";
import { Button } from "@/components/ui/button";
import { useCurrentUser, useRooms, useRoomTypes } from "@/lib/queries";
import type { Room, RoomType } from "@/lib/types";
import { cn, formatMoney } from "@/lib/utils";

type OpenDialog =
  | { kind: "room-type"; roomType: RoomType | null }
  | { kind: "add-rooms"; roomType: RoomType }
  | { kind: "edit-room"; room: Room }
  | { kind: "delete-room-type"; roomType: RoomType }
  | { kind: "delete-room"; room: Room };

const byRoomNumber = new Intl.Collator("en", { numeric: true });

export function InventorySettings() {
  const roomTypes = useRoomTypes();
  const rooms = useRooms();
  const user = useCurrentUser().data;
  // The API enforces this; hiding the controls just avoids offering actions that would be refused.
  const canManage = user?.role === "owner" || user?.role === "manager";

  const [dialog, setDialog] = useState<OpenDialog | null>(null);
  const close = () => setDialog(null);

  const roomsByType = useMemo(() => {
    const grouped = new Map<string, Room[]>();
    const sorted = [...(rooms.data ?? [])].sort((a, b) => byRoomNumber.compare(a.room_number, b.room_number));
    for (const room of sorted) {
      const list = grouped.get(room.room_type_id) ?? [];
      list.push(room);
      grouped.set(room.room_type_id, list);
    }
    return grouped;
  }, [rooms.data]);

  const types = roomTypes.data;
  const allRooms = rooms.data;
  const failure = roomTypes.error ?? rooms.error;

  const activeTypes = new Set(types?.filter((type) => type.is_active).map((type) => type.id));
  const sellable = allRooms?.filter((room) => room.is_active && activeTypes.has(room.room_type_id)).length ?? 0;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-4">
        <div className="mr-auto">
          <h2 className="text-xl font-semibold tracking-tight">Inventory</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            The room types you sell and the physical rooms behind them.
          </p>
        </div>
        {canManage && types && types.length > 0 && (
          <Button onClick={() => setDialog({ kind: "room-type", roomType: null })}>
            <Plus className="size-4" />
            Add room type
          </Button>
        )}
      </div>

      {user && !canManage && (
        <div className="flex items-center gap-2.5 rounded-lg border border-border bg-card px-4 py-3 text-[13px] text-muted-foreground shadow-soft">
          <Lock className="size-4 shrink-0" />
          Only the owner or a manager can change the inventory. You can view it here.
        </div>
      )}

      {failure ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-border bg-card px-6 py-16 text-center shadow-soft">
          <CircleAlert className="size-6 text-destructive" />
          <p className="text-sm text-muted-foreground">{failure.message}</p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void roomTypes.refetch();
              void rooms.refetch();
            }}
          >
            Try again
          </Button>
        </div>
      ) : !types || !allRooms ? (
        <div className="space-y-4" aria-busy="true" aria-label="Loading inventory">
          {Array.from({ length: 2 }, (_, index) => (
            <div key={index} className="h-40 animate-pulse rounded-xl border border-border bg-card" />
          ))}
        </div>
      ) : types.length === 0 ? (
        <div className="flex flex-col items-center rounded-xl border border-dashed border-input bg-card px-6 py-16 text-center shadow-soft">
          <span className="flex size-12 items-center justify-center rounded-xl bg-accent text-accent-foreground">
            <BedDouble className="size-6" strokeWidth={1.75} />
          </span>
          <h3 className="mt-4 text-base font-semibold">Set up your rooms</h3>
          <p className="mt-1.5 max-w-sm text-sm text-muted-foreground">
            Start with a room type such as Standard or Deluxe, then add the rooms of that type. They appear on the
            tape chart straight away.
          </p>
          {canManage && (
            <Button className="mt-5" onClick={() => setDialog({ kind: "room-type", roomType: null })}>
              <Plus className="size-4" />
              Add your first room type
            </Button>
          )}
        </div>
      ) : (
        <>
          <dl className="grid grid-cols-3 gap-3">
            <Stat icon={Layers} label="Room types" value={types.length} />
            <Stat icon={DoorOpen} label="Rooms" value={allRooms.length} />
            <Stat icon={BedDouble} label="Sellable rooms" value={sellable} />
          </dl>

          <div className="space-y-4">
            {types.map((roomType) => (
              <RoomTypeCard
                key={roomType.id}
                roomType={roomType}
                rooms={roomsByType.get(roomType.id) ?? []}
                canManage={canManage}
                onOpen={setDialog}
              />
            ))}
          </div>
        </>
      )}

      {dialog?.kind === "room-type" && <RoomTypeDialog roomType={dialog.roomType} onClose={close} />}
      {dialog?.kind === "add-rooms" && <AddRoomsDialog roomType={dialog.roomType} onClose={close} />}
      {dialog?.kind === "edit-room" && (
        <EditRoomDialog
          room={dialog.room}
          roomTypes={types ?? []}
          onClose={close}
          onDelete={() => setDialog({ kind: "delete-room", room: dialog.room })}
        />
      )}
      {dialog?.kind === "delete-room-type" && <DeleteDialog target={{ roomType: dialog.roomType }} onClose={close} />}
      {dialog?.kind === "delete-room" && <DeleteDialog target={{ room: dialog.room }} onClose={close} />}
    </div>
  );
}

function Stat({ icon: Icon, label, value }: { icon: typeof Layers; label: string; value: number }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3 shadow-soft">
      <span className="hidden size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground sm:flex">
        <Icon className="size-[18px]" strokeWidth={1.75} />
      </span>
      <div className="min-w-0">
        <dt className="truncate text-xs text-muted-foreground">{label}</dt>
        <dd className="text-xl font-semibold leading-tight tabular-nums">{value}</dd>
      </div>
    </div>
  );
}

function RoomTypeCard({
  roomType,
  rooms,
  canManage,
  onOpen,
}: {
  roomType: RoomType;
  rooms: Room[];
  canManage: boolean;
  onOpen: (dialog: OpenDialog) => void;
}) {
  const occupancy =
    roomType.base_occupancy === roomType.max_occupancy
      ? `Sleeps ${roomType.max_occupancy}`
      : `Sleeps ${roomType.base_occupancy}–${roomType.max_occupancy}`;

  return (
    <section
      aria-label={roomType.name}
      className="overflow-hidden rounded-xl border border-border bg-card shadow-soft"
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3 border-b border-border px-4 py-3.5 sm:px-5">
        <div className="mr-auto min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className={cn("text-[15px] font-semibold leading-tight", !roomType.is_active && "text-muted-foreground")}>
              {roomType.name}
            </h3>
            <span className="rounded-md bg-accent px-1.5 py-0.5 text-[11px] font-semibold tracking-wide text-accent-foreground">
              {roomType.code}
            </span>
            {!roomType.is_active && (
              <span className="rounded-md border border-border px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                Not for sale
              </span>
            )}
          </div>
          <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted-foreground">
            <span>
              <span className="font-medium text-foreground">{formatMoney(roomType.base_rate)}</span> / night
            </span>
            <span className="flex items-center gap-1">
              <Users className="size-3.5" />
              {occupancy}
            </span>
            <span>
              {rooms.length} {rooms.length === 1 ? "room" : "rooms"}
            </span>
          </p>
          {roomType.description && (
            <p className="mt-1.5 max-w-prose text-[13px] text-muted-foreground">{roomType.description}</p>
          )}
        </div>
        {canManage && (
          <div className="flex items-center gap-1">
            <Button variant="outline" size="sm" onClick={() => onOpen({ kind: "add-rooms", roomType })}>
              <Plus className="size-3.5" />
              Add rooms
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label={`Edit ${roomType.name}`}
              title="Edit"
              onClick={() => onOpen({ kind: "room-type", roomType })}
            >
              <Pencil className="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label={`Delete ${roomType.name}`}
              title="Delete"
              onClick={() => onOpen({ kind: "delete-room-type", roomType })}
              className="hover:bg-destructive/10 hover:text-destructive"
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        )}
      </div>

      {rooms.length === 0 ? (
        <p className="px-5 py-6 text-[13px] text-muted-foreground">
          No rooms yet. {canManage ? "Add the rooms of this type so they can be booked and assigned." : ""}
        </p>
      ) : (
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(6.75rem,1fr))] gap-2 p-4 sm:p-5">
          {rooms.map((room) => {
            const chip = (
              <>
                <span className="block text-sm font-semibold leading-tight tabular-nums">{room.room_number}</span>
                <span className="mt-0.5 block truncate text-[11px] leading-tight text-muted-foreground">
                  {!room.is_active ? "Out of service" : room.floor ? `Floor ${room.floor}` : " "}
                </span>
              </>
            );
            const chipClass = cn(
              "block w-full rounded-lg border px-3 py-2 text-left",
              room.is_active ? "border-border bg-background/60" : "border-dashed border-input text-muted-foreground",
            );
            return (
              <li key={room.id}>
                {canManage ? (
                  <button
                    type="button"
                    aria-label={`Edit room ${room.room_number}`}
                    onClick={() => onOpen({ kind: "edit-room", room })}
                    className={cn(
                      chipClass,
                      "transition-[border-color,background-color,box-shadow] duration-150 hover:border-ring/60 hover:bg-accent/60 hover:shadow-soft",
                    )}
                  >
                    {chip}
                  </button>
                ) : (
                  <div className={chipClass}>{chip}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
