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

const selectionPage: AppointmentPage = {
  items: [
    {
      id: "dora-appointment",
      scheduled_at: "2026-08-11T15:30:00Z",
      patient_name: "Dora Nunes",
      phone: "+5534999994444",
      procedure: "Consulta",
      status: "pending",
      message: null,
    },
    {
      id: "enzo-appointment",
      scheduled_at: "2026-08-11T16:30:00Z",
      patient_name: "Enzo Reis",
      phone: "+5534999995555",
      procedure: "Retorno",
      status: "pending",
      message: null,
    },
    page.items[0]!,
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

function serveAppointments(
  counter?: { value: number },
  responsePage: AppointmentPage = page,
) {
  server.use(
    http.get("*/api/v1/appointments", () => {
      if (counter) counter.value += 1;
      return HttpResponse.json(responsePage);
    }),
  );
}

afterEach(() => vi.restoreAllMocks());

it("confirms dispatch for the whole day and reports created messages", async () => {
  serveAppointments();
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
  let receivedDate = "";
  server.use(
    http.post("*/api/v1/confirmations/dispatch", async ({ request }) => {
      const payload = (await request.json()) as { date: string; appointment_ids?: string[] };
      receivedDate = payload.date;
      expect(payload.appointment_ids).toBeUndefined();
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

  await user.click(await screen.findByRole("button", { name: "Enviar para todos do dia" }));

  expect(confirm).toHaveBeenCalledOnce();
  expect(receivedDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  expect(
    await screen.findByText("3 mensagens criadas, 0 duplicadas e 0 ignoradas"),
  ).toBeInTheDocument();
});

it("does not dispatch the whole day when the operator cancels confirmation", async () => {
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

  await user.click(await screen.findByRole("button", { name: "Enviar para todos do dia" }));

  expect(dispatchCount).toBe(0);
});

it("dispatches only selected eligible appointments", async () => {
  serveAppointments(undefined, selectionPage);
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
  let receivedIds: string[] | undefined;
  server.use(
    http.post("*/api/v1/confirmations/dispatch", async ({ request }) => {
      receivedIds = ((await request.json()) as { appointment_ids?: string[] }).appointment_ids;
      return HttpResponse.json({
        eligible: 1,
        created: 1,
        already_existing: 0,
        ignored: 0,
        queued: 1,
        pending_reconciliation: 0,
      });
    }),
  );
  const user = userEvent.setup();
  renderApp();

  const selectedButton = await screen.findByRole("button", { name: "Enviar para selecionados" });
  expect(selectedButton).toBeDisabled();
  await user.click(
    await screen.findByRole("checkbox", { name: "Selecionar Dora Nunes" }),
  );
  await user.click(screen.getByRole("button", { name: "Enviar para 1 selecionado" }));

  expect(confirm).toHaveBeenCalledWith(
    "Enviar solicitação de confirmação para 1 paciente selecionado?",
  );
  expect(receivedIds).toEqual(["dora-appointment"]);
  expect(await screen.findByText("1 mensagem criada, 0 duplicadas e 0 ignoradas")).toBeInTheDocument();
});

it("selects every eligible appointment visible on the page", async () => {
  serveAppointments(undefined, selectionPage);
  renderApp();
  const user = userEvent.setup();

  await user.click(
    await screen.findByRole("checkbox", {
      name: "Selecionar todos os agendamentos elegíveis desta página",
    }),
  );

  expect(screen.getByRole("checkbox", { name: "Selecionar Dora Nunes" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "Selecionar Enzo Reis" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "Selecionar Ana Souza" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Enviar para 2 selecionados" })).toBeEnabled();
});

it("shows attempts inside the delivery status and distinguishes temporary and final failures", async () => {
  serveAppointments();
  renderApp();

  const sentRow = await screen.findByRole("row", { name: /Ana Souza/ });
  expect(within(sentRow).getByRole("button", { name: "Paciente confirmou" })).toBeEnabled();
  expect(within(sentRow).getByRole("button", { name: "Paciente recusou" })).toBeEnabled();
  expect(within(sentRow).getByText("Enviada")).toBeInTheDocument();
  expect(within(sentRow).queryByText(/tentativa/i)).not.toBeInTheDocument();

  const exhaustedRow = screen.getByRole("row", { name: /Beto Lima/ });
  expect(within(exhaustedRow).getByText("Falha definitiva")).toBeInTheDocument();
  expect(within(exhaustedRow).getByText("3 tentativas de envio realizadas")).toBeInTheDocument();
  expect(within(exhaustedRow).getByRole("button", { name: "Limite atingido" })).toBeDisabled();

  const retryableRow = screen.getByRole("row", { name: /Carla Melo/ });
  expect(within(retryableRow).getByText("Falha temporária")).toBeInTheDocument();
  expect(within(retryableRow).getByText("Tentativa de envio 1 de 3")).toBeInTheDocument();
  expect(within(retryableRow).getByText("Nova tentativa automática agendada")).toBeInTheDocument();
  expect(
    within(retryableRow).getByRole("button", { name: "Tentar novamente agora" }),
  ).toBeEnabled();
  expect(
    screen.queryByRole("columnheader", { name: "Tentativas de envio" }),
  ).not.toBeInTheDocument();
});

it.each([
  ["Paciente confirmou", "confirmed", "Resposta registrada: paciente confirmou"],
  ["Paciente recusou", "declined", "Resposta registrada: paciente recusou"],
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

it.each([
  [true, "Nova tentativa enviada para a fila"],
  [false, "Nova tentativa agendada e aguardando reconciliação da fila"],
] as const)("retries a failed message with queued=%s", async (queued, feedback) => {
  const requests = { value: 0 };
  serveAppointments(requests);
  server.use(
    http.post("*/api/v1/messages/carla-message/retry", () =>
      HttpResponse.json({
        id: "carla-message",
        status: "pending",
        attempt_count: 1,
        max_attempts: 3,
        queued,
        pending_reconciliation: !queued,
        enqueued_at: "2026-08-11T12:00:00Z",
        next_enqueue_at: null,
      }),
    ),
  );
  const user = userEvent.setup();
  renderApp();
  const row = await screen.findByRole("row", { name: /Carla Melo/ });

  await user.click(within(row).getByRole("button", { name: "Tentar novamente agora" }));

  expect(await screen.findByText(feedback)).toBeInTheDocument();
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

  const processingRow = await screen.findByRole("row", { name: /Ana Souza/ });
  expect(within(processingRow).getByText("Enviando")).toBeInTheDocument();
  expect(
    within(processingRow).getByText("Tentativa de envio 1 de 3 em andamento"),
  ).toBeInTheDocument();
  await waitFor(() => expect(requests.value).toBeGreaterThan(1), { timeout: 3_000 });
});
