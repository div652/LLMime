import markdown
import xml.etree.ElementTree as ET
import re
import uuid
import json

def gen_id():
    return uuid.uuid4().hex[:14]

def gen_key():
    return f"_{uuid.uuid4().hex[:3]}"

class MarkdownToSlateCompiler:
    def __init__(self):
        self.inline_math_map = {}
        
    def compile(self, text: str) -> dict:
        slate_ast = {"fragment": {"children": []}, "data": {}}
        
        block_tokens = re.split(r'\$\$(.*?)\$\$', text, flags=re.DOTALL)
        for i, block_part in enumerate(block_tokens):
            if i % 2 == 1:
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
                if not block_part.strip():
                    continue
                self.inline_math_map.clear()
                
                def hide_math(m):
                    idx = len(self.inline_math_map)
                    key = f"MATHPLACEHOLDER{idx}END"
                    self.inline_math_map[key] = m.group(1)
                    return key
                    
                protected_text = re.sub(r'(?<!\$)\$([^$\n]+?)\$(?!\$)', hide_math, block_part)
                html = markdown.markdown(protected_text, extensions=['fenced_code', 'tables'])
                root = ET.fromstring(f"<div>{html}</div>")
                
                for child in root:
                    ast_nodes = self.parse_block(child)
                    slate_ast["fragment"]["children"].extend(ast_nodes)
                    
        return slate_ast

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
        # If the li contains <p> tags (complex list), flatten it
        for child in li_node:
            children.extend(self.parse_inline(child))
            if child.tail:
                children.extend(self.process_text(child.tail, {}))
        
        # also process direct text in the li
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
        
        children = []
        if node.text:
            children.extend(self.process_text(node.text, marks))
            
        for child in node:
            child_marks = marks.copy()
            if child.tag in ['strong', 'b']:
                child_marks['bold'] = True
            elif child.tag in ['em', 'i']:
                child_marks['italic'] = True
            elif child.tag == 'code':
                child_marks['code'] = True
                
            children.extend(self.parse_inline(child, child_marks))
            
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

c = MarkdownToSlateCompiler()
test_text = """## The Mathematical Equation
Let a training sample consist of a prompt sequence $X$ and a target response sequence $Y$:

* **Prompt tokens:** $X = (x_1, x_2, \\dots)$ of length $n$.
* **Response tokens:** $Y = (y_1, y_2, \\dots)$ of length $m$.

$$
W = (w_1, w_2, \\dots)
$$

Here is a Python code block:

```python
import torch
import torch.nn as nn

# 1. Define the network
model = nn.Sequential(
    nn.Linear(2, 4),  # Input 2, Hidden 4
    nn.ReLU(),
    nn.Linear(4, 1)   # Hidden 4, Output 1
)
```
"""
ast = c.compile(test_text)
print(json.dumps(ast, indent=2))
print("\n=== SEMANTIC XML ===")
for node in ast["fragment"]["children"]:
    print(c.ast_to_semantic_xml(node))
