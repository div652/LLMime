# Project Overview: LLM-to-Notion Universal Clipboard Bridge

## 1. The Problem Space
Modern Large Language Models (LLMs) like Gemini, ChatGPT, and Claude natively output highly structured technical formats—most notably LaTeX for mathematical equations and Mermaid.js for architectural diagrams. 

However, modern engineering wikis and note-taking applications (such as Notion and Slite) use abstract, block-based JSON data models rather than raw Markdown files. When a user attempts to copy an LLM's response and paste it into Notion, the result is severely degraded:
* Block and inline LaTeX (e.g., `$$E=mc^2$$`) paste as literal raw strings.
* Mermaid diagrams paste as standard text code blocks rather than rendering the native visual flowchart.
* The user is forced to manually wrap strings in `/equation` blocks or `/mermaid` triggers, creating a high-friction, tedious workflow.

LLM output : ![What LLM outputs](LLM_output.png)

What appears when directly pasted in Slite or Notion or Obsidian : ![What appears when directly pasted in Slite or Notion or Obsidian](slite_bad.png)

What it should look like (I had to manually enter latex equations in slite to look it like this currently) : ![What it should look like](slite_good.png)

Existing solutions in the market are inadequate. Browser extensions are rigidly tied to specific web domains (ignoring desktop LLM apps) and often require multi-step keyboard shortcuts to activate. API-based sync tools force data into specific databases rather than allowing contextual, in-line pasting.

## 2. The Solution Vision
We are building a **Universal Clipboard Bridge**. This is a frictionless, native desktop daemon that intercepts the user's system clipboard. When it detects raw LLM Markdown containing technical structures, it instantly compiles those text tokens into an intermediate `text/html` DOM structure and writes it back to the clipboard memory buffer.

When the user pastes into Notion or Slite, the target application reads the rich HTML layer, correctly mapping the semantic tags (like `<div class="notion-text-equation-block">`) into its native block-based database.

## 3. Intended Use Case & User Experience
**The Goal:** Zero additional clicks. Zero custom shortcuts. 
The system operates entirely invisibly.

**The Workflow:**
1. The user asks Gemini to explain the optimal stopping theory or to design a lock-free concurrent queue.
2. The model outputs a response rich with math and Mermaid flowcharts.
3. The user highlights the text and presses `Ctrl + C`.
4. *Under the hood (in < 50ms):* The daemon intercepts the markdown buffer, parses the technical delimiters, compiles HTML, and updates the OS clipboard.
5. The user switches to their Notion or Slite workspace and presses `Ctrl + V`.
6. Equations instantly render as native math blocks, and diagrams appear natively visual.

## 4. Platform Strategy: Linux First
The rollout strategy prioritizes **Linux** for V1.0, followed by macOS, and finally Windows. 
Linux provides direct, unabstracted access to clipboard subsystems (X11 `xclip` / Wayland `wl-clipboard`), allowing us to establish the core dual-format (`text/plain` and `text/html`) memory binding with minimal overhead. Once the single-pass parser is optimized on Linux, cross-platform UI abstraction (via PyQt or native API wrappers) will be introduced for macOS and Windows deployment.

## 5. Scope & Feature Roadmap

### V1.0 Targets (The "High Friction" Core)
The first iteration will aggressively target the most painful elements of technical documentation transfer:
1. **Block LaTeX Equations:** `$$...$$` to native Notion Math Blocks.
2. **Inline LaTeX Spans:** `$...$` to native Notion Inline Math.
3. **Mermaid.js Diagrams:** ` ```mermaid...``` ` to native visual Mermaid blocks.
4. **Code Syntax Blocks:** Standard ` ```cpp ` fences mapped to proper language blocks.
5. **Core Markdown:** Headings (`#`), bolding, and standard nested lists to maintain structural integrity around the math.

### V2.0+ (Future Directions)
Once the clipboard bridge is stable, future formats will include:
* **Graphviz / DOT:** Translation of `DOT` outputs into compatible diagram blocks.
* **Complex Data Grids:** Parsing GitHub Flavored Markdown (GFM) pipe-tables into rich, sortable database blocks.
* **Custom XML UI Layouts:** Mapping LLM "Artifact" outputs (e.g., interactive tabs or grouped layouts) into Notion toggle-lists or multi-column layouts.
