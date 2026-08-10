import type { Appointment } from "../api/types";
import { formatAppointmentTime, formatBrazilianPhone } from "../utils/format";
import { StatusBadge } from "./StatusBadge";

export function AppointmentList({ appointments }: { appointments: Appointment[] }) {
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
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
