import { useState } from "react";

import type { ImportReport } from "../api/types";
import { useImportAppointments } from "../hooks/useImport";

function summaryLabel(count: number, singular: string, plural: string) {
  return `${count} ${count === 1 ? singular : plural}`;
}

function firstFile(files: FileList): File | null {
  return (typeof files.item === "function" ? files.item(0) : null) ?? files[0] ?? null;
}

export function ImportPanel() {
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const importMutation = useImportAppointments();

  function selectFile(nextFile: File | null) {
    if (!nextFile) return;
    setFile(nextFile);
    setReport(null);
    importMutation.reset();
  }

  function submit() {
    if (!file || importMutation.isPending) return;
    setReport(null);
    importMutation.reset();
    importMutation.mutate(file, { onSuccess: setReport });
  }

  return (
    <section className="panel import-panel" aria-labelledby="import-title">
      <div className="panel-heading">
        <div>
          <h2 id="import-title">Importar agenda</h2>
          <p>Envie um CSV UTF-8 com data, paciente, telefone e procedimento.</p>
        </div>
      </div>

      <div
        className="drop-zone"
        aria-label="Área para soltar o CSV"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          selectFile(firstFile(event.dataTransfer.files));
        }}
      >
        <label htmlFor="appointment-csv">Arquivo CSV</label>
        <input
          id="appointment-csv"
          type="file"
          accept=".csv,text/csv"
          onChange={(event) => selectFile(event.target.files ? firstFile(event.target.files) : null)}
        />
        <span>{file ? file.name : "Selecione ou arraste o arquivo para esta área"}</span>
      </div>

      <button
        className="primary-button"
        type="button"
        disabled={!file || importMutation.isPending}
        onClick={submit}
      >
        {importMutation.isPending ? "Importando…" : "Importar agenda"}
      </button>

      {importMutation.isError ? (
        <div role="alert" className="state-message state-error compact-state">
          {importMutation.error.message}
        </div>
      ) : null}

      {report ? (
        <div className="import-report" aria-live="polite">
          <div className="summary-grid">
            <strong>
              {summaryLabel(report.summary.total_rows, "linha processada", "linhas processadas")}
            </strong>
            <strong>{summaryLabel(report.summary.imported, "importada", "importadas")}</strong>
            <strong>{summaryLabel(report.summary.rejected, "rejeitada", "rejeitadas")}</strong>
            <strong>
              {summaryLabel(report.summary.duplicates, "duplicada", "duplicadas")}
            </strong>
          </div>
          {report.errors.length ? (
            <div className="import-errors">
              <h3>Linhas rejeitadas</h3>
              <ul>
                {report.errors.map((error) => (
                  <li key={error.line_number}>
                    <strong>Linha {error.line_number}</strong>
                    <span>{error.reason}</span>
                    <code>{JSON.stringify(error.raw_data)}</code>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
