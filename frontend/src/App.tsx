import { useState } from "react";

import type { AppointmentStatus } from "./api/types";
import { AppointmentList } from "./components/AppointmentList";
import { DashboardFilters } from "./components/DashboardFilters";
import { ImportPanel } from "./components/ImportPanel";
import { useAppointments } from "./hooks/useAppointments";
import { useMessageActions } from "./hooks/useMessageActions";
import { todayInClinicTimezone } from "./utils/format";

export function App() {
  const [date, setDate] = useState(todayInClinicTimezone);
  const [status, setStatus] = useState<AppointmentStatus | "">("");
  const [page, setPage] = useState(1);
  const [feedback, setFeedback] = useState("");
  const [actionError, setActionError] = useState("");
  const appointments = useAppointments({ date, status, page, pageSize: 20 });
  const actions = useMessageActions();
  const actionsDisabled =
    actions.dispatch.isPending || actions.respond.isPending || actions.retry.isPending;

  function changeDate(value: string) {
    setDate(value);
    setPage(1);
  }

  function changeStatus(value: AppointmentStatus | "") {
    setStatus(value);
    setPage(1);
  }

  async function dispatchConfirmations() {
    if (!window.confirm(`Disparar as confirmações da agenda de ${date}?`)) return;
    prepareAction();
    try {
      const result = await actions.dispatch.mutateAsync(date);
      setFeedback(
        `${result.created} ${result.created === 1 ? "mensagem criada" : "mensagens criadas"}, ` +
          `${result.already_existing} ${result.already_existing === 1 ? "duplicada" : "duplicadas"} e ` +
          `${result.ignored} ${result.ignored === 1 ? "ignorada" : "ignoradas"}`,
      );
    } catch (error) {
      setActionError(messageFrom(error));
    }
  }

  async function respond(appointmentId: string, response: "confirmed" | "declined") {
    prepareAction();
    try {
      await actions.respond.mutateAsync({ appointmentId, status: response });
      setFeedback(response === "confirmed" ? "Consulta confirmada" : "Consulta recusada");
    } catch (error) {
      setActionError(messageFrom(error));
    }
  }

  async function retry(messageId: string) {
    prepareAction();
    try {
      await actions.retry.mutateAsync(messageId);
      setFeedback("Mensagem agendada para reprocessamento");
    } catch (error) {
      setActionError(messageFrom(error));
    }
  }

  function prepareAction() {
    setFeedback("");
    setActionError("");
  }

  return (
    <main>
      <header className="page-header">
        <p className="eyebrow">Clínica</p>
        <h1>Confirmação de consultas</h1>
        <p>Acompanhe a agenda e o processamento das mensagens.</p>
      </header>

      <ImportPanel />

      <section className="panel" aria-labelledby="agenda-title">
        <div className="panel-heading">
          <div>
            <h2 id="agenda-title">Agenda do dia</h2>
            <p>Filtre os agendamentos por data e situação da consulta.</p>
          </div>
          <div className="dashboard-controls">
            <DashboardFilters
              date={date}
              status={status}
              onDateChange={changeDate}
              onStatusChange={changeStatus}
            />
            <button
              type="button"
              className="primary-button dispatch-button"
              disabled={actionsDisabled || !date}
              onClick={() => void dispatchConfirmations()}
            >
              {actions.dispatch.isPending ? "Disparando…" : "Disparar confirmações"}
            </button>
          </div>
        </div>

        {feedback ? <p role="status" className="action-feedback">{feedback}</p> : null}
        {actionError ? <p role="alert" className="action-feedback state-error">{actionError}</p> : null}

        {appointments.isPending ? (
          <div role="status" aria-label="Carregando agenda" className="state-message">
            Carregando agenda…
          </div>
        ) : appointments.isError ? (
          <div role="alert" className="state-message state-error">
            {appointments.error.message}
          </div>
        ) : appointments.data.items.length === 0 ? (
          <div className="state-message">Nenhum agendamento encontrado</div>
        ) : (
          <AppointmentList
            appointments={appointments.data.items}
            actionsDisabled={actionsDisabled}
            onRespond={(appointmentId, response) => void respond(appointmentId, response)}
            onRetry={(messageId) => void retry(messageId)}
          />
        )}

        {appointments.data ? (
          <nav className="pagination" aria-label="Paginação da agenda">
            <button
              type="button"
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={page <= 1}
            >
              Página anterior
            </button>
            <span>
              Página {page} de {Math.max(appointments.data.pagination.total_pages, 1)}
            </span>
            <button
              type="button"
              onClick={() => setPage((current) => current + 1)}
              disabled={page >= appointments.data.pagination.total_pages}
            >
              Próxima página
            </button>
          </nav>
        ) : null}
      </section>
    </main>
  );
}

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : "Não foi possível concluir a ação.";
}
