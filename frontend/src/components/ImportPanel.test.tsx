import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, delay, http } from "msw";

import { ImportPanel } from "./ImportPanel";
import { server } from "../test/server";

function renderImportPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ImportPanel />
    </QueryClientProvider>,
  );
}

function csvFile() {
  return new File(
    [
      "data_hora,paciente,telefone,procedimento\n",
      "11/08/2026 09:30,Ana,34999991111,Consulta\n",
    ],
    "agenda.csv",
    { type: "text/csv" },
  );
}

it("uploads the CSV and shows partial import errors", async () => {
  server.use(
    http.post("*/api/v1/imports/appointments", ({ request }) => {
      expect(request.headers.get("Content-Type")).toMatch(/^multipart\/form-data; boundary=/);
      return HttpResponse.json({
        summary: { total_rows: 2, imported: 1, rejected: 1, duplicates: 0 },
        appointment_dates: ["2026-08-11"],
        imported_lines: [2],
        duplicate_lines: [],
        errors: [
          {
            line_number: 3,
            raw_data: {
              data_hora: "invalid",
              paciente: "Beto",
              telefone: "123",
              procedimento: "Retorno",
            },
            reason: "Telefone inválido",
          },
        ],
      });
    }),
  );
  const user = userEvent.setup();
  renderImportPanel();

  await user.upload(screen.getByLabelText("Arquivo CSV"), csvFile());
  await user.click(screen.getByRole("button", { name: "Importar agenda" }));

  expect(await screen.findByText("2 linhas processadas")).toBeInTheDocument();
  expect(await screen.findByText("1 importada")).toBeInTheDocument();
  expect(screen.getByText("1 rejeitada")).toBeInTheDocument();
  expect(screen.getByText("Linha 3")).toBeInTheDocument();
  expect(screen.getByText("Telefone inválido")).toBeInTheDocument();
});

it("accepts a file dropped on the labeled drop zone", () => {
  renderImportPanel();
  const file = csvFile();

  fireEvent.drop(screen.getByLabelText("Área para soltar o CSV"), {
    dataTransfer: { files: [file] },
  });

  expect(screen.getByText("agenda.csv")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Importar agenda" })).toBeEnabled();
});

it("disables submit and announces progress while uploading", async () => {
  server.use(
    http.post("*/api/v1/imports/appointments", async () => {
      await delay(100);
      return HttpResponse.json({
        summary: { total_rows: 1, imported: 1, rejected: 0, duplicates: 0 },
        appointment_dates: ["2026-08-11"],
        imported_lines: [2],
        duplicate_lines: [],
        errors: [],
      });
    }),
  );
  const user = userEvent.setup();
  renderImportPanel();
  await user.upload(screen.getByLabelText("Arquivo CSV"), csvFile());

  await user.click(screen.getByRole("button", { name: "Importar agenda" }));

  expect(screen.getByRole("button", { name: "Importando…" })).toBeDisabled();
  expect(await screen.findByText("1 importada")).toBeInTheDocument();
});

it("shows duplicate summary and standardized API failure", async () => {
  let attempt = 0;
  server.use(
    http.post("*/api/v1/imports/appointments", () => {
      attempt += 1;
      if (attempt === 1) {
        return HttpResponse.json({
          summary: { total_rows: 2, imported: 0, rejected: 0, duplicates: 2 },
          appointment_dates: ["2026-08-11"],
          imported_lines: [],
          duplicate_lines: [2, 3],
          errors: [],
        });
      }
      return HttpResponse.json(
        {
          error: {
            code: "upload_too_large",
            message: "Arquivo muito grande",
            details: {},
            request_id: "r-upload",
          },
        },
        { status: 413 },
      );
    }),
  );
  const user = userEvent.setup();
  renderImportPanel();
  await user.upload(screen.getByLabelText("Arquivo CSV"), csvFile());

  await user.click(screen.getByRole("button", { name: "Importar agenda" }));
  expect(await screen.findByText("2 duplicadas")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Importar agenda" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Arquivo muito grande");
  expect(screen.queryByText("2 duplicadas")).not.toBeInTheDocument();
});
