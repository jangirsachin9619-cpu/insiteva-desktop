import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def write_startup_error(exc: BaseException) -> Path:
    path = ROOT / "startup_error.log"
    path.write_text(
        "INSITEVA startup error\n"
        f"Python: {sys.version}\n"
        f"Executable: {sys.executable}\n"
        f"Working directory: {Path.cwd()}\n\n"
        + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        encoding="utf-8",
    )
    return path


try:
    from PySide6.QtWidgets import QApplication, QMessageBox
    from core.auth import InsitevaAuthClient
    from desktop.auth_dialog import AuthDialog
    from desktop.app import INSITEVA
except Exception as exc:
    log = write_startup_error(exc)
    print(f"INSITEVA could not start. See: {log}")
    print(f"{type(exc).__name__}: {exc}")
    raise


if __name__ == "__main__":
    app = QApplication(sys.argv)
    try:
        auth = InsitevaAuthClient()
        login = AuthDialog(auth)
        if login.exec() != login.Accepted:
            sys.exit(0)
        window = INSITEVA(auth_client=auth)
        window.show()
        sys.exit(app.exec())
    except Exception as exc:
        log = write_startup_error(exc)
        try:
            QMessageBox.critical(
                None,
                "INSITEVA startup error",
                f"INSITEVA could not start.\n\n{type(exc).__name__}: {exc}\n\nDetails saved to:\n{log}",
            )
        finally:
            raise
