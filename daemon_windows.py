"""
LLMime — Windows daemon.

Feature-parity port of the Linux ``daemon.py`` for Windows. It watches the
clipboard for LLM Markdown containing math / code, compiles it into Slite's
native SlateJS binary payload, and writes that payload back to the clipboard
so it pastes into Slite (an Electron app) as fully-native, editable blocks.

Why this is a separate file from ``daemon.py``
----------------------------------------------
The *compiler* (Markdown -> Slite AST -> Chromium binary) is OS-independent
and lives in ``compiler.py``; both daemons share it verbatim. The *transport*
— how the bytes land on the OS clipboard — is fundamentally different:

* On Linux/X11, Qt registers clipboard formats by their MIME-string name, so
  ``QMimeData.setData("chromium/x-web-custom-data", ...)`` is read correctly
  by Chromium/Electron apps.
* On Windows, the clipboard is keyed by numeric format IDs registered *by
  name* via ``RegisterClipboardFormat``. Chromium/Electron registers web
  custom data under the Windows clipboard format name
  ``"Chromium Web Custom MIME Data Format"`` — NOT the MIME string. Qt's
  Windows clipboard backend does not register our payload under that exact
  name, so a Qt ``setData`` would be invisible to Slite.

Therefore the Windows daemon keeps PyQt6 only for the tray icon, the toast,
and clipboard *monitoring* (for UX parity with Linux), but performs the
clipboard *write* through the native Win32 API (``win32clipboard``) using the
exact Chromium format name. See ``TECHNICAL_SPEC_V2.md`` Section 6.
"""

import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

import win32clipboard
import win32con

# Shared OS-independent core.
from compiler import MarkdownToSlateCompiler, looks_like_markdown
# Reuse the Qt tray icon + toast from the Linux daemon (pure Qt, OS-independent).
from daemon import create_tray_icon, Toast

# Windows clipboard format names. These are registered process-wide by name;
# RegisterClipboardFormat returns the same numeric ID for a given name across
# every app, which is how we hand data to Slite/Chromium.
WEB_CUSTOM_FORMAT_NAME = "Chromium Web Custom MIME Data Format"
HTML_FORMAT_NAME = "HTML Format"  # the well-known CF_HTML registered format


def make_cf_html(fragment_html: str) -> bytes:
    """Wrap an HTML fragment in the CF_HTML clipboard envelope.

    CF_HTML is UTF-8 with a header whose byte offsets point at the start/end
    of the document and of the pasted fragment. The offsets must be computed
    against the *encoded* bytes, so we template fixed-width placeholders, then
    backfill the real offsets once positions are known.
    """
    header = (
        "Version:0.9\r\n"
        "StartHTML:{:010d}\r\n"
        "EndHTML:{:010d}\r\n"
        "StartFragment:{:010d}\r\n"
        "EndFragment:{:010d}\r\n"
    )
    pre = "<html><body>\r\n<!--StartFragment-->"
    post = "<!--EndFragment-->\r\n</body></html>"

    # Length of the header is constant because the offsets are fixed-width.
    header_len = len(header.format(0, 0, 0, 0).encode("utf-8"))
    start_html = header_len
    start_fragment = start_html + len(pre.encode("utf-8"))
    end_fragment = start_fragment + len(fragment_html.encode("utf-8"))
    end_html = end_fragment + len(post.encode("utf-8"))

    document = (
        header.format(start_html, end_html, start_fragment, end_fragment)
        + pre + fragment_html + post
    )
    return document.encode("utf-8")


def custom_format_present() -> bool:
    """True if the Chromium web-custom-data format is already on the clipboard.

    This single check does double duty:
      1. Re-entrancy guard — after our own native write the format is present,
         so the resulting clipboard-change notification is ignored.
      2. Native-source guard — a genuine copy *from* Slite also carries this
         format, and we must leave those untouched (same intent as the Linux
         daemon's ``hasFormat('chromium/x-web-custom-data')`` early return).

    ``IsClipboardFormatAvailable`` does not require opening the clipboard, so
    it is cheap and cannot deadlock against the source application.
    """
    cf = win32clipboard.RegisterClipboardFormat(WEB_CUSTOM_FORMAT_NAME)
    return bool(win32clipboard.IsClipboardFormatAvailable(cf))


def _open_clipboard_with_retry(attempts: int = 10):
    """OpenClipboard can transiently fail if another app holds it. Retry briefly."""
    last_err = None
    for _ in range(attempts):
        try:
            win32clipboard.OpenClipboard()
            return True
        except Exception as e:  # pywin32 raises on busy clipboard
            last_err = e
    if last_err is not None:
        raise last_err
    return False


def write_native_clipboard(plain_text: str, html: str, custom_bytes: bytes) -> None:
    """Atomically replace the clipboard with text + CF_HTML + Slite custom data.

    All formats must be written inside a single Open/Empty/Close session so
    the Chromium payload and its text/html fallbacks coexist for one paste.
    """
    cf_custom = win32clipboard.RegisterClipboardFormat(WEB_CUSTOM_FORMAT_NAME)
    cf_html = win32clipboard.RegisterClipboardFormat(HTML_FORMAT_NAME)

    _open_clipboard_with_retry()
    try:
        win32clipboard.EmptyClipboard()
        # Plain-text fallback (pywin32 accepts a str for CF_UNICODETEXT).
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, plain_text)
        # Rich-text fallback for apps that don't understand the Slite format.
        if html:
            win32clipboard.SetClipboardData(cf_html, make_cf_html(html))
        # The payload Slite actually consumes for native, editable paste.
        win32clipboard.SetClipboardData(cf_custom, custom_bytes)
    finally:
        win32clipboard.CloseClipboard()


class WindowsClipboardBridge:
    def __init__(self, app):
        self.app = app
        self.clipboard = app.clipboard()
        self.compiler = MarkdownToSlateCompiler()
        self._toast = None
        self.clipboard.dataChanged.connect(self.on_clipboard_change)

        # System tray icon (shared with the Linux daemon).
        try:
            from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
            from PyQt6.QtGui import QAction
            self.tray_icon = QSystemTrayIcon(create_tray_icon(), self.app)
            self.tray_menu = QMenu()
            quit_action = QAction("Quit LLMime", self.app)
            quit_action.triggered.connect(self.app.quit)
            self.tray_menu.addAction(quit_action)
            self.tray_icon.setContextMenu(self.tray_menu)
            self.tray_icon.setToolTip("LLMime - Slite Clipboard Bridge (Windows)")
            self.tray_icon.show()
        except Exception as e:
            print(f"Warning: Could not create system tray icon: {e}", file=sys.stderr)

    def on_clipboard_change(self):
        # If the Slite native format is already present, this change was caused
        # either by our own write or by a copy made inside Slite. Skip both.
        try:
            if custom_format_present():
                return
        except Exception:
            # If the probe fails, fall through and let the text checks decide.
            pass

        mime_data = self.clipboard.mimeData()
        if not mime_data.hasText():
            return

        plain_text = mime_data.text()
        if not looks_like_markdown(plain_text):
            return

        custom_bytes = self.compiler.compile(plain_text)
        html = mime_data.html() if mime_data.hasHtml() else ""

        try:
            write_native_clipboard(plain_text, html, custom_bytes)
        except Exception as e:
            print(f"Error writing clipboard: {e}", file=sys.stderr)
            return

        self._toast = Toast("✨ LLMime: Converted to Native Slite!")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    bridge = WindowsClipboardBridge(app)
    print("LLMime v3 (Windows) daemon running. Native Win32 AST clipboard injection active...")
    sys.exit(app.exec())
