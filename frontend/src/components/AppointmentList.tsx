import type { Appointment } from "../api/types";
import { formatAppointmentTime, formatBrazilianPhone } from "../utils/format";
import { StatusBadge } from "./StatusBadge";

interface AppointmentListProps {
  appointments: Appointment[];
  actionsDisabled: boolean;
  onRespond: (appointmentId: string, status: "confirmed" | "declined") => void;
  onRetry: (messageId: string) => void;
}

export function AppointmentList({
  appointments,
  actionsDisabled,
  onRespond,
  onRetry,
}: AppointmentListProps) {
  return (
    <div className="table-scroll">
      <table aria-label="Agenda de consultas">
        <thead>
          <tr>
            <th scope="col">Paciente</th>
            <th scope="col">Horário</th>
            <th scope="col">Telefone</th>
            <th scope="col">Procedimento</th>
            <th scope="col">Consulta</th>
            <th scope="col">Mensagem</th>
            <th scope="col">Tentativas</th>
            <th scope="col">Ações</th>
          </tr>
        </thead>
        <tbody>
          {appointments.map((appointment) => (
            <tr key={appointment.id}>
              <td data-label="Paciente">{appointment.patient_name}</td>
              <td data-label="Horário">{formatAppointmentTime(appointment.scheduled_at)}</td>
              <td data-label="Telefone">{formatBrazilianPhone(appointment.phone)}</td>
              <td data-label="Procedimento">{appointment.procedure}</td>
              <td data-label="Consulta">
                <StatusBadge status={appointment.status} />
              </td>
              <td data-label="Mensagem">
                {appointment.message ? (
                  <>
                    <StatusBadge status={appointment.message.status} />
                    {appointment.message.last_error ? (
                      <span className="message-error">{appointment.message.last_error}</span>
                    ) : null}
                  </>
                ) : (
                  <span className="muted">Não disparada</span>
                )}
              </td>
              <td data-label="Tentativas">
                {appointment.message
                  ? `${appointment.message.attempt_count}/${appointment.message.max_attempts}`
                  : "—"}
              </td>
              <td data-label="Ações">
                <AppointmentActions
                  appointment={appointment}
                  disabled={actionsDisabled}
                  onRespond={onRespond}
                  onRetry={onRetry}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AppointmentActions({
  appointment,
  disabled,
  onRespond,
  onRetry,
}: {
  appointment: Appointment;
  disabled: boolean;
  onRespond: AppointmentListProps["onRespond"];
  onRetry: AppointmentListProps["onRetry"];
}) {
  const message = appointment.message;

  if (message?.status === "sent" && appointment.status === "pending") {
    return (
      <div className="row-actions">
        <button
          type="button"
          className="action-button action-confirm"
          disabled={disabled}
          onClick={() => onRespond(appointment.id, "confirmed")}
        >
          Confirmar
        </button>
        <button
          type="button"
          className="action-button action-decline"
          disabled={disabled}
          onClick={() => onRespond(appointment.id, "declined")}
        >
          Recusar
        </button>
      </div>
    );
  }

  if (message?.status === "failed") {
    const exhausted = message.attempt_count >= message.max_attempts;
    return (
      <button
        type="button"
        className="action-button"
        disabled={disabled || exhausted}
        onClick={() => onRetry(message.id)}
      >
        {exhausted ? "Limite atingido" : "Reprocessar"}
      </button>
    );
  }

  if (appointment.status !== "pending") {
    return <span className="muted">Resposta registrada</span>;
  }

  return <span className="muted">Aguardando envio</span>;
}
