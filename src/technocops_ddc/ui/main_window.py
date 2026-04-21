from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from PyQt6.QtCore import QThread, QTimer, Qt
from PyQt6.QtGui import QAction, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QProgressDialog,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from technocops_ddc import APP_NAME, APP_VERSION, APP_VERSION_LABEL, COMPANY_NAME
from technocops_ddc.config import APP_ICON_PATH, APP_LOGO_PATH, COPYRIGHT_LABEL, LOGO_PATH, WINDOW_TITLE
from technocops_ddc.models import ConversionResult, InputBatch, InputDocument, UpdateInfo
from technocops_ddc.services.conversion_service import ConversionService
from technocops_ddc.services.dtbook_converter import DTBookConverter
from technocops_ddc.services.file_service import InputCollectionService
from technocops_ddc.services.language_service import DocumentLanguageDetector
from technocops_ddc.services.license_service import LicenseService
from technocops_ddc.services.metadata_extractor import DocumentMetadataExtractor
from technocops_ddc.services.update_service import UpdateService
from technocops_ddc.ui.widgets import (
    HeaderWidget,
    IdRegenerationWidget,
    InputListWidget,
    MetadataDialog,
    MetadataForm,
    MetadataSummaryCard,
    PageRangeWidget,
)
from technocops_ddc.ui.worker import ConversionWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.file_service = InputCollectionService()
        self.converter = DTBookConverter()
        self.conversion_service = ConversionService(converter=self.converter)
        self.language_detector = DocumentLanguageDetector()
        self.license_service = LicenseService()
        self.license_state = self.license_service.refresh_state(self.license_service.load_state())
        self.metadata_extractor = DocumentMetadataExtractor()
        self.update_service = UpdateService()

        self.documents: list[InputDocument] = []
        self.temp_directories: list[TemporaryDirectory[str]] = []
        self.base_result: ConversionResult | None = None
        self.last_result: ConversionResult | None = None
        self.xml_source_label = ""
        self.worker_thread: QThread | None = None
        self.worker: ConversionWorker | None = None
        self.update_in_progress = False

        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1440, 860)
        self.setMinimumSize(1180, 760)
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))

        self._build_ui()
        self._configure_menu()
        self._refresh_document_list()
        self._refresh_state()
        self._start_license_countdown()

        if self.update_service.is_configured:
            QTimer.singleShot(1200, self.check_for_updates_silent)

    def _build_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(16, 14, 16, 12)
        root_layout.setSpacing(12)

        root_layout.addWidget(self._build_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([540, 900])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root_layout.addWidget(splitter, stretch=1)

        footer = QLabel(f"{COPYRIGHT_LABEL}    |    Version {APP_VERSION_LABEL}")
        footer.setProperty("role", "footer")
        root_layout.addWidget(footer)

        status_bar = QStatusBar()
        status_bar.showMessage("Ready")
        self.setStatusBar(status_bar)

    def _build_header(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        if APP_LOGO_PATH.exists():
            logo = QLabel()
            logo.setPixmap(
                QPixmap(str(APP_LOGO_PATH)).scaled(
                    92,
                    92,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            logo.setFixedSize(92, 92)
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo, alignment=Qt.AlignmentFlag.AlignVCenter)
        elif LOGO_PATH.exists():
            from PyQt6.QtSvgWidgets import QSvgWidget

            logo = QSvgWidget(str(LOGO_PATH))
            logo.setFixedSize(92, 92)
            layout.addWidget(logo, alignment=Qt.AlignmentFlag.AlignVCenter)
        else:
            logo_fallback = QLabel("TC")
            logo_fallback.setFixedSize(84, 84)
            logo_fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo_fallback.setStyleSheet("background:#0b5cab;color:white;border-radius:22px;font-size:28px;font-weight:700;")
            layout.addWidget(logo_fallback, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.header_widget = HeaderWidget()
        self.header_widget.set_status(
            APP_NAME,
            f"{COMPANY_NAME} | Offline HTML to DTBook XML conversion and validation suite",
            "0 files loaded",
            self._license_status_text(),
        )
        layout.addWidget(self.header_widget, stretch=1)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)
        self.check_updates_button = self._create_button("Check Updates", self.check_for_updates, secondary=True)
        self.about_button = self._create_button("About", self.show_about_dialog, secondary=True)
        actions_layout.addWidget(self.check_updates_button)
        actions_layout.addWidget(self.about_button)
        layout.addLayout(actions_layout)
        return container

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(560)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        upload_box = QGroupBox("Input Sources")
        upload_layout = QVBoxLayout(upload_box)
        upload_layout.setSpacing(10)

        upload_buttons = QHBoxLayout()
        upload_buttons.addWidget(self._create_button("Add HTML", self.add_html_files))
        upload_buttons.addWidget(self._create_button("Add ZIP", self.add_zip_archive))
        upload_buttons.addWidget(self._create_button("Add Folder", self.add_folder))
        upload_layout.addLayout(upload_buttons)

        manage_buttons = QHBoxLayout()
        manage_buttons.addWidget(self._create_button("Remove", self.remove_selected_documents, secondary=True))
        manage_buttons.addWidget(self._create_button("Clear", self.clear_documents, secondary=True))
        manage_buttons.addWidget(self._create_button("Move Up", lambda: self.move_selected_document(-1), secondary=True))
        manage_buttons.addWidget(self._create_button("Move Down", lambda: self.move_selected_document(1), secondary=True))
        upload_layout.addLayout(manage_buttons)

        helper_label = QLabel("Drag and drop HTML files, ZIP archives, or folders here. Sequence is preserved and can be reordered.")
        helper_label.setWordWrap(True)
        helper_label.setProperty("role", "subtitle")
        upload_layout.addWidget(helper_label)

        self.input_list = InputListWidget()
        self.input_list.setMinimumHeight(150)
        self.input_list.setMaximumHeight(215)
        self.input_list.externalFilesDropped.connect(self.handle_dropped_paths)
        self.input_list.orderChanged.connect(self.sync_documents_from_list)
        self.input_list.currentItemChanged.connect(lambda *_args: self.preview_selected_input())
        upload_layout.addWidget(self.input_list)

        self.input_summary_label = QLabel("No input files selected.")
        self.input_summary_label.setProperty("role", "subtitle")
        upload_layout.addWidget(self.input_summary_label)

        metadata_box = QGroupBox("DTBook Metadata")
        metadata_layout = QVBoxLayout(metadata_box)
        metadata_layout.setSpacing(10)
        self.metadata_form = MetadataForm()
        self.metadata_form.metadataChanged.connect(self.refresh_metadata_summary)
        self.metadata_dialog = MetadataDialog(self.metadata_form, self)
        self.metadata_summary = MetadataSummaryCard()
        self.edit_metadata_button = self._create_button("Edit Metadata", self.show_metadata_dialog)
        self.edit_metadata_button.setProperty("variant", "secondary")
        self.edit_metadata_button.style().polish(self.edit_metadata_button)

        metadata_actions = QHBoxLayout()
        metadata_actions.addWidget(self.edit_metadata_button)
        metadata_actions.addStretch(1)

        metadata_layout.addLayout(metadata_actions)
        metadata_layout.addWidget(self.metadata_summary)

        layout.addWidget(upload_box, stretch=0)
        layout.addWidget(metadata_box, stretch=1)
        self.refresh_metadata_summary()
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        conversion_box = QGroupBox("Conversion")
        conversion_layout = QVBoxLayout(conversion_box)
        conversion_layout.setSpacing(10)

        self.stop_on_critical_checkbox = QCheckBox("Block export when critical validation errors exist")
        self.stop_on_critical_checkbox.setChecked(True)
        conversion_layout.addWidget(self.stop_on_critical_checkbox)

        self.page_range_widget = PageRangeWidget()
        conversion_layout.addWidget(self.page_range_widget)

        self.id_regeneration_widget = IdRegenerationWidget()
        self.id_regeneration_widget.loadXmlRequested.connect(self.load_xml_for_finalizer)
        self.id_regeneration_widget.applyRequested.connect(self.apply_result_post_processing)
        conversion_layout.addWidget(self.id_regeneration_widget)

        status_row = QHBoxLayout()
        self.progress_label = QLabel("Waiting for input...")
        self.progress_label.setProperty("role", "subtitle")
        status_row.addWidget(self.progress_label, stretch=1)
        action_buttons = QHBoxLayout()
        action_buttons.setSpacing(8)
        self.convert_button = self._create_button("Generate XML", self.start_conversion)
        self.save_button = self._create_button("Save XML", self.save_output)
        self.save_button.setEnabled(False)
        action_buttons.addWidget(self.convert_button)
        action_buttons.addWidget(self.save_button)
        status_row.addLayout(action_buttons)
        conversion_layout.addLayout(status_row)

        from PyQt6.QtWidgets import QProgressBar

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        conversion_layout.addWidget(self.progress_bar)

        self.preview_tabs = QTabWidget()

        self.input_preview = QPlainTextEdit()
        self.input_preview.setReadOnly(True)
        self.input_preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.input_preview.setPlaceholderText("Selected HTML preview will appear here.")

        self.xml_preview = QPlainTextEdit()
        self.xml_preview.setReadOnly(True)
        self.xml_preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.xml_preview.setPlaceholderText("Generated DTBook XML preview will appear here.")

        self.logs_preview = QPlainTextEdit()
        self.logs_preview.setReadOnly(True)
        self.logs_preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.logs_preview.setPlaceholderText("Validation logs and conversion notes will appear here.")

        self.preview_tabs.addTab(self.input_preview, "Input Preview")
        self.preview_tabs.addTab(self.xml_preview, "XML Preview")
        self.preview_tabs.addTab(self.logs_preview, "Logs")

        layout.addWidget(conversion_box, stretch=0)
        layout.addWidget(self.preview_tabs, stretch=1)
        return panel

    def _configure_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        check_updates_action = QAction("Check for Updates", self)
        check_updates_action.triggered.connect(lambda _checked=False: self.check_for_updates())
        file_menu.addAction(check_updates_action)

        about_action = QAction("About", self)
        about_action.triggered.connect(lambda _checked=False: self.show_about_dialog())
        file_menu.addAction(about_action)

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def _create_button(self, label: str, callback, secondary: bool = False) -> QPushButton:
        button = QPushButton(label)
        if secondary:
            button.setProperty("variant", "secondary")
            button.style().polish(button)
        button.clicked.connect(lambda _checked=False, fn=callback: fn())
        return button

    def add_html_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select HTML Files",
            "",
            "HTML Files (*.html *.htm)",
        )
        if paths:
            self._append_batch(self.file_service.collect_from_files([Path(path) for path in paths]))

    def add_zip_archive(self) -> None:
        archive_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select ZIP Archive",
            "",
            "ZIP Archives (*.zip)",
        )
        if archive_path:
            self._append_batch(self.file_service.collect_from_zip(Path(archive_path)))

    def add_folder(self) -> None:
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder_path:
            self._append_batch(self.file_service.collect_from_folder(Path(folder_path)))

    def handle_dropped_paths(self, dropped_paths: list[str]) -> None:
        for raw_path in dropped_paths:
            path = Path(raw_path)
            if path.is_dir():
                self._append_batch(self.file_service.collect_from_folder(path))
            elif self.file_service.is_zip(path):
                self._append_batch(self.file_service.collect_from_zip(path))
            elif self.file_service.is_supported_html(path):
                self._append_batch(self.file_service.collect_from_files([path], source_label="Dropped file"))

    def _append_batch(self, batch: InputBatch) -> None:
        if batch.temporary_directory is not None:
            self.temp_directories.append(batch.temporary_directory)

        if not batch.documents:
            QMessageBox.warning(self, APP_NAME, f"No HTML files were found in {batch.source_label}.")
            return

        should_reset_metadata = not self.documents
        if self.documents and self._document_series_key(self.documents[0].path.stem) != self._document_series_key(batch.documents[0].path.stem):
            should_reset_metadata = True
        if should_reset_metadata:
            self.metadata_form.reset_metadata()

        self.documents.extend(batch.documents)
        self._resequence_documents()
        self._refresh_document_list()
        self.metadata_form.apply_document_defaults(self.documents[0].path.stem)
        detected_language = self.language_detector.detect_from_documents(self.documents)
        self.metadata_form.apply_detected_language(detected_language)
        suggestions = self.metadata_extractor.extract_from_documents(self.documents)
        self.metadata_form.apply_suggested_metadata(
            title=suggestions.title,
            source_isbn=suggestions.source_isbn,
            publisher=suggestions.publisher,
            source_publisher=suggestions.source_publisher,
        )
        self.statusBar().showMessage(f"Loaded {len(batch.documents)} files from {batch.source_label}.")

    def _refresh_document_list(self) -> None:
        self.input_list.clear()
        for document in self.documents:
            item = QListWidgetItem(f"{document.order:02d}. {document.name}")
            item.setData(Qt.ItemDataRole.UserRole, document.document_id)
            item.setToolTip(str(document.path))
            self.input_list.addItem(item)

        if self.input_list.count() > 0 and self.input_list.currentRow() < 0:
            self.input_list.setCurrentRow(0)

        self.input_summary_label.setText(f"{len(self.documents)} HTML files queued for conversion.")
        self._refresh_state()

    def _refresh_state(self) -> None:
        document_count = len(self.documents)
        badge_text = f"{document_count} files loaded" if document_count else "0 files loaded"
        subtitle = f"{COMPANY_NAME} | Offline HTML to DTBook XML conversion and validation suite"

        if self.last_result is not None:
            issues = len(self.last_result.issues)
            badge_text = f"{document_count} files | {issues} issues detected"

        self.header_widget.set_status(APP_NAME, subtitle, badge_text, self._license_status_text())
        can_use_tool = self.license_service.can_launch(self.license_state)
        self.convert_button.setEnabled(document_count > 0 and self.worker_thread is None and can_use_tool)
        self.save_button.setEnabled(
            self.last_result is not None
            and self.worker_thread is None
            and can_use_tool
            and not (self.last_result.has_critical_errors and self.stop_on_critical_checkbox.isChecked())
        )
        xml_source_available = self.base_result is not None and self.worker_thread is None and can_use_tool
        source_label = self.xml_source_label if xml_source_available else ""
        self.id_regeneration_widget.set_source_available(xml_source_available, source_label)
        self.refresh_metadata_summary()

    def _start_license_countdown(self) -> None:
        self.license_timer = QTimer(self)
        self.license_timer.setInterval(1000)
        self.license_timer.timeout.connect(self._on_license_timer_tick)
        self.license_timer.start()

    def _on_license_timer_tick(self) -> None:
        self.license_state = self.license_service.refresh_state(self.license_state)
        self._refresh_state()

    def _license_status_text(self) -> str:
        installed_text = self.license_state.installed_at_dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        expires_text = self.license_state.trial_expires_at_dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        if self.license_state.activated:
            return f"License: Activated | Installed: {installed_text}"

        return (
            f"Trial: {self.license_service.remaining_time_label(self.license_state)}"
            f" ({self.license_service.remaining_days_label(self.license_state)})"
            f" | Installed: {installed_text}"
            f" | Expires: {expires_text}"
        )

    def _resequence_documents(self) -> None:
        for index, document in enumerate(self.documents, start=1):
            document.order = index

    def sync_documents_from_list(self) -> None:
        identifier_to_document = {document.document_id: document for document in self.documents}
        reordered_documents: list[InputDocument] = []
        for row in range(self.input_list.count()):
            identifier = self.input_list.item(row).data(Qt.ItemDataRole.UserRole)
            document = identifier_to_document.get(identifier)
            if document is not None:
                reordered_documents.append(document)

        if len(reordered_documents) == len(self.documents):
            self.documents = reordered_documents
            self._resequence_documents()
            self._refresh_document_list()

    def move_selected_document(self, direction: int) -> None:
        selected_rows = sorted({index.row() for index in self.input_list.selectedIndexes()})
        if not selected_rows:
            return

        if direction < 0:
            for row in selected_rows:
                if row == 0:
                    continue
                self.documents[row - 1], self.documents[row] = self.documents[row], self.documents[row - 1]
        else:
            for row in reversed(selected_rows):
                if row >= len(self.documents) - 1:
                    continue
                self.documents[row + 1], self.documents[row] = self.documents[row], self.documents[row + 1]

        self._resequence_documents()
        self._refresh_document_list()
        if selected_rows:
            target_row = max(0, min(len(self.documents) - 1, selected_rows[0] + direction))
            self.input_list.setCurrentRow(target_row)

    def remove_selected_documents(self) -> None:
        selected_ids = {
            self.input_list.item(index.row()).data(Qt.ItemDataRole.UserRole)
            for index in self.input_list.selectedIndexes()
        }
        if not selected_ids:
            return

        self.documents = [document for document in self.documents if document.document_id not in selected_ids]
        self.base_result = None
        self.last_result = None
        self.xml_source_label = ""
        self.xml_preview.clear()
        self.logs_preview.clear()
        if not self.documents:
            self.metadata_form.reset_metadata()
        self._resequence_documents()
        self._refresh_document_list()

    def clear_documents(self) -> None:
        self.documents.clear()
        self.base_result = None
        self.last_result = None
        self.xml_source_label = ""
        self.input_preview.clear()
        self.xml_preview.clear()
        self.logs_preview.clear()
        self.progress_bar.setValue(0)
        self.progress_label.setText("Waiting for input...")
        self._cleanup_temp_directories()
        self.metadata_form.reset_metadata()
        self._refresh_document_list()

    def preview_selected_input(self) -> None:
        current_item = self.input_list.currentItem()
        if current_item is None:
            self.input_preview.clear()
            return

        identifier = current_item.data(Qt.ItemDataRole.UserRole)
        document = next((doc for doc in self.documents if doc.document_id == identifier), None)
        if document is None:
            self.input_preview.clear()
            return

        try:
            preview_text = self.converter._read_html(document.path)
        except OSError as exc:
            self.input_preview.setPlainText(f"Unable to read file:\n{exc}")
            return

        self.input_preview.setPlainText(preview_text)

    def show_metadata_dialog(self) -> None:
        self.metadata_dialog.exec()
        self.refresh_metadata_summary()

    def refresh_metadata_summary(self) -> None:
        if not hasattr(self, "metadata_summary"):
            return
        self.metadata_summary.set_metadata(self.metadata_form.metadata())

    def start_conversion(self) -> None:
        if not self.documents:
            QMessageBox.warning(self, APP_NAME, "Add at least one HTML file before starting the conversion.")
            return

        metadata = self.metadata_form.metadata()
        missing_fields = self.conversion_service.validate_metadata(metadata)
        if missing_fields:
            QMessageBox.warning(
                self,
                APP_NAME,
                "The following metadata fields are required before conversion:\n\n" + "\n".join(missing_fields),
            )
            return

        page_range_errors = self.page_range_widget.validation_errors()
        if page_range_errors:
            QMessageBox.warning(self, APP_NAME, "\n".join(page_range_errors))
            return

        self.last_result = None
        self.base_result = None
        self.save_button.setEnabled(False)
        self.xml_preview.clear()
        self.logs_preview.setPlainText("Conversion started...\n")
        self.preview_tabs.setCurrentWidget(self.logs_preview)

        self.worker_thread = QThread(self)
        self.worker = ConversionWorker(
            self.conversion_service,
            list(self.documents),
            metadata,
            page_range=self.page_range_widget.selection(),
        )
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.progressChanged.connect(self.on_conversion_progress)
        self.worker.finished.connect(self.on_conversion_finished)
        self.worker.failed.connect(self.on_conversion_failed)
        self.worker.finished.connect(self._teardown_worker)
        self.worker.failed.connect(self._teardown_worker)
        self.worker_thread.start()

        self.progress_bar.setValue(0)
        self.progress_label.setText(f"Starting conversion ({self.page_range_widget.summary_label()})...")
        self.statusBar().showMessage("Conversion in progress...")
        self._refresh_state()

    def on_conversion_progress(self, value: int, message: str) -> None:
        self.progress_bar.setValue(value)
        self.progress_label.setText(message)
        self.statusBar().showMessage(message)

    def on_conversion_finished(self, result: object) -> None:
        if not isinstance(result, ConversionResult):
            self.on_conversion_failed("Unexpected conversion result type.")
            return

        self.base_result = result
        self.last_result = result
        self.xml_source_label = "Current source: generated XML from the latest conversion."
        self.progress_bar.setValue(100)
        self.progress_label.setText("Conversion completed.")
        self.xml_preview.setPlainText(result.xml_text)
        self.logs_preview.setPlainText(self._build_issue_log_text(result))
        self.preview_tabs.setCurrentWidget(self.xml_preview)
        self.statusBar().showMessage("Conversion completed.")
        self._refresh_state()

        if result.has_critical_errors and self.stop_on_critical_checkbox.isChecked():
            QMessageBox.warning(
                self,
                APP_NAME,
                "Critical validation issues were found. Export is blocked until the issues are resolved or the block option is disabled.",
            )

    def on_conversion_failed(self, message: str) -> None:
        self.base_result = None
        self.last_result = None
        self.xml_source_label = ""
        self.progress_bar.setValue(0)
        self.progress_label.setText("Conversion failed.")
        self.logs_preview.setPlainText(f"Conversion failed:\n{message}")
        self.preview_tabs.setCurrentWidget(self.logs_preview)
        self.statusBar().showMessage("Conversion failed.")
        QMessageBox.critical(self, APP_NAME, f"Conversion failed:\n\n{message}")
        self._refresh_state()

    def _teardown_worker(self, *_args) -> None:
        if self.worker_thread is not None:
            self.worker_thread.quit()
            self.worker_thread.wait(3000)
        if self.worker is not None:
            self.worker.deleteLater()
        if self.worker_thread is not None:
            self.worker_thread.deleteLater()
        self.worker = None
        self.worker_thread = None
        self._refresh_state()

    def save_output(self) -> None:
        if self.last_result is None:
            return

        if self.last_result.has_critical_errors and self.stop_on_critical_checkbox.isChecked():
            QMessageBox.warning(
                self,
                APP_NAME,
                "Export is currently blocked because critical validation issues are present.",
            )
            return

        default_name = self.conversion_service.extract_uid_from_xml(self.last_result.xml_text)
        if not default_name:
            default_name = self.metadata_form.metadata().uid.strip()
        if not default_name:
            default_name = self.metadata_form.title_input.text().strip()
        if not default_name:
            default_name = "technocops_dtbook_output"
        default_name = "".join(character if character.isalnum() or character in {"_", "-"} else "_" for character in default_name)
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save DTBook XML",
            f"{default_name}.xml",
            "XML Files (*.xml)",
        )
        if not target_path:
            return

        saved_output = self.conversion_service.save_output(Path(target_path), self.last_result)
        self.statusBar().showMessage(f"Saved XML to {saved_output.xml_path}")
        image_message = ""
        if saved_output.image_output_dir is not None:
            image_message = f"\nImage Folder: {saved_output.image_output_dir}"
        QMessageBox.information(
            self,
            APP_NAME,
            "Output saved successfully.\n\n"
            f"XML: {saved_output.xml_path}\n"
            f"JSON Report: {saved_output.json_report_path}\n"
            f"Text Report: {saved_output.text_report_path}"
            f"{image_message}",
        )

    def check_for_updates_silent(self) -> None:
        self.check_for_updates(silent=True)

    def check_for_updates(self, silent: bool = False) -> None:
        if self.update_in_progress:
            if not silent:
                QMessageBox.information(self, APP_NAME, "An application update is already in progress.")
            return

        if not self.update_service.is_configured:
            if not silent:
                self.show_updater_hint()
            return

        try:
            self.statusBar().showMessage("Checking for updates...")
            update_info = self.update_service.check_for_update(APP_VERSION)
        except Exception as exc:  # noqa: BLE001
            self.statusBar().showMessage("Update check failed.")
            if not silent:
                QMessageBox.warning(self, APP_NAME, f"Unable to check for updates:\n\n{exc}")
            return

        if update_info is None:
            self.statusBar().showMessage("Application is already up to date.")
            if not silent:
                QMessageBox.information(self, APP_NAME, "You are already using the latest available version.")
            return

        self.statusBar().showMessage(f"Version {update_info.version} is available.")
        self._show_update_prompt(update_info)

    def _show_update_prompt(self, update_info: UpdateInfo) -> None:
        message_box = QMessageBox(self)
        message_box.setWindowTitle("Update Available")
        message_box.setIcon(QMessageBox.Icon.Information)
        message_box.setText(f"Version {update_info.version} is ready to install.")
        message_box.setInformativeText(
            "The update will be downloaded and installed automatically. Your local data and license stay in secure app storage.\n\n"
            "Release summary:\n\n"
            + (update_info.summary or "No release notes were provided.")
        )
        update_button = message_box.addButton("Update Now", QMessageBox.ButtonRole.AcceptRole)
        message_box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        message_box.exec()

        clicked_button = message_box.clickedButton()
        if clicked_button is update_button:
            self._install_update(update_info)

    def _install_update(self, update_info: UpdateInfo) -> None:
        if self.worker_thread is not None:
            QMessageBox.information(
                self,
                APP_NAME,
                "Please let the current conversion finish before starting the application update.",
            )
            return

        self.update_in_progress = True
        self.check_updates_button.setEnabled(False)
        self.statusBar().showMessage("Update is in progress...")

        progress_dialog = QProgressDialog("Update is in progress...\n\nDownloading installer...", "", 0, 0, self)
        progress_dialog.setWindowTitle("Update in Progress")
        progress_dialog.setCancelButton(None)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setAutoClose(False)
        progress_dialog.setAutoReset(False)
        progress_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress_dialog.show()
        QApplication.processEvents()

        def on_progress(downloaded_bytes: int, total_bytes: int | None) -> None:
            if total_bytes:
                progress_dialog.setRange(0, total_bytes)
                progress_dialog.setValue(min(downloaded_bytes, total_bytes))
                downloaded_mb = downloaded_bytes / (1024 * 1024)
                total_mb = total_bytes / (1024 * 1024)
                progress_dialog.setLabelText(
                    "Update is in progress...\n\n"
                    f"Downloading installer... {downloaded_mb:.1f} MB / {total_mb:.1f} MB"
                )
            else:
                progress_dialog.setRange(0, 0)
                progress_dialog.setLabelText("Update is in progress...\n\nDownloading installer...")
            QApplication.processEvents()

        try:
            update_path = self.update_service.download_update(update_info, progress_callback=on_progress)
            progress_dialog.setRange(0, 0)
            progress_dialog.setLabelText("Update is in progress...\n\nPreparing automatic installer...")
            QApplication.processEvents()
            self.update_service.start_background_update(
                update_path,
                restart_path=self.update_service.default_restart_path(),
            )
        except Exception as exc:  # noqa: BLE001
            self.update_in_progress = False
            self.check_updates_button.setEnabled(True)
            progress_dialog.close()
            self.statusBar().showMessage("Update failed.")
            QMessageBox.warning(self, APP_NAME, f"Unable to install the update automatically:\n\n{exc}")
            return

        progress_dialog.close()
        QMessageBox.information(
            self,
            APP_NAME,
            "Update is in progress.\n\nThe application will close now and restart automatically after installation completes.",
        )
        QTimer.singleShot(150, self.close)

    def show_updater_hint(self) -> None:
        QMessageBox.information(
            self,
            "Automatic Updates",
            "Automatic updates are not configured for this build yet.",
        )

    def show_about_dialog(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"{APP_NAME} {APP_VERSION_LABEL}\n\n"
            f"Company: {COMPANY_NAME}\n"
            "Purpose: Convert ABBYY FineReader HTML into structured DTBook XML and validate the generated output.\n"
            "Mode: Offline desktop production workflow with validation, logging, licensing, and installer-ready packaging.",
        )

    @staticmethod
    def _build_issue_log_text(result: ConversionResult) -> str:
        if not result.issues:
            return "Conversion completed with no validation issues."
        return "\n".join(issue.display_text for issue in result.issues)

    def load_xml_for_finalizer(self) -> None:
        xml_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open XML for ID Finalizer",
            "",
            "XML Files (*.xml)",
        )
        if not xml_path:
            return

        try:
            xml_text = Path(xml_path).read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"Unable to read the XML file:\n\n{exc}")
            return

        self.base_result = ConversionResult(xml_text=xml_text, issues=[], image_assets=[])
        self.last_result = self.base_result
        self.xml_source_label = f"Current source: loaded XML ({Path(xml_path).name})."
        self.xml_preview.setPlainText(xml_text)
        self.logs_preview.setPlainText(
            "XML file loaded for ID-only finalization.\n"
            "No content changes will be made unless you explicitly apply the ID finalizer."
        )
        self.preview_tabs.setCurrentWidget(self.xml_preview)
        self.statusBar().showMessage(f"Loaded XML for ID finalizer: {xml_path}")
        self._refresh_state()

    def apply_result_post_processing(self) -> None:
        if self.base_result is None:
            QMessageBox.information(
                self,
                APP_NAME,
                "Generate XML first or load an existing XML file before applying the ID finalizer.",
            )
            return

        if not (
            self.id_regeneration_widget.regenerate_page_ids
            or self.id_regeneration_widget.regenerate_level_ids
        ):
            QMessageBox.information(
                self,
                APP_NAME,
                "Select `Regenerate Page IDs`, `Regenerate Level IDs`, or both before applying the XML finalizer.",
            )
            return

        try:
            xml_text = self.conversion_service.finalize_xml_ids(
                self.base_result.xml_text,
                regenerate_page_ids=self.id_regeneration_widget.regenerate_page_ids,
                regenerate_level_ids=self.id_regeneration_widget.regenerate_level_ids,
            )
        except Exception as exc:  # noqa: BLE001
            self.last_result = self.base_result
            self.logs_preview.setPlainText(
                self._build_issue_log_text(self.base_result)
                + f"\n\n[WARNING] ID finalizer could not be applied: {exc}"
            )
            self.xml_preview.setPlainText(self.base_result.xml_text)
            self.statusBar().showMessage("Conversion completed with ID finalizer warning.")
            self._refresh_state()
            return

        self.last_result = ConversionResult(
            xml_text=xml_text,
            issues=list(self.base_result.issues),
            image_assets=list(self.base_result.image_assets),
        )
        self.xml_preview.setPlainText(self.last_result.xml_text)
        self.logs_preview.setPlainText(self._build_issue_log_text(self.last_result))
        self.preview_tabs.setCurrentWidget(self.xml_preview)
        self.statusBar().showMessage("ID finalizer applied to the XML source without changing content.")
        self._refresh_state()

    def _cleanup_temp_directories(self) -> None:
        while self.temp_directories:
            temp_directory = self.temp_directories.pop()
            temp_directory.cleanup()

    @staticmethod
    def _document_series_key(document_name: str) -> str:
        cleaned = document_name.strip()
        if not cleaned:
            return ""
        return cleaned.split("_", 1)[0].lower()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._cleanup_temp_directories()
        if self.worker_thread is not None:
            self.worker_thread.quit()
            self.worker_thread.wait(2000)
        super().closeEvent(event)
