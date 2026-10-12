# Pending tasks: from working core to production SaaS

What is left to take the Hotel PMS from a functional core to a product that can be sold and run in production.

**Last updated:** 1 October 2026

## Where things stand

Built and tested: multi-tenant core with Row-Level Security, self-service hotel sign-up, room types and rooms, reservations and tape chart, folios with an append-only ledger, GST calculation and PDF invoices, night audit, guest directory, two-way channel manager sync, and the analytics dashboard.

Not yet in place: any way to charge hotels, any super-admin view across tenants, email of any kind, staff user management, a public website, and a production deployment.

## How to read this

- `- [ ]` is an open task. Tick it when it is merged and verified.
- **Blocker** marks a task that must be done before the first paying customer.
- Sections are ordered roughly by dependency: sections 0 to 2 and 5 gate a launch; 3 and 4 can follow.

| # | Section | Gates launch? |
|---|---------|---------------|
| 0 | Known gaps in what's built | Partly |
| 1 | SaaS super admin and billing | Yes |
| 2 | Security and auth | Yes |
| 3 | Guest communications | No |
| 4 | Marketing landing page | Yes, for self-serve sales |
| 5 | Production deployment | Yes |

---

## 0. Known gaps in what's built

Issues found while building the current features. Each is small on its own; together they are the difference between a demo and something a hotel can rely on.

### Staff and access

- [ ] **Blocker.** Staff user management: owners can invite, edit, deactivate and change the role of users. Today the only user a hotel has is the owner created at sign-up.
- [ ] Let a user change their own password and name.
- [ ] Check every screen as each non-owner role (manager, front desk, housekeeping, accountant). The role rules are tested in the API, but the restricted layouts have never been viewed in a browser.
- [ ] Give accountants a direct route to folios and invoices; today invoices are only reachable through the reservation dialog.

### Billing correctness

- [ ] **Blocker.** A guest who checks in and out before the night audit runs has no room charge, and can be checked out at a zero balance. Post outstanding room nights at check-out, or block check-out until they are posted.
- [ ] Early departure does not shorten the reservation, so the unused nights still count as sold and stay blocked in inventory.
- [ ] Decide when the invoice number is issued. It is currently assigned on first download, so numbers follow download order and an undownloaded folio never gets one. Issuing at check-out is the usual alternative.
- [ ] Confirm the invoice number format (`INV/26-27/000123`) and the 16-character limit with an accountant.
- [ ] Capture a SAC code for extra charges in the UI; only room charges carry 996311 automatically, so extras print "—".
- [ ] Have an accountant confirm the default GST rates offered for extras (0%, 5%, 18%).
- [ ] Bundle a Unicode font in the invoice PDF so the rupee sign and non-Latin guest names render.
- [ ] Credit notes for corrections after an invoice has been issued.
- [ ] Refunds and advance-deposit handling as first-class operations, not reversals.

### Channel manager

- [ ] Push availability when rooms or room types are added, removed or deactivated (today only reservation changes trigger a push).
- [ ] A scheduled full resync, so a push lost while Redis was down is corrected without someone pressing "Sync now".
- [ ] A delivery log for outbound pushes (only the last result per connection is kept).
- [ ] An adapter for at least one real channel manager; the current payload format is our own.
- [ ] Rate and restriction pushes (prices, minimum stay, stop-sell); only availability is sent today.

### Product gaps

- [ ] Edit a reservation from the UI (dates, room type, rate, guest count). The API supports it; the dialog only assigns rooms, checks in or out, and cancels.
- [ ] Housekeeping: room status (clean, dirty, inspected, out of order) and a task list.
- [ ] Rate plans and seasonal pricing; each room type has one base rate.
- [ ] Group bookings and multiple rooms on one reservation.
- [ ] Reports beyond the dashboard: daily revenue, GST summary for filing, arrivals and departures, exports to CSV or Excel.
- [ ] Store the history of room counts so past occupancy uses the rooms that existed then.
- [ ] Automated frontend tests. The backend has 183 tests; the frontend has none.

### Engineering hygiene

- [ ] **Blocker.** Put the project under version control. The folder has a `.gitignore` but is not a git repository.
- [ ] Continuous integration: run ruff, mypy, pytest, `tsc` and `next lint` on every change.
- [ ] Resolve the `npm audit` findings reported on every install.
- [ ] Run only one `next dev` per checkout, or give each its own build directory; two instances corrupt the shared `.next` folder.

---

## 1. SaaS super admin and billing

How you charge hotels and how you run the platform across all of them.

### Plans and subscriptions

- [ ] **Blocker.** Decide the pricing model: per property, per room, or tiered by features. Everything below depends on it.
- [ ] `plans` and `subscriptions` tables: plan, status (trialing, active, past due, cancelled), trial end, current period end. These are platform tables, outside tenant RLS.
- [ ] Free trial started at sign-up, with the end date shown in the app.
- [ ] Enforce plan limits (rooms, users, channel connections) in the API, with a clear message when a limit is reached.

### Payment gateway

- [ ] **Blocker.** Choose the gateway. Razorpay suits INR, UPI and Indian cards; Stripe suits international cards. Supporting both doubles the work.
- [ ] Checkout for starting or changing a subscription.
- [ ] Webhook endpoint for payment succeeded, payment failed, subscription cancelled and renewed. Verify signatures and make handling idempotent, as the channel manager webhook already does.
- [ ] Self-service billing page for the hotel owner: current plan, next charge, payment method, past invoices, cancel.
- [ ] GST invoices from you to the hotel for the subscription itself.
- [ ] Dunning: retry failed payments, email the owner, and set a grace period before suspension.

### Account suspension

- [ ] **Blocker.** Suspend a hotel for non-payment or abuse. `hotels.is_active` exists and login already checks it; add a reason and a timestamp.
- [ ] Decide what a suspended hotel can still do. Read-only access and data export is safer than a hard lock-out.
- [ ] Refuse inbound channel webhooks and stop outbound pushes for a suspended hotel.
- [ ] Reactivation on payment, automatically from the gateway webhook.
- [ ] Account closure: export of the hotel's data, then deletion after a stated retention period.

### Super admin console

- [ ] **Blocker.** A platform-admin identity separate from hotel users, with its own login and mandatory two-factor authentication.
- [ ] A safe way for platform admins to read across tenants. The API role is deliberately blocked by RLS, so this needs its own audited path, not a switch that disables RLS.
- [ ] Tenant list: plan, status, rooms, users, sign-up date, last activity.
- [ ] Tenant detail: subscription history, usage, recent errors, channel sync health.
- [ ] Support impersonation ("view as this hotel") with a visible banner and an audit record of who did it and when.
- [ ] Platform metrics: sign-ups, trial conversions, monthly recurring revenue, churn.
- [ ] Manual actions: extend a trial, apply a credit, suspend, reactivate.

---

## 2. Security and auth

### Sign-up and account recovery

- [ ] **Blocker.** Email verification at sign-up. Anyone can currently create unlimited hotels and take hotel codes with addresses they do not own.
- [ ] **Blocker.** Forgot-password flow: emailed single-use link that expires, and that does not reveal whether an account exists.
- [ ] CAPTCHA or an equivalent bot check on sign-up and on forgot-password.
- [ ] Reserve hotel codes that would be confusing or abusable (`admin`, `api`, `www`, `support`).

### Rate limiting and abuse

- [ ] **Blocker.** Rate limiting on login, sign-up, forgot-password and the webhook endpoint. Redis is already in the stack.
- [ ] Lock or slow an account after repeated failed logins.
- [ ] Request size limits and timeouts at the proxy.

### Sessions

- [ ] Move the access token out of `localStorage` to an httpOnly cookie, or add short-lived tokens with refresh. A token in `localStorage` is readable by any injected script.
- [ ] Log out everywhere, and invalidate sessions when a password changes or a user is deactivated.
- [ ] Two-factor authentication for owners and managers.

### Hardening

- [ ] Security headers on the Next.js app: Content-Security-Policy, HSTS, frame and referrer policies.
- [ ] Audit log of sensitive actions: logins, role changes, ledger reversals, API key creation, profile changes.
- [ ] Encrypt channel signing secrets at rest; they are stored readable because verification needs them.
- [ ] Secrets management for production (no `.env` files on servers) and a rotation procedure for the JWT key.
- [ ] Dependency and container scanning in CI.
- [ ] An independent penetration test before launch, with tenant isolation as the main target.

### Compliance

- [ ] Privacy policy and terms of service, linked from sign-up.
- [ ] Review against India's Digital Personal Data Protection Act: guest ID documents and contact details are stored.
- [ ] Data retention rules for guest records and ID documents, and a way to delete a guest's personal data on request.
- [ ] Data processing agreement for hotels that ask for one.

---

## 3. Guest communications

### Foundations

- [ ] Choose a transactional email provider and set up the sending domain (SPF, DKIM, DMARC).
- [ ] A notifications service that queues messages on Celery with retries, in the same after-commit pattern the channel sync uses.
- [ ] A message log per hotel: what was sent, to whom, when, and whether it was delivered or bounced.
- [ ] Per-hotel settings: which messages are on, sender name, reply-to address.
- [ ] Handle bounces and unsubscribes.

### Email

- [ ] Booking confirmation on reservation, with stay details and confirmation number.
- [ ] Modification and cancellation notices.
- [ ] Pre-arrival message with check-in time and directions.
- [ ] Invoice email at check-out with the PDF attached. The PDF service already exists.
- [ ] "Email invoice" button in the folio panel for sending on request.
- [ ] Editable templates with the hotel's name and details.

### WhatsApp

- [ ] WhatsApp Business API account through a provider, and Meta approval of each message template.
- [ ] Record guest consent before sending; WhatsApp requires opt-in.
- [ ] Booking confirmation and check-out invoice over WhatsApp, with the PDF as a document.
- [ ] Decide who pays per-message charges: you, or the hotel as a metered add-on.

### Staff notifications

- [ ] Alert the hotel when an OTA booking arrives, and when one is rejected for lack of availability.
- [ ] Alert when outbound channel sync has been failing for some time.
- [ ] Night audit summary to the owner each morning.

---

## 4. Marketing landing page

The app root currently redirects straight to the dashboard; there is no public site.

### Pages

- [ ] **Blocker for self-serve sales.** Landing page at the root: headline, product screenshots, feature sections, sign-up call to action.
- [ ] Features page covering tape chart, GST billing and invoices, night audit, channel manager and analytics.
- [ ] Pricing page with the tiers from section 1 and a comparison table.
- [ ] Sign-up call to action wired to the existing `/register` page, carrying the chosen plan.
- [ ] Contact or book-a-demo form.
- [ ] Privacy policy, terms of service and refund policy pages.

### Supporting work

- [ ] Move the app behind its own path or subdomain so the root can serve the marketing site.
- [ ] A populated demo hotel for screenshots and live demos; `seed_demo` exists but has no history for the analytics dashboard.
- [ ] SEO basics: titles, descriptions, Open Graph images, sitemap, robots file.
- [ ] Privacy-respecting analytics and sign-up conversion tracking.
- [ ] Help centre or documentation, including the channel manager webhook reference.
- [ ] Final product name, logo and domain; the app is still labelled "Hotel PMS".

---

## 5. Production deployment

Nothing is deployed. Local development uses Docker Compose for PostgreSQL and Redis only; the API, worker and frontend run from the command line.

### Build and release

- [ ] **Blocker.** Dockerfiles for the FastAPI app, the Celery worker and beat, and the Next.js app.
- [ ] Deployment pipeline with staging and production environments.
- [ ] Run Alembic migrations as a release step, as the owner role, before the new API version starts.
- [ ] A rollback procedure, tested once.

### Hosting

- [ ] **Blocker.** Choose the hosting. An Indian region keeps guest data in the country and latency low.
- [ ] Next.js frontend, with `BACKEND_URL` pointing at the API.
- [ ] FastAPI behind a production server setup with several workers and a reverse proxy.
- [ ] Managed PostgreSQL 16 with both roles created: the owner for migrations and the restricted runtime role. Verify RLS is enforced in production, not assumed.
- [ ] Managed Redis with persistence, since it carries the task queue.
- [ ] Celery worker and beat as separate long-running services. Exactly one beat instance, or the night audit is dispatched twice.
- [ ] Domain, TLS certificates and a CDN.

### Configuration

- [ ] **Blocker.** Production environment settings: `ENVIRONMENT=production`, a strong JWT secret, and `CHANNEL_OUTBOUND_ALLOW_PRIVATE_HOSTS` left off (the API refuses to start otherwise).
- [ ] Connection pooling sized for the number of API and worker processes.
- [ ] CORS and allowed hosts locked to the real domains.

### Reliability

- [ ] **Blocker.** Automated database backups with point-in-time recovery, and a restore that has actually been tried.
- [ ] Error tracking for the API, the worker and the frontend.
- [ ] Structured logs shipped to one place, with request IDs.
- [ ] Uptime checks on `/health` and `/health/ready`.
- [ ] Alerts for: API errors, Celery queue backlog, night audit not run for a hotel, channel pushes failing.
- [ ] Load test the reservation and tape chart endpoints at a realistic number of hotels.
- [ ] A status page and an incident procedure.
- [ ] Run a real night audit cycle in staging across more than one time zone before launch.

---

## Suggested order

1. Version control and CI (section 0).
2. Staff user management and the check-out billing gap (section 0).
3. Email provider, then email verification and forgot-password (sections 2 and 3 share it).
4. Rate limiting and CAPTCHA (section 2).
5. Production deployment with backups and monitoring (section 5).
6. Pricing decision, payment gateway, suspension (section 1).
7. Landing and pricing pages (section 4).
8. Super admin console (section 1).
9. Guest emails, then WhatsApp (section 3).
10. Remaining items in section 0, by customer demand.
