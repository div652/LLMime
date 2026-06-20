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

The daemon runs silently in the background. It intercepts the clipboard via `PyQt6` and checks (via `compiler.looks_like_markdown`) whether the copied text carries a **structural Markdown signal** — math (`$$`/`$`), a fenced code block (` ``` `), a Markdown table, an ATX heading (`#`), a list, or `**bold**` — and that it does not already contain a native Slite format. (Originally this gate was math-only, which silently ignored code/tables/headings; see the trigger note below.)

> **Trigger widening (v3.1):** The gate now fires on any of the structural markers above, not just `$`. Ordinary prose is still left untouched because a *structural* marker is required (an inline dash or `@` in a sentence does not match). The detector is OS-independent and lives in `compiler.looks_like_markdown`, so both daemons share it.

> **Code layout note (v3.1):** The OS-independent core — the Markdown→Slite AST compiler (`MarkdownToSlateCompiler`) and the Chromium binary packer (`build_web_custom_data`) — was extracted into `compiler.py`. Both the Linux daemon (`daemon.py`) and the Windows daemon (`daemon_windows.py`) import it verbatim, so the two platforms can never drift in how they generate the payload. Only the clipboard *transport* differs per OS (see Section 6).

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

### 6. Windows Support (v3.1)

The original v3 daemon targeted Linux/X11. Windows feature parity is provided by `daemon_windows.py`, which reuses the exact same compiler and binary payload but uses a different clipboard *transport*.

#### 6.1 Why a Separate Transport Was Necessary (Failure Mode 6)
* **Symptom:** Writing `QMimeData.setData("chromium/x-web-custom-data", payload)` via PyQt6 on Windows produced a clipboard entry that Slite (Electron) **did not recognise** on paste — it behaved exactly like the pre-LLMime broken state.
* **Root Cause:** Linux/X11 identifies clipboard formats directly by their MIME-string name, so the atom `chromium/x-web-custom-data` is what Chromium reads. **Windows does not.** The Win32 clipboard is keyed by numeric format IDs registered *by name* via `RegisterClipboardFormat`. Chromium/Electron registers its web custom data under the Windows clipboard format name **`"Chromium Web Custom MIME Data Format"`**, not the MIME string. Qt's Windows clipboard backend wraps arbitrary MIME types under its own naming scheme, so the payload never lands under the name Slite looks up.
* **Resolution:** On Windows we keep PyQt6 only for the **tray icon, the toast, and clipboard monitoring** (UX parity), but perform the clipboard **write through the native Win32 API** (`win32clipboard` from `pywin32`). We `RegisterClipboardFormat("Chromium Web Custom MIME Data Format")` and `SetClipboardData` the *identical* `base::Pickle` bytes the Linux version produces.

#### 6.2 The Windows Write Path
A single `OpenClipboard → EmptyClipboard → SetClipboardData(...) → CloseClipboard` session writes three formats together so they coexist for one paste:
| Format | Source | Purpose |
|---|---|---|
| `CF_UNICODETEXT` | original copied text | plain-text fallback |
| `"HTML Format"` (CF_HTML) | the Markdown library's HTML, wrapped in the CF_HTML offset header | rich-text fallback for non-Slite apps |
| `"Chromium Web Custom MIME Data Format"` | `compiler.build_web_custom_data(...)` | the native, editable Slite payload |

The leading `uint32` size prefix and per-string 4-byte padding from Section 3.1 are byte-for-byte the same on Windows — only the format **name** and the **API used to set it** change.

#### 6.3 Re-entrancy & Native-Source Guard
The Linux daemon used an `is_internal_update` boolean to ignore the clipboard-change event caused by its own write. On Windows, clipboard-update notifications are delivered asynchronously through the message loop, so a boolean flag can race. Instead, `daemon_windows.py` guards with a single content check: **`IsClipboardFormatAvailable("Chromium Web Custom MIME Data Format")`**. If that format is already present, the change is ignored. This elegantly covers *both* cases at once:
1. **Our own write** (the format we just set is present) → skip, no infinite loop.
2. **A genuine copy made inside Slite** (Slite writes that format too) → skip, exactly matching the Linux daemon's original "abort if native Slite copy" intent.

`IsClipboardFormatAvailable` does not require opening the clipboard, so the probe is cheap and cannot deadlock against the source application.

#### 6.4 Verification Performed
* `compiler.py` payload decodes back to the correct AST/semantic-XML (round-trip test).
* `daemon_windows.write_native_clipboard` writes, and a raw Win32 read-back confirms the clipboard carries a format literally named `Chromium Web Custom MIME Data Format`, the text round-trips, and the payload decodes to the expected Slite AST node types.
* End-to-end: with the daemon running, setting clipboard text containing `$$…$$` from a separate process caused the daemon to auto-convert (the Chromium format appeared, containing the freshly copied content).
* **Not yet verified:** an actual paste into the Slite Windows desktop app, because Slite was not installed on the build machine. Use `dump_clipboard_win.py` (copy a Slite block, then run it) to confirm the format name on a machine that has Slite, and to compare Slite's own payload schema against ours.

#### 6.5 Windows Build & Autostart
`build_windows.ps1` creates `venv-win`, installs `requirements-windows.txt` (adds `pywin32`) plus PyInstaller, builds `dist\LLMime.exe` with `--onefile --noconsole`, and registers autostart via a shortcut in the user's Startup folder (`shell:startup`). `dump_clipboard_win.py` is a native Win32 clipboard inspector for diagnostics (the Qt-based `dump_electron.py` hides true Windows format names).

---

### 7. Slite Tables Are Databases (Failure Mode 7)

The original assumption (Limitation 4, v3) was that Slite tables would be a SlateJS `table` node embedded in `application/x-slite-global`. **A real Slite table copy disproves this.**

* **Symptom:** Pasting a Markdown table emitted as a guessed `table` / `table-row` / `table-cell` node caused Slite to reject the **whole** fragment and paste raw Markdown text — even surrounding headings/paragraphs were lost.
* **Root cause (from a real Slite copy, captured with `dump_clipboard_win.py`):** A Slite "table" is a **database**. It is *not* in `application/x-slite-global` at all. Instead it uses two dedicated clipboard keys:
  * `application/x-slite-database-fragment` — the whole grid.
  * `application/x-slite-database-field` — the selection-anchor field/column descriptor.
* **Observed `database-fragment` schema:**
  * `columns`: `{columnKey: {key, name, type, position, data, createdAt, updatedAt, createdBy, updatedBy}}`. Column `type` is one of `text`, `users`, `multi-select`, `todo`, … The first column is the primary "Title" (`type: text`).
  * `records` (rows): `{recordId: {key, position, fields: {columnKey: fieldData}, createdAt, updatedAt, createdBy, updatedBy}}`. The Title column is **absent** from `record.fields`; its value lives only in `content`.
  * `fields`: an ordered `[[recordId, [[columnKey, fieldDataOrNull], …]], …]` projection (Title column entry is `null`).
  * `content`: `{"{recordId}-{columnKey}": {fieldId, recordId, id, type: "database-table-cell", key, children: [<SlateJS blocks: unstyled / unordered-list / …>]}}`. **This is where the rich cell content lives** — so cell text/formatting reuses the same node types we already emit. Text-type columns additionally duplicate a plain `data.text` in `record.fields`.
  * Records/columns carry `createdBy`/`updatedBy` = the author's user id and millisecond `createdAt`/`updatedAt` timestamps.
* **Hard constraint:** A database is a **standalone** clipboard payload (only the `database-*` keys are present, no `x-slite-global`). It therefore **cannot be embedded inline** alongside a heading and paragraphs in a single paste. So a copied LLM answer of "heading + table + prose" cannot become heading + native-table + prose in one shot.
* **Resolution — two paths, by content shape:**
  * **Single-table copy** (the entire selection is one Markdown table): `compiler._build_table_database` generates a native Slite **database** payload — `application/x-slite-database-fragment` (+ `-field` anchor) with one `text` column per Markdown column, one record per body row, and a `database-table-cell` per cell in `content` (reusing the inline pipeline, so `$math$` becomes `inline-formula` inside cells). Column 0 is treated as the primary "Title" column (no `record.fields` entry, content only), matching observed behaviour.
  * **Mixed content** (heading/prose around a table): falls back to flattening the table into valid `unstyled` paragraph rows (cells joined by `|`, header bold, inline math preserved), because a database can't be embedded inline.
* **VERIFIED against a live Slite paste** (Windows, Slite desktop): a single-table copy pastes as a real, editable Slite table/database with inline math intact. Confirmed findings:
  * `createdBy`/`updatedBy` are **not required** — they were omitted (`user_id = None`) and Slite regenerated ownership on paste. So the `user_id` capture idea is unnecessary for tables.
  * The millisecond `createdAt`/`updatedAt` we generate are accepted, and including both `database-fragment` and `database-field` works.

---

### 4. Known Limitations
1. **Wayland Support:** Standard PyQt clipboard monitors can fail to read/write under strict Wayland policies. The Linux daemon (`daemon.py`) expects an X11 session or XWayland fallback. (The Windows daemon is unaffected — it uses the native Win32 clipboard.)
1b. **Slite-on-Windows paste unverified:** The Windows payload, format name, and end-to-end auto-conversion are verified (Section 6.4), but an actual paste into the Slite Windows desktop app has not been confirmed on the build machine (Slite was not installed). Run `dump_clipboard_win.py` against a real Slite copy to validate the schema if a paste ever misbehaves.
2. **Notion Incompatibility:** As detailed in Section 2, Notion does not support simple HTML or SlateJS AST clipboard injection.
3. **Partial Delimiters:** If a user copies text with a single open `$$` but no matching closing pair, it will either fail to match or parse incorrectly.
4. **Mixed-content tables flatten to paragraphs.** A *single-table* copy now pastes as a native, editable Slite database table (Section 7, verified). But because a Slite database is a standalone payload that can't be embedded inline with other blocks, a table copied *together with* surrounding headings/prose is flattened to `unstyled` paragraph rows (cells joined by `|`, header bold, inline math preserved) — readable and safe, but not an editable table. Copy the table on its own to get a native table.

---

### 5. Future Expansion & Next Steps
If you or another developer want to improve this project further, consider these tasks:

#### Task 1: Native database tables — ✅ DONE (single-table copies)
* Implemented in `compiler._build_table_database` and **verified** by a live Slite paste on Windows (Section 7). Single-table copies become real editable Slite tables with inline math; `createdBy`/`updatedBy` proved unnecessary.
* **Remaining nice-to-have:** native tables for *mixed* content (heading + table + prose) are not possible inline because a database is a standalone payload — those still use the flattened-paragraph fallback. No known workaround within Slite's clipboard format.

#### Task 2: Integrate Mermaid.js Diagrams
* **Goal:** Automatically compile ` ```mermaid ` blocks into Slite's native Diagram AST components.
* **Pointers:** Slite supports visual diagram components. Check how diagram states are stored in the AST (often a specialized block type containing raw Mermaid code strings).

#### Task 3: Support Wayland watch via CLI
* **Goal:** Eliminate the PyQt X11 clipboard dependency for Wayland systems.
* **Pointers:** Use `wl-paste --watch` as an input stream, and write output payloads back using `wl-copy`.

#### Task 4: Reverse-engineer Notion's native clipboard structure
* **Goal:** Restore Notion support.
* **Pointers:** Run `dump_electron.py` or inspect Notion's native desktop application clipboard formats while copying different block types to see if Notion utilizes a custom application key format.
