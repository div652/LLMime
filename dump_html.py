import sys
from PyQt6.QtWidgets import QApplication

app = QApplication(sys.argv)
mime = app.clipboard().mimeData()

print("============= NOTION HTML DUMP =============")

if mime.hasHtml():
    print(mime.html())
else:
    print("❌ No HTML found in clipboard.")

print("\n============= NOTION TEXT DUMP =============")
if mime.hasText():
    print(mime.text())

print("============================================")
app.quit()
