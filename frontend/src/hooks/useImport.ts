import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";

export function useImportAppointments() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => api.importAppointments(file),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["appointments"] });
    },
  });
}
