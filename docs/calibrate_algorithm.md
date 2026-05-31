# calibrate.py — stan prac i TODO

## Co robi narzędzie

`tools/calibrate.py` — auto-kalibracja pozycji segmentów z katalogu zdjęć.
Wyjście: gotowe wartości `digits:` do `config.yaml` i `DIGIT_ANCHORS` do pliku testowego.

## Problem z size_4

Obrazy size_4 (800x600) są **bardzo rozmyte i prześwietlone**. Segmenty nie mają
ciemnych przerw między sobą — glow/bloom wypełnia całą cyfrę.

### Obserwacje z analizy pikseli

Center strip (środkowe 30% szerokości cyfry) dla cyfry "8" w capture(3).jpg:
- Peak 1: y≈287, brightness≈255 → segment **a** (górny poziomy)
- Trough: y≈363, brightness≈69 (27% max) — NIE spada do 0!
- Peak 2: y≈406, brightness≈229 → segment **g** (środkowy poziomy)
- Trough: y≈483, brightness≈46 (18% max)
- Peak 3: y≈527, brightness≈149 → segment **d** (dolny poziomy)

Wnioski: Jasność nigdy nie spada wystarczająco nisko między segmentami.
Obecny `find_bands` z `threshold_frac=0.15` scala wszystkie 3 piki w jeden band.

### Dodatkowe problemy

1. **Górny rząd cyfr** widoczny u góry klatki (y=0..~240) zlewa się z segmentem `a`
   dolnego rzędu → `y_start` auto-detekcja działa (≈245), ale sam segment `a` jest
   blisko granicy.

2. **MAX przez wszystkie obrazy** scala kolumny cyfr w jedną kolumnę — nie nadaje
   się do znajdowania x-band pozycji.

3. Hybrydowe podejście (x z indywidualnych obrazów, y z center-strip MAX) jest na
   właściwym tropie — x-bands działają (`col_bands` poprawnie ≈4), ale y detection
   wciąż sypie się przez brak ciemnych przerw.

## TODO: następny krok

Zmienić `detect_y_positions` z **band detection → peak detection**:

```python
def find_peaks(profile, window=10, min_relative_prominence=0.15):
    """
    Find local maxima in 1-D profile.
    min_relative_prominence: peak must be this fraction above the deeper of
    its two surrounding troughs (relative to global max).
    Returns sorted list of peak y indices.
    """
    n = len(profile)
    maxv = max(profile) if profile else 1
    candidates = []
    for i in range(window, n - window):
        if profile[i] == max(profile[max(0,i-window):i+window+1]):
            left_min  = min(profile[max(0, i - 2*window) : i + 1])
            right_min = min(profile[i : min(n, i + 2*window)])
            prominence = (profile[i] - max(left_min, right_min)) / maxv
            if prominence >= min_relative_prominence:
                candidates.append((i, profile[i]))
    # Deduplicate: if multiple candidates within window, keep highest
    peaks = []
    for i, v in candidates:
        if peaks and i - peaks[-1] < window:
            if v > profile[peaks[-1]]:
                peaks[-1] = i
        else:
            peaks.append(i)
    return peaks
```

Zamiast `find_bands(local_profile)` → `find_peaks(local_profile, window=10)`.
Oczekiwane wyniki dla size_4:
- digit 0: peaks ≈ [45, 161, 281] (offset od y_start=245) → ay=290, gy=406, dy=526

## Architektura tools/calibrate.py (obecna)

```
main()
  ├── load images, filter skips
  ├── detect_col_bands_single() per image → average_col_bands()   ← działa
  ├── find_lower_row_start() on first image row profile           ← działa
  ├── build_center_strip_max() → per-digit center-strip MAX mask  ← działa
  ├── detect_y_positions()  ← TU JEST PROBLEM (band→peak fix)
  └── detect_bx_from_images()
```

## Konfiguracje

| setup  | rozdzielczość | ay   | gy  | b_digit0 | plik testowy                   |
|--------|---------------|------|-----|----------|--------------------------------|
| size_2 | 640×480       | 143  | 249 | 140      | tests/test_integration_size2.py |
| size_3 | 800×600       | 230  | 357 | 172      | tests/test_integration_size3.py |
| size_4 | 800×600       | TBD  | TBD | TBD      | tests/test_integration_size4.py |

size_3 wartości = aktualny `config.yaml` (przed zmianą ustawienia kamery).
