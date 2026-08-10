import type {
  ApiErrorPayload,
  AppointmentFilters,
  AppointmentPage,
  DispatchResult,
  ImportReport,
  MessageDetail,
  MessagePage,
  MessageStatus,
  PatientResponseResult,
  RetryResult,
} from "./types";

const configuredOrigin = import.meta.env.VITE_API_URL?.replace(/\/$/, "");
const browserOrigin = typeof window === "undefined" ? "http://localhost" : window.location.origin;
const apiOrigin = configuredOrigin || browserOrigin;
const apiRoot = `${apiOrigin}/api/v1`;
const timeoutMs = Number(import.meta.env.VITE_API_TIMEOUT_MS || 10_000);

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId: string | null;
  readonly details: unknown;

  constructor(
    message: string,
    options: {
      code: string;
      status: number;
      requestId?: string | null;
      details?: unknown;
    },
  ) {
    super(message);
    this.name = "ApiError";
    this.code = options.code;
    this.status = options.status;
    this.requestId = options.requestId ?? null;
    this.details = options.details ?? {};
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`${apiRoot}${path}`, {
      ...init,
      headers,
      signal: init.signal ?? AbortSignal.timeout(timeoutMs),
    });
  } catch (error) {
    if (error instanceof ApiError) throw error;
    const timedOut = error instanceof DOMException && error.name === "TimeoutError";
    throw new ApiError(
      timedOut ? "A API demorou demais para responder." : "Não foi possível acessar a API.",
      { code: timedOut ? "request_timeout" : "network_error", status: 0 },
    );
  }

  const contentType = response.headers.get("Content-Type") ?? "";
  const payload: unknown = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    if (isApiErrorPayload(payload)) {
      throw new ApiError(payload.error.message, {
        code: payload.error.code,
        status: response.status,
        requestId: payload.error.request_id,
        details: payload.error.details,
      });
    }
    throw new ApiError("A API retornou uma resposta inesperada.", {
      code: "unexpected_response",
      status: response.status,
      details: payload,
    });
  }

  return payload as T;
}

function isApiErrorPayload(payload: unknown): payload is ApiErrorPayload {
  if (!payload || typeof payload !== "object" || !("error" in payload)) return false;
  const error = payload.error;
  return (
    error !== null &&
    typeof error === "object" &&
    "code" in error &&
    typeof error.code === "string" &&
    "message" in error &&
    typeof error.message === "string" &&
    "request_id" in error &&
    typeof error.request_id === "string"
  );
}

function queryString(values: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const serialized = params.toString();
  return serialized ? `?${serialized}` : "";
}

export const api = {
  listAppointments(filters: AppointmentFilters): Promise<AppointmentPage> {
    return request(
      `/appointments${queryString({
        date: filters.date,
        status: filters.status || undefined,
        page: filters.page,
        page_size: filters.pageSize,
      })}`,
    );
  },

  importAppointments(file: File): Promise<ImportReport> {
    const formData = new FormData();
    formData.set("file", file);
    return request("/imports/appointments", { method: "POST", body: formData });
  },

  dispatch(date: string): Promise<DispatchResult> {
    return request("/confirmations/dispatch", {
      method: "POST",
      body: JSON.stringify({ date }),
    });
  },

  respond(
    appointmentId: string,
    status: "confirmed" | "declined",
  ): Promise<PatientResponseResult> {
    return request(`/appointments/${appointmentId}/response`, {
      method: "POST",
      body: JSON.stringify({ status }),
    });
  },

  retry(messageId: string): Promise<RetryResult> {
    return request(`/messages/${messageId}/retry`, { method: "POST" });
  },

  listMessages(filters: {
    status?: MessageStatus | "";
    page?: number;
    pageSize?: number;
  }): Promise<MessagePage> {
    return request(
      `/messages${queryString({
        status: filters.status || undefined,
        page: filters.page,
        page_size: filters.pageSize,
      })}`,
    );
  },

  getMessage(messageId: string): Promise<MessageDetail> {
    return request(`/messages/${messageId}`);
  },
};
