#!/usr/bin/env python3
"""Generate test_cases/size_2/ — pixel-inverted copies of test_cases/size_1/."""
from pathlib import Path
from PIL import Image, ImageOps

src = Path(__file__).parent.parent / "test_cases" / "size_1"
dst = Path(__file__).parent.parent / "test_cases" / "size_2"
dst.mkdir(exist_ok=True)

images = sorted(src.glob("*.jpg"))
for img_path in images:
    inverted = ImageOps.invert(Image.open(img_path).convert("L"))
    out_path = dst / img_path.name
    inverted.save(out_path, quality=95)
    print(f"  {img_path.name}")
print(f"Done: {len(images)} images → {dst}")
