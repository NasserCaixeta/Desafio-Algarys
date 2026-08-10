import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, expect, it, vi } from "vitest";

import { App } from "../App";
import type { AppointmentPage } from "../api/types";
import { server } from "../test/server";

const page: AppointmentPage = {
  items: [
    {
      id: "ana-appointment",
      scheduled_at: "2026-08-11T12:30:00Z",
      patient_name: "Ana Souza",
      phone: "+5534999991111",
      procedure: "Consulta",
      status: "pending",
      message: {
        id: "ana-message",
        status: "sent",
        attempt_count: 1,
        max_attempts: 3,
        last_error: null,
      },
    },
    {
      id: "beto-appointment",
      scheduled_at: "2026-08-11T13:30:00Z",
      patient_name: "Beto Lima",
      phone: "+5534999992222",
      procedure: "Retorno",
      status: "pending",
      message: {
        id: "beto-message",
        status: "failed",
        attempt_count: 3,
        max_attempts: 3,
        last_error: "simulated failure",
      },
    },
    {
      id: "carla-appointment",
      scheduled_at: "2026-08-11T14:30:00Z",
      patient_name: "Carla Melo",
      phone: "+5534999993333",
      procedure: "Avaliação",
      status: "pending",
      message: {
        id: "carla-message",
        status: "failed",
        attempt_count: 1,
        max_attempts: 3,
        last_error: "simulated failure",
      },
    },
  ],
  pagination: { page: 1, page_size: 20, total: 3, total_pages: 1 },
};

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );
}

function serveAppointments(counter?: { value: number }) {
  server.use(
    http.get("*/api/v1/appointments", () => {
      if (counter) counter.value += 1;
      return HttpResponse.json(page);
    }),
  );
}

afterEach(() => vi.restoreAllMocks());

it("confirms dispatch and reports created messages", async () => {
  serveAppointments();
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
  let receivedDate = "";
  server.use(
    http.post("*/api/v1/confirmations/dispatch", async ({ request }) => {
      receivedDate = ((await request.json()) as { date: string }).date;
      return HttpResponse.json({
        eligible: 3,
        created: 3,
        already_existing: 0,
        ignored: 0,
        queued: 3,
        pending_reconciliation: 0,
      });
    }),
  );
  const user = userEvent.setup();
  renderApp();

  await user.click(await screen.findByRole("button", { name: "Disparar confirmações" }));

  expect(confirm).toHaveBeenCalledOnce();
  expect(receivedDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  expect(await screen.findByText("3 mensagens criadas")).toBeInTheDocument();
});

it("does not dispatch when the operator cancels confirmation", async () => {
  serveAppointments();
  vi.spyOn(window, "confirm").mockReturnValue(false);
  let dispatchCount = 0;
  server.use(
    http.post("*/api/v1/confirmations/dispatch", () => {
      dispatchCount += 1;
      return HttpResponse.json({});
    }),
  );
  const user = userEvent.setup();
  renderApp();

  await user.click(await screen.findByRole("button", { name: "Disparar confirmações" }));

  expect(dispatchCount).toBe(0);
});

it("enables answers only for sent and disables exhausted retry", async () => {
  serveAppointments();
  renderApp();

  const sentRow = await screen.findByRole("row", { name: /Ana Souza/ });
  expect(within(sentRow).getByRole("button", { name: "Confirmar" })).toBeEnabled();
  expect(within(sentRow).getByRole("button", { name: "Recusar" })).toBeEnabled();
  const exhaustedRow = screen.getByRole("row", { name: /Beto Lima/ });
  expect(within(exhaustedRow).getByRole("button", { name: "Limite atingido" })).toBeDisabled();
  const retryableRow = screen.getByRole("row", { name: /Carla Melo/ });
  expect(within(retryableRow).getByRole("button", { name: "Reprocessar" })).toBeEnabled();
});

it.each([
  ["Confirmar", "confirmed", "Consulta confirmada"],
  ["Recusar", "declined", "Consulta recusada"],
] as const)("records patient response with %s", async (button, status, feedback) => {
  const requests = { value: 0 };
  serveAppointments(requests);
  let receivedStatus = "";
  server.use(
    http.post("*/api/v1/appointments/ana-appointment/response", async ({ request }) => {
      receivedStatus = ((await request.json()) as { status: string }).status;
      return HttpResponse.json({ id: "ana-appointment", status });
    }),
  );
  const user = userEvent.setup();
  renderApp();
  const row = await screen.findByRole("row", { name: /Ana Souza/ });

  await user.click(within(row).getByRole("button", { name: button }));

  expect(receivedStatus).toBe(status);
  expect(await screen.findByText(feedback)).toBeInTheDocument();
  await waitFor(() => expect(requests.value).toBeGreaterThan(1));
});

it("retries a failed message and refreshes appointments", async () => {
  const requests = { value: 0 };
  serveAppointments(requests);
  server.use(
    http.post("*/api/v1/messages/carla-message/retry", () =>
      HttpResponse.json({
        id: "carla-message",
        status: "pending",
        attempt_count: 1,
        max_attempts: 3,
        queued: true,
        pending_reconciliation: false,
        enqueued_at: "2026-08-11T12:00:00Z",
        next_enqueue_at: null,
      }),
    ),
  );
  const user = userEvent.setup();
  renderApp();
  const row = await screen.findByRole("row", { name: /Carla Melo/ });

  await user.click(within(row).getByRole("button", { name: "Reprocessar" }));

  expect(await screen.findByText("Mensagem agendada para reprocessamento")).toBeInTheDocument();
  await waitFor(() => expect(requests.value).toBeGreaterThan(1));
});

it("polls while a message still has asynchronous work", async () => {
  const requests = { value: 0 };
  server.use(
    http.get("*/api/v1/appointments", () => {
      requests.value += 1;
      return HttpResponse.json({
        ...page,
        items: [
          {
            ...page.items[0],
            message: { ...page.items[0]?.message, status: "processing" },
          },
        ],
      });
    }),
  );
  renderApp();

  await screen.findByRole("row", { name: /Ana Souza/ });
  await waitFor(() => expect(requests.value).toBeGreaterThan(1), { timeout: 3_000 });
});
