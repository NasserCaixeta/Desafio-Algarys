import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import type { AppointmentFilters, AppointmentPage } from "../api/types";

const configuredPollInterval = Number(import.meta.env.VITE_POLL_INTERVAL_MS || 2_000);

function needsPolling(data: AppointmentPage | undefined): boolean {
  return Boolean(
    data?.items.some(({ message }) => {
      if (!message) return false;
      return (
        message.status === "pending" ||
        message.status === "processing" ||
        (message.status === "failed" && message.attempt_count < message.max_attempts)
      );
    }),
  );
}

export function useAppointments(filters: AppointmentFilters) {
  return useQuery({
    queryKey: ["appointments", filters.date, filters.status, filters.page],
    queryFn: () => api.listAppointments(filters),
    placeholderData: keepPreviousData,
    refetchInterval: (query) =>
      needsPolling(query.state.data) ? configuredPollInterval : false,
  });
}
