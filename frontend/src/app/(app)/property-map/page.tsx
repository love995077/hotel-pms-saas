import type { Metadata } from "next";

import { PropertyMap } from "@/components/property-map/property-map";

export const metadata: Metadata = { title: "Property map" };

export default function PropertyMapPage() {
  return (
    <div className="mx-auto max-w-[1600px]">
      <PropertyMap />
    </div>
  );
}
