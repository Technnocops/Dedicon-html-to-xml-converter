from __future__ import annotations

from PyQt6.QtCore import QDate, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from technocops_ddc.models import (
    AuthorEntry,
    DEFAULT_PRODUCER,
    DOCUMENT_TYPE_OPTIONS,
    DTBookMetadata,
    FIXED_PUBLISHER,
    PageRangeSelection,
)


class InputListWidget(QListWidget):
    externalFilesDropped = pyqtSignal(list)
    orderChanged = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(False)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls() and event.source() is not self:
            paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            self.externalFilesDropped.emit(paths)
            event.acceptProposedAction()
            return

        super().dropEvent(event)
        self.orderChanged.emit()


class MetadataForm(QWidget):
    metadataChanged = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.document_hint = ""
        self.auto_language_code = ""
        self.uid_input = QLineEdit()
        self.title_input = QLineEdit()
        self.publisher_input = QLineEdit(FIXED_PUBLISHER)
        self.language_input = QLineEdit()
        self.identifier_input = QLineEdit()
        self.source_input = QLineEdit()
        self.source_publisher_input = QLineEdit()
        self.producer_input = QLineEdit(DEFAULT_PRODUCER)
        self.doc_type_input = QComboBox()
        self.doc_type_input.addItem("Select document type", "")
        for label, value in DOCUMENT_TYPE_OPTIONS:
            self.doc_type_input.addItem(label, value)
        self.author_rows: list[AuthorRowWidget] = []

        self.uid_input.setPlaceholderText("Please enter UID or click Generate IDs")
        self.identifier_input.setPlaceholderText("Please enter Identifier")
        self.title_input.setPlaceholderText("Please enter Title")
        self.publisher_input.setPlaceholderText("Dedicon")
        self.source_input.setPlaceholderText("Please enter ISBN")
        self.source_publisher_input.setPlaceholderText("Please enter Source Publisher")
        self.producer_input.setPlaceholderText(DEFAULT_PRODUCER)
        self.language_input.setPlaceholderText("Please enter language code (example: nl)")
        self._configure_input_sizes()
        self._connect_field_signals()
        self.publisher_input.setReadOnly(True)

        today = QDate.currentDate()
        self.completion_date_input = QDateEdit(today)
        self.produced_date_input = QDateEdit(today)
        for widget in (self.completion_date_input, self.produced_date_input):
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("yyyy-MM-dd")
            widget.setMinimumHeight(38)
            widget.setToolTip("Select the date from the calendar popup.")
            widget.dateChanged.connect(lambda *_args: self.metadataChanged.emit())
        self.doc_type_input.setMinimumHeight(38)
        self.doc_type_input.setCurrentIndex(0)
        self.doc_type_input.currentTextChanged.connect(lambda *_args: self.metadataChanged.emit())

        self.generate_ids_button = QPushButton("Generate IDs")
        self.generate_ids_button.setProperty("variant", "secondary")
        self.generate_ids_button.setProperty("state", "idle")
        self.generate_ids_button.clicked.connect(lambda _checked=False: self.generate_ids())

        identity_form = QFormLayout()
        identity_form.setSpacing(8)
        identity_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        identity_form.addRow("UID", self.uid_input)
        identity_form.addRow("Identifier", self.identifier_input)
        identity_form.addRow("Title", self.title_input)
        identity_form.addRow("Language", self.language_input)
        identity_form.addRow("Document Type", self.doc_type_input)

        publication_form = QFormLayout()
        publication_form.setSpacing(8)
        publication_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        publication_form.addRow("Completion Date", self.completion_date_input)
        publication_form.addRow("Produced Date", self.produced_date_input)
        publication_form.addRow("Publisher", self.publisher_input)
        publication_form.addRow("Source Publisher", self.source_publisher_input)
        publication_form.addRow("Source ISBN", self.source_input)
        publication_form.addRow("Producer", self.producer_input)

        forms_row = QHBoxLayout()
        forms_row.setSpacing(14)
        forms_row.addLayout(identity_form, stretch=1)
        forms_row.addLayout(publication_form, stretch=1)

        authors_label = QLabel("Authors")
        authors_label.setProperty("role", "section-title")
        authors_hint = QLabel("Add one author per row so it stays easy to review.")
        authors_hint.setProperty("role", "subtitle")
        authors_header = QHBoxLayout()
        authors_text_layout = QVBoxLayout()
        authors_text_layout.setContentsMargins(0, 0, 0, 0)
        authors_text_layout.setSpacing(2)
        authors_text_layout.addWidget(authors_label)
        authors_text_layout.addWidget(authors_hint)
        self.author_rows_container = QWidget()
        self.author_rows_layout = QVBoxLayout(self.author_rows_container)
        self.author_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.author_rows_layout.setSpacing(5)
        self.add_author_button = QPushButton("+ Add Author")
        self.add_author_button.setProperty("variant", "secondary")
        self.add_author_button.clicked.connect(lambda _checked=False: self.add_author_row())
        self.add_author_row()
        authors_header.addLayout(authors_text_layout, stretch=1)
        authors_header.addWidget(self.add_author_button, alignment=Qt.AlignmentFlag.AlignTop)

        tools_layout = QHBoxLayout()
        tools_layout.addWidget(self.generate_ids_button)
        tools_layout.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(forms_row)
        layout.addLayout(authors_header)
        layout.addWidget(self.author_rows_container)
        layout.addLayout(tools_layout)

    def generate_ids(self) -> None:
        generated_uid = (
            self.uid_input.text().strip()
            or self.identifier_input.text().strip()
            or self._derive_book_id(self.document_hint)
        )
        if not generated_uid:
            self.generate_ids_button.setText("Load a file first")
            self.generate_ids_button.setProperty("state", "warning")
            self._refresh_button_style(self.generate_ids_button)
            QTimer.singleShot(1200, self._reset_generate_button)
            return
        self.uid_input.setText(generated_uid)
        self.identifier_input.setText(generated_uid)
        self.generate_ids_button.setText("IDs Generated")
        self.generate_ids_button.setProperty("state", "success")
        self._refresh_button_style(self.generate_ids_button)
        self.metadataChanged.emit()

    def apply_document_defaults(self, first_document_name: str) -> None:
        self.document_hint = first_document_name
        self._reset_generate_button()

    def apply_detected_language(self, language_code: str) -> None:
        normalized = language_code.strip().lower()
        if not normalized:
            return
        current_value = self.language_input.text().strip().lower()
        if current_value in {"", "en", self.auto_language_code}:
            self.language_input.setText(normalized)
            self.auto_language_code = normalized

    def apply_suggested_metadata(
        self,
        *,
        title: str = "",
        source_isbn: str = "",
        publisher: str = "",
        source_publisher: str = "",
    ) -> None:
        if not self.publisher_input.text().strip():
            self.publisher_input.setText(FIXED_PUBLISHER)
        self.publisher_input.setPlaceholderText("Dedicon")

    def reset_metadata(self) -> None:
        self.document_hint = ""
        self.auto_language_code = ""
        self.uid_input.clear()
        self.identifier_input.clear()
        self.title_input.clear()
        self.language_input.clear()
        self.source_input.clear()
        self.source_publisher_input.clear()
        self.producer_input.setText(DEFAULT_PRODUCER)
        self.publisher_input.setText(FIXED_PUBLISHER)
        self.doc_type_input.setCurrentIndex(0)
        today = QDate.currentDate()
        self.completion_date_input.setDate(today)
        self.produced_date_input.setDate(today)
        self._reset_generate_button()

        while len(self.author_rows) > 1:
            row = self.author_rows.pop()
            row.setParent(None)
            row.deleteLater()
        if not self.author_rows:
            self.add_author_row()
        self.author_rows[0].clear()
        self._refresh_author_rows()
        self.metadataChanged.emit()

    def add_author_row(self, surname: str = "", first_name: str = "") -> None:
        author_row = AuthorRowWidget(surname=surname, first_name=first_name)
        author_row.removeRequested.connect(self.remove_author_row)
        author_row.surname_input.textChanged.connect(lambda *_args: self.metadataChanged.emit())
        author_row.firstname_input.textChanged.connect(lambda *_args: self.metadataChanged.emit())
        self.author_rows.append(author_row)
        self.author_rows_layout.addWidget(author_row)
        self._refresh_author_rows()
        self.metadataChanged.emit()

    def remove_author_row(self, row: "AuthorRowWidget") -> None:
        if len(self.author_rows) == 1:
            row.clear()
            self.metadataChanged.emit()
            return
        self.author_rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._refresh_author_rows()
        self.metadataChanged.emit()

    def authors(self) -> list[AuthorEntry]:
        authors = [
            AuthorEntry(
                surname=row.surname_input.text().strip(),
                first_name=row.firstname_input.text().strip(),
            )
            for row in self.author_rows
        ]
        return [author for author in authors if not author.is_empty]

    def metadata(self) -> DTBookMetadata:
        authors = self.authors()
        primary_author = authors[0] if authors else AuthorEntry()
        return DTBookMetadata(
            uid=self.uid_input.text().strip(),
            title=self.title_input.text().strip(),
            creator_surname=primary_author.surname,
            creator_first_name=primary_author.first_name,
            completion_date=self.completion_date_input.date().toString("yyyy-MM-dd"),
            publisher=FIXED_PUBLISHER,
            language=self.language_input.text().strip(),
            identifier=self.identifier_input.text().strip(),
            source_isbn=self.source_input.text().strip(),
            produced_date=self.produced_date_input.date().toString("yyyy-MM-dd"),
            source_publisher=self.source_publisher_input.text().strip(),
            producer=self.producer_input.text().strip(),
            authors=authors,
            doc_type=(self.doc_type_input.currentData() or "").strip(),
        )

    def _reset_generate_button(self) -> None:
        self.generate_ids_button.setText("Generate IDs")
        self.generate_ids_button.setProperty("state", "idle")
        self._refresh_button_style(self.generate_ids_button)

    def _refresh_author_rows(self) -> None:
        for index, row in enumerate(self.author_rows, start=1):
            row.set_index(index)
            row.remove_button.setEnabled(len(self.author_rows) > 1)

    def _configure_input_sizes(self) -> None:
        text_inputs = (
            self.uid_input,
            self.title_input,
            self.publisher_input,
            self.language_input,
            self.identifier_input,
            self.source_input,
            self.source_publisher_input,
            self.producer_input,
        )
        for widget in text_inputs:
            widget.setMinimumHeight(38)

    def _connect_field_signals(self) -> None:
        for widget in (
            self.uid_input,
            self.title_input,
            self.publisher_input,
            self.language_input,
            self.identifier_input,
            self.source_input,
            self.source_publisher_input,
            self.producer_input,
        ):
            widget.textChanged.connect(lambda *_args: self.metadataChanged.emit())

    @staticmethod
    def _derive_book_id(document_name: str) -> str:
        candidate = document_name.strip()
        if not candidate:
            return ""
        base_name = candidate.rsplit(".", 1)[0]
        first_token = base_name.split("_", 1)[0].strip()
        if first_token.isdigit():
            return first_token
        return ""

    @staticmethod
    def _refresh_button_style(button: QPushButton) -> None:
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()


class AuthorRowWidget(QWidget):
    removeRequested = pyqtSignal(QWidget)

    def __init__(self, surname: str = "", first_name: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.index_label = QLabel()
        self.index_label.setProperty("role", "author-index")
        self.surname_input = QLineEdit(surname)
        self.firstname_input = QLineEdit(first_name)
        self.surname_input.setPlaceholderText("Surname")
        self.firstname_input.setPlaceholderText("First name")
        self.remove_button = QPushButton("Remove")
        self.remove_button.setProperty("variant", "secondary")
        self.remove_button.clicked.connect(lambda _checked=False: self.removeRequested.emit(self))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.index_label)
        layout.addWidget(self.surname_input, stretch=1)
        layout.addWidget(self.firstname_input, stretch=1)
        layout.addWidget(self.remove_button)

    def set_index(self, index: int) -> None:
        self.index_label.setText(f"Author {index}")

    def clear(self) -> None:
        self.surname_input.clear()
        self.firstname_input.clear()


class HeaderWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title_label = QLabel()
        self.title_label.setProperty("role", "title")
        self.subtitle_label = QLabel()
        self.subtitle_label.setProperty("role", "subtitle")
        self.badge_label = QLabel()
        self.badge_label.setProperty("role", "badge")
        self.detail_label = QLabel()
        self.detail_label.setProperty("role", "subtitle")
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.detail_label.setWordWrap(True)

        text_layout = QVBoxLayout()
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.subtitle_label)

        info_layout = QVBoxLayout()
        info_layout.addWidget(self.badge_label, alignment=Qt.AlignmentFlag.AlignRight)
        info_layout.addWidget(self.detail_label, alignment=Qt.AlignmentFlag.AlignRight)
        info_layout.addStretch(1)

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(text_layout, 0, 0)
        layout.addLayout(info_layout, 0, 1)
        layout.setColumnStretch(0, 1)

    def set_status(self, title: str, subtitle: str, badge: str, detail: str = "") -> None:
        self.title_label.setText(title)
        self.subtitle_label.setText(subtitle)
        self.badge_label.setText(badge)
        self.detail_label.setText(detail)
        self.detail_label.setVisible(bool(detail))


class PageRangeWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.start_spin = QSpinBox()
        self.start_spin.setRange(1, 999999)
        self.start_spin.setValue(1)
        self.start_spin.setMinimumWidth(110)

        heading_label = QLabel("Generated Page Number Start")
        helper_label = QLabel(
            "Use this as the first generated page number. Every HTML `<page>` marker after that will continue automatically to the end."
        )
        helper_label.setWordWrap(True)
        helper_label.setProperty("role", "subtitle")

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(heading_label)
        row.addWidget(self.start_spin)
        row.addStretch(1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        container = QVBoxLayout()
        container.setContentsMargins(0, 0, 0, 0)
        container.setSpacing(6)
        container.addLayout(row)
        container.addWidget(helper_label)
        layout.addLayout(container, stretch=1)

    def selection(self) -> PageRangeSelection:
        return PageRangeSelection(start_page=self.start_spin.value())

    def validation_errors(self) -> list[str]:
        return self.selection().validate()

    def summary_label(self) -> str:
        return self.selection().label


class IdRegenerationWidget(QWidget):
    optionsChanged = pyqtSignal()
    loadXmlRequested = pyqtSignal()
    applyRequested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.page_ids_checkbox = QCheckBox("Regenerate Page IDs")
        self.level_ids_checkbox = QCheckBox("Regenerate Level IDs")
        self.load_xml_button = QPushButton("Load XML")
        self.load_xml_button.setProperty("variant", "secondary")
        self.apply_button = QPushButton("Apply ID Finalizer")
        self.apply_button.setProperty("variant", "secondary")
        self.status_label = QLabel("Available after `Generate XML` or after loading an existing XML file.")
        self.status_label.setWordWrap(True)
        self.status_label.setProperty("role", "subtitle")
        hint = QLabel("Only `id` and `page` attributes are updated. Content and structure remain unchanged.")
        hint.setWordWrap(True)
        hint.setProperty("role", "subtitle")

        self.page_ids_checkbox.toggled.connect(self._emit_options_changed)
        self.level_ids_checkbox.toggled.connect(self._emit_options_changed)
        self.load_xml_button.clicked.connect(lambda _checked=False: self.loadXmlRequested.emit())
        self.apply_button.clicked.connect(lambda _checked=False: self.applyRequested.emit())

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(12)
        controls.addWidget(self.page_ids_checkbox)
        controls.addWidget(self.level_ids_checkbox)
        controls.addStretch(1)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        actions.addWidget(self.load_xml_button)
        actions.addWidget(self.apply_button)
        actions.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(controls)
        layout.addLayout(actions)
        layout.addWidget(self.status_label)
        layout.addWidget(hint)
        self.set_source_available(False)

    @property
    def regenerate_page_ids(self) -> bool:
        return self.page_ids_checkbox.isChecked()

    @property
    def regenerate_level_ids(self) -> bool:
        return self.level_ids_checkbox.isChecked()

    def set_source_available(self, available: bool, source_label: str = "") -> None:
        self.page_ids_checkbox.setEnabled(available)
        self.level_ids_checkbox.setEnabled(available)
        if not available:
            self.page_ids_checkbox.setChecked(False)
            self.level_ids_checkbox.setChecked(False)
            self.apply_button.setEnabled(False)
            self.status_label.setText("Available after `Generate XML` or after loading an existing XML file.")
            return

        source_text = source_label or "XML source is ready for ID-only finalization."
        self.status_label.setText(source_text)
        self._refresh_apply_button()

    def _emit_options_changed(self) -> None:
        self._refresh_apply_button()
        self.optionsChanged.emit()

    def _refresh_apply_button(self) -> None:
        self.apply_button.setEnabled(
            (self.page_ids_checkbox.isEnabled() or self.level_ids_checkbox.isEnabled())
            and (self.page_ids_checkbox.isChecked() or self.level_ids_checkbox.isChecked())
        )


class MetadataSummaryCard(QWidget):
    FIELD_ORDER = (
        ("title", "Title"),
        ("uid", "UID"),
        ("source_isbn", "ISBN"),
        ("language", "Language"),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.value_labels: dict[str, QLabel] = {}

        hint_label = QLabel("Primary metadata is shown here in English. Use `Edit Metadata` to review or update all remaining fields.")
        hint_label.setProperty("role", "subtitle")
        hint_label.setWordWrap(True)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)

        for index, (field_name, field_label) in enumerate(self.FIELD_ORDER):
            row = index // 2
            column = (index % 2) * 2

            label = QLabel(field_label)
            label.setProperty("role", "summary-label")
            value = QLabel("Not set")
            value.setProperty("role", "summary-value")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

            grid.addWidget(label, row, column)
            grid.addWidget(value, row, column + 1)
            self.value_labels[field_name] = value

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(hint_label)
        layout.addLayout(grid)

    def set_metadata(self, metadata: DTBookMetadata) -> None:
        values = {
            "title": metadata.title,
            "uid": metadata.uid,
            "source_isbn": metadata.source_isbn,
            "language": metadata.language,
        }
        for field_name, value in values.items():
            self.value_labels[field_name].setText(value.strip() or "Not set")


class MetadataDialog(QDialog):
    def __init__(self, metadata_form: MetadataForm, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("DTBook Metadata Editor")
        self.resize(980, 700)
        self.setMinimumSize(860, 620)
        self.metadata_form = metadata_form

        intro = QLabel("Review or update every metadata field here. Use Clean Metadata to reset the editor for a new document.")
        intro.setProperty("role", "subtitle")
        intro.setWordWrap(True)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(metadata_form)

        self.clean_button = QPushButton("Clean Metadata")
        self.clean_button.setProperty("variant", "secondary")
        self.clean_button.clicked.connect(self.metadata_form.reset_metadata)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addWidget(self.clean_button)
        actions.addStretch(1)
        actions.addWidget(button_box)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(intro)
        layout.addWidget(scroll_area, stretch=1)
        layout.addLayout(actions)
