import sys
import os
import re
import uuid
import struct
import json
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QSystemTrayIcon, QMenu
from PyQt6.QtCore import QMimeData, Qt, QTimer, QPropertyAnimation
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QAction

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


def gen_id():
    return uuid.uuid4().hex[:14]

def gen_key():
    return f"_{uuid.uuid4().hex[:3]}"

def write_string16(s: str) -> bytes:
    data = struct.pack('<I', len(s)) + s.encode('utf-16le')
    padding = (4 - (len(data) % 4)) % 4
    data += b'\0' * padding
    return data

def build_web_custom_data(data_dict: dict) -> bytes:
    payload = struct.pack('<I', len(data_dict))
    for k, v in data_dict.items():
        payload += write_string16(k)
        payload += write_string16(v)
    return struct.pack('<I', len(payload)) + payload

import markdown
import xml.etree.ElementTree as ET

class MarkdownToSlateCompiler:
    """Converts standard LLM Markdown directly into Slite's binary SlateJS format."""
    
    def __init__(self):
        self.inline_math_map = {}
        
    def compile(self, text: str) -> bytes:
        slate_ast = {"fragment": {"children": []}, "data": {}}
        
        # Tokenize by finding block $$...$$ first
        block_tokens = re.split(r'\$\$(.*?)\$\$', text, flags=re.DOTALL)
        
        for i, block_part in enumerate(block_tokens):
            if i % 2 == 1:
                # Block math
                math_text = block_part.strip()
                f_id = gen_id()
                fl_id = gen_id()
                ast_node = {
                    "type": "formula",
                    "id": f_id,
                    "key": gen_key(),
                    "children": [{
                        "type": "formula-line",
                        "id": fl_id,
                        "key": gen_key(),
                        "children": [{"text": math_text, "key": gen_key()}]
                    }]
                }
                slate_ast["fragment"]["children"].append(ast_node)
            else:
                # Plain text blocks containing markdown
                if not block_part.strip():
                    continue
                
                self.inline_math_map.clear()
                
                # Protect inline math from markdown parser
                def hide_math(m):
                    idx = len(self.inline_math_map)
                    key = f"MATHPLACEHOLDER{idx}END"
                    self.inline_math_map[key] = m.group(1)
                    return key
                    
                protected_text = re.sub(r'(?<!\$)\$([^$\n]+?)\$(?!\$)', hide_math, block_part)
                
                # Render to HTML
                html = markdown.markdown(protected_text, extensions=['fenced_code', 'tables'])
                
                # Parse HTML tree
                try:
                    root = ET.fromstring(f"<div>{html}</div>")
                    for child in root:
                        ast_nodes = self.parse_block(child)
                        slate_ast["fragment"]["children"].extend(ast_nodes)
                except Exception as e:
                    # Fallback to plain text if XML parsing somehow fails
                    slate_ast["fragment"]["children"].append({
                        "type": "unstyled",
                        "id": gen_id(),
                        "key": gen_key(),
                        "children": [{"text": block_part, "key": gen_key()}]
                    })
                
        # Generate semantic-xml dynamically from AST
        semantic_xml = "".join(self.ast_to_semantic_xml(node) for node in slate_ast["fragment"]["children"])
                
        custom_dict = {
            "application/x-slite-global": json.dumps(slate_ast, separators=(',', ':')),
            "application/x-slite-semantic-xml": semantic_xml
        }
        
        return build_web_custom_data(custom_dict)

    def parse_block(self, node) -> list:
        tag = node.tag.lower()
        if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            type_map = {'h1': 'header-one', 'h2': 'header-two', 'h3': 'header-three', 
                        'h4': 'header-four', 'h5': 'header-five', 'h6': 'header-six'}
            return [{
                "type": type_map[tag],
                "id": gen_id(),
                "key": gen_key(),
                "children": self.parse_inline(node)
            }]
        elif tag == 'ul':
            return [{
                "type": "unordered-list",
                "id": gen_id(),
                "key": gen_key(),
                "children": [self.parse_list_item(li, "unordered-list-item") for li in node if li.tag == 'li']
            }]
        elif tag == 'ol':
            return [{
                "type": "ordered-list",
                "id": gen_id(),
                "key": gen_key(),
                "children": [self.parse_list_item(li, "ordered-list-item") for li in node if li.tag == 'li']
            }]
        elif tag == 'p':
            children = self.parse_inline(node)
            if not children:
                children = [{"text": "", "key": gen_key()}]
            return [{
                "type": "unstyled",
                "id": gen_id(),
                "key": gen_key(),
                "children": children
            }]
        elif tag == 'pre':
            code_el = node.find('code')
            text = code_el.text if code_el is not None else node.text
            if not text: text = ""
            lines = text.split('\n')
            blocks = []
            for line in lines:
                blocks.append({
                    "type": "unstyled",
                    "id": gen_id(),
                    "key": gen_key(),
                    "children": [{"text": line, "code": True, "key": gen_key()}]
                })
            return blocks
        else:
            children = self.parse_inline(node)
            if not children:
                children = [{"text": "", "key": gen_key()}]
            return [{
                "type": "unstyled",
                "id": gen_id(),
                "key": gen_key(),
                "children": children
            }]

    def parse_list_item(self, li_node, item_type):
        children = []
        for child in li_node:
            children.extend(self.parse_inline(child))
            if child.tail:
                children.extend(self.process_text(child.tail, {}))
        
        if li_node.text:
            children = self.process_text(li_node.text, {}) + children
            
        if not children:
            children = [{"text": "", "key": gen_key()}]
            
        return {
            "type": item_type,
            "id": gen_id(),
            "key": gen_key(),
            "children": children
        }

    def parse_inline(self, node, marks=None) -> list:
        if marks is None:
            marks = {}
        else:
            marks = marks.copy()
            
        tag = node.tag.lower() if isinstance(node.tag, str) else ''
        if tag in ['strong', 'b']:
            marks['bold'] = True
        elif tag in ['em', 'i']:
            marks['italic'] = True
        elif tag == 'code':
            marks['code'] = True
            
        children = []
        if node.text:
            children.extend(self.process_text(node.text, marks))
            
        for child in node:
            children.extend(self.parse_inline(child, marks))
            
            if child.tail:
                children.extend(self.process_text(child.tail, marks))
                
        return children

    def process_text(self, text: str, marks: dict) -> list:
        text = text.replace('\n', ' ')
        parts = re.split(r'(MATHPLACEHOLDER\d+END)', text)
        nodes = []
        for p in parts:
            if not p:
                continue
            if p.startswith('MATHPLACEHOLDER') and p.endswith('END'):
                math_str = self.inline_math_map.get(p)
                if math_str is not None:
                    nodes.append({
                        "formula": math_str,
                        "id": gen_id(),
                        "type": "inline-formula",
                        "children": [{"text": "", "key": gen_key()}],
                        "key": gen_key()
                    })
                else:
                    nodes.append({"text": p, **marks, "key": gen_key()})
            else:
                nodes.append({"text": p, **marks, "key": gen_key()})
        return nodes

    def ast_to_semantic_xml(self, node) -> str:
        if "text" in node:
            text = node["text"].replace('<', '&lt;').replace('>', '&gt;')
            if node.get("bold"): text = f"<b>{text}</b>"
            if node.get("italic"): text = f"<i>{text}</i>"
            if node.get("code"): text = f"<code>{text}</code>"
            return text
        
        tag_map = {
            "header-one": "h1", "header-two": "h2", "header-three": "h3",
            "header-four": "h4", "header-five": "h5", "header-six": "h6",
            "unstyled": "p", "unordered-list": "ul", "unordered-list-item": "li",
            "ordered-list": "ol", "ordered-list-item": "li",
            "formula": "formula", "formula-line": "formula-line",
        }
        
        if node["type"] == "inline-formula":
            safe_math = node["formula"].replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
            return f'<inline-formula id="{node["id"]}" formula="{safe_math}" />'
            
        tag = tag_map.get(node["type"], "div")
        inner = "".join(self.ast_to_semantic_xml(c) for c in node.get("children", []))
        if "id" in node:
            return f'<{tag} id="{node["id"]}">{inner}</{tag}>'
        else:
            return f'<{tag}>{inner}</{tag}>'

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
