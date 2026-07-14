"""Application icon helpers."""

import os
import shutil

from PySide6.QtGui import QIcon

PACKAGE_ICON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resources", "linuxshot.svg",
)
INSTALLED_ICON = os.path.expanduser(
    "~/.local/share/icons/hicolor/scalable/apps/linuxshot.svg"
)


def ensure_icon_installed() -> None:
    """Copy the bundled icon into the hicolor theme so desktop files and
    notifications can refer to it by name.
    """
    if os.path.isfile(INSTALLED_ICON) or not os.path.isfile(PACKAGE_ICON):
        return
    os.makedirs(os.path.dirname(INSTALLED_ICON), exist_ok=True)
    shutil.copy2(PACKAGE_ICON, INSTALLED_ICON)


def app_icon() -> QIcon:
    if os.path.isfile(PACKAGE_ICON):
        return QIcon(PACKAGE_ICON)
    return QIcon.fromTheme("camera-photo")


def theme_icon(name: str, fallback: str = "image-x-generic") -> QIcon:
    icon = QIcon.fromTheme(name)
    if icon.isNull():
        icon = QIcon.fromTheme(fallback)
    return icon
