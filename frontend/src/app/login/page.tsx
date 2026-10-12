"use client";

/**
 * Sign-in page. Layout adapted from the 21st.dev "Sign In Split Screen"
 * component by felipemenezes098
 * (https://21st.dev/@felipemenezes098/components/sign-in-6): the social login
 * is removed (this product has none) and a hotel code field is added, because
 * accounts are scoped to a hotel.
 */

import { useMutation } from "@tanstack/react-query";
import { ArrowRight, CalendarRange, CircleAlert, Eye, EyeOff, LoaderCircle, ReceiptText, Share2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { APP_NAME } from "@/lib/constants";
import type { TokenResponse } from "@/lib/types";
import { hasValidSession, useAuthStore } from "@/stores/auth";

const HIGHLIGHTS = [
  { icon: CalendarRange, text: "Every room and every stay on one tape chart" },
  { icon: ReceiptText, text: "GST-ready folios with an automatic night audit" },
  { icon: Share2, text: "OTA bookings land in your inventory instantly" },
];

export default function LoginPage() {
  const router = useRouter();
  const { token, expiresAt, hydrated, hotelSlug: rememberedHotel, setSession } = useAuthStore();

  const [hotelSlug, setHotelSlug] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  // Prefill the hotel code from the last session, and skip the form entirely
  // if that session is still valid.
  useEffect(() => {
    if (!hydrated) return;
    if (hasValidSession({ token, expiresAt })) router.replace("/dashboard");
    else setHotelSlug((current) => current || rememberedHotel);
  }, [hydrated, token, expiresAt, rememberedHotel, router]);

  const login = useMutation({
    mutationFn: () =>
      api<TokenResponse>("/auth/login", {
        method: "POST",
        anonymous: true,
        body: { hotel_slug: hotelSlug.trim().toLowerCase(), email: email.trim(), password },
      }),
    onSuccess: (session) => {
      setSession(session.access_token, session.expires_in, hotelSlug.trim().toLowerCase());
      router.replace("/dashboard");
    },
  });

  return (
    <div className="relative flex min-h-dvh items-center justify-center overflow-hidden p-4 sm:p-6">
      {/* Soft backdrop so the card does not float on a flat colour. */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute -left-40 -top-40 size-[32rem] rounded-full bg-primary/10 blur-3xl" />
        <div className="absolute -bottom-48 -right-32 size-[30rem] rounded-full bg-sky-300/20 blur-3xl" />
      </div>

      <div className="relative grid w-full max-w-4xl overflow-hidden rounded-2xl border border-border bg-card shadow-lift animate-in fade-in-0 slide-in-from-bottom-2 duration-500 md:grid-cols-[1.05fr_1fr]">
        {/* Brand panel */}
        <div className="relative hidden flex-col justify-between overflow-hidden bg-gradient-to-b from-primary to-sidebar p-10 text-primary-foreground md:flex">
          <div aria-hidden className="pointer-events-none absolute -right-24 -top-24 size-72 rounded-full bg-white/10 blur-3xl" />
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 opacity-[0.07]"
            style={{
              backgroundImage:
                "linear-gradient(to right, white 1px, transparent 1px), linear-gradient(to bottom, white 1px, transparent 1px)",
              backgroundSize: "40px 40px",
            }}
          />

          <div className="relative flex items-center gap-2.5">
            <span className="flex size-9 items-center justify-center rounded-lg bg-white/15 ring-1 ring-inset ring-white/25">
              <span className="size-3.5 rotate-45 rounded-[3px] bg-white" />
            </span>
            <span className="text-base font-semibold tracking-tight">{APP_NAME}</span>
          </div>

          <div className="relative mt-16">
            <h2 className="max-w-[16ch] text-balance text-[30px] font-semibold leading-[1.12] tracking-tight">
              Run your whole hotel from one calm screen.
            </h2>
            <ul className="mt-8 space-y-4">
              {HIGHLIGHTS.map(({ icon: Icon, text }) => (
                <li key={text} className="flex items-center gap-3 text-sm text-primary-foreground/85">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-white/10 ring-1 ring-inset ring-white/15">
                    <Icon className="size-4" strokeWidth={1.75} />
                  </span>
                  {text}
                </li>
              ))}
            </ul>
          </div>

          <p className="relative mt-16 text-xs text-primary-foreground/60">
            Your hotel&apos;s data is isolated from every other property.
          </p>
        </div>

        {/* Form */}
        <form
          className="flex flex-col justify-center gap-6 p-7 sm:p-10"
          onSubmit={(event) => {
            event.preventDefault();
            login.mutate();
          }}
        >
          <div>
            <h1 className="text-[22px] font-semibold tracking-tight">Welcome back</h1>
            <p className="mt-1.5 text-sm text-muted-foreground">Sign in to your hotel&apos;s workspace.</p>
          </div>

          {login.isError && (
            <div
              role="alert"
              className="flex items-start gap-2.5 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2.5 text-[13px] text-destructive animate-in fade-in-0 slide-in-from-top-1"
            >
              <CircleAlert className="mt-px size-4 shrink-0" />
              {login.error.message}
            </div>
          )}

          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="hotel">Hotel code</Label>
              <Input
                id="hotel"
                value={hotelSlug}
                onChange={(event) => setHotelSlug(event.target.value)}
                placeholder="your-hotel"
                autoComplete="organization"
                autoCapitalize="none"
                spellCheck={false}
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@hotel.com"
                autoComplete="email"
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="••••••••••••"
                  autoComplete="current-password"
                  className="pr-10"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((shown) => !shown)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                  className="absolute right-1 top-1/2 flex size-8 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground transition-colors hover:text-foreground"
                >
                  {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </div>
          </div>

          <Button type="submit" size="lg" className="group w-full" disabled={login.isPending}>
            {login.isPending ? (
              <>
                <LoaderCircle className="size-4 animate-spin" />
                Signing in…
              </>
            ) : (
              <>
                Sign in
                <ArrowRight className="size-4 transition-transform duration-200 group-hover:translate-x-0.5" />
              </>
            )}
          </Button>

          <div className="space-y-2 text-center">
            <p className="text-sm text-muted-foreground">
              New here?{" "}
              <Link href="/register" className="font-medium text-primary underline-offset-4 hover:underline">
                Register your hotel
              </Link>
            </p>
            <p className="text-xs text-muted-foreground">
              Can&apos;t sign in? Ask your hotel&apos;s owner or manager to check your account.
            </p>
          </div>
        </form>
      </div>
    </div>
  );
}
