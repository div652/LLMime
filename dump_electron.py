import sys
from PyQt6.QtWidgets import QApplication

app = QApplication(sys.argv)
mime = app.clipboard().mimeData()

print("============= CLIPBOARD FORMATS =============")
formats = mime.formats()
for f in formats:
    print(f"- {f}")

print("\n============= CUSTOM PAYLOAD DUMP =============")

ignore_list = [
    'text/plain', 'text/html', 'UTF8_STRING', 'STRING', 'TEXT', 
    'TARGETS', 'MULTIPLE', 'TIMESTAMP', 'SAVE_TARGETS', 
    'chromium/x-internal-source-rfh-token', 'chromium/x-source-url', 
    'text/plain;charset=utf-8'
]

for f in formats:
    if f in ignore_list:
        continue
    
    print(f"\n>>> DUMPING FORMAT: {f}")
    data = mime.data(f)
    raw_bytes = data.data()
    
    print(f"Total Bytes: {len(raw_bytes)}")
    
    strings = []
    current_str = b''
    for b in raw_bytes:
        # Include basic ASCII and extended bytes
        if 32 <= b <= 126 or b > 127: 
            current_str += bytes([b])
        elif b == 0:
            pass # ignore nulls for utf-16
        else:
            if len(current_str) >= 3:
                try:
                    s = current_str.decode('utf-8', errors='ignore')
                    if s.strip():
                        strings.append(s.strip())
                except Exception:
                    pass
            current_str = b''
            
    if len(current_str) >= 3:
        try:
            s = current_str.decode('utf-8', errors='ignore')
            if s.strip():
                strings.append(s.strip())
        except Exception:
            pass
            
    # Print up to 30 snippets found
    for idx, s in enumerate(strings[:30]):
        print(f"[{idx}] {s}")
    
    if len(strings) == 0:
        print("(No decipherable text/json found in this binary format)")

print("\n==========================================================")
app.quit()
