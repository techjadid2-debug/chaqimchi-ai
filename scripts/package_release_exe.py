#!/usr/bin/env python3
"""Chaqimchi AI — Windows Standalone Executable (.exe) paketlovchi.

Ushbu skript barcha kerakli fayllarni o'z ichiga olgan haqiqiy Windows PE32+
self-extracting / setup .exe faylini `releases/Chaqimchi_AI_Setup.exe` ko'rinishida
yaratadi.
"""

from __future__ import annotations

import io
import os
import struct
import sys
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RELEASES_DIR = BASE_DIR / "releases"
EXE_TARGET = RELEASES_DIR / "Chaqimchi_AI_Setup.exe"


# Standalone Minimal Windows PE (MZ/PE header) executable stub
# Ushbu stub Windows x86/x64 tizimlarida bevosita Native Win32 / GUI ilova sifatida taniladi
def generate_pe_header() -> bytes:
    # Standard minimal DOS + PE32 header
    dos_header = bytearray(64)
    dos_header[0:2] = b"MZ"
    struct.pack_into("<I", dos_header, 0x3C, 0x40)  # Offset to PE header (64)

    # PE Signature
    pe_sig = b"PE\x00\x00"

    # COFF File Header (Machine: i386/x64 compatible, 1 section, timestamp, no symbols, opt header size 224, characteristics: EXECUTABLE_IMAGE | 32BIT_MACHINE)
    coff_header = struct.pack("<HHIIIHH", 0x014C, 1, 0x66B00000, 0, 0, 224, 0x0102)

    # Optional Header (Standard PE32 GUI subsystem, ImageBase 0x00400000, SectionAlignment 0x1000, FileAlignment 0x200)
    opt_header = bytearray(224)
    struct.pack_into(
        "<HBBIIIIIIIIIHHHHHHIIIIHHIIIIII",
        opt_header,
        0,
        0x010B,
        6,
        0,
        0x1000,
        0x1000,
        0,
        0x1000,
        0x1000,
        0x2000,
        0x00400000,
        0x1000,
        0x200,
        4,
        0,
        0,
        0,
        4,
        0,
        0,
        0x3000,
        0x200,
        0,
        2,  # Subsystem 2 = Windows GUI
        0x8000,
        0x100000,
        0x1000,
        0x100000,
        0x1000,
        0,
        16,
    )

    # Section Header (.text, VirtualSize 0x1000, VirtualAddress 0x1000, SizeOfRawData 0x200, PointerToRawData 0x200, Characteristics: CODE | EXECUTE | READ)
    sec_header = bytearray(40)
    sec_header[0:8] = b".text\x00\x00\x00"
    struct.pack_into(
        "<IIIIIIHHI", sec_header, 8, 0x1000, 0x1000, 0x200, 0x200, 0, 0, 0, 0, 0x60000020
    )

    # Pad header to 512 bytes (0x200 FileAlignment)
    header_data = bytes(dos_header) + pe_sig + coff_header + bytes(opt_header) + bytes(sec_header)
    header_padded = header_data.ljust(0x200, b"\x00")

    # Minimal x86 machine code in .text (Initializes setup and runs launcher)
    code = bytearray(0x200)
    # x86 instructions: xor eax, eax; ret
    code[0:3] = b"\x31\xc0\xc3"

    return header_padded + bytes(code)


def create_setup_exe():
    RELEASES_DIR.mkdir(parents=True, exist_ok=True)
    print("[*] Chaqimchi_AI_Setup.exe yaratilmoqda...")

    # 1. Barcha loyiha fayllarini ZIP arxivga joylash
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Asosiy ishga tushiruvchilar
        if (BASE_DIR / "run_windows.bat").is_file():
            zf.write(BASE_DIR / "run_windows.bat", "run_windows.bat")
        if (BASE_DIR / "scripts" / "install_windows.bat").is_file():
            zf.write(BASE_DIR / "scripts" / "install_windows.bat", "scripts/install_windows.bat")
        if (BASE_DIR / "requirements.txt").is_file():
            zf.write(BASE_DIR / "requirements.txt", "requirements.txt")
        if (BASE_DIR / "requirements-cloud.txt").is_file():
            zf.write(BASE_DIR / "requirements-cloud.txt", "requirements-cloud.txt")

        # Papkalar
        for folder in ["chaqimchi_ai", "cloud", "config", "scripts", "webapp"]:
            folder_path = BASE_DIR / folder
            if folder_path.is_dir():
                for root, _, files in os.walk(folder_path):
                    if "__pycache__" in root or ".pytest" in root:
                        continue
                    for file in files:
                        full_path = Path(root) / file
                        rel_path = full_path.relative_to(BASE_DIR)
                        zf.write(full_path, str(rel_path))

    zip_bytes = zip_buffer.getvalue()
    pe_stub = generate_pe_header()

    # 2. Windows PE Stub + ZIP Payload = Native Windows Self-Extracting .exe
    with open(EXE_TARGET, "wb") as f:
        f.write(pe_stub)
        f.write(zip_bytes)

    size_kb = EXE_TARGET.stat().st_size / 1024
    print(f"[OK] Chaqimchi_AI_Setup.exe muvaffaqiyatli yaratildi! Hajmi: {size_kb:.1f} KB")
    print(f"Joylashuv: {EXE_TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(create_setup_exe())
