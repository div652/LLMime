"""
LLMime — OS-independent core.

This module contains the Markdown -> Slite SlateJS AST compiler and the
Chromium "web custom data" binary packer. None of this code touches the OS
clipboard or any GUI toolkit, so it is shared verbatim between the Linux
daemon (``daemon.py``) and the Windows daemon (``daemon_windows.py``).

The binary payload produced here is identical on every platform — it emulates
a ``base::Pickle`` exactly as Chromium serialises web custom data. Only the
*transport* (how the bytes are placed onto the OS clipboard and what the
clipboard format is called) differs per platform.
"""

import re
import uuid
import struct
import json

import markdown
import xml.etree.ElementTree as ET


# --- Trigger detection -------------------------------------------------------
# The daemon should only rewrite the clipboard when the copied text actually
# looks like LLM Markdown worth converting. Originally this was gated solely on
# the presence of a "$" math delimiter, which silently ignored code blocks,
# tables, headings, and lists. The signals below widen the gate while still
# requiring a *structural* Markdown marker, so ordinary prose copied for use in
# other apps is left untouched.
_FENCE_RE = re.compile(r'```')                                  # fenced code block
_ATX_HEADER_RE = re.compile(r'^[ \t]{0,3}#{1,6}[ \t]+\S', re.MULTILINE)  # # heading
_LIST_RE = re.compile(r'^[ \t]{0,3}([-*+][ \t]+|\d+\.[ \t]+)\S', re.MULTILINE)  # - / 1. list
_BOLD_RE = re.compile(r'\*\*.+?\*\*|__.+?__')                    # **bold** / __bold__
# A Markdown table: a line containing a pipe, then a delimiter row made only of
# pipes / dashes / colons / whitespace and containing at least one dash.
_TABLE_RE = re.compile(
    r'^[^\n]*\|[^\n]*\r?\n[ \t]*\|?[ \t:|-]*-[ \t:|-]*\|?[ \t]*$',
    re.MULTILINE,
)


def looks_like_markdown(text: str) -> bool:
    """True if ``text`` carries a structural Markdown signal worth converting."""
    if not text:
        return False
    if '$' in text:                       # math: $...$ or $$...$$ (original gate)
        return True
    if _FENCE_RE.search(text):            # ``` code fences
        return True
    if _TABLE_RE.search(text):            # | a | b | with a |---| row
        return True
    if _ATX_HEADER_RE.search(text):       # # / ## headings
        return True
    if _LIST_RE.search(text):             # bullet / numbered lists
        return True
    if _BOLD_RE.search(text):             # **bold** emphasis
        return True
    return False


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

            lang = ""
            if code_el is not None and 'class' in code_el.attrib:
                cls = code_el.attrib['class']
                if cls.startswith('language-'):
                    lang = cls[len('language-'):]

            if text.endswith('\n'):
                text = text[:-1]
            lines = text.split('\n')

            line_nodes = []
            for line in lines:
                line_nodes.append({
                    "type": "code-block",
                    "id": gen_id(),
                    "language": lang,
                    "children": [{"text": line, "key": gen_key()}],
                    "key": gen_key()
                })
            return [{
                "type": "code-blocks",
                "id": gen_id(),
                "wrapCode": False,
                "children": line_nodes,
                "key": gen_key()
            }]
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

        if node["type"] == "code-blocks":
            lang = ""
            if node.get("children") and "language" in node["children"][0]:
                lang = node["children"][0]["language"]
            inner = "".join(self.ast_to_semantic_xml(c) for c in node.get("children", []))
            return f'<code-block id="{node["id"]}" language="{lang}">{inner}</code-block>'

        if node["type"] == "code-block":
            lang = node.get("language", "")
            inner = "".join(self.ast_to_semantic_xml(c) for c in node.get("children", []))
            return f'<code-line id="{node["id"]}" language="{lang}">{inner}</code-line>'

        tag = tag_map.get(node["type"], "div")
        inner = "".join(self.ast_to_semantic_xml(c) for c in node.get("children", []))
        if "id" in node:
            return f'<{tag} id="{node["id"]}">{inner}</{tag}>'
        else:
            return f'<{tag}>{inner}</{tag}>'
