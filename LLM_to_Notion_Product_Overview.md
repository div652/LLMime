# Project Overview: LLM-to-Slite Universal Clipboard Bridge

> [!NOTE]
> **Notion Support Status:** This project originally aimed to support both Notion and Slite via universal HTML pre-rendering. However, because Notion handles equations using an interactive React component tree that does not hydrate from pasted HTML blocks (rendering them instead as uneditable static text or stripping them entirely), **Notion is currently not supported**. The project has pivoted to focus exclusively on **Slite** by reverse-engineering Slite's native binary clipboard format.

---

## 1. The Problem Space
Modern Large Language Models (LLMs) like Gemini, ChatGPT, and Claude natively output highly structured technical formats—most notably LaTeX for mathematical equations and Markdown for styling.

However, modern engineering wikis and note-taking applications (such as Slite and Notion) use abstract, block-based JSON data models rather than raw Markdown files. When a user attempts to copy an LLM's response and paste it into Slite, the result is severely degraded:
* Block and inline LaTeX (e.g., `$$E=mc^2$$` or `$x$`) paste as literal raw strings.
* The user is forced to manually wrap strings in equation triggers, creating a high-friction, tedious workflow.
* Pasting pre-rendered HTML (e.g. from KaTeX) renders equations as static visual elements that are completely uneditable by the user.

LLM output:
![What LLM outputs](LLM_output.png)

What appears when directly pasted in Slite:
![What appears when directly pasted in Slite](slite_bad.png)

What it should look like (properly rendered and fully editable inline/block equations):
![What it should look like](slite_good.png)

Existing solutions in the market are inadequate. Browser extensions are rigidly tied to specific web domains (ignoring desktop LLM apps) and often require multi-step keyboard shortcuts to activate. API-based sync tools force data into specific databases rather than allowing contextual, in-line pasting.

---

## 2. The Solution Vision: Native AST Injection
We have built **LLMime**, a frictionless, native desktop daemon that intercepts the user's system clipboard. When it detects raw LLM Markdown containing mathematical structures (`$$` or `$`), it compiles those text tokens directly into Slite's native SlateJS Abstract Syntax Tree (AST) structure, packs it into Slite's proprietary binary clipboard payload, and writes it back to the clipboard memory buffer.

When the user pastes into Slite, the editor reads the high-fidelity custom data payload (`chromium/x-web-custom-data`), instantly rendering the content as native, fully editable paragraph text, headings, lists, block equations, and inline math.

---

## 3. Intended Use Case & User Experience
**The Goal:** Zero additional clicks. Zero custom shortcuts. The system operates entirely invisibly.

**The Workflow:**
1. The user asks Gemini to explain a machine learning formula or list steps.
2. The model outputs a response rich with math and formatting.
3. The user highlights the text and presses `Ctrl + C`.
4. *Under the hood (in < 50ms):* The daemon intercepts the markdown buffer, parses the technical delimiters, compiles Slite SlateJS AST, packages the binary clipboard format, and updates the OS clipboard.
5. The user switches to their Slite workspace and presses `Ctrl + V`.
6. Equations instantly render as native, editable math blocks and inline formulas.

---

## 4. Platform Strategy: Linux First
The rollout strategy prioritizes **Linux** for V1.0, followed by macOS, and finally Windows.
Linux provides direct, unabstracted access to clipboard subsystems (X11 `xclip` / Wayland `wl-clipboard`), allowing us to establish the core MIME type binding with minimal overhead. Once the single-pass parser is optimized on Linux, cross-platform UI abstraction (via PyQt or native API wrappers) will be introduced for macOS and Windows deployment.

---

## 5. Scope & Feature Roadmap

### V1.0 Targets (The "High Friction" Core)
The first iteration aggressively targets technical documentation transfer for Slite:
1. **Block LaTeX Equations:** `$$...$$` to native Slite `formula` blocks.
2. **Inline LaTeX Spans:** `$...$` to native Slite `inline-formula` spans inside paragraph blocks.
3. **Core Markdown:** Headings (`#`), bolding (`**`), italics (`*`), and standard nested lists mapped to native SlateJS AST nodes.
4. **Code Syntax Blocks:** Standard ` ``` ` fences mapped to code formatting in SlateJS.

### V2.0+ (Future Directions)
Once the clipboard bridge is stable, future formats will include:
* **Mermaid.js Diagrams:** Mapping ` ```mermaid ` fences to native Slite visual diagram nodes.
* **Complex Data Grids:** Parsing GitHub Flavored Markdown (GFM) pipe-tables into rich table blocks.
* **Notion Support (Re-evaluation):** Reverse-engineering Notion's native desktop or web-based custom clipboard format (similar to Slite's custom Chromium clipboard MIME data) to allow native Notion block injection.
