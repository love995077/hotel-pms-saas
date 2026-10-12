import type { Metadata } from "next";

import { DashboardStats } from "@/components/dashboard-stats";
import { Performance } from "@/components/dashboard/performance";
import { TapeChart } from "@/components/tape-chart/tape-chart";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage() {
  return (
    <div className="mx-auto flex max-w-[1600px] flex-col gap-4 lg:gap-6">
      <Performance />
      <DashboardStats />
      <TapeChart />
    </div>
  );
}
