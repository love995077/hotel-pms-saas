import type { UserRole } from "@/lib/types";

// Mirrors the role groups in the API (app/api/deps.py). The API is what
// enforces them; these only decide which controls to show.
const GROUPS = {
  management: ["owner", "manager"],
  frontOffice: ["owner", "manager", "front_desk"],
  billing: ["owner", "manager", "front_desk", "accountant"],
  ledgerControl: ["owner", "manager", "accountant"],
} as const satisfies Record<string, readonly UserRole[]>;

export type Permission = keyof typeof GROUPS;

export function can(role: UserRole | undefined, permission: Permission): boolean {
  return role !== undefined && (GROUPS[permission] as readonly UserRole[]).includes(role);
}
