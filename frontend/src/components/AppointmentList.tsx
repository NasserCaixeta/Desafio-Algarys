import type { Appointment, AppointmentMessage } from "../api/types";
import { formatAppointmentTime, formatBrazilianPhone } from "../utils/format";
import { StatusBadge } from "./StatusBadge";

interface AppointmentListProps {
  appointments: Appointment[];
  actionsDisabled: boolean;
  selectedAppointmentIds: ReadonlySet<string>;
  onSelectionChange: (appointmentId: string, selected: boolean) => void;
  onVisibleSelectionChange: (appointmentIds: string[], selected: boolean) => void;
  onRespond: (appointmentId: string, status: "confirmed" | "declined") => void;
  onRetry: (messageId: string) => void;
}

export function AppointmentList({
  appointments,
  actionsDisabled,
  selectedAppointmentIds,
  onSelectionChange,
  onVisibleSelectionChange,
  onRespond,
  onRetry,
}: AppointmentListProps) {
  const selectableAppointmentIds = appointments
    .filter(isSelectableForDispatch)
    .map((appointment) => appointment.id);
  const allVisibleSelected =
    selectableAppointmentIds.length > 0 &&
    selectableAppointmentIds.every((appointmentId) =>
      selectedAppointmentIds.has(appointmentId),
    );

  return (
    <div className="table-scroll">
      <table aria-label="Agenda de consultas">
        <thead>
          <tr>
            <th scope="col" className="selection-cell">
              <input
                type="checkbox"
                aria-label="Selecionar todos os agendamentos elegíveis desta página"
                checked={allVisibleSelected}
                disabled={actionsDisabled || selectableAppointmentIds.length === 0}
                onChange={(event) =>
                  onVisibleSelectionChange(selectableAppointmentIds, event.target.checked)
                }
              />
            </th>
            <th scope="col">Paciente</th>
            <th scope="col">Horário</th>
            <th scope="col">Telefone</th>
            <th scope="col">Procedimento</th>
            <th scope="col">Resposta do paciente</th>
            <th scope="col">Status do envio</th>
            <th scope="col">Ações</th>
          </tr>
        </thead>
        <tbody>
          {appointments.map((appointment) => (
            <tr key={appointment.id}>
              <td data-label="Selecionar" className="selection-cell">
                <input
                  type="checkbox"
                  aria-label={`Selecionar ${appointment.patient_name}`}
                  checked={selectedAppointmentIds.has(appointment.id)}
                  disabled={actionsDisabled || !isSelectableForDispatch(appointment)}
                  onChange={(event) =>
                    onSelectionChange(appointment.id, event.target.checked)
                  }
                />
              </td>
              <td data-label="Paciente">{appointment.patient_name}</td>
              <td data-label="Horário">{formatAppointmentTime(appointment.scheduled_at)}</td>
              <td data-label="Telefone">{formatBrazilianPhone(appointment.phone)}</td>
              <td data-label="Procedimento">{appointment.procedure}</td>
              <td data-label="Resposta do paciente">
                <StatusBadge status={appointment.status} />
              </td>
              <td data-label="Status do envio">
                <MessageDeliveryStatus message={appointment.message} />
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

function isSelectableForDispatch(appointment: Appointment): boolean {
  return appointment.status === "pending" && appointment.message === null;
}

function MessageDeliveryStatus({ message }: { message: AppointmentMessage | null }) {
  if (message === null) return <span className="muted">Não enviada</span>;

  if (message.status === "pending") {
    const isRetry = message.attempt_count > 0;
    return (
      <div className="message-status-details">
        <StatusBadge
          status="pending"
          label={isRetry ? "Nova tentativa agendada" : "Aguardando envio"}
        />
        {isRetry ? (
          <span className="delivery-detail">
            {completedAttemptsLabel(message.attempt_count)} de {message.max_attempts}
          </span>
        ) : null}
      </div>
    );
  }

  if (message.status === "processing") {
    return (
      <div className="message-status-details">
        <StatusBadge status="processing" label="Enviando" />
        <span className="delivery-detail">
          Tentativa de envio {message.attempt_count} de {message.max_attempts} em andamento
        </span>
      </div>
    );
  }

  if (message.status === "sent") {
    return <StatusBadge status="sent" />;
  }

  const exhausted = message.attempt_count >= message.max_attempts;
  return (
    <div className="message-status-details">
      <StatusBadge
        status="failed"
        label={exhausted ? "Falha definitiva" : "Falha temporária"}
      />
      <span className="delivery-detail">
        {exhausted
          ? `${message.attempt_count} tentativas de envio realizadas`
          : `Tentativa de envio ${message.attempt_count} de ${message.max_attempts}`}
      </span>
      {message.last_error ? (
        <span className="message-error">
          <strong>Erro:</strong> <span>{message.last_error}</span>
        </span>
      ) : null}
      {!exhausted ? (
        <span className="retry-scheduled">Nova tentativa automática agendada</span>
      ) : null}
    </div>
  );
}

function completedAttemptsLabel(attemptCount: number): string {
  return `${attemptCount} ${attemptCount === 1 ? "tentativa concluída" : "tentativas concluídas"}`;
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
          Paciente confirmou
        </button>
        <button
          type="button"
          className="action-button action-decline"
          disabled={disabled}
          onClick={() => onRespond(appointment.id, "declined")}
        >
          Paciente recusou
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
        {exhausted ? "Limite atingido" : "Tentar novamente agora"}
      </button>
    );
  }

  if (appointment.status !== "pending") {
    return <span className="muted">Resposta registrada</span>;
  }

  return <span className="muted">Aguardando envio</span>;
}
