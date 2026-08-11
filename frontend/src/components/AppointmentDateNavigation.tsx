import type { AppointmentCalendar } from "../api/types";

interface AppointmentDateNavigationProps {
  calendar: AppointmentCalendar | undefined;
  currentDate: string;
  isPending: boolean;
  isError: boolean;
  onDateChange: (date: string) => void;
}

export function AppointmentDateNavigation({
  calendar,
  currentDate,
  isPending,
  isError,
  onDateChange,
}: AppointmentDateNavigationProps) {
  return (
    <section className="appointment-dates" aria-labelledby="appointment-dates-title">
      <div className="appointment-dates-heading">
        <h3 id="appointment-dates-title">Datas com agenda</h3>
        <span>Selecione um dia que possui consultas</span>
      </div>

      {isPending ? <p className="muted">Carregando datas…</p> : null}
      {isError ? (
        <p role="alert" className="state-error">
          Não foi possível carregar as datas com agenda.
        </p>
      ) : null}
      {!isPending && !isError && calendar?.items.length === 0 ? (
        <p className="muted">Ainda não há consultas importadas.</p>
      ) : null}
      {calendar?.items.length ? (
        <div className="appointment-date-list">
          {calendar.items.map((item) => (
            <button
              key={item.date}
              type="button"
              className={item.date === currentDate ? "appointment-date is-active" : "appointment-date"}
              aria-current={item.date === currentDate ? "date" : undefined}
              aria-label={`${formatCalendarDate(item.date)} — ${appointmentCountLabel(item.count)}`}
              onClick={() => onDateChange(item.date)}
            >
              <span>{formatCalendarDate(item.date)}</span>
              <strong>{appointmentCountLabel(item.count)}</strong>
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function formatCalendarDate(value: string): string {
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

function appointmentCountLabel(count: number): string {
  return `${count} ${count === 1 ? "consulta" : "consultas"}`;
}
