import { useState } from "react";

import type { AppointmentStatus } from "./api/types";
import { AppointmentList } from "./components/AppointmentList";
import { DashboardFilters } from "./components/DashboardFilters";
import { ImportPanel } from "./components/ImportPanel";
import { useAppointments } from "./hooks/useAppointments";
import { todayInClinicTimezone } from "./utils/format";

export function App() {
  const [date, setDate] = useState(todayInClinicTimezone);
  const [status, setStatus] = useState<AppointmentStatus | "">("");
  const [page, setPage] = useState(1);
  const appointments = useAppointments({ date, status, page, pageSize: 20 });

  function changeDate(value: string) {
    setDate(value);
    setPage(1);
  }

  function changeStatus(value: AppointmentStatus | "") {
    setStatus(value);
    setPage(1);
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
          <DashboardFilters
            date={date}
            status={status}
            onDateChange={changeDate}
            onStatusChange={changeStatus}
          />
        </div>

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
          <AppointmentList appointments={appointments.data.items} />
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
