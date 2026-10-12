// Shapes returned by the FastAPI backend. Dates are ISO "YYYY-MM-DD" strings
// and money is a decimal string, exactly as the API sends them.

export type UserRole = "owner" | "manager" | "front_desk" | "housekeeping" | "accountant";

export type ReservationStatus =
  | "confirmed"
  | "checked_in"
  | "checked_out"
  | "cancelled"
  | "no_show";

export type BookingSource =
  | "direct"
  | "walk_in"
  | "phone"
  | "website"
  | "booking_com"
  | "makemytrip"
  | "goibibo"
  | "agoda"
  | "expedia"
  | "airbnb"
  | "corporate"
  | "travel_agent"
  | "other";

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface RegisterRequest {
  hotel_name: string;
  slug: string;
  email: string;
  full_name: string;
  password: string;
}

export interface RegisterResponse {
  hotel_id: string;
  name: string;
  slug: string;
}

export interface CurrentUser {
  id: string;
  hotel_id: string;
  email: string;
  full_name: string;
  role: UserRole;
}

/** What is printed about the hotel on its invoices. */
export interface HotelInput {
  name: string;
  gstin: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  phone: string | null;
  email: string | null;
}

export interface Hotel extends HotelInput {
  id: string;
  slug: string;
  updated_at: string;
}

export interface RoomType {
  id: string;
  name: string;
  code: string;
  description: string | null;
  base_occupancy: number;
  max_occupancy: number;
  base_rate: string;
  is_active: boolean;
}

export interface RoomTypeInput {
  name: string;
  code: string;
  description: string | null;
  base_occupancy: number;
  max_occupancy: number;
  base_rate: string;
}

export interface Room {
  id: string;
  room_type_id: string;
  room_number: string;
  floor: string | null;
  is_active: boolean;
}

export interface RoomInput {
  room_type_id: string;
  room_number: string;
  floor: string | null;
}

export interface DayAvailability {
  date: string;
  total_rooms: number;
  booked: number;
  available: number;
}

export interface TapeChartRoom {
  id: string;
  room_number: string;
  floor: string | null;
}

export interface TapeChartRoomType {
  id: string;
  name: string;
  code: string;
  rooms: TapeChartRoom[];
  availability: DayAvailability[];
}

export interface TapeChartReservation {
  id: string;
  confirmation_number: string;
  guest_id: string;
  guest_name: string;
  room_type_id: string;
  room_id: string | null;
  check_in_date: string;
  check_out_date: string;
  adults: number;
  children: number;
  rate_per_night: string;
  status: ReservationStatus;
  source: BookingSource;
}

export interface TapeChart {
  start: string;
  end: string;
  room_types: TapeChartRoomType[];
  reservations: TapeChartReservation[];
}

export interface GuestInput {
  first_name: string;
  last_name: string;
  email: string | null;
  phone: string | null;
  id_document_type: string | null;
  id_document_number: string | null;
  nationality: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  company_name: string | null;
  gstin: string | null;
}

export interface Guest extends GuestInput {
  id: string;
  created_at: string;
}

export interface Reservation {
  id: string;
  confirmation_number: string;
  guest_id: string;
  room_type_id: string;
  room_id: string | null;
  check_in_date: string;
  check_out_date: string;
  adults: number;
  children: number;
  rate_per_night: string;
  status: ReservationStatus;
  source: BookingSource;
  external_reference: string | null;
  notes: string | null;
  created_at: string;
}

export interface ReservationInput {
  guest_id: string;
  room_type_id: string;
  room_id: string | null;
  check_in_date: string;
  check_out_date: string;
  adults: number;
  children: number;
  /** Omitted: the room type's base rate applies. */
  rate_per_night?: string;
  source: BookingSource;
  notes: string | null;
}

export interface RoomTypeAvailability {
  room_type_id: string;
  available_for_stay: number;
  days: DayAvailability[];
}

export interface GstQuote {
  nights: number;
  tariff_per_night: string;
  gst_rate: string;
  taxable_amount: string;
  total_tax: string;
  total_amount: string;
}

export type PaymentMethod = "cash" | "card" | "upi" | "bank_transfer" | "cheque" | "other";

export interface FolioTransaction {
  id: string;
  folio_id: string;
  business_date: string;
  entry_type: "debit" | "credit";
  category: "room_charge" | "extra_charge" | "payment";
  description: string;
  amount: string;
  gst_rate: string;
  cgst_amount: string;
  sgst_amount: string;
  total_amount: string;
  payment_method: PaymentMethod | null;
  reference: string | null;
  reverses_transaction_id: string | null;
  created_at: string;
}

export interface Folio {
  id: string;
  reservation_id: string;
  folio_number: string;
  status: "open" | "closed";
  closed_at: string | null;
  /** Issued the first time the closed folio's tax invoice is produced. */
  invoice_number: string | null;
  invoice_date: string | null;
  total_debits: string;
  total_credits: string;
  /** What the guest still owes; negative means the hotel owes the guest. */
  balance: string;
  transactions: FolioTransaction[];
}

export interface ChargeInput {
  description: string;
  amount: string;
  gst_rate: string;
}

export interface PaymentInput {
  amount: string;
  payment_method: PaymentMethod;
  reference: string | null;
}

export interface ChannelConnection {
  id: string;
  name: string;
  key_id: string;
  is_active: boolean;
  created_at: string;
  /** Where availability updates are pushed; null for an inbound-only key. */
  outbound_url: string | null;
  /** Outcome of the most recent availability push, if there has been one. */
  last_push_at: string | null;
  last_push_ok: boolean | null;
  last_push_detail: string | null;
}

export interface OutboundTestResult {
  ok: boolean;
  /** Null when the endpoint could not be reached at all. */
  status_code: number | null;
  detail: string;
  duration_ms: number;
}

export interface ChannelConnectionCreated extends ChannelConnection {
  /** Returned once, when the connection is created. */
  signing_secret: string;
}

export interface ChannelWebhookEvent {
  id: string;
  connection_id: string;
  event_type: string;
  channel: string;
  external_booking_id: string;
  status: "processed" | "duplicate" | "rejected" | string;
  detail: string | null;
  reservation_id: string | null;
  received_at: string;
}

/** Money fields are null for roles that may not see revenue. */
export interface Performance {
  rooms_available: number;
  rooms_sold: number;
  occupancy_pct: string;
  /** Room charges before GST. */
  room_revenue: string | null;
  /** Extras before GST. */
  other_revenue: string | null;
  adr: string | null;
  revpar: string | null;
}

export interface DayPerformance extends Performance {
  date: string;
}

export interface DashboardStats {
  can_view_revenue: boolean;
  /** `is_projected`: revenue is tonight's booked rates, not yet posted charges. */
  today: DayPerformance & { is_projected: boolean };
  /** The days before today taken together. */
  period: Performance;
  /** One entry per day, oldest first, ending yesterday. */
  trend: DayPerformance[];
}
