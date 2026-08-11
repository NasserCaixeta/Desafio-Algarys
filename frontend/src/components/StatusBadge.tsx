import type { AppointmentStatus, MessageStatus } from "../api/types";

const labels: Record<AppointmentStatus | MessageStatus, string> = {
  pending: "Pendente",
  processing: "Processando",
  sent: "Enviada",
  failed: "Falhou",
  confirmed: "Confirmada",
  declined: "Recusada",
};

export function StatusBadge({
  status,
  label,
}: {
  status: AppointmentStatus | MessageStatus;
  label?: string;
}) {
  return <span className={`status-badge status-${status}`}>{label ?? labels[status]}</span>;
}
