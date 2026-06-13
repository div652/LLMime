import sys
import base64
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QMimeData

# A pre-rendered SVG of E=mc^2
svg_content = """<svg xmlns="http://www.w3.org/2000/svg" width="67.591" height="15.541" viewBox="0 0 17.883 4.112"><g stroke="none" fill="#000"><path d="M4.667 4.111H.76q-.258 0-.356-.056T.263 3.86Q.22 3.737.3 3.298l.608-3.076Q.935.056 1.134.056h3.69q.231 0 .285.086.054.086.021.264l-.064.333q-.033.167-.113.21t-.226.043H1.815q-.086 0-.113.064-.027.065-.054.194l-.161.795h2.524q.215 0 .269.08.054.081.021.264l-.064.323q-.032.172-.113.21t-.225.038H1.364q-.086 0-.113.064-.027.065-.054.194l-.172.935q-.021.118.016.15.038.033.177.033h3.136q.215 0 .269.08.053.081.021.264l-.064.333q-.032.172-.113.21t-.225.038zM8.887 2.16H5.474q-.247 0-.295-.124-.049-.123-.006-.328l.065-.333q.032-.172.107-.21t.226-.038h3.413q.248 0 .296.124.048.123 0 .328l-.064.333q-.033.172-.108.21t-.226.038zm-.397 1.951H5.077q-.247 0-.296-.123-.048-.124-.005-.328l.064-.333q.033-.172.108-.21t.225-.038h3.413q.248 0 .296.124.048.123.006.328l-.065.333q-.032.172-.107.21t-.226.038zM17.883 1.257q0 .408-.236.811t-.742.666q-.29.134-.7.134-.236 0-.322-.053-.086-.054-.086-.183l.032-.247q0-.011.021-.016t.043 0q.419.451 1.053.451.279 0 .43-.177t.15-.553q0-.419-.188-.709t-.634-.484l-.848-.3q-.591-.204-.951-.623t-.36-1.021q0-.397.236-.784T16.519.51Q16.82.387 17.218.387q.193 0 .284.054t.092.193l-.043.258q-.011.021-.032.021t-.043-.01q-.355-.419-1.01-.419-.236 0-.376.166t-.14.526q0 .387.182.682t.613.484l.87.311q.58.205.94.618t.36 1.021z"></path></g></svg>"""

b64_img = base64.b64encode(svg_content.encode('utf-8')).decode('utf-8')
data_uri = f"data:image/svg+xml;base64,{b64_img}"

test_html = f'''<p>Here is an equation rendered as a universal SVG image:</p>
<p><img src="{data_uri}" alt="E=mc^2"/></p>
<p>Does this paste beautifully into Slite?</p>'''

test_plain = "Here is an equation rendered as a universal SVG image:\n\n$$ E=mc^2 $$\n\nDoes this paste beautifully into Slite?"

app = QApplication(sys.argv)
clipboard = app.clipboard()
mime = QMimeData()
mime.setText(test_plain)
mime.setHtml(test_html)

clipboard.setMimeData(mime)
print("✅ SVG Clipboard injected. Try pasting into Slite.")
app.exec()
