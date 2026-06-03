"""
Auto-calibration tool: detects digit anchor positions from a directory of images.

Hybrid approach:
  - Digit x-band positions: averaged from individual images (columns don't merge)
  - Segment y-positions: from pixel-wise MAX of center strips (aggregates all
    frames so every horizontal segment position appears at least once)

Handles displays where the upper digit row is partially visible at the top.

Usage:
    python tools/calibrate.py test_cases/size_4
    python tools/calibrate.py test_cases/size_4 --debug
    python tools/calibrate.py test_cases/size_4 --y-start 200
    python tools/calibrate.py test_cases/size_4 --threshold 120
"""

import argparse
import fnmatch
import sys
from pathlib import Path

from PIL import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_bands(profile, min_gap=5, min_width=8, threshold_frac=0.15):
    """Contiguous bright bands in 1-D profile. Returns [(start, end), ...]."""
    if not profile or max(profile) == 0:
        return []
    thresh = max(profile) * threshold_frac
    in_band, bands, start = False, [], 0
    for i, v in enumerate(profile):
        if not in_band and v > thresh:
            in_band, start = True, i
        elif in_band and v <= thresh:
            in_band = False
            if i - start >= min_width:
                bands.append((start, i - 1))
    if in_band and len(profile) - start >= min_width:
        bands.append((start, len(profile) - 1))
    merged = []
    for b in bands:
        if merged and b[0] - merged[-1][1] <= min_gap:
            merged[-1] = (merged[-1][0], b[1])
        else:
            merged.append(list(b))
    return [tuple(b) for b in merged]


def band_center(start, end):
    return (start + end) // 2


def find_peaks(profile, window=15, min_relative_prominence=0.10, search_range=80):
    """
    Find local maxima in 1-D raw brightness profile.

    window: half-width of local-max check (peak must be highest in ±window)
    min_relative_prominence: peak must rise this fraction above the higher of its
        two surrounding valley minima (relative to global max)
    search_range: how far left/right to search for valley minima

    Returns sorted list of peak y indices.
    """
    n = len(profile)
    if not profile or max(profile) == 0:
        return []
    maxv = max(profile)
    candidates = []
    for i in range(window, n - window):
        if profile[i] == max(profile[max(0, i - window):i + window + 1]):
            left_min = min(profile[max(0, i - search_range):i + 1])
            right_min = min(profile[i:min(n, i + search_range)])
            prominence = (profile[i] - max(left_min, right_min)) / maxv
            if prominence >= min_relative_prominence:
                candidates.append((i, profile[i]))
    # Deduplicate: multiple candidates within window → keep highest
    peaks = []
    for i, v in candidates:
        if peaks and i - peaks[-1] < window:
            if v > profile[peaks[-1]]:
                peaks[-1] = i
        else:
            peaks.append(i)
    return peaks


def find_lower_row_start(row_sum, min_gap_height=8, dark_frac=0.12):
    """Find y where lower display row starts (after gap between rows)."""
    if not row_sum or max(row_sum) == 0:
        return 0
    thresh = max(row_sum) * dark_frac
    in_gap, gaps, start = False, [], 0
    for y, v in enumerate(row_sum):
        if not in_gap and v < thresh:
            in_gap, start = True, y
        elif in_gap and v >= thresh:
            in_gap = False
            if y - start >= min_gap_height:
                gaps.append((start, y - 1))
    if not gaps:
        return 0
    return max(gaps, key=lambda g: g[1] - g[0])[1] + 1


def load_mask(path, threshold):
    try:
        img = Image.open(path).convert("L")
    except Exception:
        return None, 0, 0
    pixels = img.load()
    w, h = img.size
    mask = [[1 if pixels[x, y] > threshold else 0 for x in range(w)]
            for y in range(h)]
    return mask, w, h


# ---------------------------------------------------------------------------
# Step 1: collect digit x-band positions from individual images
# ---------------------------------------------------------------------------

def detect_col_bands_single(mask, w, h, n_digits):
    col_sum = [sum(mask[y][x] for y in range(h)) for x in range(w)]
    bands = find_bands(col_sum, min_gap=8, min_width=20, threshold_frac=0.2)
    if len(bands) < n_digits:
        return None
    if len(bands) > n_digits:
        bands = sorted(bands, key=lambda b: b[1] - b[0], reverse=True)[:n_digits]
        bands = sorted(bands, key=lambda b: b[0])
    return bands


def average_col_bands(all_bands):
    """Average x-band positions from multiple successful detections."""
    n = len(all_bands)
    n_digits = len(all_bands[0])
    result = []
    for d in range(n_digits):
        x0 = round(sum(b[d][0] for b in all_bands) / n)
        x1 = round(sum(b[d][1] for b in all_bands) / n)
        result.append((x0, x1))
    return result


# ---------------------------------------------------------------------------
# Step 2: build per-digit center-strip MAX across all images
# ---------------------------------------------------------------------------

def build_center_strip_max(images, col_bands, w, h):
    """
    For each digit, build a per-row MAX brightness value using only
    the center strip of that digit's x-band.

    Returns: list of n_digits raw brightness profiles (int 0-255, length h each).
    """
    n_digits = len(col_bands)
    strip_maxes = [[-1] * h for _ in range(n_digits)]

    for p in images:
        try:
            img = Image.open(p).convert("L")
        except Exception:
            continue
        pixels = img.load()
        iw, ih = img.size
        if iw != w or ih != h:
            continue

        for d, (cx0, cx1) in enumerate(col_bands):
            ax_center = (cx0 + cx1) // 2
            strip_half = max(4, (cx1 - cx0) // 6)
            sx0 = max(0, ax_center - strip_half)
            sx1 = min(w - 1, ax_center + strip_half)
            strip_width = sx1 - sx0 + 1

            for y in range(h):
                row_sum = sum(pixels[x, y] for x in range(sx0, sx1 + 1))
                avg = row_sum // strip_width
                if avg > strip_maxes[d][y]:
                    strip_maxes[d][y] = avg

    # Replace sentinel -1 with 0 (rows not covered by any image)
    return [[max(0, v) for v in profile] for profile in strip_maxes]


# ---------------------------------------------------------------------------
# Step 3: find y-positions from aggregated center-strip profiles
# ---------------------------------------------------------------------------

def detect_y_positions(strip_maxes, col_bands, w, h, y_start, debug=False):
    """
    Returns list of n_digits dicts: {"ax", "ay", "dy", "bx"} or None.
    Uses center-strip MAX raw brightness profiles for ay/gy detection;
    dy (bottom segment) is derived as dy = 2*gy - ay.
    """
    results = []
    for d, (cx0, cx1) in enumerate(col_bands):
        ax_center = (cx0 + cx1) // 2
        row_profile = strip_maxes[d]

        local_profile = row_profile[y_start:]
        peaks = find_peaks(local_profile, window=15, min_relative_prominence=0.10,
                           search_range=80)

        if debug:
            full_coords = [p + y_start for p in peaks]
            strip_half = max(4, (cx1 - cx0) // 6)
            sx0 = max(0, ax_center - strip_half)
            sx1 = min(w - 1, ax_center + strip_half)
            print(f"  digit {d} x=[{cx0},{cx1}] strip=[{sx0},{sx1}]: "
                  f"peaks={full_coords}")

        if len(peaks) < 2:
            print(f"  Digit {d}: {len(peaks)} peaks found (need ≥2)")
            return None

        # Sort by y-position: peaks[0]=segment a (top), peaks[1]=segment g (middle)
        peaks_sorted = sorted(peaks)
        ay = peaks_sorted[0] + y_start
        gy = peaks_sorted[1] + y_start
        dy = 2 * gy - ay  # derive bottom segment d = 2g - a

        if debug:
            print(f"    -> ax={ax_center} ay={ay} gy={gy} dy={dy}")

        results.append({"ax": ax_center, "ay": ay, "dy": dy, "bx": None})

    return results


def detect_bx_from_images(images, threshold, col_bands, results, w, h):
    """
    Detect bx (rightmost bright x in right half of digit between ay and gy)
    using pixel-wise MAX across all images for the bx scan region.
    """
    n_digits = len(col_bands)
    # Build partial MAX for bx region per digit
    for d, (cx0, cx1) in enumerate(col_bands):
        ay = results[d]["ay"]
        gy = (ay + results[d]["dy"]) // 2  # middle segment y = (a + d) / 2
        ax_center = (cx0 + cx1) // 2

        y_top = max(0, ay - 15)
        y_bot = min(h - 1, gy + 15)
        x_start = ax_center

        col_maxes = [-1] * (cx1 - x_start + 1)
        for p in images:
            try:
                img = Image.open(p).convert("L")
            except Exception:
                continue
            pixels = img.load()
            for xi, x in enumerate(range(x_start, cx1 + 1)):
                col_sum = sum(pixels[x, y] for y in range(y_top, y_bot + 1))
                if col_sum > col_maxes[xi]:
                    col_maxes[xi] = col_sum

        bright_thresh = max(col_maxes) * 0.35 if max(col_maxes) > 0 else 0
        bx = x_start
        for xi, v in enumerate(col_maxes):
            if v > bright_thresh:
                bx = x_start + xi
        results[d]["bx"] = bx

    return results


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_yaml(anchors, label=""):
    if label:
        print(f"# Calibrated for {label}")
    print("digits:")
    for a in anchors:
        print(f"  - a: [{a['ax']}, {a['ay']}]")
        print(f"    d: [{a['ax']}, {a['dy']}]")
        print(f"    b: {a['bx']}")


def print_python(anchors, label=""):
    if label:
        print(f"# Calibrated for {label}")
    print("DIGIT_ANCHORS = [")
    for a in anchors:
        print(f'    {{"a": ({a["ax"]}, {a["ay"]}), '
              f'"d": ({a["ax"]}, {a["dy"]}), "bx": {a["bx"]}}},')
    print("]")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Auto-calibrate digit anchor positions from a directory of images.",
    )
    parser.add_argument("image_dir", help="Directory with .jpg images")
    parser.add_argument("--threshold", type=int, default=150)
    parser.add_argument("--y-start", type=int, default=None,
                        help="Override auto-detected lower-row start y")
    parser.add_argument("--skip", nargs="*",
                        default=["off*.jpg", "off*.JPG", "kreski.jpg"])
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    img_dir = Path(args.image_dir)
    if not img_dir.is_dir():
        print(f"Not a directory: {img_dir}"); sys.exit(1)

    all_images = sorted(img_dir.glob("*.jpg")) + sorted(img_dir.glob("*.JPG"))

    def skip(p):
        return any(fnmatch.fnmatch(p.name, pat) for pat in (args.skip or []))

    images = [p for p in all_images if not skip(p)]
    if not images:
        print("No images found"); sys.exit(1)

    print(f"Processing {len(images)} images from {img_dir}")
    print(f"Threshold={args.threshold} | "
          f"y-start={'auto' if args.y_start is None else args.y_start}\n")

    # --- Probe one image for dimensions ---
    probe_mask, w, h = load_mask(images[0], args.threshold)
    if probe_mask is None:
        print("Cannot load first image"); sys.exit(1)

    # --- Step 1: collect x-bands from individual images ---
    n_digits = 4
    all_col_bands = []
    for p in images:
        mask, iw, ih = load_mask(p, args.threshold)
        if mask is None or iw != w or ih != h:
            continue
        bands = detect_col_bands_single(mask, w, h, n_digits)
        if bands:
            all_col_bands.append(bands)

    if not all_col_bands:
        print("Could not detect 4 digit columns in any image")
        sys.exit(1)

    col_bands = average_col_bands(all_col_bands)
    if args.debug:
        print(f"Averaged col_bands from {len(all_col_bands)} images: {col_bands}")

    # --- Step 2: y_start from first good mask ---
    if args.y_start is not None:
        y_start = args.y_start
    else:
        full_row = [sum(probe_mask[y][x] for x in range(w)) for y in range(h)]
        y_start = find_lower_row_start(full_row)
    if args.debug:
        print(f"y_start={y_start}\n")

    # --- Step 3: center-strip MAX row profiles (raw brightness) ---
    strip_maxes = build_center_strip_max(images, col_bands, w, h)

    # --- Step 4: detect y-positions via peak detection ---
    results = detect_y_positions(strip_maxes, col_bands, w, h, y_start, debug=args.debug)
    if results is None:
        print("\nCalibration failed. Try --threshold, --y-start, or --debug")
        sys.exit(1)

    # --- Step 5: detect bx ---
    results = detect_bx_from_images(images, args.threshold, col_bands, results, w, h)

    print()
    print("=" * 52)
    print("config.yaml / ESPHome  (paste into digits: section)")
    print("=" * 52)
    print_yaml(results, label=str(img_dir))

    print()
    print("=" * 52)
    print("Python  (paste into DIGIT_ANCHORS in test file)")
    print("=" * 52)
    print_python(results, label=str(img_dir))


if __name__ == "__main__":
    main()
