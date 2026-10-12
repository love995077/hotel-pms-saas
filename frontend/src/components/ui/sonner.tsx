"use client";

import { Toaster as Sonner } from "sonner";

export function Toaster(props: React.ComponentProps<typeof Sonner>) {
  return (
    <Sonner
      position="bottom-right"
      toastOptions={{
        classNames: {
          toast: "!rounded-lg !border !border-border !bg-card !text-foreground !shadow-lift !font-sans",
          description: "!text-muted-foreground",
          success: "[&_[data-icon]]:!text-emerald-600",
          error: "[&_[data-icon]]:!text-destructive",
        },
      }}
      {...props}
    />
  );
}
