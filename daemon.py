import sys
import re
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QMimeData

class MarkdownToHTMLCompiler:
    def __init__(self):
        # Pre-compile regex for performance
        self.block_math = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
        self.inline_math = re.compile(r'(?<!\$)\$([^$]+?)\$(?!\$)')
        self.mermaid = re.compile(r'```mermaid\s*(.*?)\s*```', re.DOTALL)
        self.cpp_code = re.compile(r'```cpp\s*(.*?)\s*```', re.DOTALL)
        self.general_code = re.compile(r'```([a-z0-9]+)?\s*(.*?)\s*```', re.DOTALL)
        
    def compile(self, text: str) -> str:
        # Phase 1: High-priority technical blocks
        # We use \g<1> to safely substitute group 1 back into the string
        
        # Block math
        html = self.block_math.sub(r'<div class="notion-text-equation-block" data-macro="\g<1>">$$\g<1>$$</div>', text)
        
        # Inline math
        html = self.inline_math.sub(r'<span class="notion-inline-math" data-macro="\g<1>">$\g<1>$</span>', html)
        
        # Mermaid
        html = self.mermaid.sub(r'<pre><code class="language-mermaid">\g<1></code></pre>', html)
        
        # CPP code
        html = self.cpp_code.sub(r'<pre><code class="language-cpp">\g<1></code></pre>', html)
        
        # Remaining General code (fallback)
        html = self.general_code.sub(r'<pre><code class="language-\g<1>">\g<2></code></pre>', html)
        
        # Phase 2: Structural Integrity (Headers & Paragraphs)
        html = re.sub(r'^### (.*?)$', r'<h3>\g<1></h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.*?)$', r'<h2>\g<1></h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.*?)$', r'<h1>\g<1></h1>', html, flags=re.MULTILINE)
        
        # Basic line returns mapped to break formatting
        html = html.replace('\n', '<br>')
        
        return f"<html><body>{html}</body></html>"

class ClipboardBridge:
    def __init__(self, app):
        self.app = app
        self.clipboard = app.clipboard()
        self.compiler = MarkdownToHTMLCompiler()
        
        # This state flag ensures we do not trigger an infinite loop when we modify the clipboard ourselves
        self.is_internal_update = False
        
        self.clipboard.dataChanged.connect(self.on_clipboard_change)

    def on_clipboard_change(self):
        # Prevent recursive loops
        if self.is_internal_update:
            return

        mime_data = self.clipboard.mimeData()
        
        # Gatekeeper / validation heuristic
        if mime_data.hasText():
            plain_text = mime_data.text()
            
            # If there's already HTML, it might be copied from a browser; don't break existing rich clipboards
            if mime_data.hasHtml():
                return
                
            # If the text has no technical tokens whatsoever, drop it to save CPU cycles
            if '$$' not in plain_text and '$' not in plain_text and '```' not in plain_text:
                return
            
            # Process payload
            html_content = self.compiler.compile(plain_text)
            self.set_clipboard_payload(plain_text, html_content)

    def set_clipboard_payload(self, plain_text: str, html: str):
        self.is_internal_update = True
        try:
            new_mime = QMimeData()
            new_mime.setText(plain_text)
            new_mime.setHtml(html)
            self.clipboard.setMimeData(new_mime)
        finally:
            self.is_internal_update = False

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # Headless GUI daemon (won't quit when no windows are open)
    app.setQuitOnLastWindowClosed(False)
    
    bridge = ClipboardBridge(app)
    
    print("LLM-to-Notion Universal Clipboard Bridge Daemon running. Listening for Markdown payloads...")
    sys.exit(app.exec())
