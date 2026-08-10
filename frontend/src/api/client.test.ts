import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { api, ApiError } from "./client";
import { server } from "../test/server";

describe("api client", () => {
  it("throws the standardized API message and request id", async () => {
    server.use(
      http.get("*/api/v1/appointments", () =>
        HttpResponse.json(
          {
            error: {
              code: "unavailable",
              message: "API indisponível",
              details: {},
              request_id: "r1",
            },
          },
          { status: 503 },
        ),
      ),
    );

    await expect(
      api.listAppointments({ date: "2026-08-11" }),
    ).rejects.toMatchObject({
      name: "ApiError",
      message: "API indisponível",
      code: "unavailable",
      requestId: "r1",
      status: 503,
    } satisfies Partial<ApiError>);
  });

  it("serializes filters and returns a typed appointment page", async () => {
    server.use(
      http.get("*/api/v1/appointments", ({ request }) => {
        const url = new URL(request.url);
        expect(url.searchParams.get("date")).toBe("2026-08-11");
        expect(url.searchParams.get("status")).toBe("pending");
        expect(url.searchParams.get("page")).toBe("2");
        return HttpResponse.json({
          items: [],
          pagination: { page: 2, page_size: 20, total: 0, total_pages: 0 },
        });
      }),
    );

    const result = await api.listAppointments({
      date: "2026-08-11",
      status: "pending",
      page: 2,
    });

    expect(result.pagination.page).toBe(2);
    expect(result.items).toEqual([]);
  });
});
