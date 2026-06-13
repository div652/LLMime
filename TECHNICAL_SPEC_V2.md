# LLMime — Technical Specification v2
## KaTeX Pre-Rendering Clipboard Bridge

### 1. Problem Statement

LLM outputs contain raw Markdown with LaTeX equations (`$$...$$`, `$...$`), Mermaid diagrams, code blocks, and rich formatting (`**bold**`, lists, headers). When copy-pasted into productivity apps like **Slite**, **Notion**, or **Obsidian**, these render as ugly plaintext symbols instead of formatted content.

**Goal:** Build a background Linux daemon that intercepts clipboard content, detects LLM-generated Markdown, and injects a pre-rendered HTML version so pasting "just works" in any rich text editor.

---

### 2. Lessons From the Failed v1 Approach

> [!CAUTION]
> **Do NOT attempt native equation block injection.** The v1 implementation tried to spoof Slite/Notion's internal DOM structures (`data-type="formula"`, `notion-text-equation-block`) via clipboard HTML. This was experimentally proven impossible — even injecting Slite's **own** exported formula HTML back into the clipboard resulted in raw text on paste. These apps only create equation blocks through their UI or API, never from pasted HTML.

#### Key Findings (v1 Post-Mortem)

| Finding | Detail |
|---|---|
| **Browser `text/html` conflict** | When copying from a browser (ChatGPT, Gemini), the clipboard already contains a `text/html` MIME type from the webpage. Any daemon gatekeeper like `if hasHtml(): return` will silently abort. **Fix:** Always process `text/plain` regardless of existing HTML. |
| **Half-HTML breaks host Markdown parsers** | If you inject `text/html` that only converts *some* elements (e.g., math but not bold), the host app switches from its Markdown parser to its HTML parser, causing `**bold**` to render as literal asterisks and `\n` to be stripped. **Fix:** Convert the *entire* document to proper HTML, not just the technical tokens. |
| **Naive `\n` → `<br>` destroys layout** | Replacing newlines with `<br>` tags breaks equation blocks (injects `<br>` into LaTeX) and gets stripped by apps that expect `<p>` elements. **Fix:** Use a proper Markdown library for structural conversion. |
| **GPaste clipboard manager conflict** | GPaste can intercept and re-normalize clipboard events, stripping custom MIME types. Not the primary bug, but a complicating factor. **Mitigation:** Document as known environment issue. |
| **X11 vs Wayland** | Wayland blocks headless background apps from accessing the clipboard entirely. **Fix:** Verify `$XDG_SESSION_TYPE` is `x11`, or use `wl-paste --watch` for Wayland. User is confirmed X11. |

---

### 3. Architecture: KaTeX Pre-Rendering Pipeline

Instead of asking the host app to *interpret* formula syntax (which they refuse), we **pre-render** LaTeX into pure visual HTML using KaTeX. The output is ordinary styled `<span>` elements — any rich text editor will display them as formatted typography.

```
┌─────────────────────────────────────────────────────────────────┐
│                     LLMime Daemon Pipeline                      │
│                                                                 │
│  Ctrl+C  →  QClipboard.dataChanged signal fires                │
│          →  Read text/plain from clipboard                      │
│          →  Gatekeeper: contains $$, $, or ```?                 │
│             (no → ignore, yes → continue)                       │
│          →  Phase 1: Extract & render LaTeX via KaTeX CLI       │
│             - Block math ($$...$$) → katex --display-mode       │
│             - Inline math ($...$)  → katex (inline)             │
│          →  Phase 2: Full markdown → HTML via Python `markdown` │
│             - Headers, bold, italic, lists, tables, code blocks │
│          →  Phase 3: Inject text/html + text/plain into clip    │
│          →  Show Toast notification ("LLMime: Converted!")      │
│  Ctrl+V  →  Host app reads styled HTML, renders beautifully    │
└─────────────────────────────────────────────────────────────────┘
```

#### Why This Works

The KaTeX CLI converts raw LaTeX into pure CSS-styled `<span>` elements:

```
Input:  E = mc^2
Output: <span class="katex">
          <span class="katex-html">
            <span class="mord mathnormal">E</span>
            <span class="mrel">=</span>
            <span class="mord">mc<sup>2</sup></span>
          </span>
        </span>
```

The host app sees this as ordinary rich text (like pasting from a webpage) and renders it visually. No special equation block support required.

---

### 4. Implementation Guide

#### 4.1 Dependencies

```bash
# System
sudo apt install nodejs npm xclip

# Python (in venv)
pip install PyQt6 Markdown

# Node.js
npm install -g katex
```

#### 4.2 Core Module: `daemon.py`

The daemon has four components:

**A. MarkdownToHTMLCompiler**
```python
import re, subprocess, markdown

class MarkdownToHTMLCompiler:
    def __init__(self):
        self.block_math = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
        self.inline_math = re.compile(r'(?<!\$)\$([^$\n]+?)\$(?!\$)')

    def render_katex(self, latex: str, display_mode: bool = False) -> str:
        """Shell out to KaTeX CLI for server-side LaTeX → HTML rendering."""
        cmd = ["katex"]
        if display_mode:
            cmd.append("--display-mode")
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        html, err = proc.communicate(input=latex.strip())
        if proc.returncode != 0:
            return f"[LaTeX Error: {latex.strip()}]"
        return html.strip()

    def compile(self, text: str) -> str:
        # Phase 1: Replace LaTeX blocks with pre-rendered HTML
        # Block math first (greedy, before inline)
        html = self.block_math.sub(
            lambda m: self.render_katex(m.group(1), display_mode=True), text)
        # Inline math
        html = self.inline_math.sub(
            lambda m: self.render_katex(m.group(1), display_mode=False), html)

        # Phase 2: Convert remaining Markdown to structural HTML
        html = markdown.markdown(html, extensions=['fenced_code', 'tables'])

        return f"<html><body>\n{html}\n</body></html>"
```

**B. Toast Notification** (proven working in v1)
```python
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation

class Toast(QWidget):
    """Ephemeral translucent popup that fades after 1.5s."""
    def __init__(self, message):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint |
                           Qt.WindowType.FramelessWindowHint |
                           Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout()
        label = QLabel(message)
        label.setStyleSheet("background-color: rgba(0,0,0,200); color: white; "
                           "padding: 10px; border-radius: 5px; font-weight: bold;")
        layout.addWidget(label)
        self.setLayout(layout)
        # Position at bottom-center of screen
        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move((screen.width() - self.width()) // 2, screen.height() - 150)
        self.show()
        # Fade animation
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(1500)
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.0)
        QTimer.singleShot(1500, lambda: (self.animation.start(),
                          self.animation.finished.connect(self.close)))
```

**C. ClipboardBridge** (v1 proven, with `hasHtml` guard removed)
```python
class ClipboardBridge:
    def __init__(self, app):
        self.clipboard = app.clipboard()
        self.compiler = MarkdownToHTMLCompiler()
        self.is_internal_update = False
        self.clipboard.dataChanged.connect(self.on_clipboard_change)
        self._toast = None  # prevent garbage collection

    def on_clipboard_change(self):
        if self.is_internal_update:
            return
        mime_data = self.clipboard.mimeData()
        if mime_data.hasText():
            plain = mime_data.text()
            # Gatekeeper: only process if LLM technical tokens detected
            # DO NOT check hasHtml() — browsers always set this
            if '$$' not in plain and '$' not in plain and '```' not in plain:
                return
            html = self.compiler.compile(plain)
            self.is_internal_update = True
            try:
                new_mime = QMimeData()
                new_mime.setText(plain)
                new_mime.setHtml(html)
                self.clipboard.setMimeData(new_mime)
            finally:
                self.is_internal_update = False
            self._toast = Toast("LLMime: Converted!")
```

**D. Main Entry Point**
```python
if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # headless daemon
    bridge = ClipboardBridge(app)
    print("LLMime daemon running...")
    sys.exit(app.exec())
```

#### 4.3 Build & Deploy: `build.sh`

```bash
#!/bin/bash
source venv/bin/activate
pip install pyinstaller
# IMPORTANT: Quote ExecStart path — spaces in path cause 203/EXEC errors
pyinstaller --onefile --noconsole daemon.py

# Systemd service (double-quote the ExecStart path!)
cat > ~/.config/systemd/user/llm-bridge.service << EOF
[Unit]
Description=LLMime Clipboard Bridge

[Service]
ExecStart="$(pwd)/dist/daemon"
Restart=always
RestartSec=5
Environment=DISPLAY=:0

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now llm-bridge.service
```

---

### 5. Known Edge Cases (from v1 testing)

| Issue | Status | Notes |
|---|---|---|
| Sub-section mouse copying doesn't trigger | Open | Partial selections may lack matching `$$` pairs |
| ChatGPT copies fail while Gemini works | Open | ChatGPT may use canvas-based UI affecting `text/plain` |
| Table formatting | Open | `markdown` library `tables` extension generates `<table>` HTML — verify host app renders it |
| GPaste conflict | Mitigated | User should disable GPaste while using LLMime |

---

### 6. Diagnostic Tools

Keep these scripts handy for debugging clipboard issues:

**Dump clipboard contents:**
```python
# dump_clipboard.py
from PyQt6.QtWidgets import QApplication
import sys
app = QApplication(sys.argv)
mime = app.clipboard().mimeData()
print("TEXT:", mime.text() if mime.hasText() else "None")
print("HTML:", mime.html() if mime.hasHtml() else "None")
print("FORMATS:", mime.formats())
```

**Check display server:**
```bash
echo $XDG_SESSION_TYPE  # Must be "x11" for PyQt6 clipboard
```

---

### 7. File Structure (v2)

```
LLMime/
├── daemon.py                        # [NEW] Core daemon with KaTeX pipeline
├── build.sh                         # [UPDATED] Build + systemd setup
├── requirements.txt                 # [UPDATED] PyQt6, Markdown
├── TECHNICAL_SPEC_V2.md             # This document
├── LLM_to_Notion_Product_Overview.md # Original problem statement
├── LLM_output.png                   # Reference: raw LLM output
├── slite_bad.png                    # Reference: broken paste result
├── slite_good.png                   # Reference: target paste result
└── venv/                            # Python virtual environment
```
