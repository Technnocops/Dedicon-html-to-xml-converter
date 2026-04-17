from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QImage, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QApplication


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRANDING_DIR = PROJECT_ROOT / "assets" / "branding"
LOGO_SOURCE = BRANDING_DIR / "Dedicon-removebg-preview.png"
PNG_OUTPUT = BRANDING_DIR / "technocops_app_icon.png"
ICO_OUTPUT = BRANDING_DIR / "technocops_app_icon.ico"
SPLASH_OUTPUT = BRANDING_DIR / "technocops_splash.png"


def load_source_logo() -> QImage:
    image = QImage(str(LOGO_SOURCE))
    if image.isNull():
        raise FileNotFoundError(f"Unable to load branding image: {LOGO_SOURCE}")
    return image


def draw_brand_icon(size: int = 512) -> QImage:
    logo_image = load_source_logo()
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    background = QLinearGradient(0, 0, size, size)
    background.setColorAt(0.0, QColor("#04111f"))
    background.setColorAt(0.5, QColor("#0b2644"))
    background.setColorAt(1.0, QColor("#1a5ec7"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(background)
    painter.drawRoundedRect(QRectF(18, 18, size - 36, size - 36), 112, 112)

    painter.setPen(QPen(QColor(255, 255, 255, 35), 2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRectF(34, 34, size - 68, size - 68), 94, 94)

    glow = QLinearGradient(64, 48, size - 64, size - 64)
    glow.setColorAt(0.0, QColor(61, 201, 255, 44))
    glow.setColorAt(1.0, QColor(54, 255, 168, 28))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(glow)
    painter.drawRoundedRect(QRectF(52, 52, size - 104, size - 104), 88, 88)

    scaled_logo = logo_image.scaled(
        int(size * 0.76),
        int(size * 0.76),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = int((size - scaled_logo.width()) / 2)
    y = int((size - scaled_logo.height()) / 2)
    painter.drawImage(x, y, scaled_logo)
    painter.end()
    return image


def save_icon_assets() -> None:
    BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    image = draw_brand_icon()
    image.save(str(PNG_OUTPUT), "PNG")

    icon = QIcon()
    for size in (256, 128, 96, 64, 48, 32, 24, 16):
        icon.addFile(str(PNG_OUTPUT), QSize(size, size))
    icon.pixmap(QSize(256, 256)).save(str(ICO_OUTPUT), "ICO")


def draw_splash_image(width: int = 980, height: int = 540) -> QImage:
    logo_image = load_source_logo()
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    background = QLinearGradient(0, 0, width, height)
    background.setColorAt(0.0, QColor("#06111f"))
    background.setColorAt(0.45, QColor("#0d2745"))
    background.setColorAt(1.0, QColor("#1657c1"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(background)
    painter.drawRoundedRect(QRectF(0, 0, width, height), 32, 32)

    painter.setPen(QPen(QColor(255, 255, 255, 36), 2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRectF(14, 14, width - 28, height - 28), 26, 26)

    scaled_logo = logo_image.scaled(
        640,
        220,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    logo_x = int((width - scaled_logo.width()) / 2)
    painter.drawImage(logo_x, 70, scaled_logo)

    painter.setPen(QColor("#ebf4ff"))
    painter.setFont(QFont("Segoe UI Variable", 24, QFont.Weight.DemiBold))
    painter.drawText(
        QRectF(70, 310, width - 140, 36),
        Qt.AlignmentFlag.AlignCenter,
        "Technocops DDC Converter (HTML to XML) Pro",
    )

    painter.setPen(QColor("#b7d1f5"))
    painter.setFont(QFont("Segoe UI Variable", 13, QFont.Weight.Medium))
    painter.drawText(
        QRectF(90, 356, width - 180, 26),
        Qt.AlignmentFlag.AlignCenter,
        "Offline HTML-to-XML conversion workflow with validation and licensed access",
    )

    badge_rect = QRectF(width / 2 - 88, height - 68, 176, 30)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(14, 30, 52, 165))
    painter.drawRoundedRect(badge_rect, 15, 15)
    painter.setPen(QColor("#95f0c2"))
    painter.setFont(QFont("Segoe UI Variable", 11, QFont.Weight.DemiBold))
    painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "Version 1.0.0")

    painter.end()
    return image


def save_splash_asset() -> None:
    draw_splash_image().save(str(SPLASH_OUTPUT), "PNG")


def main() -> int:
    app = QApplication.instance() or QApplication([])
    save_icon_assets()
    save_splash_asset()
    print(PNG_OUTPUT)
    print(ICO_OUTPUT)
    print(SPLASH_OUTPUT)
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
