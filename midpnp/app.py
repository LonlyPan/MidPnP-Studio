"""应用入口：初始化数据、主题、主窗口与全局异常处理。"""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QLocale, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_NAME, __version__
from .config import load_settings
from .core.machine.service import MachineService
from .core.storage import Storage
from .paths import AppPaths
from .ui.context import AppContext
from .ui.main_window import MainWindow
from .ui.theme import STYLESHEET


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MidPnP Studio 贴片机上位机")
    parser.add_argument("--data-dir", type=str, default="", help="覆盖应用数据目录")
    parser.add_argument("--smoke-test", action="store_true", help="启动后自动退出，用于打包自检")
    parser.add_argument("--page", type=str, default="home", help="启动页")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv[:1] + (argv or []))
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("MidPnP")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    app.setFont(QFont("Noto Sans SC", 9))
    QLocale.setDefault(QLocale(QLocale.Language.Chinese, QLocale.Country.China))
    app.setStyleSheet(STYLESHEET)

    paths = AppPaths.create(Path(args.data_dir) if args.data_dir else None)
    storage = Storage(paths.database)
    try:
        storage.seed_demo()
    except Exception:
        pass
    settings = load_settings(paths.settings)
    first_run = not settings.machine_selected and not settings.machine_profile_id
    machine = MachineService()
    context = AppContext(paths, storage, settings, machine)

    # 首次启动：先看图选设备（拓竹式设备选择），选完再创建主界面
    if first_run and not args.smoke_test:
        try:
            from .ui.machine_gallery import select_machine

            chosen = select_machine(context, first_run=True, parent=None)
            if chosen is not None:
                context.apply_profile(chosen)
            context.settings.machine_selected = True
            context.save_settings()
        except Exception:
            pass

    window = MainWindow(context)

    def handle_exception(exc_type: type[BaseException], exc_value: BaseException, exc_tb: object) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)  # type: ignore[arg-type]
            return
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))  # type: ignore[arg-type]
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        crash_file = paths.logs / f"crash_{stamp}.log"
        try:
            crash_file.write_text(details, encoding="utf-8")
        except OSError:
            pass
        QMessageBox.critical(
            window,
            "未处理的异常",
            f"应用遇到异常，详情已写入：\n{crash_file}\n\n{exc_value}",
        )

    sys.excepthook = handle_exception
    window.showMaximized()
    if args.page:
        QTimer.singleShot(100, lambda: window.navigate(args.page))
    if args.smoke_test:
        QTimer.singleShot(2600, app.quit)
    try:
        return app.exec()
    finally:
        try:
            machine.shutdown()
        except Exception:
            pass
        try:
            storage.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
