import { HttpResponse, http, type RequestHandler } from "msw";

export const handlers: RequestHandler[] = [
  http.get("*/api/v1/appointments/calendar", () => HttpResponse.json({ items: [] })),
];
