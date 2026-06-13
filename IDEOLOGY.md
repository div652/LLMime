# LLMime Project Ideology
## The Philosophy of Continuous Context and Living Specifications

### 1. Code is Transient, Context is Eternal
In modern software engineering, code changes rapidly. Features are added, refactored, or discarded. However, the **architectural context**—why decisions were made, what experiments failed, and how the underlying protocols work—is the most valuable asset of a repository.

This project is built under a strict belief: **Documentation is code.** If the specifications are not updated when the implementation pivots, the project begins to accumulate *conceptual debt*. Conceptual debt is harder to debug than technical debt; it leads to future engineers (or AI agents) wasting time repeating the same failed experiments.

---

### 2. The Habit of Real-Time Specification Updates
Whenever a major architectural pivot occurs:
1. **Update the specs first (or immediately after validation):** Never let the code drift from the specifications. The moment we discovered Notion could not be supported via simple HTML injection, the product requirements and technical specs were updated to record that limitation and explain why.
2. **Document the failures explicitly:** In software, a failed attempt is a data point. Our technical specifications document our post-mortems (like the failure of KaTeX visual HTML rendering and Notion hydration barriers) in detail so that no one tries to rebuild the failed v1/v2 architectures.
3. **Ensure seamless handoffs:** A repository should be in a state where a new developer, a peer, or an AI agent can clone the repo, read the documents, and immediately understand the entire design space, implementation state, and next steps without needing to guess.

---

### 3. The Self-Learning / Self-Documenting Concept
We operate in an era where AI agents and humans pair program. AI models have context window limitations (compaction, truncation). 
* Detailed technical specifications act as the **"external RAM"** for the project.
* By structuring specs with precise failure modes, schemas, and diagnostics, we enable agents and developers to reload the project context instantly.
* This "self-learning" feedback loop ensures that the repository remains self-documenting and resilient to context loss.

---

### 4. Guidelines for Future Maintainers
If you are taking over this repository:
* **Commit to the Specs:** If you implement a table parser or integrate Wayland support, update `TECHNICAL_SPEC_V2.md` and `LLM_to_Notion_Product_Overview.md` to reflect your changes before concluding your work.
* **Keep the Specs Honest:** If you find a bug, a new failure mode, or a limitation, add it to the "Known Limitations" section. Do not sweep architectural shortcuts under the rug.
* **Keep it Clean:** Maintain simple, self-explanatory file naming and file hierarchy.
