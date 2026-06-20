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
import time
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


# Separator inserted between cells when a Markdown table is flattened to plain
# paragraph rows (see MarkdownToSlateCompiler.parse_table for why).
TABLE_CELL_SEPARATOR = "  |  "

# HTML void elements (no closing tag). Markdown passes raw inline HTML such as
# ``<br>`` straight through, but ElementTree needs well-formed XML, so we
# self-close them (``<br>`` -> ``<br/>``) before parsing. LLM tables commonly
# use ``<br>`` inside cells, which would otherwise break the whole parse.
_VOID_TAGS = "area|base|br|col|embed|hr|img|input|link|meta|param|source|track|wbr"
_VOID_RE = re.compile(rf'<({_VOID_TAGS})((?:\s[^>]*?)?)\s*/?>', re.IGNORECASE)


def self_close_void_tags(html: str) -> str:
    return _VOID_RE.sub(r'<\1\2/>', html)


class MarkdownToSlateCompiler:
    """Converts standard LLM Markdown directly into Slite's binary SlateJS format."""

    def __init__(self):
        self.inline_math_map = {}
        # Optional Slite user id used as createdBy/updatedBy when generating a
        # native database (table). The daemon may set this after learning it
        # from a real Slite copy; if None, those fields are omitted.
        self.user_id = None

    def _shield_inline_math(self, text: str) -> str:
        """Replace inline ``$...$`` math with placeholders so Markdown can't
        mangle it, recording the originals in ``self.inline_math_map`` for
        ``process_text`` to restore as ``inline-formula`` nodes."""
        self.inline_math_map.clear()

        def hide_math(m):
            idx = len(self.inline_math_map)
            key = f"MATHPLACEHOLDER{idx}END"
            self.inline_math_map[key] = m.group(1)
            return key

        return re.sub(r'(?<!\$)\$([^$\n]+?)\$(?!\$)', hide_math, text)

    def compile(self, text: str) -> bytes:
        # Native tables: if the whole copy is a single Markdown table, emit a
        # Slite *database* payload (its own clipboard keys) instead of the AST.
        db_payload = self._try_compile_table_database(text)
        if db_payload is not None:
            return db_payload

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

                protected_text = self._shield_inline_math(block_part)

                # Render to HTML (self-close void tags like <br> so it's valid XML)
                html = self_close_void_tags(markdown.markdown(protected_text, extensions=['fenced_code', 'tables']))

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

    # --- Native Slite table (database) -------------------------------------
    # Slite tables are databases, serialised under their own clipboard keys
    # (application/x-slite-database-fragment / -field), NOT as an x-slite-global
    # node. A database is a *standalone* payload, so this path is taken ONLY
    # when the entire copied selection is a single Markdown table. See
    # TECHNICAL_SPEC_V2.md Section 7 for the reverse-engineered schema.

    def _try_compile_table_database(self, text: str) -> bytes:
        """If ``text`` is exactly one Markdown table, return a Slite database
        payload; otherwise return None so the caller uses the normal AST path."""
        if not _TABLE_RE.search(text) or '$$' in text:
            return None

        protected = self._shield_inline_math(text)
        html = self_close_void_tags(markdown.markdown(protected, extensions=['fenced_code', 'tables']))
        try:
            root = ET.fromstring(f"<div>{html}</div>")
        except Exception:
            return None

        kids = [c for c in root if isinstance(c.tag, str)]
        if len(kids) != 1 or kids[0].tag.lower() != 'table':
            return None

        return self._build_table_database(kids[0])

    @staticmethod
    def _db_key():
        # Slite record/column keys are short opaque ids (e.g. "XPbPH-a9DN").
        return uuid.uuid4().hex[:10]

    def _inline_plaintext(self, inline_nodes) -> str:
        """Flatten inline nodes to a plain string for a column's ``data.text``."""
        out = []
        for n in inline_nodes:
            if "text" in n:
                out.append(n["text"])
            elif n.get("type") == "inline-formula":
                out.append(n.get("formula", ""))
        return "".join(out)

    def _build_table_database(self, table_node) -> bytes:
        now = int(time.time() * 1000)

        # Collect the header cells and the body rows from the <table>.
        header_cells, body_rows = [], []
        for section in list(table_node):
            stag = section.tag.lower() if isinstance(section.tag, str) else ''
            if stag == 'thead':
                for tr in section:
                    if isinstance(tr.tag, str) and tr.tag.lower() == 'tr':
                        header_cells = [c for c in tr if isinstance(c.tag, str) and c.tag.lower() in ('th', 'td')]
                        break
            elif stag == 'tbody':
                for tr in section:
                    if isinstance(tr.tag, str) and tr.tag.lower() == 'tr':
                        body_rows.append([c for c in tr if isinstance(c.tag, str) and c.tag.lower() in ('th', 'td')])
            elif stag == 'tr':
                cells = [c for c in section if isinstance(c.tag, str) and c.tag.lower() in ('th', 'td')]
                if not header_cells:
                    header_cells = cells
                else:
                    body_rows.append(cells)

        if not header_cells:
            return None
        ncols = len(header_cells)

        def _audit(extra=None):
            d = {"createdAt": now, "updatedAt": now}
            if self.user_id:
                d["createdBy"] = self.user_id
                d["updatedBy"] = self.user_id
            if extra:
                d.update(extra)
            return d

        # Columns — column 0 is the primary "Title" column, like Slite.
        col_keys = [self._db_key() for _ in range(ncols)]
        columns = {}
        for j, cell in enumerate(header_cells):
            name = self._inline_plaintext(self.parse_inline(cell)) or f"Column {j + 1}"
            columns[col_keys[j]] = _audit({
                "key": col_keys[j],
                "name": name,
                "type": "text",
                "data": {},
                "position": 2048 * (j + 1),
            })

        records, content, fields_proj = {}, {}, []
        for i, row in enumerate(body_rows):
            rec_key = self._db_key()
            rec_fields = {}
            proj_cells = [[col_keys[0], None]]  # title column carries no field data
            for j in range(ncols):
                cell = row[j] if j < len(row) else None
                inline = self.parse_inline(cell) if cell is not None else [{"text": "", "key": gen_key()}]
                if not inline:
                    inline = [{"text": "", "key": gen_key()}]

                # Rich cell content lives in `content` keyed "{recordId}-{columnKey}".
                content[f"{rec_key}-{col_keys[j]}"] = {
                    "fieldId": col_keys[j],
                    "recordId": rec_key,
                    "id": gen_id(),
                    "type": "database-table-cell",
                    "children": [{
                        "id": gen_id(),
                        "type": "unstyled",
                        "children": inline,
                        "key": gen_key(),
                    }],
                    "key": gen_key(),
                }

                # Non-title text columns also store a flat text value in fields.
                if j > 0:
                    field_data = _audit({
                        "columnKey": col_keys[j],
                        "data": {"text": self._inline_plaintext(inline)},
                    })
                    rec_fields[col_keys[j]] = field_data
                    proj_cells.append([col_keys[j], field_data])

            records[rec_key] = _audit({
                "key": rec_key,
                "fields": rec_fields,
                "position": 2048 * (i + 1),
            })
            fields_proj.append([rec_key, proj_cells])

        fragment = {
            "fields": fields_proj,
            "records": records,
            "columns": columns,
            "content": content,
        }

        custom_dict = {
            "application/x-slite-database-fragment": json.dumps(fragment, separators=(',', ':')),
        }
        # Anchor descriptor (first record + first column), mirroring a real copy.
        if records:
            first_rec = next(iter(records.values()))
            custom_dict["application/x-slite-database-field"] = json.dumps({
                "record": first_rec,
                "column": columns[col_keys[0]],
            }, separators=(',', ':'))

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
        elif tag == 'table':
            return self.parse_table(node)
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

    def parse_table(self, node):
        """Render a Markdown ``<table>`` as a sequence of safe paragraph rows.

        Slite has **no inline table node** — its tables are full *databases*
        (clipboard keys ``application/x-slite-database-*``), which are a
        standalone payload that cannot be embedded inline alongside other blocks
        such as a heading or paragraphs. See TECHNICAL_SPEC_V2.md Section 7.

        Emitting a guessed ``table`` node makes Slite reject the *entire*
        fragment and paste raw text. So instead we flatten the table into valid
        ``unstyled`` paragraphs — one per row, cells joined by ``|`` — which
        paste cleanly and still preserve inline math/bold inside cells. Header
        cells are bolded so the column titles stay distinguishable.

        Returns a *list* of paragraph nodes (one per row).
        """
        paragraphs = []
        for section in list(node):
            sec_tag = section.tag.lower() if isinstance(section.tag, str) else ''
            if sec_tag == 'tr':
                tr_nodes = [section]
            elif sec_tag in ('thead', 'tbody', 'tfoot'):
                tr_nodes = [c for c in section if isinstance(c.tag, str) and c.tag.lower() == 'tr']
            else:
                continue

            for tr in tr_nodes:
                cells = [c for c in tr if isinstance(c.tag, str) and c.tag.lower() in ('td', 'th')]
                row_children = []
                for idx, cell in enumerate(cells):
                    is_header = cell.tag.lower() == 'th'
                    inline = self.parse_inline(cell, {'bold': True} if is_header else None)
                    if idx > 0:
                        row_children.append({"text": TABLE_CELL_SEPARATOR, "key": gen_key()})
                    row_children.extend(inline)
                if not row_children:
                    row_children = [{"text": "", "key": gen_key()}]
                paragraphs.append({
                    "type": "unstyled",
                    "id": gen_id(),
                    "key": gen_key(),
                    "children": row_children,
                })

        if not paragraphs:
            paragraphs.append({
                "type": "unstyled",
                "id": gen_id(),
                "key": gen_key(),
                "children": [{"text": "", "key": gen_key()}],
            })
        return paragraphs

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
