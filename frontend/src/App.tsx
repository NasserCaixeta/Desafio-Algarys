import { useEffect, useState } from "react";

import type { AppointmentStatus, ImportReport } from "./api/types";
import { AppointmentDateNavigation } from "./components/AppointmentDateNavigation";
import { AppointmentList } from "./components/AppointmentList";
import { DashboardFilters } from "./components/DashboardFilters";
import { ImportPanel } from "./components/ImportPanel";
import { InitialLoadingScreen } from "./components/InitialLoadingScreen";
import { useAppointments } from "./hooks/useAppointments";
import { useAppointmentDates } from "./hooks/useAppointmentDates";
import { useMessageActions } from "./hooks/useMessageActions";
import { todayInClinicTimezone } from "./utils/format";

export function App() {
  const [introFinished, setIntroFinished] = useState(import.meta.env.MODE === "test");
  const [date, setDate] = useState(todayInClinicTimezone);
  const [status, setStatus] = useState<AppointmentStatus | "">("");
  const [page, setPage] = useState(1);
  const [feedback, setFeedback] = useState("");
  const [actionError, setActionError] = useState("");
  const [selectedAppointmentIds, setSelectedAppointmentIds] = useState<Set<string>>(
    () => new Set(),
  );
  const appointments = useAppointments({ date, status, page, pageSize: 20 });
  const appointmentDates = useAppointmentDates();
  const actions = useMessageActions();
  const selectedCount = selectedAppointmentIds.size;
  const actionsDisabled =
    actions.dispatch.isPending || actions.respond.isPending || actions.retry.isPending;

  useEffect(() => {
    if (introFinished) return;
    const timeout = window.setTimeout(() => setIntroFinished(true), 900);
    return () => window.clearTimeout(timeout);
  }, [introFinished]);

  function changeDate(value: string) {
    setDate(value);
    setPage(1);
    setSelectedAppointmentIds(new Set());
  }

  function changeStatus(value: AppointmentStatus | "") {
    setStatus(value);
    setPage(1);
    setSelectedAppointmentIds(new Set());
  }

  function handleImported(report: ImportReport) {
    const displayedAgendaIsEmpty = (appointments.data?.pagination.total ?? 0) === 0;
    if (!displayedAgendaIsEmpty || report.appointment_dates.length === 0) return;

    const importedDate = nearestDate(report.appointment_dates, todayInClinicTimezone());
    setStatus("");
    changeDate(importedDate);
  }

  function setAppointmentSelected(appointmentId: string, selected: boolean) {
    setSelectedAppointmentIds((current) => {
      const next = new Set(current);
      if (selected) next.add(appointmentId);
      else next.delete(appointmentId);
      return next;
    });
  }

  function setVisibleAppointmentsSelected(appointmentIds: string[], selected: boolean) {
    setSelectedAppointmentIds((current) => {
      const next = new Set(current);
      for (const appointmentId of appointmentIds) {
        if (selected) next.add(appointmentId);
        else next.delete(appointmentId);
      }
      return next;
    });
  }

  async function dispatchConfirmations(appointmentIds?: string[]) {
    const confirmation = dispatchConfirmationText(date, appointmentIds);
    if (!window.confirm(confirmation)) return;
    prepareAction();
    try {
      const result = await actions.dispatch.mutateAsync({ date, appointmentIds });
      setSelectedAppointmentIds(new Set());
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
      setFeedback(
        response === "confirmed"
          ? "Resposta registrada: paciente confirmou"
          : "Resposta registrada: paciente recusou",
      );
    } catch (error) {
      setActionError(messageFrom(error));
    }
  }

  async function retry(messageId: string) {
    prepareAction();
    try {
      const result = await actions.retry.mutateAsync(messageId);
      setFeedback(
        result.queued
          ? "Nova tentativa enviada para a fila"
          : "Nova tentativa agendada e aguardando reconciliação da fila",
      );
    } catch (error) {
      setActionError(messageFrom(error));
    }
  }

  function prepareAction() {
    setFeedback("");
    setActionError("");
  }

  if (!introFinished || (appointments.isPending && appointmentDates.isPending)) {
    return <InitialLoadingScreen />;
  }

  return (
    <main>
      <header className="page-header">
        <p className="eyebrow">Clínica</p>
        <h1>Confirmação de consultas</h1>
        <p>Acompanhe a agenda e o processamento das mensagens.</p>
      </header>

      <ImportPanel onImported={handleImported} />

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
            <div className="dispatch-actions" aria-label="Enviar solicitações de confirmação">
              <button
                type="button"
                className="primary-button dispatch-button"
                disabled={actionsDisabled || !date || selectedCount === 0}
                onClick={() => void dispatchConfirmations([...selectedAppointmentIds])}
              >
                {actions.dispatch.isPending
                  ? "Enviando…"
                  : selectedDispatchLabel(selectedCount)}
              </button>
              <button
                type="button"
                className="action-button dispatch-button"
                disabled={actionsDisabled || !date}
                onClick={() => void dispatchConfirmations()}
              >
                {actions.dispatch.isPending ? "Enviando…" : "Enviar para todos do dia"}
              </button>
            </div>
          </div>
        </div>

        <AppointmentDateNavigation
          calendar={appointmentDates.data}
          currentDate={date}
          isPending={appointmentDates.isPending}
          isError={appointmentDates.isError}
          onDateChange={changeDate}
        />

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
            selectedAppointmentIds={selectedAppointmentIds}
            onSelectionChange={setAppointmentSelected}
            onVisibleSelectionChange={setVisibleAppointmentsSelected}
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

function dispatchConfirmationText(date: string, appointmentIds?: string[]): string {
  if (appointmentIds === undefined) {
    return `Enviar solicitações de confirmação para todos os pacientes elegíveis de ${date}?`;
  }
  if (appointmentIds.length === 1) {
    return "Enviar solicitação de confirmação para 1 paciente selecionado?";
  }
  return `Enviar solicitações de confirmação para ${appointmentIds.length} pacientes selecionados?`;
}

function selectedDispatchLabel(selectedCount: number): string {
  if (selectedCount === 0) return "Enviar para selecionados";
  if (selectedCount === 1) return "Enviar para 1 selecionado";
  return `Enviar para ${selectedCount} selecionados`;
}

function nearestDate(dates: string[], referenceDate: string): string {
  const referenceDay = isoDateToUtcDay(referenceDate);
  return [...dates].sort((left, right) => {
    const leftDistance = Math.abs(isoDateToUtcDay(left) - referenceDay);
    const rightDistance = Math.abs(isoDateToUtcDay(right) - referenceDay);
    return leftDistance - rightDistance || left.localeCompare(right);
  })[0]!;
}

function isoDateToUtcDay(value: string): number {
  const [year, month, day] = value.split("-");
  return Date.UTC(Number(year), Number(month) - 1, Number(day));
}
