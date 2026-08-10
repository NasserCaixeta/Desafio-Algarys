import type { AppointmentStatus, MessageStatus } from "../api/types";

const labels: Record<AppointmentStatus | MessageStatus, string> = {
  pending: "Pendente",
  processing: "Processando",
  sent: "Enviada",
  failed: "Falhou",
  confirmed: "Confirmada",
  declined: "Recusada",
};

export function StatusBadge({ status }: { status: AppointmentStatus | MessageStatus }) {
  return <span className={`status-badge status-${status}`}>{labels[status]}</span>;
}
