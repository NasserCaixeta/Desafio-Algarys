import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";

export function useAppointmentDates() {
  return useQuery({
    queryKey: ["appointment-dates"],
    queryFn: () => api.listAppointmentDates(),
  });
}
