from __future__ import annotations

import sys

from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QSplashScreen

from technocops_ddc import APP_NAME, APP_VERSION_LABEL, COMPANY_NAME
from technocops_ddc.config import APP_ICON_PATH, SPLASH_IMAGE_PATH
from technocops_ddc.services.license_service import LicenseService
from technocops_ddc.services.security_service import SecurityService
from technocops_ddc.ui.license_dialog import LicenseDialog
from technocops_ddc.ui.main_window import MainWindow
from technocops_ddc.ui.styles import APP_STYLESHEET


def _create_splash() -> QSplashScreen | None:
    if not SPLASH_IMAGE_PATH.exists():
        return None

    pixmap = QPixmap(str(SPLASH_IMAGE_PATH))
    if pixmap.isNull():
        return None

    scaled = pixmap.scaled(
        620,
        360,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    splash = QSplashScreen(
        scaled,
        Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint,
    )
    splash.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    splash.showMessage(
        f"{APP_NAME} {APP_VERSION_LABEL}",
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
        Qt.GlobalColor.white,
    )
    return splash


def run() -> int:
    application = QApplication(sys.argv)
    application.setApplicationName(APP_NAME)
    application.setOrganizationName(COMPANY_NAME)
    application.setStyleSheet(APP_STYLESHEET)
    if APP_ICON_PATH.exists():
        application.setWindowIcon(QIcon(str(APP_ICON_PATH)))

    security_service = SecurityService()
    security_status = security_service.run_startup_checks()
    if not security_status.is_ok:
        QMessageBox.critical(application.activeWindow(), APP_NAME, "\n".join(security_status.errors))
        return 1

    license_service = LicenseService()
    license_state = license_service.refresh_state(license_service.load_state())
    if not license_state.activated:
        license_dialog = LicenseDialog(license_service, license_state)
        if license_dialog.exec() == 0:
            return 0
        license_state = license_service.refresh_state(license_service.load_state())
        if not license_state.activated and not license_service.is_trial_active(license_state):
            return 0

    splash = _create_splash()
    if splash is not None:
        splash.show()
        application.processEvents()

    window = MainWindow()
    window.show()
    if splash is not None:
        splash.finish(window)
    return application.exec()
