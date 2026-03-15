#!/usr/bin/env python3
"""Extract and decode images from Godot PCK file for the STS2 wiki.

Handles .ctex files (Godot CompressedTexture2D) containing WebP or S3TC data.
Splits texture atlases into individual sprites using .tpsheet metadata.
"""

import argparse
import io
import json
import logging
import os
import struct
from pathlib import Path

import texture2ddecoder
from PIL import Image

logger = logging.getLogger(__name__)


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
            logger.warning("Failed to decode WebP data (%dx%d)", width, height)
            return None

    if container_data[:8] == b"\x89PNG\r\n\x1a\n":
        try:
            return Image.open(io.BytesIO(container_data)).convert("RGBA")
        except Exception:
            logger.warning("Failed to decode PNG data (%dx%d)", width, height)
            return None

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

    # Try format-specific decoder first
    decoders: list[tuple[str, object, int]] = []
    if img_format == 22:
        decoders.append(("BC7", texture2ddecoder.decode_bc7, expected_16byte))
    elif img_format == 19:
        decoders.append(("BC3", texture2ddecoder.decode_bc3, expected_16byte))
    elif img_format == 17:
        decoders.append(("BC1", texture2ddecoder.decode_bc1, expected_8byte))

    # Fallback: try all decoders if format unknown
    if not decoders:
        decoders = [
            ("BC7", texture2ddecoder.decode_bc7, expected_16byte),
            ("BC3", texture2ddecoder.decode_bc3, expected_16byte),
            ("BC1", texture2ddecoder.decode_bc1, expected_8byte),
        ]

    last_err: Exception | None = None
    for _name, decoder, size in decoders:
        if len(block_data) < size:
            continue
        try:
            raw = decoder(block_data[:size], width, height)  # type: ignore[operator]
            return Image.frombytes("RGBA", (width, height), raw, "raw", "BGRA")
        except Exception as e:
            last_err = e

    if last_err:
        logger.warning(
            "Failed to decode block-compressed texture (%dx%d, format=%d): %s",
            width,
            height,
            img_format,
            last_err,
        )
    return None


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

        # Load tpsheet to find all texture image names
        with open(tpsheet_path) as tf:
            tpsheet = json.load(tf)

        atlas_output = os.path.join(output_dir, atlas_name)

        # Process each texture in the tpsheet
        atlas_total = 0
        for texture in tpsheet.get("textures", []):
            tex_image_name = texture["image"]  # e.g., "card_atlas_0.png"
            tex_base = os.path.splitext(tex_image_name)[0]  # "card_atlas_0"

            # Find the .ctex file for this specific texture image
            ctex_path = None
            for pck_file_path in pck_index:
                if tex_base in pck_file_path and pck_file_path.endswith(".ctex"):
                    ctex_path = pck_file_path
                    break

            if not ctex_path:
                print(f"  Skipping {tex_image_name}: no .ctex found in PCK")
                continue

            print(f"  Decoding {tex_image_name} from {ctex_path}...")
            ctex_data = read_pck_file(ctex_path)
            if not ctex_data:
                print(f"  ERROR: Could not read {ctex_path}")
                continue

            atlas_image = decode_ctex(ctex_data)
            if not atlas_image:
                print(f"  ERROR: Could not decode {ctex_path}")
                continue

            print(f"  Atlas size: {atlas_image.width}x{atlas_image.height}")

            # Extract sprites from this specific texture
            count = 0
            for sprite in texture.get("sprites", []):
                filename = sprite["filename"]
                region = sprite["region"]
                margin = sprite.get("margin", {"x": 0, "y": 0, "w": 0, "h": 0})

                x, y = region["x"], region["y"]
                w, h = region["w"], region["h"]

                cropped = atlas_image.crop((x, y, x + w, y + h))

                if margin.get("x") or margin.get("y") or margin.get("w") or margin.get("h"):
                    full_w = w + margin.get("x", 0) + margin.get("w", 0)
                    full_h = h + margin.get("y", 0) + margin.get("h", 0)
                    full = Image.new("RGBA", (full_w, full_h), (0, 0, 0, 0))
                    full.paste(cropped, (margin.get("x", 0), margin.get("y", 0)))
                    cropped = full

                out_name = os.path.splitext(filename)[0] + ".png"
                out_path = os.path.join(atlas_output, out_name)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                cropped.save(out_path, "PNG")
                count += 1

            print(f"  Extracted {count} sprites from {tex_image_name}")
            atlas_total += count

        print(f"  Total for {atlas_name}: {atlas_total} sprites")
        total += atlas_total
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
