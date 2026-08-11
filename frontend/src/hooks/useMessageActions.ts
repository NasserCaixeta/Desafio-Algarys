import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";

export function useMessageActions() {
  const queryClient = useQueryClient();

  async function refreshDashboard() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["appointments"] }),
      queryClient.invalidateQueries({ queryKey: ["messages"] }),
    ]);
  }

  const dispatch = useMutation({
    mutationFn: ({ date, appointmentIds }: { date: string; appointmentIds?: string[] }) =>
      api.dispatch(date, appointmentIds),
    onSuccess: refreshDashboard,
  });
  const respond = useMutation({
    mutationFn: ({ appointmentId, status }: {
      appointmentId: string;
      status: "confirmed" | "declined";
    }) => api.respond(appointmentId, status),
    onSuccess: refreshDashboard,
  });
  const retry = useMutation({
    mutationFn: (messageId: string) => api.retry(messageId),
    onSuccess: refreshDashboard,
  });

  return { dispatch, respond, retry };
}
