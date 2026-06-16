"""
Windows clipboard inspector (native Win32, no Qt).

The Linux ``dump_electron.py`` reads formats through Qt, which on Windows
re-maps clipboard formats and hides their true registered names. This tool
enumerates the clipboard using the raw Win32 API so you can see exactly what a
real app put there.

Usage
-----
1. In Slite (Windows desktop / Electron), select a block with an equation or a
   code block and press Ctrl+C.
2. Run:  py dump_clipboard_win.py
3. Confirm a format named "Chromium Web Custom MIME Data Format" appears, and
   that its payload contains the "application/x-slite-global" /
   "application/x-slite-semantic-xml" keys. That name is what
   ``daemon_windows.py`` writes to.

This is the honest verification step the project ideology calls for: prove the
format name on the real machine instead of trusting an assumption.
"""

import win32clipboard

# Standard formats we don't need to dump in detail.
STANDARD = {
    1: "CF_TEXT", 2: "CF_BITMAP", 3: "CF_METAFILEPICT", 4: "CF_SYLK",
    5: "CF_DIF", 6: "CF_TIFF", 7: "CF_OEMTEXT", 8: "CF_DIB", 9: "CF_PALETTE",
    13: "CF_UNICODETEXT", 15: "CF_HDROP", 16: "CF_LOCALE", 17: "CF_DIBV5",
}


def format_name(fmt: int) -> str:
    if fmt in STANDARD:
        return STANDARD[fmt]
    try:
        name = win32clipboard.GetClipboardFormatName(fmt)
        return name if name else f"<unnamed #{fmt}>"
    except Exception:
        return f"<unnamed #{fmt}>"


def extract_strings(raw: bytes, min_len: int = 3):
    """Pull readable UTF-16LE-ish snippets out of a binary blob."""
    out, cur = [], bytearray()
    for b in raw:
        if 32 <= b <= 126 or b > 127:
            cur.append(b)
        elif b == 0:
            continue  # skip the high byte of ASCII UTF-16LE
        else:
            if len(cur) >= min_len:
                s = bytes(cur).decode("utf-8", errors="ignore").strip()
                if s:
                    out.append(s)
            cur = bytearray()
    if len(cur) >= min_len:
        s = bytes(cur).decode("utf-8", errors="ignore").strip()
        if s:
            out.append(s)
    return out


def main():
    win32clipboard.OpenClipboard()
    try:
        print("============= CLIPBOARD FORMATS (native Win32) =============")
        formats = []
        fmt = win32clipboard.EnumClipboardFormats(0)
        while fmt:
            formats.append(fmt)
            fmt = win32clipboard.EnumClipboardFormats(fmt)

        for f in formats:
            print(f"- [{f}] {format_name(f)}")

        print("\n============= CUSTOM PAYLOAD DUMP =============")
        for f in formats:
            name = format_name(f)
            if name in ("CF_UNICODETEXT", "CF_TEXT", "CF_OEMTEXT", "CF_LOCALE",
                        "CF_BITMAP", "CF_DIB", "CF_DIBV5"):
                continue
            try:
                data = win32clipboard.GetClipboardData(f)
            except Exception as e:
                print(f"\n>>> {name}: <could not read: {e}>")
                continue
            if isinstance(data, str):
                print(f"\n>>> {name} (text, {len(data)} chars)")
                print(data[:500])
                continue
            raw = bytes(data) if data is not None else b""
            print(f"\n>>> {name} ({len(raw)} bytes)")
            for i, s in enumerate(extract_strings(raw)[:30]):
                print(f"[{i}] {s[:200]}")
    finally:
        win32clipboard.CloseClipboard()
    print("\n===========================================================")


if __name__ == "__main__":
    main()
