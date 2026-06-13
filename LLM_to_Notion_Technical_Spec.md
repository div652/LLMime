# Technical Specification: LLM-to-Notion Clipboard Bridge

## 1. System Architecture
The application runs as a lightweight, background OS daemon. The architecture is divided into three highly decoupled modules:
1. **The Clipboard Watcher:** Polls or hooks into the OS paste buffer, triggering only when a new `text/plain` payload matching specific LLM structural heuristics is detected.
2. **The AST / State-Machine Compiler:** Converts raw markdown strings into structured HTML tokens in a single efficient pass.
3. **The Memory Binder:** Injects the compiled `text/html` payload alongside the original `text/plain` fallback back into the system clipboard.

## 2. Format Specification & HTML Mapping Targets
Target applications like Notion use internal DOM parsers to convert pasted HTML into JSON blocks. We must spoof these exact tags.

| LLM Output Token | Target HTML Signature | Notion Behavior |
| :--- | :--- | :--- |
| `$$ [math] $$` | `<div class="notion-text-equation-block" data-macro="[math]">$$[math]$$</div>` | Instantiates a native block-level equation. |
| `$ [math] $` | `<span class="notion-inline-math" data-macro="[math]">$[math]$</span>` | Instantiates inline math text styling. |
| ` ```mermaid \n [code] \n ``` ` | `<pre><code class="language-mermaid">[code]</code></pre>` | Triggers internal Mermaid rendering engine. |
| ` ```cpp \n [code] \n ``` ` | `<pre><code class="language-cpp">[code]</code></pre>` | Standard code block with C++ syntax highlighting. |

## 3. Platform Execution: Linux First implementation
To achieve near zero-latency conversion—critical for a seamless UX—the bridge relies on native OS APIs. For Linux, manipulating both the MIME types (`text/plain` and `text/html`) requires interacting with the X11 or Wayland clipboards.

While Python provides rapid prototyping, standard `pyperclip` only handles plain text. We will leverage **PyQt6** as a headless daemon, as its `QClipboard` class securely wraps Linux clipboard protocols and supports multi-MIME payload injection out of the box.

```python
# Linux/Cross-Platform Headless Clipboard Binder
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QMimeData

def set_clipboard_payload(plain_text: str, html: str):
    app = QApplication.instance() or QApplication([])
    mime_data = QMimeData()
    mime_data.setText(plain_text)
    mime_data.setHtml(html)
    app.clipboard().setMimeData(mime_data)
```

## 4. The Parsing Engine: $O(N)$ State Machine
Poorly written regex can suffer from catastrophic backtracking, introducing noticeable latency between `Ctrl+C` and `Ctrl+V`. Because LLMs output tokens auto-regressively in a predictable schema, we can model the text transformation as a single-pass state machine operating in strict $O(N)$ time.

```python
import re

class MarkdownToHTMLCompiler:
    def __init__(self):
        # Pre-compile regex for performance
        self.block_math = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
        self.inline_math = re.compile(r'\$([^$
]+?)\$')
        self.mermaid = re.compile(r'```mermaid\s*(.*?)\s*```', re.DOTALL)
        
    def compile(self, text: str) -> str:
        # Phase 1: High-priority technical blocks
        html = self.block_math.sub(r'<div class="notion-text-equation-block" data-macro="">$$$$</div>', text)
        html = self.inline_math.sub(r'<span class="notion-inline-math" data-macro="">$$</span>', html)
        html = self.mermaid.sub(r'<pre><code class="language-mermaid"></code></pre>', html)
        
        # Phase 2: Structural Integrity (Headers & Paragraphs)
        html = re.sub(r'^### (.*?)$', r'<h3></h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.*?)$', r'<h2></h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.*?)$', r'<h1></h1>', html, flags=re.MULTILINE)
        html = html.replace('\n', '<br>')
        
        return f"<html><body>{html}</body></html>"
```

## 5. Step-by-Step Implementation Guide

### Step 1: Daemon Initialization
Set up a headless Python script using `keyboard` or `pynput` to listen for a specific global trigger (e.g., `Ctrl+Shift+C`), or continuously poll `QClipboard.dataChanged()` to evaluate all incoming text automatically.

### Step 2: Content Validation Filter
Implement a heuristic gatekeeper. If the copied text does not contain `$$` or ` ``` `, immediately drop the process to save CPU cycles. The compiler should only run if technical structures are present.

### Step 3: Compilation and Re-injection
Pass the string through the `MarkdownToHTMLCompiler`. Inject the resulting HTML string and the original Markdown string back into `QClipboard`. By supplying both, Notion will parse the HTML, while standard text editors (like Vim or a terminal) will fallback safely to the raw Markdown.

### Step 4: Packaging and Daemonization (Linux)
1. Use `PyInstaller --onefile --noconsole daemon.py` to create a standalone binary.
2. Write a `systemd` service file (`~/.config/systemd/user/llm-bridge.service`) to ensure the watcher launches automatically on boot under the user's session.
3. For subsequent macOS/Windows ports, this binary can be wrapped with `pystray` to provide a system-tray toggle for enabling/disabling the watcher.
