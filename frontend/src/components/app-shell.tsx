"use client";

import { useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { BookOpenCheck, Building2, LayoutDashboard, LoaderCircle, LogOut, Menu, Settings, Users } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  Sidebar,
  SidebarFooter,
  SidebarHeader,
  SidebarItem,
  SidebarNav,
  SidebarSection,
  SidebarToggle,
  useSidebar,
} from "@/components/ui/sidebar";
import { APP_NAME } from "@/lib/constants";
import { useCurrentUser } from "@/lib/queries";
import type { CurrentUser } from "@/lib/types";
import { cn, initials } from "@/lib/utils";
import { hasValidSession, useAuthStore } from "@/stores/auth";

const NAVIGATION = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/reservations", label: "Reservations", icon: BookOpenCheck },
  { href: "/guests", label: "Guests", icon: Users },
] as const;

// Shown to owners and managers only; the API enforces the same rule.
const ADMINISTRATION = [{ href: "/settings", label: "Settings", icon: Settings }] as const;

const ROLE_LABELS: Record<CurrentUser["role"], string> = {
  owner: "Owner",
  manager: "Manager",
  front_desk: "Front desk",
  housekeeping: "Housekeeping",
  accountant: "Accountant",
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { token, expiresAt, hydrated, hotelSlug, clearSession } = useAuthStore();
  const signedIn = hydrated && hasValidSession({ token, expiresAt });

  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const user = useCurrentUser(signedIn).data;

  useEffect(() => {
    if (hydrated && !signedIn) router.replace("/login");
  }, [hydrated, signedIn, router]);

  if (!signedIn) {
    return (
      <div className="flex h-dvh items-center justify-center">
        <LoaderCircle className="size-5 animate-spin text-muted-foreground" aria-label="Loading" />
      </div>
    );
  }

  const signOut = () => {
    clearSession();
    // Drop every cached response so the next user never sees this hotel's data.
    queryClient.clear();
  };

  const canManage = user?.role === "owner" || user?.role === "manager";
  const current = [...NAVIGATION, ...ADMINISTRATION].find((item) => pathname.startsWith(item.href));

  return (
    <div className="flex h-dvh overflow-hidden">
      {mobileOpen && (
        <button
          type="button"
          aria-label="Close menu"
          onClick={() => setMobileOpen(false)}
          className="fixed inset-0 z-40 bg-foreground/40 backdrop-blur-[2px] animate-in fade-in-0 lg:hidden"
        />
      )}

      <div
        className={cn(
          "fixed inset-y-0 left-0 z-50 transition-transform duration-300 ease-out lg:static lg:translate-x-0",
          mobileOpen ? "translate-x-0 shadow-lift" : "-translate-x-full",
        )}
      >
        <Sidebar collapsed={collapsed && !mobileOpen} onCollapsedChange={setCollapsed}>
          <SidebarHeader>
            <Brand />
            <SidebarToggle className="ml-auto hidden lg:flex" />
          </SidebarHeader>

          <SidebarNav>
            <SidebarSection label="Front office">
              {NAVIGATION.map(({ href, label, icon: Icon }) => (
                <SidebarItem
                  key={href}
                  href={href}
                  active={pathname.startsWith(href)}
                  icon={<Icon className="size-[18px]" strokeWidth={1.75} />}
                  onNavigate={() => setMobileOpen(false)}
                >
                  {label}
                </SidebarItem>
              ))}
            </SidebarSection>
            {canManage && (
              <SidebarSection label="Administration">
                {ADMINISTRATION.map(({ href, label, icon: Icon }) => (
                  <SidebarItem
                    key={href}
                    href={href}
                    active={pathname.startsWith(href)}
                    icon={<Icon className="size-[18px]" strokeWidth={1.75} />}
                    onNavigate={() => setMobileOpen(false)}
                  >
                    {label}
                  </SidebarItem>
                ))}
              </SidebarSection>
            )}
          </SidebarNav>

          <SidebarFooter>
            <UserFooter user={user} onSignOut={signOut} />
          </SidebarFooter>
        </Sidebar>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-card/80 px-4 backdrop-blur lg:px-6">
          <button
            type="button"
            aria-label="Open menu"
            onClick={() => setMobileOpen(true)}
            className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground lg:hidden"
          >
            <Menu className="size-[18px]" />
          </button>
          <h1 className="text-[15px] font-semibold">{current?.label ?? APP_NAME}</h1>
          <div className="ml-auto flex items-center gap-3 text-[13px] text-muted-foreground">
            <span className="hidden sm:inline">{format(new Date(), "EEEE, d MMMM yyyy")}</span>
            {hotelSlug && (
              <span className="flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 font-medium text-foreground">
                <Building2 className="size-3.5 text-muted-foreground" />
                {hotelSlug}
              </span>
            )}
          </div>
        </header>

        <main className="scroll-slim min-h-0 flex-1 overflow-y-auto p-4 lg:p-6">{children}</main>
      </div>
    </div>
  );
}

function Brand() {
  const { collapsed, toggleCollapsed } = useSidebar();
  const mark = (
    <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-white/25 to-white/5 ring-1 ring-inset ring-white/20">
      <span className="size-3 rotate-45 rounded-[3px] bg-white" />
    </span>
  );
  if (collapsed) {
    return (
      <button type="button" onClick={toggleCollapsed} aria-label="Expand sidebar" className="rounded-lg">
        {mark}
      </button>
    );
  }
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      {mark}
      <span className="truncate text-[15px] font-semibold tracking-tight">{APP_NAME}</span>
    </div>
  );
}

function UserFooter({ user, onSignOut }: { user: CurrentUser | undefined; onSignOut: () => void }) {
  const { collapsed } = useSidebar();
  return (
    <>
      <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-white/15 text-[11px] font-semibold ring-1 ring-inset ring-white/20">
        {user ? initials(user.full_name) : "··"}
      </span>
      {!collapsed && (
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium leading-tight">{user?.full_name ?? "Loading…"}</p>
          <p className="truncate text-[11.5px] leading-tight text-sidebar-foreground/55">
            {user ? ROLE_LABELS[user.role] : " "}
          </p>
        </div>
      )}
      <button
        type="button"
        onClick={onSignOut}
        aria-label="Sign out"
        title="Sign out"
        className="flex size-8 shrink-0 items-center justify-center rounded-md text-sidebar-foreground/60 outline-none transition-colors hover:bg-white/10 hover:text-sidebar-foreground focus-visible:ring-2 focus-visible:ring-white/60 focus-visible:ring-offset-0"
      >
        <LogOut className="size-4" strokeWidth={1.75} />
      </button>
    </>
  );
}
