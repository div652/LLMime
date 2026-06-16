import sys
import os
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QSystemTrayIcon, QMenu
from PyQt6.QtCore import QMimeData, Qt, QTimer, QPropertyAnimation
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QAction

# OS-independent core (Markdown -> Slite AST -> Chromium binary payload).
# Shared verbatim with the Windows daemon. See compiler.py.
from compiler import MarkdownToSlateCompiler

def create_tray_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # Draw a rounded rectangle for clipboard backing (sleek indigo)
    painter.setBrush(QColor("#4F46E5"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(4, 4, 56, 56, 12, 12)
    
    # Draw a small metal clip at the top
    painter.setBrush(QColor("#E0E7FF"))
    painter.drawRoundedRect(20, 2, 24, 10, 3, 3)
    
    # Draw a bold white letter "L" representing LLMime
    painter.setPen(QColor("#FFFFFF"))
    font = QFont("sans-serif", 28, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "L")
    
    painter.end()
    return QIcon(pixmap)


class Toast(QWidget):
    """Ephemeral translucent popup"""
    def __init__(self, message, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout()
        self.label = QLabel(message)
        self.label.setStyleSheet(
            "background-color: rgba(0, 0, 0, 200); color: white; padding: 10px 16px; border-radius: 6px; font-weight: bold; font-family: sans-serif; font-size: 13px;"
        )
        layout.addWidget(self.label)
        self.setLayout(layout)
        try:
            screen = QApplication.primaryScreen().availableGeometry()
            self.adjustSize()
            self.move(screen.width() - self.width() - 24, screen.height() - self.height() - 100)
        except Exception:
            pass
        self.show()
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(1500)
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.0)
        QTimer.singleShot(1500, self.start_fade)
        
    def start_fade(self):
        if hasattr(self, 'animation'):
            self.animation.start()
            self.animation.finished.connect(self.close)

class ClipboardBridge:
    def __init__(self, app):
        self.app = app
        self.clipboard = app.clipboard()
        self.compiler = MarkdownToSlateCompiler()
        self.is_internal_update = False
        self._toast = None
        self.clipboard.dataChanged.connect(self.on_clipboard_change)
        
        # System Tray Icon setup
        try:
            self.tray_icon = QSystemTrayIcon(create_tray_icon(), self.app)
            self.tray_menu = QMenu()
            
            quit_action = QAction("Quit LLMime", self.app)
            quit_action.triggered.connect(self.app.quit)
            self.tray_menu.addAction(quit_action)
            
            self.tray_icon.setContextMenu(self.tray_menu)
            self.tray_icon.setToolTip("LLMime - Slite Clipboard Bridge")
            self.tray_icon.show()
        except Exception as e:
            print(f"Warning: Could not create system tray icon: {e}", file=sys.stderr)
    
    def on_clipboard_change(self):
        if self.is_internal_update:
            return
        
        mime_data = self.clipboard.mimeData()
        
        # Abort if the copy is native from Slite
        if mime_data.hasFormat('chromium/x-web-custom-data'):
            return
            
        if mime_data.hasText():
            plain_text = mime_data.text()
            if '$$' not in plain_text and '$' not in plain_text:
                return
            
            raw_bytes = self.compiler.compile(plain_text)
            
            self.is_internal_update = True
            try:
                new_mime = QMimeData()
                new_mime.setText(plain_text)
                
                # Copy existing HTML fallback if present
                if mime_data.hasHtml():
                    new_mime.setHtml(mime_data.html())
                    
                # Inject binary Slite payload
                new_mime.setData("chromium/x-web-custom-data", raw_bytes)
                
                self.clipboard.setMimeData(new_mime)
            finally:
                self.is_internal_update = False
            
            self._toast = Toast("✨ LLMime: Converted to Native Slite!")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    bridge = ClipboardBridge(app)
    print("LLMime v3 daemon running. Slite AST binary compiler pipeline active...")
    sys.exit(app.exec())
