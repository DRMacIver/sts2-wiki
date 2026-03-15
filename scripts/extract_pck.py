#!/usr/bin/env python3
"""Extract files from a Godot 4 PCK file."""

import argparse
import os
import struct


def extract_pck(pck_path: str, output_dir: str, filter_prefix: str | None = None) -> None:
    with open(pck_path, "rb") as f:
        magic = f.read(4)
        assert magic == b"GDPC", f"Bad magic: {magic!r}"

        fmt_version = struct.unpack("<I", f.read(4))[0]
        engine_major = struct.unpack("<I", f.read(4))[0]
        engine_minor = struct.unpack("<I", f.read(4))[0]
        engine_patch = struct.unpack("<I", f.read(4))[0]
        _pack_flags = struct.unpack("<I", f.read(4))[0]
        file_base = struct.unpack("<Q", f.read(8))[0]

        print(f"PCK format version: {fmt_version}")
        print(f"Engine: {engine_major}.{engine_minor}.{engine_patch}")

        if fmt_version >= 3:
            directory_offset = struct.unpack("<Q", f.read(8))[0]

        # Read reserved (16 x uint32 = 64 bytes)
        f.read(64)

        # For V3/V4, seek to directory offset
        if fmt_version >= 3:
            f.seek(directory_offset)

        file_count = struct.unpack("<I", f.read(4))[0]
        print(f"File count: {file_count}")

        entries = []
        for _ in range(file_count):
            path_len = struct.unpack("<I", f.read(4))[0]
            path_bytes = f.read(path_len)
            path = path_bytes.rstrip(b"\x00").decode("utf-8")

            offset = struct.unpack("<q", f.read(8))[0]
            size = struct.unpack("<q", f.read(8))[0]
            _md5 = f.read(16)
            _flags = struct.unpack("<I", f.read(4))[0]

            entries.append((path, offset, size))

        extracted = 0
        for path, offset, size in entries:
            if filter_prefix and not path.startswith(filter_prefix):
                continue

            actual_offset = file_base + offset
            out_path = os.path.join(output_dir, path.replace("res://", ""))
            os.makedirs(os.path.dirname(out_path), exist_ok=True)

            pos = f.tell()
            f.seek(actual_offset)
            data = f.read(size)
            f.seek(pos)

            with open(out_path, "wb") as out:
                out.write(data)
            extracted += 1

        print(f"Extracted {extracted} files")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract files from a Godot 4 PCK file")
    parser.add_argument("pck_path", help="Path to the .pck file")
    parser.add_argument("output_dir", help="Output directory")
    parser.add_argument("--prefix", help="Only extract files with this path prefix")
    args = parser.parse_args()

    extract_pck(args.pck_path, args.output_dir, args.prefix)


if __name__ == "__main__":
    main()
