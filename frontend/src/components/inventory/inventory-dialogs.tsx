"use client";

import { LoaderCircle, Trash2 } from "lucide-react";
import { useId, useState } from "react";
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
import { Field, FormError, Select, SubmitButton, Textarea } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  useCreateRooms,
  useCreateRoomType,
  useDeleteRoom,
  useDeleteRoomType,
  useRooms,
  useUpdateRoom,
  useUpdateRoomType,
} from "@/lib/queries";
import { type Terms, unitGroup, useTerms } from "@/lib/terminology";
import type { Room, RoomType } from "@/lib/types";

// Each dialog is mounted only while it is open, so its form state always
// starts from the record it was opened for.
interface DialogProps {
  onClose: () => void;
}

const MONEY_PATTERN = /^\d{1,10}(\.\d{1,2})?$/;

function ActiveToggle({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description: string;
}) {
  const id = useId();
  return (
    <label
      htmlFor={id}
      className="flex cursor-pointer items-start gap-3 rounded-lg border border-border bg-muted/40 px-3.5 py-3"
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-0.5 size-4 shrink-0 rounded accent-[rgb(var(--primary))]"
      />
      <span>
        <span className="block text-[13px] font-medium leading-tight">{label}</span>
        <span className="mt-1 block text-xs leading-snug text-muted-foreground">{description}</span>
      </span>
    </label>
  );
}

/** "Deluxe King" -> "DK", "Standard" -> "STA" */
function suggestCode(name: string): string {
  const words = name.toUpperCase().match(/[A-Z0-9]+/g) ?? [];
  if (words.length === 0) return "";
  if (words.length === 1) return words[0].slice(0, 3);
  return words
    .map((word) => word[0])
    .join("")
    .slice(0, 4);
}

export function RoomTypeDialog({ roomType, onClose }: DialogProps & { roomType: RoomType | null }) {
  const words = useTerms();
  const create = useCreateRoomType();
  const update = useUpdateRoomType();
  const mutation = roomType ? update : create;

  const [name, setName] = useState(roomType?.name ?? "");
  const [code, setCode] = useState(roomType?.code ?? "");
  // The code follows the name until the user edits it themselves.
  const [codeEdited, setCodeEdited] = useState(roomType !== null);
  const [rate, setRate] = useState(roomType ? Number(roomType.base_rate).toString() : "");
  const [baseOccupancy, setBaseOccupancy] = useState(String(roomType?.base_occupancy ?? 2));
  const [maxOccupancy, setMaxOccupancy] = useState(String(roomType?.max_occupancy ?? 2));
  const [description, setDescription] = useState(roomType?.description ?? "");
  const [isActive, setIsActive] = useState(roomType?.is_active ?? true);
  const [submitted, setSubmitted] = useState(false);

  const rateError = MONEY_PATTERN.test(rate.trim()) ? null : "Enter an amount such as 4500 or 4500.50.";
  const occupancyError =
    Number(maxOccupancy) < Number(baseOccupancy) ? "Can't be lower than the standard occupancy." : null;

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    if (rateError || occupancyError) return;
    const input = {
      name: name.trim(),
      code: code.trim(),
      description: description.trim() || null,
      base_occupancy: Number(baseOccupancy),
      max_occupancy: Number(maxOccupancy),
      base_rate: rate.trim(),
    };
    const onSuccess = (saved: RoomType) => {
      toast.success(roomType ? `${saved.name} updated` : `${saved.name} added`, {
        description: roomType ? undefined : `Now add the ${words.unitsLower} of this type.`,
      });
      onClose();
    };
    if (roomType) update.mutate({ id: roomType.id, changes: { ...input, is_active: isActive } }, { onSuccess });
    else create.mutate(input, { onSuccess });
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form onSubmit={onSubmit} className="flex min-h-0 flex-col">
          <DialogHeader>
            <DialogTitle>
              {roomType ? `Edit ${words.unitType.toLowerCase()}` : `Add a ${words.unitType.toLowerCase()}`}
            </DialogTitle>
            <DialogDescription>
              A category you sell, such as Standard or Deluxe. Bookings are taken against it.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <FormError className="mb-4" message={mutation.error?.message} />
            <div className="grid gap-4 sm:grid-cols-[1fr_8rem]">
              <Field label="Name">
                {(field) => (
                  <Input
                    {...field}
                    value={name}
                    onChange={(event) => {
                      setName(event.target.value);
                      if (!codeEdited) setCode(suggestCode(event.target.value));
                    }}
                    placeholder="Deluxe"
                    maxLength={100}
                    autoFocus
                    required
                  />
                )}
              </Field>
              <Field label="Code">
                {(field) => (
                  <Input
                    {...field}
                    value={code}
                    onChange={(event) => {
                      setCodeEdited(true);
                      setCode(event.target.value.toUpperCase());
                    }}
                    placeholder="DLX"
                    maxLength={20}
                    autoCapitalize="characters"
                    spellCheck={false}
                    required
                  />
                )}
              </Field>
              <Field
                label="Rate per night"
                hint="Before tax, in rupees."
                error={submitted ? rateError : null}
                className="sm:col-span-2"
              >
                {(field) => (
                  <div className="relative">
                    <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                      ₹
                    </span>
                    <Input
                      {...field}
                      value={rate}
                      onChange={(event) => setRate(event.target.value)}
                      placeholder="4500"
                      inputMode="decimal"
                      className="pl-7"
                      required
                    />
                  </div>
                )}
              </Field>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-4">
              <Field label="Standard occupancy" hint="Guests included in the rate.">
                {(field) => (
                  <Input
                    {...field}
                    type="number"
                    min={1}
                    max={20}
                    value={baseOccupancy}
                    onChange={(event) => setBaseOccupancy(event.target.value)}
                    required
                  />
                )}
              </Field>
              <Field
                label="Maximum occupancy"
                hint="Most guests it sleeps. Above this, staff see a warning, not a block."
                error={submitted ? occupancyError : null}
              >
                {(field) => (
                  <Input
                    {...field}
                    type="number"
                    min={1}
                    max={20}
                    value={maxOccupancy}
                    onChange={(event) => setMaxOccupancy(event.target.value)}
                    required
                  />
                )}
              </Field>
            </div>
            <Field label="Description (optional)" className="mt-4">
              {(field) => (
                <Textarea
                  {...field}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  rows={2}
                  placeholder="King bed, sea view, balcony"
                />
              )}
            </Field>
            {roomType && (
              <div className="mt-4">
                <ActiveToggle
                  checked={isActive}
                  onChange={setIsActive}
                  label="Available for sale"
                  description={`Turn off to stop selling this ${words.unitType.toLowerCase()} without losing its history.`}
                />
              </div>
            )}
          </DialogBody>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <SubmitButton pending={mutation.isPending}>{roomType ? "Save changes" : `Add ${words.unitType.toLowerCase()}`}</SubmitButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** "101, 102 103" -> ["101", "102", "103"], without repeats. */
function parseRoomNumbers(value: string): string[] {
  return Array.from(new Set(value.split(/[\s,;]+/).filter(Boolean)));
}

export function AddRoomsDialog({ roomType, onClose }: DialogProps & { roomType: RoomType }) {
  const createRooms = useCreateRooms();
  const words = useTerms();
  const groups = useGroupNames();
  const [numbers, setNumbers] = useState("");
  const [floor, setFloor] = useState("");
  const [rejected, setRejected] = useState<string | null>(null);

  const parsed = parseRoomNumbers(numbers);
  const tooLong = parsed.find((number) => number.length > 20);

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (parsed.length === 0 || tooLong) return;
    setRejected(null);
    createRooms.mutate(
      { room_type_id: roomType.id, floor_or_zone: floor.trim() || null, room_numbers: parsed },
      {
        onSuccess: ({ created, failed }) => {
          if (created.length > 0) {
            toast.success(
              created.length === 1
                ? `${words.unit} ${created[0].room_number} added`
                : `${created.length} ${words.unitsLower} added to ${roomType.name}`,
            );
          }
          if (failed.length === 0) return onClose();
          // Leave only the numbers that still need attention in the box.
          setNumbers(failed.map((item) => item.room_number).join(", "));
          setRejected(
            failed.length === 1
              ? `${words.unit} ${failed[0].room_number} was not added: ${failed[0].message}.`
              : `${failed.length} ${words.unitsLower} were not added (${failed.map((item) => item.room_number).join(", ")}): ${failed[0].message}.`,
          );
        },
      },
    );
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form onSubmit={onSubmit} className="flex min-h-0 flex-col">
          <DialogHeader>
            <DialogTitle>
              Add {words.unitsLower} to {roomType.name}
            </DialogTitle>
            <DialogDescription>
              The physical {words.unitsLower} guests are assigned to. Add one, or several at once.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <FormError className="mb-4" message={rejected ?? createRooms.error?.message} />
            <div className="grid gap-4 sm:grid-cols-[1fr_11rem]">
              <Field
                label={`${words.unit} numbers`}
                hint={
                  parsed.length > 1
                    ? `${parsed.length} ${words.unitsLower} will be added.`
                    : "Separate several with commas or spaces: 101, 102, 103"
                }
                error={tooLong ? `"${tooLong}" is longer than 20 characters.` : null}
              >
                {(field) => (
                  <Input
                    {...field}
                    value={numbers}
                    onChange={(event) => setNumbers(event.target.value)}
                    placeholder="101, 102, 103"
                    autoComplete="off"
                    autoFocus
                    required
                  />
                )}
              </Field>
              <GroupField
                words={words}
                groups={groups}
                value={floor}
                onChange={setFloor}
                derived={parsed.length > 0 ? unitGroup({ room_number: parsed[0], floor_or_zone: null }, words) : null}
              />
            </div>
          </DialogBody>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <SubmitButton pending={createRooms.isPending}>
              {parsed.length > 1 ? `Add ${parsed.length} ${words.unitsLower}` : `Add ${words.unitLower}`}
            </SubmitButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function EditRoomDialog({
  room,
  roomTypes,
  onClose,
  onDelete,
}: DialogProps & { room: Room; roomTypes: RoomType[]; onDelete: () => void }) {
  const update = useUpdateRoom();
  const words = useTerms();
  const groups = useGroupNames();
  const [number, setNumber] = useState(room.room_number);
  const [floor, setFloor] = useState(room.floor_or_zone ?? "");
  const [roomTypeId, setRoomTypeId] = useState(room.room_type_id);
  const [isActive, setIsActive] = useState(room.is_active);

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    update.mutate(
      {
        id: room.id,
        changes: {
          room_number: number.trim(),
          floor_or_zone: floor.trim() || null,
          room_type_id: roomTypeId,
          is_active: isActive,
        },
      },
      {
        onSuccess: (saved) => {
          toast.success(`${words.unit} ${saved.room_number} updated`);
          onClose();
        },
      },
    );
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form onSubmit={onSubmit} className="flex min-h-0 flex-col">
          <DialogHeader>
            <DialogTitle>
              {words.unit} {room.room_number}
            </DialogTitle>
            <DialogDescription>
              Rename it, regroup it, move it to another {words.unitType.toLowerCase()}, or mark it out of order.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <FormError className="mb-4" message={update.error?.message} />
            <div className="grid grid-cols-2 gap-4">
              <Field label={`${words.unit} number`}>
                {(field) => (
                  <Input
                    {...field}
                    value={number}
                    onChange={(event) => setNumber(event.target.value)}
                    maxLength={20}
                    autoComplete="off"
                    required
                  />
                )}
              </Field>
              <GroupField
                words={words}
                groups={groups}
                value={floor}
                onChange={setFloor}
                derived={unitGroup({ room_number: number || room.room_number, floor_or_zone: null }, words)}
              />
              <Field label={words.unitType} className="col-span-2">
                {(field) => (
                  <Select
                    {...field}
                    value={roomTypeId}
                    onChange={(event) => setRoomTypeId(event.target.value)}
                  >
                    {roomTypes.map((roomType) => (
                      <option key={roomType.id} value={roomType.id}>
                        {roomType.name} ({roomType.code}){roomType.is_active ? "" : " · not for sale"}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
            </div>
            <div className="mt-4">
              <ActiveToggle
                checked={isActive}
                onChange={setIsActive}
                label="In service"
                description={`Turn off for maintenance or long repairs. The ${words.unitLower} shows as out of order on the property map and stops counting towards what you can sell.`}
              />
            </div>
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={onDelete}
              className="text-destructive hover:bg-destructive/10 hover:text-destructive sm:mr-auto"
            >
              <Trash2 className="size-4" />
              Delete {words.unitLower}
            </Button>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <SubmitButton pending={update.isPending}>Save changes</SubmitButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function DeleteDialog({ target, onClose }: DialogProps & { target: { roomType: RoomType } | { room: Room } }) {
  const deleteRoomType = useDeleteRoomType();
  const deleteRoom = useDeleteRoom();
  const isType = "roomType" in target;
  const mutation = isType ? deleteRoomType : deleteRoom;
  const words = useTerms();
  const label = isType ? target.roomType.name : `${words.unit} ${target.room.room_number}`;

  function onConfirm() {
    mutation.mutate(isType ? target.roomType.id : target.room.id, {
      onSuccess: () => {
        toast.success(`${label} deleted`);
        onClose();
      },
    });
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Delete {label}?</DialogTitle>
          <DialogDescription>
            This can&apos;t be undone.{" "}
            {isType
              ? `A ${words.unitType.toLowerCase()} that has ${words.unitsLower} or reservations can't be deleted; stop selling it instead.`
              : `A ${words.unitLower} that has reservations can't be deleted; take it out of service instead.`}
          </DialogDescription>
        </DialogHeader>
        <DialogBody className={mutation.isError ? undefined : "py-2"}>
          <FormError className="mb-4" message={mutation.error?.message} />
        </DialogBody>
        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="outline">
              Cancel
            </Button>
          </DialogClose>
          <Button
            type="button"
            onClick={onConfirm}
            disabled={mutation.isPending}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {mutation.isPending && <LoaderCircle className="size-4 animate-spin" />}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** The groups already in use, offered as suggestions so spellings stay consistent. */
function useGroupNames(): string[] {
  const rooms = useRooms().data ?? [];
  return Array.from(new Set(rooms.map((room) => room.floor_or_zone).filter((name): name is string => !!name))).sort();
}

function GroupField({
  words,
  groups,
  value,
  onChange,
  derived,
}: {
  words: Terms;
  groups: string[];
  value: string;
  onChange: (value: string) => void;
  /** What a blank value is shown as. */
  derived: string | null;
}) {
  const listId = useId();
  return (
    <Field
      label={`${words.group} (optional)`}
      hint={value.trim() === "" && derived ? `Blank shows as "${derived}".` : undefined}
    >
      {(field) => (
        <>
          <Input
            {...field}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={words.groupShort === "Floor" ? "1st Floor" : `${words.groupShort} A`}
            maxLength={50}
            list={listId}
            autoComplete="off"
          />
          <datalist id={listId}>
            {groups.map((group) => (
              <option key={group} value={group} />
            ))}
          </datalist>
        </>
      )}
    </Field>
  );
}
