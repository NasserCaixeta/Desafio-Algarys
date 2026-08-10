from importlib import import_module
from importlib.util import find_spec


def test_package_exposes_version() -> None:
    spec = find_spec("clinic_confirmations")
    assert spec is not None, "clinic_confirmations package must exist"
    package = import_module("clinic_confirmations")
    assert package.__version__ == "1.0.0"
