from collections.abc import Sequence


class CsvImportError(ValueError):
    """Base error for failures that invalidate the CSV file as a whole."""


class InvalidCsvEncodingError(CsvImportError):
    """Raised when an uploaded file is not valid UTF-8."""

    def __init__(self) -> None:
        super().__init__("O arquivo CSV deve estar codificado em UTF-8.")


class InvalidCsvHeaderError(CsvImportError):
    """Raised when the CSV does not use the documented exact header."""

    expected = ("data_hora", "paciente", "telefone", "procedimento")

    def __init__(self, received: Sequence[str] | None) -> None:
        self.received = tuple(received or ())
        super().__init__("Cabeçalho CSV inválido. Esperado: " + ",".join(self.expected) + ".")


class InvalidCsvFormatError(CsvImportError):
    """Raised when the byte stream is UTF-8 but not structurally valid CSV."""

    def __init__(self) -> None:
        super().__init__("O arquivo possui uma estrutura CSV inválida.")


class UploadTooLargeError(CsvImportError):
    """Raised before parsing when an upload exceeds the configured byte limit."""

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        super().__init__(f"O arquivo excede o limite de {max_bytes} bytes.")
