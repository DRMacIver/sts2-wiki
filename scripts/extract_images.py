#!/usr/bin/env python3
"""Extract and decode images from Godot PCK file for the STS2 wiki.

Handles .ctex files (Godot CompressedTexture2D) containing WebP or S3TC data.
Splits texture atlases into individual sprites using .tpsheet metadata.
"""

import argparse
import io
import json
import os
import struct
from pathlib import Path

import texture2ddecoder
from PIL import Image


def decode_ctex(data: bytes) -> Image.Image | None:
    """Decode a Godot .ctex file to a PIL Image.

    The .ctex format (Godot 4 CompressedTexture2D) has:
    - Optional metadata preamble before GST2
    - GST2 header: magic(4) + version(4) + width(4) + height(4) + flags(4) = 20 bytes
    - For lossless/lossy: additional fields then WebP/PNG data at offset 56
    - For VRAM compressed (BPTC/S3TC): mipmap table then block data at offset 52
    """
    gst2_idx = data.find(b"GST2")
    if gst2_idx < 0:
        return None

    header = data[gst2_idx:]
    if len(header) < 56:
        return None

    width = struct.unpack_from("<I", header, 8)[0]
    height = struct.unpack_from("<I", header, 12)[0]

    # Check for WebP/PNG at known offset (56 bytes from GST2)
    container_data = header[56:]
    if container_data[:4] == b"RIFF" and len(container_data) > 12:
        try:
            return Image.open(io.BytesIO(container_data)).convert("RGBA")
        except Exception:
            pass

    if container_data[:8] == b"\x89PNG\r\n\x1a\n":
        try:
            return Image.open(io.BytesIO(container_data)).convert("RGBA")
        except Exception:
            pass

    # Block-compressed formats — data starts at offset 52 for VRAM textures
    # The image format enum is at offset 48 (22 = BPTC_RGBA, 17 = DXT1, 19 = DXT5)
    img_format = struct.unpack_from("<I", header, 48)[0] if len(header) > 52 else 0
    block_data = header[52:]

    expected_blocks = ((width + 3) // 4) * ((height + 3) // 4)
    expected_16byte = expected_blocks * 16
    expected_8byte = expected_blocks * 8

    # Pad if slightly short (last few bytes may be missing)
    if len(block_data) < expected_16byte and len(block_data) >= expected_16byte - 16:
        block_data = block_data + b"\x00" * (expected_16byte - len(block_data))

    # BC7 (BPTC_RGBA = format 22)
    if img_format == 22 and len(block_data) >= expected_16byte:
        try:
            raw = texture2ddecoder.decode_bc7(block_data[:expected_16byte], width, height)
            return Image.frombytes("RGBA", (width, height), raw, "raw", "BGRA")
        except Exception:
            pass

    # BC3 (DXT5 = format 19)
    if img_format in (19, 0) and len(block_data) >= expected_16byte:
        try:
            raw = texture2ddecoder.decode_bc3(block_data[:expected_16byte], width, height)
            return Image.frombytes("RGBA", (width, height), raw, "raw", "BGRA")
        except Exception:
            pass

    # BC1 (DXT1 = format 17)
    if img_format in (17, 0) and len(block_data) >= expected_8byte:
        try:
            raw = texture2ddecoder.decode_bc1(block_data[:expected_8byte], width, height)
            return Image.frombytes("RGBA", (width, height), raw, "raw", "BGRA")
        except Exception:
            pass

    # Fallback: try all decoders regardless of format field
    for decoder, size in [
        (texture2ddecoder.decode_bc7, expected_16byte),
        (texture2ddecoder.decode_bc3, expected_16byte),
        (texture2ddecoder.decode_bc1, expected_8byte),
    ]:
        if len(block_data) >= size:
            try:
                raw = decoder(block_data[:size], width, height)
                return Image.frombytes("RGBA", (width, height), raw, "raw", "BGRA")
            except Exception:
                pass

    return None


def extract_atlas_sprites(
    atlas_image: Image.Image,
    tpsheet_path: str,
    output_dir: str,
) -> int:
    """Split an atlas image into individual sprites using .tpsheet metadata."""
    with open(tpsheet_path) as f:
        tpsheet = json.load(f)

    count = 0
    for texture in tpsheet.get("textures", []):
        for sprite in texture.get("sprites", []):
            filename = sprite["filename"]
            region = sprite["region"]
            margin = sprite.get("margin", {"x": 0, "y": 0, "w": 0, "h": 0})

            x, y = region["x"], region["y"]
            w, h = region["w"], region["h"]

            # Crop from atlas
            cropped = atlas_image.crop((x, y, x + w, y + h))

            # Apply margin (add padding back)
            if margin.get("x") or margin.get("y") or margin.get("w") or margin.get("h"):
                full_w = w + margin.get("x", 0) + margin.get("w", 0)
                full_h = h + margin.get("y", 0) + margin.get("h", 0)
                full = Image.new("RGBA", (full_w, full_h), (0, 0, 0, 0))
                full.paste(cropped, (margin.get("x", 0), margin.get("y", 0)))
                cropped = full

            # Save
            out_name = os.path.splitext(filename)[0] + ".png"
            out_path = os.path.join(output_dir, out_name)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            cropped.save(out_path, "PNG")
            count += 1

    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract images from Godot PCK")
    parser.add_argument("pck_path", help="Path to the .pck file")
    parser.add_argument("extracted_dir", help="Directory with extracted atlas metadata")
    parser.add_argument("output_dir", help="Output directory for images")
    parser.add_argument(
        "--atlases",
        nargs="*",
        default=["power_atlas", "relic_atlas", "potion_atlas", "intent_atlas"],
        help="Atlas names to extract",
    )
    args = parser.parse_args()

    pck_path = os.path.expanduser(args.pck_path)
    extracted_dir = args.extracted_dir
    output_dir = args.output_dir
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Read PCK file index
    pck_index: dict[str, tuple[int, int]] = {}
    with open(pck_path, "rb") as f:
        magic = f.read(4)
        assert magic == b"GDPC", f"Bad magic: {magic!r}"
        fmt_version = struct.unpack("<I", f.read(4))[0]
        f.read(16)  # engine info + flags
        file_base = struct.unpack("<Q", f.read(8))[0]
        if fmt_version >= 3:
            directory_offset = struct.unpack("<Q", f.read(8))[0]
        else:
            directory_offset = 0
        f.read(64)  # reserved
        if fmt_version >= 3:
            f.seek(directory_offset)
        file_count = struct.unpack("<I", f.read(4))[0]

        for _ in range(file_count):
            path_len = struct.unpack("<I", f.read(4))[0]
            path = f.read(path_len).rstrip(b"\x00").decode("utf-8")
            offset = struct.unpack("<q", f.read(8))[0]
            size = struct.unpack("<q", f.read(8))[0]
            f.read(16 + 4)  # md5 + flags
            pck_index[path] = (file_base + offset, size)

    def read_pck_file(path: str) -> bytes | None:
        if path not in pck_index:
            return None
        offset, size = pck_index[path]
        with open(pck_path, "rb") as f:
            f.seek(offset)
            return f.read(size)

    total = 0
    for atlas_name in args.atlases:
        tpsheet_path = os.path.join(extracted_dir, "images", "atlases", f"{atlas_name}.tpsheet")
        if not os.path.exists(tpsheet_path):
            print(f"  Skipping {atlas_name}: no .tpsheet found")
            continue

        # Find the .ctex file in PCK for this atlas
        # Try multiple possible paths
        ctex_path = None
        for pck_file_path in pck_index:
            if atlas_name in pck_file_path and pck_file_path.endswith(".ctex"):
                ctex_path = pck_file_path
                break

        if not ctex_path:
            print(f"  Skipping {atlas_name}: no .ctex found in PCK")
            continue

        print(f"  Decoding {atlas_name} from {ctex_path}...")
        ctex_data = read_pck_file(ctex_path)
        if not ctex_data:
            print(f"  ERROR: Could not read {ctex_path}")
            continue

        atlas_image = decode_ctex(ctex_data)
        if not atlas_image:
            print(f"  ERROR: Could not decode {ctex_path}")
            continue

        print(f"  Atlas size: {atlas_image.width}x{atlas_image.height}")

        atlas_output = os.path.join(output_dir, atlas_name)
        count = extract_atlas_sprites(atlas_image, tpsheet_path, atlas_output)
        print(f"  Extracted {count} sprites from {atlas_name}")
        total += count

    # Also extract individual card portrait images if available
    card_portrait_dir = os.path.join(output_dir, "card_portraits")
    Path(card_portrait_dir).mkdir(parents=True, exist_ok=True)
    portrait_count = 0
    for pck_file_path, (offset, size) in pck_index.items():
        if "card_portrait" in pck_file_path and pck_file_path.endswith(".ctex"):
            ctex_data = read_pck_file(pck_file_path)
            if ctex_data:
                img = decode_ctex(ctex_data)
                if img:
                    # Extract filename from path
                    base = os.path.basename(pck_file_path)
                    # Remove hash suffix: name.png-hash.ctex -> name.png
                    name = base.split("-")[0] if "-" in base else base
                    name = name.removesuffix(".ctex").removesuffix(".png") + ".png"
                    img.save(os.path.join(card_portrait_dir, name), "PNG")
                    portrait_count += 1

    if portrait_count:
        print(f"  Extracted {portrait_count} card portraits")
        total += portrait_count

    print(f"\nTotal: {total} images extracted to {output_dir}")


if __name__ == "__main__":
    main()
