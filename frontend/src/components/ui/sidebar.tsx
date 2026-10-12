"use client";

/**
 * Collapsible app sidebar: shrinks to an icon rail, with sections, badges, a
 * footer and an active pill that glides between items.
 *
 * Adapted from the 21st.dev "Sidebar" component by wensity
 * (https://21st.dev/@wensity/components/sidebar): icons switched to
 * lucide-react, items render Next.js links, colours bound to the app's
 * sidebar tokens, and the resizable/floating/nested variants dropped.
 */

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { cn } from "@/lib/utils";

const EASE_OUT: [number, number, number, number] = [0.23, 1, 0.32, 1];

interface SidebarContextValue {
  collapsed: boolean;
  toggleCollapsed: () => void;
  navId: string;
}

const SidebarContext = React.createContext<SidebarContextValue | null>(null);

export function useSidebar(): SidebarContextValue {
  const context = React.useContext(SidebarContext);
  if (!context) throw new Error("Sidebar components must be used within <Sidebar>");
  return context;
}

export interface SidebarProps extends React.HTMLAttributes<HTMLElement> {
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  /** Width in px when expanded. */
  width?: number;
  /** Width in px when collapsed to the icon rail. */
  collapsedWidth?: number;
}

export function Sidebar({
  collapsed,
  onCollapsedChange,
  width = 248,
  collapsedWidth = 64,
  className,
  style,
  children,
  ...props
}: SidebarProps) {
  const navId = React.useId();
  const prefersReducedMotion = useReducedMotion();
  const context = React.useMemo(
    () => ({ collapsed, toggleCollapsed: () => onCollapsedChange(!collapsed), navId }),
    [collapsed, onCollapsedChange, navId],
  );

  return (
    <SidebarContext.Provider value={context}>
      <nav
        aria-label="Main navigation"
        data-collapsed={collapsed}
        style={{
          ...style,
          width: collapsed ? collapsedWidth : width,
          // Width is a layout change, so it runs as an interruptible CSS transition.
          transition: prefersReducedMotion ? "none" : "width 240ms cubic-bezier(0.23,1,0.32,1)",
        }}
        className={cn(
          "relative isolate flex h-full shrink-0 flex-col overflow-hidden bg-sidebar text-sidebar-foreground",
          className,
        )}
        {...props}
      >
        {children}
      </nav>
    </SidebarContext.Provider>
  );
}

function FadingLabel({
  show,
  className,
  children,
}: {
  show: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  const prefersReducedMotion = useReducedMotion();
  return (
    <AnimatePresence initial={false}>
      {show && (
        <motion.span
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: prefersReducedMotion ? 0 : 0.12, ease: EASE_OUT }}
          className={className}
        >
          {children}
        </motion.span>
      )}
    </AnimatePresence>
  );
}

export function SidebarHeader({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  const { collapsed } = useSidebar();
  return (
    <div
      className={cn(
        "flex h-14 shrink-0 items-center border-b border-white/10",
        collapsed ? "justify-center px-0" : "gap-2.5 px-4",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function SidebarNav({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-y-contain py-3", className)}
      {...props}
    >
      {children}
    </div>
  );
}

export function SidebarSection({
  label,
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { label?: string }) {
  const { collapsed } = useSidebar();
  return (
    <div role="group" aria-label={label} className={cn("py-1", className)} {...props}>
      {label && (
        <div className="flex h-7 items-end px-5 pb-1.5">
          <FadingLabel
            show={!collapsed}
            className="whitespace-nowrap text-[10.5px] font-medium uppercase leading-none tracking-[0.1em] text-sidebar-foreground/45"
          >
            {label}
          </FadingLabel>
        </div>
      )}
      <div className="flex flex-col gap-0.5 px-3">{children}</div>
    </div>
  );
}

export interface SidebarItemProps {
  href: string;
  icon: React.ReactNode;
  active?: boolean;
  badge?: React.ReactNode;
  onNavigate?: () => void;
  children: string;
}

export function SidebarItem({ href, icon, active = false, badge, onNavigate, children }: SidebarItemProps) {
  const { collapsed, navId } = useSidebar();
  const prefersReducedMotion = useReducedMotion();

  return (
    <Link
      href={href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      title={collapsed ? children : undefined}
      className={cn(
        "group/item relative flex h-9 w-full select-none items-center gap-3 whitespace-nowrap rounded-lg px-2.5 text-[13.5px] font-medium leading-none outline-none transition-colors duration-150",
        "focus-visible:ring-2 focus-visible:ring-white/60 focus-visible:ring-offset-0",
        active
          ? "text-white"
          : "text-sidebar-foreground/70 hover:bg-white/[0.06] hover:text-sidebar-foreground",
      )}
    >
      {active &&
        (prefersReducedMotion ? (
          <span aria-hidden className="absolute inset-0 rounded-lg bg-sidebar-accent" />
        ) : (
          <motion.span
            aria-hidden
            layoutId={`${navId}-active-pill`}
            transition={{ type: "spring", stiffness: 520, damping: 42 }}
            className="absolute inset-0 rounded-lg bg-sidebar-accent shadow-[inset_0_1px_0_rgb(255_255_255/0.12)]"
          />
        ))}
      <span
        className={cn(
          "relative z-10 flex size-5 shrink-0 items-center justify-center transition-colors duration-150",
          active ? "text-white" : "text-sidebar-foreground/55 group-hover/item:text-sidebar-foreground",
        )}
      >
        {icon}
      </span>
      <FadingLabel show={!collapsed} className="relative z-10 min-w-0 flex-1 truncate text-left">
        {children}
      </FadingLabel>
      {badge ? (
        <FadingLabel show={!collapsed} className="relative z-10 flex shrink-0 items-center">
          {badge}
        </FadingLabel>
      ) : null}
    </Link>
  );
}

export function SidebarFooter({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  const { collapsed } = useSidebar();
  return (
    <div
      className={cn(
        "flex shrink-0 items-center border-t border-white/10 py-3",
        collapsed ? "flex-col justify-center gap-2 px-0" : "gap-2.5 px-4",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function SidebarToggle({ className }: { className?: string }) {
  const { collapsed, toggleCollapsed } = useSidebar();
  const Icon = collapsed ? PanelLeftOpen : PanelLeftClose;
  return (
    <button
      type="button"
      onClick={toggleCollapsed}
      aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      aria-expanded={!collapsed}
      className={cn(
        "flex size-8 shrink-0 items-center justify-center rounded-md text-sidebar-foreground/60 outline-none transition-[color,background-color,transform] duration-150",
        "hover:bg-white/10 hover:text-sidebar-foreground active:scale-95",
        "focus-visible:ring-2 focus-visible:ring-white/60 focus-visible:ring-offset-0",
        className,
      )}
    >
      <Icon className="size-[17px]" strokeWidth={1.75} />
    </button>
  );
}
