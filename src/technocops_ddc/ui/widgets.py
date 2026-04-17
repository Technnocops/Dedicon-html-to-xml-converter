from __future__ import annotations

import uuid

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

from technocops_ddc.models import AuthorEntry, DTBookMetadata, PageRangeSelection


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
        self.publisher_input = QLineEdit()
        self.language_input = QLineEdit("en")
        self.identifier_input = QLineEdit()
        self.source_input = QLineEdit()
        self.source_publisher_input = QLineEdit()
        self.producer_input = QLineEdit()
        self.doc_type_input = QComboBox()
        self.doc_type_input.addItems(["sv", "ro"])
        self.author_rows: list[AuthorRowWidget] = []

        self.uid_input.setPlaceholderText("Example: 374388")
        self.identifier_input.setPlaceholderText("Usually same as UID")
        self.title_input.setPlaceholderText("Document title")
        self.publisher_input.setPlaceholderText("Publisher name")
        self.source_input.setPlaceholderText("ISBN if available")
        self.source_publisher_input.setPlaceholderText("Source publisher")
        self.producer_input.setPlaceholderText("Example: Continuum Content Solutions")
        self.language_input.setPlaceholderText("Auto-detected language code")
        self._configure_input_sizes()
        self._connect_field_signals()

        today = QDate.currentDate()
        self.completion_date_input = QDateEdit(today)
        self.produced_date_input = QDateEdit(today)
        for widget in (self.completion_date_input, self.produced_date_input):
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("yyyy-MM-dd")
            widget.setMinimumHeight(38)
            widget.dateChanged.connect(lambda *_args: self.metadataChanged.emit())
        self.doc_type_input.setMinimumHeight(38)
        self.doc_type_input.currentTextChanged.connect(lambda *_args: self.metadataChanged.emit())

        self.generate_ids_button = QPushButton("Generate IDs")
        self.generate_ids_button.setProperty("variant", "secondary")
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

        self.generate_ids()

    def generate_ids(self) -> None:
        generated_uid = self._derive_book_id(self.document_hint) or uuid.uuid4().hex
        self.uid_input.setText(generated_uid)
        self.identifier_input.setText(generated_uid)
        if self.generate_ids_button.text() != "IDs Generated":
            self.generate_ids_button.setText("IDs Generated")
        self.generate_ids_button.setEnabled(False)
        QTimer.singleShot(1200, self._reset_generate_button)
        self.metadataChanged.emit()

    def apply_document_defaults(self, first_document_name: str) -> None:
        self.document_hint = first_document_name
        if not self.title_input.text().strip():
            self.title_input.setText(first_document_name)
        suggested_id = self._derive_book_id(first_document_name)
        if suggested_id:
            self.uid_input.setText(suggested_id)
            self.identifier_input.setText(suggested_id)

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
        if title and not self.title_input.text().strip():
            self.title_input.setText(title)
        if source_isbn and not self.source_input.text().strip():
            self.source_input.setText(source_isbn)
        if publisher and not self.publisher_input.text().strip():
            self.publisher_input.setText(publisher)
        if source_publisher and not self.source_publisher_input.text().strip():
            self.source_publisher_input.setText(source_publisher)

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
            publisher=self.publisher_input.text().strip(),
            language=self.language_input.text().strip(),
            identifier=self.identifier_input.text().strip(),
            source_isbn=self.source_input.text().strip(),
            produced_date=self.produced_date_input.date().toString("yyyy-MM-dd"),
            source_publisher=self.source_publisher_input.text().strip(),
            producer=self.producer_input.text().strip(),
            authors=authors,
            doc_type=self.doc_type_input.currentText(),
        )

    def _reset_generate_button(self) -> None:
        self.generate_ids_button.setText("Generate IDs")
        self.generate_ids_button.setEnabled(True)

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
        self.enable_checkbox = QCheckBox("Limit conversion to a page range")
        self.start_spin = QSpinBox()
        self.end_spin = QSpinBox()
        for spin_box in (self.start_spin, self.end_spin):
            spin_box.setRange(1, 99999)
            spin_box.setValue(1)
            spin_box.setMinimumWidth(96)

        self.enable_checkbox.toggled.connect(self._refresh_state)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.enable_checkbox)
        layout.addStretch(1)
        layout.addWidget(QLabel("Start Page"))
        layout.addWidget(self.start_spin)
        layout.addWidget(QLabel("End Page"))
        layout.addWidget(self.end_spin)
        self._refresh_state()

    def selection(self) -> PageRangeSelection | None:
        if not self.enable_checkbox.isChecked():
            return None
        return PageRangeSelection(
            start_page=self.start_spin.value(),
            end_page=self.end_spin.value(),
        )

    def validation_errors(self) -> list[str]:
        selection = self.selection()
        if selection is None:
            return []
        return selection.validate()

    def summary_label(self) -> str:
        selection = self.selection()
        if selection is None:
            return "All pages"
        return selection.label

    def _refresh_state(self) -> None:
        enabled = self.enable_checkbox.isChecked()
        self.start_spin.setEnabled(enabled)
        self.end_spin.setEnabled(enabled)


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

        intro = QLabel("Review or update every metadata field here. Detected values from the input files will be filled automatically when available.")
        intro.setProperty("role", "subtitle")
        intro.setWordWrap(True)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(metadata_form)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(intro)
        layout.addWidget(scroll_area, stretch=1)
        layout.addWidget(button_box)
