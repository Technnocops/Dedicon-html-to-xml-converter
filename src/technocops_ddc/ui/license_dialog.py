from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from technocops_ddc import APP_NAME
from technocops_ddc.services.license_service import LicenseService, LicenseState


class LicenseDialog(QDialog):
    def __init__(self, license_service: LicenseService, state: LicenseState, parent=None) -> None:
        super().__init__(parent)
        self.license_service = license_service
        self.state = state

        self.setWindowTitle(f"{APP_NAME} License")
        self.resize(720, 560)
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setProperty("role", "section-title")

        self.expiry_label = QLabel()
        self.expiry_label.setWordWrap(True)
        self.expiry_label.setProperty("role", "subtitle")

        self.machine_id_input = QLineEdit(state.machine_id)
        self.machine_id_input.setReadOnly(True)

        self.terms_view = QPlainTextEdit()
        self.terms_view.setReadOnly(True)
        self.terms_view.setPlainText(self.license_service.terms_text)

        self.accept_checkbox = QCheckBox("I accept the terms and conditions")
        self.accept_checkbox.setChecked(state.terms_accepted)
        self.accept_checkbox.stateChanged.connect(lambda _value: self._refresh_controls())

        self.activation_input = QLineEdit()
        self.activation_input.setPlaceholderText("Enter activation key from admin")

        self.activate_button = QPushButton("Activate Now")
        self.activate_button.clicked.connect(self.activate_license)

        self.continue_button = QPushButton("Continue Trial")
        self.continue_button.setProperty("variant", "secondary")
        self.continue_button.clicked.connect(self.continue_trial)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.button_box.rejected.connect(self.reject)

        machine_row = QHBoxLayout()
        machine_row.addWidget(QLabel("Machine ID"))
        machine_row.addWidget(self.machine_id_input, stretch=1)

        activation_row = QHBoxLayout()
        activation_row.addWidget(self.activation_input, stretch=1)
        activation_row.addWidget(self.activate_button)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(self.status_label)
        layout.addWidget(self.expiry_label)
        layout.addLayout(machine_row)
        layout.addWidget(QLabel("Terms & Conditions"))
        layout.addWidget(self.terms_view, stretch=1)
        layout.addWidget(self.accept_checkbox)
        layout.addWidget(QLabel("Activation"))
        layout.addLayout(activation_row)
        layout.addWidget(self.continue_button, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.button_box)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(1000)
        self.refresh_timer.timeout.connect(self._on_timer_tick)
        self.refresh_timer.start()
        self._refresh_controls()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self.raise_()
        self.activateWindow()

    def activate_license(self) -> None:
        if not self.accept_checkbox.isChecked():
            QMessageBox.warning(self, APP_NAME, "Accept the terms and conditions before activation.")
            return

        activation_key = self.activation_input.text().strip()
        activation_ok, message = self.license_service.activate(self.state, activation_key)
        if not activation_ok:
            QMessageBox.critical(self, APP_NAME, message)
            return

        self.accept_checkbox.setChecked(True)
        QMessageBox.information(self, APP_NAME, message)
        self.accept()

    def continue_trial(self) -> None:
        if not self.accept_checkbox.isChecked():
            QMessageBox.warning(self, APP_NAME, "Accept the terms and conditions before continuing the trial.")
            return
        if not self.license_service.is_trial_active(self.state):
            QMessageBox.critical(self, APP_NAME, "The 3-day trial has expired. Activation is now required.")
            return

        self.license_service.accept_terms(self.state)
        self.accept()

    def _refresh_controls(self) -> None:
        self.state = self.license_service.refresh_state(self.state)
        installed_text = self.state.installed_at_dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        expiry_text = self.state.trial_expires_at_dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        self.expiry_label.setText(
            "Trial status: "
            f"{self.license_service.remaining_time_label(self.state)}"
            f" ({self.license_service.remaining_days_label(self.state)})"
            f" | Installed on: {installed_text}"
            f" | Expires on: {expiry_text}"
        )

        if self.state.activated:
            self.status_label.setText("This installation is already activated.")
            self.accept_checkbox.setEnabled(False)
            self.activation_input.setEnabled(False)
            self.activate_button.setEnabled(False)
            self.continue_button.setText("Continue")
            self.continue_button.setEnabled(True)
            return

        if self.license_service.is_trial_active(self.state):
            self.status_label.setText(
                "Activate this machine now, or continue with the protected 3-day trial."
            )
            self.continue_button.setVisible(True)
            self.continue_button.setText("Continue Trial")
            self.continue_button.setEnabled(self.accept_checkbox.isChecked())
        else:
            self.status_label.setText(
                "Trial expired. Activation is required before the application can be used."
            )
            self.continue_button.setVisible(False)

    def _on_timer_tick(self) -> None:
        self._refresh_controls()
