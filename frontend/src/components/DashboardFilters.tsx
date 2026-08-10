import type { AppointmentStatus } from "../api/types";

interface DashboardFiltersProps {
  date: string;
  status: AppointmentStatus | "";
  onDateChange: (value: string) => void;
  onStatusChange: (value: AppointmentStatus | "") => void;
}

export function DashboardFilters({
  date,
  status,
  onDateChange,
  onStatusChange,
}: DashboardFiltersProps) {
  return (
    <div className="filters" aria-label="Filtros da agenda">
      <label>
        Data
        <input
          type="date"
          value={date}
          onChange={(event) => onDateChange(event.target.value)}
        />
      </label>
      <label>
        Status
        <select
          value={status}
          onChange={(event) =>
            onStatusChange(event.target.value as AppointmentStatus | "")
          }
        >
          <option value="">Todos</option>
          <option value="pending">Pendente</option>
          <option value="confirmed">Confirmada</option>
          <option value="declined">Recusada</option>
        </select>
      </label>
    </div>
  );
}
