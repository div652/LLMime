import sys
import struct
import json
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QMimeData

def write_string16(s: str) -> bytes:
    # Chromium Pickle string packing: 
    # length in characters, then UTF-16LE bytes, then zero-padding to 4-byte boundary
    data = struct.pack('<I', len(s)) + s.encode('utf-16le')
    padding = (4 - (len(data) % 4)) % 4
    data += b'\0' * padding
    return data

def build_web_custom_data(data_dict: dict) -> bytes:
    payload = struct.pack('<I', len(data_dict)) # Count of keys
    for k, v in data_dict.items():
        payload += write_string16(k)
        payload += write_string16(v)
    
    # 4-byte size header prepended to the pickled payload
    return struct.pack('<I', len(payload)) + payload

app = QApplication(sys.argv)
clipboard = app.clipboard()
mime = QMimeData()

# Our synthetic Slite native payload
slate_json = {
    "fragment": {
        "children": [
            {
                "type": "formula",
                "id": "fakeHacker123",
                "key": "_1x1",
                "children": [
                    {
                        "type": "formula-line",
                        "id": "fakeHacker456",
                        "key": "_2x2",
                        "children": [{"text": "E=mc^2", "key": "_3x3"}]
                    }
                ]
            }
        ]
    },
    "data": {}
}

semantic_xml = '<formula id="fakeHacker123"><formula-line id="fakeHacker456">E=mc^2</formula-line></formula>'

custom_dict = {
    "application/x-slite-global": json.dumps(slate_json, separators=(',', ':')),
    "application/x-slite-semantic-xml": semantic_xml
}

raw_bytes = build_web_custom_data(custom_dict)
mime.setData("chromium/x-web-custom-data", raw_bytes)
clipboard.setMimeData(mime)

print("✅ Injected fake Slite block structure into clipboard.")
app.exec()
