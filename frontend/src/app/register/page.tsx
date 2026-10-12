"use client";

/**
 * Self-service sign-up. Shares the split-card layout of the sign-in page so
 * the two read as one flow.
 */

import { ArrowRight, Check, CircleAlert, Eye, EyeOff, LoaderCircle, LockKeyhole, Sparkles, Timer } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { APP_NAME } from "@/lib/constants";
import { useRegisterHotel } from "@/lib/queries";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth";

// Mirror the backend's RegisterRequest rules.
const MIN_PASSWORD_LENGTH = 12;
const MIN_SLUG_LENGTH = 3;
const MAX_SLUG_LENGTH = 63;
const SLUG_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/;

const BENEFITS = [
  { icon: Timer, title: "Live in minutes", text: "Create your workspace now, add rooms and rates right after." },
  { icon: Sparkles, title: "Everything included", text: "Tape chart, GST folios, night audit and OTA sync." },
  { icon: LockKeyhole, title: "Private by design", text: "Your data is isolated from every other property." },
];

/** "Sea View Residency" -> "sea-view-residency" */
function slugify(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, MAX_SLUG_LENGTH)
    .replace(/-+$/, "");
}

export default function RegisterPage() {
  const router = useRouter();
  const rememberHotel = useAuthStore((state) => state.rememberHotel);
  const register = useRegisterHotel();

  const [hotelName, setHotelName] = useState("");
  const [slug, setSlug] = useState("");
  // The code follows the hotel name until the user edits it themselves.
  const [slugEdited, setSlugEdited] = useState(false);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const slugError =
    slug.length < MIN_SLUG_LENGTH
      ? `Use at least ${MIN_SLUG_LENGTH} characters.`
      : !SLUG_PATTERN.test(slug)
        ? "Use lowercase letters, numbers and single hyphens only."
        : null;
  const slugTaken = register.error?.status === 409 && register.variables?.slug === slug;
  const passwordOk = password.length >= MIN_PASSWORD_LENGTH;
  const showSlugError = (submitted || slugEdited) && slug.length > 0 && slugError !== null;

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    if (slugError || !passwordOk) return;
    register.mutate(
      { hotel_name: hotelName.trim(), slug, email: email.trim(), full_name: fullName.trim(), password },
      {
        onSuccess: (hotel) => {
          rememberHotel(hotel.slug);
          toast.success(`${hotel.name} is ready`, {
            description: `Sign in with your hotel code "${hotel.slug}".`,
          });
          router.push("/login");
        },
      },
    );
  }

  return (
    <div className="relative flex min-h-dvh items-center justify-center overflow-hidden p-4 sm:p-6">
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute -left-40 -top-40 size-[32rem] rounded-full bg-primary/10 blur-3xl" />
        <div className="absolute -bottom-48 -right-32 size-[30rem] rounded-full bg-sky-300/20 blur-3xl" />
      </div>

      <div className="relative grid w-full max-w-5xl overflow-hidden rounded-2xl border border-border bg-card shadow-lift animate-in fade-in-0 slide-in-from-bottom-2 duration-500 md:grid-cols-[1fr_1.1fr]">
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

          <div className="relative mt-14">
            <h2 className="max-w-[15ch] text-balance text-[30px] font-semibold leading-[1.12] tracking-tight">
              Open your front desk today.
            </h2>
            <ul className="mt-8 space-y-5">
              {BENEFITS.map(({ icon: Icon, title, text }) => (
                <li key={title} className="flex items-start gap-3">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-white/10 ring-1 ring-inset ring-white/15">
                    <Icon className="size-4" strokeWidth={1.75} />
                  </span>
                  <div>
                    <p className="text-sm font-medium">{title}</p>
                    <p className="mt-0.5 text-[13px] leading-snug text-primary-foreground/70">{text}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <p className="relative mt-14 text-xs text-primary-foreground/60">
            Built for boutique, business and heritage hotels.
          </p>
        </div>

        {/* Form */}
        <form className="flex flex-col justify-center gap-6 p-7 sm:p-10" onSubmit={onSubmit}>
          <div>
            <h1 className="text-[22px] font-semibold tracking-tight">Register your hotel</h1>
            <p className="mt-1.5 text-sm text-muted-foreground">
              One short form. You&apos;ll be the owner and can invite your team later.
            </p>
          </div>

          {register.isError && !slugTaken && (
            <div
              role="alert"
              className="flex items-start gap-2.5 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2.5 text-[13px] text-destructive animate-in fade-in-0 slide-in-from-top-1"
            >
              <CircleAlert className="mt-px size-4 shrink-0" />
              {register.error.message}
            </div>
          )}

          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="hotel-name">Hotel name</Label>
              <Input
                id="hotel-name"
                value={hotelName}
                onChange={(event) => {
                  setHotelName(event.target.value);
                  if (!slugEdited) setSlug(slugify(event.target.value));
                }}
                placeholder="Sea View Residency"
                autoComplete="organization"
                minLength={2}
                maxLength={200}
                autoFocus
                required
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="slug">Hotel code</Label>
              <Input
                id="slug"
                value={slug}
                onChange={(event) => {
                  setSlugEdited(true);
                  setSlug(event.target.value.toLowerCase().replace(/\s+/g, "-"));
                }}
                placeholder="sea-view-residency"
                autoCapitalize="none"
                autoComplete="off"
                spellCheck={false}
                maxLength={MAX_SLUG_LENGTH}
                aria-invalid={showSlugError || slugTaken}
                aria-describedby="slug-hint"
                required
              />
              <p
                id="slug-hint"
                role={showSlugError || slugTaken ? "alert" : undefined}
                className={cn("text-xs", showSlugError || slugTaken ? "text-destructive" : "text-muted-foreground")}
              >
                {slugTaken
                  ? "That hotel code is already taken. Try another."
                  : showSlugError
                    ? slugError
                    : "Your team types this when signing in. It can't be changed later."}
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-2">
                <Label htmlFor="full-name">Your name</Label>
                <Input
                  id="full-name"
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  placeholder="Asha Rao"
                  autoComplete="name"
                  minLength={2}
                  maxLength={200}
                  required
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="email">Work email</Label>
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
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="At least 12 characters"
                  autoComplete="new-password"
                  className="pr-10"
                  aria-invalid={submitted && !passwordOk}
                  aria-describedby="password-hint"
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
              <p
                id="password-hint"
                className={cn(
                  "flex items-center gap-1.5 text-xs transition-colors",
                  passwordOk
                    ? "text-emerald-700"
                    : submitted
                      ? "text-destructive"
                      : "text-muted-foreground",
                )}
              >
                {passwordOk && <Check className="size-3.5" strokeWidth={2.5} />}
                {passwordOk
                  ? "Long enough"
                  : `${MIN_PASSWORD_LENGTH} characters or more (${password.length}/${MIN_PASSWORD_LENGTH})`}
              </p>
            </div>
          </div>

          <Button type="submit" size="lg" className="group w-full" disabled={register.isPending || register.isSuccess}>
            {register.isPending || register.isSuccess ? (
              <>
                <LoaderCircle className="size-4 animate-spin" />
                Creating your hotel…
              </>
            ) : (
              <>
                Create my hotel
                <ArrowRight className="size-4 transition-transform duration-200 group-hover:translate-x-0.5" />
              </>
            )}
          </Button>

          <p className="text-center text-sm text-muted-foreground">
            Already registered?{" "}
            <Link href="/login" className="font-medium text-primary underline-offset-4 hover:underline">
              Sign in
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
