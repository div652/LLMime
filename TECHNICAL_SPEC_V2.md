# LLMime — Technical Specification v2 (Revised)
## Native AST Clipboard Injection Bridge for Slite

### 1. Architectural Pivot & Problem Space
LLM outputs contain raw Markdown with LaTeX equations (`$$...$$`, `$...$`), code blocks, lists, and headings. When copy-pasted into rich text editors like **Slite**, these render as literal plaintext symbols instead of formatted equations and blocks.

Initially (in v1/v2), the project attempted to solve this by pre-rendering LaTeX into styled HTML spans via KaTeX and writing a generic `text/html` payload to the clipboard. This approach was a **failure mode**:
* Pre-rendered KaTeX HTML equations pasted into editors as static rich-text spans. The editor's editor state did not recognize them as equations, making them **completely uneditable** after paste.
* Notion and Slite stripped or ignored mock equation tags (e.g., `class="notion-text-equation-block"` or Slite's custom tags) because they only instantiate native blocks from their own internal data structures during paste.

**The Pivot:** We shifted to **Native SlateJS AST Clipboard Injection**. Rather than generating HTML, the daemon parses LLM Markdown directly into Slite's proprietary SlateJS Abstract Syntax Tree (AST) format, compiles this AST into Slite's custom binary clipboard format (`chromium/x-web-custom-data`), and writes it to the OS clipboard. This makes pasted content immediately native and editable.

---

### 2. Comprehensive Failure Modes & Challenges Faced

#### Failure Mode 1: Static HTML Pre-Rendering
* **Symptom:** paste worked visually, but equations behaved as plain text styled with CSS. Double-clicking or selecting them did not open the editor's math dialog.
* **Root Cause:** KaTeX converts LaTeX into pure styled HTML spans. Productivity apps treat pasted HTML as static rich text. The application's React state was unaware of the underlying LaTeX code.
* **Resolution:** Abandoned KaTeX HTML pre-rendering. Replaced with native Slite AST generation.

#### Failure Mode 2: Notion React Hydration Barrier
* **Symptom:** Attempts to inject HTML structures matching Notion's DOM structure failed. Notion pasted nothing or fallback plain text.
* **Root Cause:** Notion uses a complex client-side editor framework that validates input against its schema. It does not allow random HTML structure mappings. Without reverse-engineering Notion's private web custom data payload (which is heavily obfuscated), injecting native equations is impossible.
* **Resolution:** Notion support is **currently paused**. The project focuses entirely on Slite, where the custom clipboard protocol was successfully reverse-engineered.

#### Failure Mode 3: Markdown Parser vs. LaTeX Token Conflict
* **Symptom:** Equations containing underscores (e.g. `x_i`), asterisks (e.g. `a * b`), or backslashes had their characters stripped or wrapped in formatting tags like `<em>` or `<strong>` by the Python `markdown` library.
* **Root Cause:** Standard Markdown libraries parse formatting characters indiscriminately, corrupting math equations before they are processed.
* **Resolution:** Implemented a **Token Shielding Parser**. Block math (`$$...$$`) is extracted early and mapped directly to SlateJS `formula` nodes. Inline math (`$...$`) is temporarily replaced with alphanumeric placeholders (e.g., `MATHPLACEHOLDER0END`). The remaining plain text is parsed as Markdown, converted to an XML element tree, and the placeholders are restored to native `inline-formula` AST nodes during structural traversal.

#### Failure Mode 4: SlateJS Parent-Child Schema Constraints
* **Symptom:** Slite threw console warnings, discarded elements, or formatted them on separate lines.
* **Root Cause:** SlateJS enforces rigid node hierarchies.
  * An `inline-formula` must be a child of an `unstyled` block (equivalent to a paragraph `<p>`), sitting alongside text nodes.
  * A block math `formula` must be a top-level block node containing a list of `formula-line` child blocks, which in turn contain text nodes.
* **Resolution:** Designed a strict hierarchical translator in `daemon.py` that separates inline text processing from top-level block processing.

#### Failure Mode 5: PyInstaller Silent Deploy Aborts
* **Symptom:** Modified code in `daemon.py` was not appearing in the running systemd daemon.
* **Root Cause:** The `build.sh` script chained commands using `&&`: `pyinstaller ... && pkill daemon && systemctl --user restart llm-bridge.service`. If the daemon was not already running, `pkill` exited with code 1, aborting the build chain before restarting the systemd service.
* **Resolution:** Decoupled commands in `build.sh` to allow execution even when no previous process is running.

---

### 3. The Final Correct Implementation (v3)

The daemon runs silently in the background. It intercepts the clipboard via `PyQt6` and checks if the text contains mathematical delimiters (`$$` or `$`) and does not already contain a native Slite format.

```
┌────────────────────────────────────────────────────────┐
│               LLMime AST Injection Pipeline            │
│                                                        │
│  Ctrl+C →  Read text/plain                             │
│         →  Shield inline math delimiters               │
│         →  Parse markdown to HTML element tree         │
│         →  Map HTML elements to SlateJS AST nodes      │
│         →  Re-inject math into SlateJS formula nodes   │
│         →  Generate matching Slite Semantic XML        │
│         →  Pack to custom Chromium binary buffer       │
│         →  Update clipboard with custom MIME format    │
│  Ctrl+V →  Slite reads native AST, fully editable!     │
└────────────────────────────────────────────────────────┘
```

#### 3.1 The Slite Clipboard Binary Protocol
Slite uses the standard Chromium clipboard format `chromium/x-web-custom-data`. Under the hood, this is a binary blob structured as follows:

| Offset (Bytes) | Type | Value / Purpose |
|---|---|---|
| `0 - 3` | `uint32` | Size of the following payload |
| `4 - 7` | `uint32` | Number of dictionary entries (we write `2`) |
| `8 - 11` | `uint32` | Length of Key 1 string |
| `12 - N` | `utf-16le` | Key 1 ("application/x-slite-global") |
| `...` | `padding` | Padded to 4-byte boundaries |
| `...` | `uint32` | Length of Value 1 string |
| `...` | `utf-16le` | Value 1 (JSON AST string) |
| `...` | `padding` | Padded to 4-byte boundaries |
| `...` | `uint32` | Length of Key 2 string |
| `...` | `utf-16le` | Key 2 ("application/x-slite-semantic-xml") |
| `...` | `padding` | Padded to 4-byte boundaries |
| `...` | `uint32` | Length of Value 2 string |
| `...` | `utf-16le` | Value 2 (Semantic XML representation) |
| `...` | `padding` | Padded to 4-byte boundaries |

We package this using Python's `struct` module:
```python
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
```

#### 3.2 AST Structures

**A. Block Formula Node:**
```json
{
  "type": "formula",
  "id": "random_14_char_id",
  "key": "_abc",
  "children": [
    {
      "type": "formula-line",
      "id": "random_14_char_id",
      "key": "_def",
      "children": [{"text": "E = mc^2", "key": "_ghi"}]
    }
  ]
}
```

**B. Inline Formula Node (Nested within Paragraph/Header):**
```json
{
  "type": "unstyled",
  "id": "random_14_char_id",
  "key": "_jkl",
  "children": [
    {"text": "Let ", "key": "_mno"},
    {
      "formula": "x",
      "id": "random_14_char_id",
      "type": "inline-formula",
      "children": [{"text": "", "key": "_pqr"}],
      "key": "_stu"
    },
    {"text": " be a real number.", "key": "_vwx"}
  ]
}
```

---

### 4. Known Limitations
1. **Wayland Support:** Standard PyQt clipboard monitors can fail to read/write under strict Wayland policies. The current version expects an X11 session or XWayland fallback.
2. **Notion Incompatibility:** As detailed in Section 2, Notion does not support simple HTML or SlateJS AST clipboard injection.
3. **Partial Delimiters:** If a user copies text with a single open `$$` but no matching closing pair, it will either fail to match or parse incorrectly.
4. **Table Formatting:** While the HTML compiler handles basic tables, the conversion from HTML tables to Slite's custom Table SlateJS AST has not been implemented (tables will currently fall back to unstyled paragraphs or code blocks).

---

### 5. Future Expansion & Next Steps
If you or another developer want to improve this project further, consider these tasks:

#### Task 1: Implement Table AST Mapping
* **Goal:** Support Markdown tables (`| Col 1 | Col 2 |`) by mapping them to Slite's native Table AST components rather than letting them collapse into unstyled text.
* **Pointers:** Inspect a copied Slite table payload using `dump_electron.py` to identify the Table, Table Row, and Table Cell schemas.

#### Task 2: Integrate Mermaid.js Diagrams
* **Goal:** Automatically compile ` ```mermaid ` blocks into Slite's native Diagram AST components.
* **Pointers:** Slite supports visual diagram components. Check how diagram states are stored in the AST (often a specialized block type containing raw Mermaid code strings).

#### Task 3: Support Wayland watch via CLI
* **Goal:** Eliminate the PyQt X11 clipboard dependency for Wayland systems.
* **Pointers:** Use `wl-paste --watch` as an input stream, and write output payloads back using `wl-copy`.

#### Task 4: Reverse-engineer Notion's native clipboard structure
* **Goal:** Restore Notion support.
* **Pointers:** Run `dump_electron.py` or inspect Notion's native desktop application clipboard formats while copying different block types to see if Notion utilizes a custom application key format.
