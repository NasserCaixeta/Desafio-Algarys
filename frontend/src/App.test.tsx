import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, delay, http } from "msw";

import { App } from "./App";
import type { AppointmentPage } from "./api/types";
import { server } from "./test/server";

const capturedRequests: URL[] = [];

const appointmentPage: AppointmentPage = {
  items: [
    {
      id: "appointment-1",
      scheduled_at: "2026-08-11T12:30:00Z",
      patient_name: "Ana Souza",
      phone: "+5534999991111",
      procedure: "Consulta inicial",
      status: "pending",
      message: {
        id: "message-1",
        status: "failed",
        attempt_count: 1,
        max_attempts: 3,
        last_error: "simulated failure",
      },
    },
  ],
  pagination: { page: 1, page_size: 20, total: 21, total_pages: 2 },
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

function useAppointmentResponse(page: AppointmentPage = appointmentPage) {
  server.use(
    http.get("*/api/v1/appointments", ({ request }) => {
      capturedRequests.push(new URL(request.url));
      return HttpResponse.json(page);
    }),
  );
}

beforeEach(() => {
  capturedRequests.length = 0;
});

it("renders appointments and sends selected filters", async () => {
  useAppointmentResponse();
  const user = userEvent.setup();

  renderApp();

  const row = await screen.findByRole("row", { name: /Ana Souza/ });
  expect(within(row).getByText("09:30")).toBeInTheDocument();
  expect(within(row).getByText("(34) 99999-1111")).toBeInTheDocument();
  expect(within(row).getByText("Consulta inicial")).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Status"), "confirmed");

  await waitFor(() => {
    expect(capturedRequests.at(-1)?.searchParams.get("status")).toBe("confirmed");
  });
});

it("renders loading and empty states", async () => {
  server.use(
    http.get("*/api/v1/appointments", async () => {
      await delay(100);
      return HttpResponse.json({
        items: [],
        pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 },
      });
    }),
  );

  renderApp();

  expect(screen.getByRole("status", { name: "Carregando agenda" })).toBeInTheDocument();
  expect(await screen.findByText("Nenhum agendamento encontrado")).toBeInTheDocument();
});

it("renders the standardized API error", async () => {
  server.use(
    http.get("*/api/v1/appointments", () =>
      HttpResponse.json(
        {
          error: {
            code: "unavailable",
            message: "Não foi possível carregar a agenda",
            details: {},
            request_id: "r-error",
          },
        },
        { status: 503 },
      ),
    ),
  );

  renderApp();

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Não foi possível carregar a agenda",
  );
});

it("shows the message error and changes page", async () => {
  useAppointmentResponse();
  const user = userEvent.setup();
  renderApp();

  expect(await screen.findByText("simulated failure")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Próxima página" }));

  await waitFor(() => {
    expect(capturedRequests.at(-1)?.searchParams.get("page")).toBe("2");
  });
});

it("shows dates that have appointments and navigates from their shortcuts", async () => {
  useAppointmentResponse();
  server.use(
    http.get("*/api/v1/appointments/calendar", () =>
      HttpResponse.json({
        items: [
          { date: "2026-08-18", count: 3 },
          { date: "2026-08-19", count: 1 },
        ],
      }),
    ),
  );
  const user = userEvent.setup();
  renderApp();

  await user.click(
    await screen.findByRole("button", { name: "18/08/2026 — 3 consultas" }),
  );

  await waitFor(() => {
    expect(capturedRequests.at(-1)?.searchParams.get("date")).toBe("2026-08-18");
  });
  expect(screen.getByLabelText("Data")).toHaveValue("2026-08-18");
});

it("opens the imported date automatically when the displayed agenda is empty", async () => {
  let imported = false;
  server.use(
    http.get("*/api/v1/appointments/calendar", () =>
      HttpResponse.json({
        items: imported ? [{ date: "2026-08-18", count: 1 }] : [],
      }),
    ),
    http.get("*/api/v1/appointments", ({ request }) => {
      const requestedDate = new URL(request.url).searchParams.get("date");
      capturedRequests.push(new URL(request.url));
      if (requestedDate === "2026-08-18") {
        return HttpResponse.json({
          ...appointmentPage,
          items: [
            {
              ...appointmentPage.items[0],
              id: "imported-appointment",
              patient_name: "Paciente importado",
              scheduled_at: "2026-08-18T12:30:00Z",
            },
          ],
          pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
        });
      }
      return HttpResponse.json({
        items: [],
        pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 },
      });
    }),
    http.post("*/api/v1/imports/appointments", () => {
      imported = true;
      return HttpResponse.json({
        summary: { total_rows: 1, imported: 1, rejected: 0, duplicates: 0 },
        appointment_dates: ["2026-08-18"],
        imported_lines: [2],
        duplicate_lines: [],
        errors: [],
      });
    }),
  );
  const user = userEvent.setup();
  renderApp();
  await screen.findByText("Nenhum agendamento encontrado");

  const file = new File(
    [
      "data_hora,paciente,telefone,procedimento\n",
      "18/08/2026 09:30,Paciente importado,34999991111,Consulta\n",
    ],
    "agenda.csv",
    { type: "text/csv" },
  );
  await user.upload(screen.getByLabelText("Arquivo CSV"), file);
  await user.click(screen.getByRole("button", { name: "Importar agenda" }));

  expect(await screen.findByText("Paciente importado")).toBeInTheDocument();
  expect(screen.getByLabelText("Data")).toHaveValue("2026-08-18");
});
