from daemon import MarkdownToHTMLCompiler

def test_compiler():
    compiler = MarkdownToHTMLCompiler()
    
    # Test block math
    text_math = "Here is an equation:\n$$E = mc^2$$\nWow!"
    res_math = compiler.compile(text_math)
    assert '<div class="notion-text-equation-block" data-macro="E = mc^2">$$E = mc^2$$</div>' in res_math, f"Math failed: {res_math}"
    
    # Test inline math
    text_inline = "This is inline $O(N)$ time."
    res_inline = compiler.compile(text_inline)
    assert '<span class="notion-inline-math" data-macro="O(N)">$O(N)$</span>' in res_inline, f"Inline match failed: {res_inline}"
    
    # Test mermaid
    text_mermaid = "```mermaid\ngraph TD;\nA-->B;\n```"
    res_mermaid = compiler.compile(text_mermaid)
    assert '<pre><code class="language-mermaid">\ngraph TD;\nA-->B;\n</code></pre>' in res_mermaid, f"Mermaid failed: {res_mermaid}"

    print("All compiler tests passed locally!")

if __name__ == "__main__":
    test_compiler()
