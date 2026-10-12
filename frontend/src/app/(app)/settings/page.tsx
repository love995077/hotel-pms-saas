"use client";

import { Building2, KeyRound, Layers } from "lucide-react";
import { useState } from "react";

import { InventorySettings } from "@/components/inventory/inventory-settings";
import { ChannelConnections } from "@/components/settings/channel-connections";
import { HotelProfile } from "@/components/settings/hotel-profile";
import { Segmented } from "@/components/ui/field";
import { useCurrentUser } from "@/lib/queries";
import { can } from "@/lib/roles";

type Section = "inventory" | "channels" | "profile";

export default function SettingsPage() {
  const [section, setSection] = useState<Section>("inventory");
  // API keys and the hotel profile are for owners and managers only; other roles never see the tabs.
  const canManage = can(useCurrentUser().data?.role, "management");

  return (
    <div className="mx-auto max-w-[1100px] space-y-5">
      {canManage && (
        <Segmented
          label="Settings section"
          value={section}
          onChange={setSection}
          options={[
            {
              value: "inventory",
              label: (
                <>
                  <Layers className="size-3.5" /> Inventory
                </>
              ),
            },
            {
              value: "channels",
              label: (
                <>
                  <KeyRound className="size-3.5" /> Channel manager
                </>
              ),
            },
            {
              value: "profile",
              label: (
                <>
                  <Building2 className="size-3.5" /> Hotel profile
                </>
              ),
            },
          ]}
        />
      )}
      {canManage && section === "channels" ? (
        <ChannelConnections />
      ) : canManage && section === "profile" ? (
        <HotelProfile />
      ) : (
        <InventorySettings />
      )}
    </div>
  );
}
