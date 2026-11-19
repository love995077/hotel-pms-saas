"use client";

import { useState } from "react";
import { toast } from "sonner";

import { PropertyTypePicker } from "@/components/settings/property-type-picker";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { FormError, SubmitButton } from "@/components/ui/field";
import { useUpdateHotel } from "@/lib/queries";
import { propertyTypeLabel } from "@/lib/terminology";
import type { PropertyType } from "@/lib/types";

/**
 * Asked once, of an owner or manager, when the property has not chosen a type
 * (properties created before types existed, or from the command line).
 * "Later" hides it for this visit; the app uses hotel terms meanwhile.
 */
export function PropertyTypePrompt({ onDismiss }: { onDismiss: () => void }) {
  const update = useUpdateHotel();
  const [choice, setChoice] = useState<PropertyType>("hotel");

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    update.mutate(
      { property_type: choice },
      { onSuccess: () => toast.success(`Set up as a ${propertyTypeLabel(choice).toLowerCase()}`) },
    );
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onDismiss()}>
      <DialogContent className="max-w-xl">
        <form onSubmit={onSubmit} className="flex min-h-0 flex-col">
          <DialogHeader>
            <DialogTitle>What type of property are you managing?</DialogTitle>
            <DialogDescription>
              This sets the words used across the app, such as rooms and floors or beds and dormitories. You can change
              it anytime in Settings, Property profile.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <FormError className="mb-4" message={update.error?.message} />
            <PropertyTypePicker value={choice} onChange={setChoice} name="first-property-type" />
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onDismiss}>
              Later
            </Button>
            <SubmitButton pending={update.isPending}>Continue</SubmitButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
