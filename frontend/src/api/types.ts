export type AppointmentStatus = "pending" | "confirmed" | "declined";
export type MessageStatus = "pending" | "processing" | "sent" | "failed";
export type AttemptResult = "processing" | "sent" | "failed" | "abandoned";

export interface Pagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface AppointmentMessage {
  id: string;
  status: MessageStatus;
  attempt_count: number;
  max_attempts: number;
  last_error: string | null;
}

export interface Appointment {
  id: string;
  scheduled_at: string;
  patient_name: string;
  phone: string;
  procedure: string;
  status: AppointmentStatus;
  message: AppointmentMessage | null;
}

export interface AppointmentPage {
  items: Appointment[];
  pagination: Pagination;
}

export interface AppointmentFilters {
  date?: string;
  status?: AppointmentStatus | "";
  page?: number;
  pageSize?: number;
}

export interface ImportRowError {
  line_number: number;
  raw_data: Record<string, string>;
  reason: string;
}

export interface ImportReport {
  summary: {
    total_rows: number;
    imported: number;
    rejected: number;
    duplicates: number;
  };
  imported_lines: number[];
  duplicate_lines: number[];
  errors: ImportRowError[];
}

export interface DispatchResult {
  eligible: number;
  created: number;
  already_existing: number;
  ignored: number;
  queued: number;
  pending_reconciliation: number;
}

export interface PatientResponseResult {
  id: string;
  status: Exclude<AppointmentStatus, "pending">;
}

export interface RetryResult {
  id: string;
  status: MessageStatus;
  attempt_count: number;
  max_attempts: number;
  queued: boolean;
  pending_reconciliation: boolean;
  enqueued_at: string | null;
  next_enqueue_at: string | null;
}

export interface MessageAttempt {
  id: string;
  attempt_number: number;
  started_at: string;
  completed_at: string | null;
  result: AttemptResult;
  error: string | null;
}

export interface Message {
  id: string;
  appointment_id: string;
  status: MessageStatus;
  attempt_count: number;
  max_attempts: number;
  last_error: string | null;
  enqueued_at: string | null;
  next_enqueue_at: string | null;
}

export interface MessageDetail extends Message {
  attempts: MessageAttempt[];
}

export interface MessagePage {
  items: Message[];
  pagination: Pagination;
}

export interface ApiErrorPayload {
  error: {
    code: string;
    message: string;
    details: unknown;
    request_id: string;
  };
}
