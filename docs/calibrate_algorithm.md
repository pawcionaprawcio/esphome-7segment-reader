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

## Zaimplementowana naprawa (2026-06-02)

### Krytyczny błąd w oryginalnym planie

Pierwotne TODO zakładało `find_peaks` na binarnym profilu (0/1). To nic nie dawało —
peak detection na binarnym sygnale = to samo co find_bands.

Rzeczywisty problem: segment **d** ma jasność ≈149, threshold=150 → 149 < 150 → **0 w masce**.
Segment znika z binarnego profilu zanim `find_bands` go zobaczy.

### Właściwa naprawa

`build_center_strip_max` zwraca teraz **raw brightness** (int 0–255), nie binarną maskę.
`detect_y_positions` wywołuje `find_peaks` na surowych wartościach.

```python
def find_peaks(profile, window=15, min_relative_prominence=0.10, search_range=80):
    """
    Find local maxima in 1-D raw brightness profile.
    search_range=80 — sięga do dołków między segmentami (~76px od peaka).
    """
```

Kluczowy parametr: `search_range=80` (nie 2*window=20 jak w oryginalnym planie).
Segmenty są ≈76–77px od siebie — `search_range=20` liczyłby prominence ze zbocza,
nie z dołka, i prominencja byłaby zaniżona (~0.14 < 0.15 → odrzut peaka).

Weryfikacja dla size_4 (dane z doca):
- peak a: 255, trough: 69 → prominence (255−69)/255 = 0.73 ✓
- peak g: 229, trough: 46 → prominence (229−46)/255 = 0.72 ✓
- peak d: 149, trough: 46 → prominence (149−46)/255 = 0.40 ✓

### Zmiana w `detect_y_positions`

Zamiast 3 pasm → ≥2 peaks posortowane po y:
- `peaks_sorted[0]` + y_start → **ay** (segment a, top)
- `peaks_sorted[1]` + y_start → **gy** (segment g, middle)

Nie wymaga 3 peaks (segment d nie jest potrzebny do kalibracji).

## Architektura tools/calibrate.py (aktualna)

```
main()
  ├── load images, filter skips
  ├── detect_col_bands_single() per image → average_col_bands()        ← działa
  ├── find_lower_row_start() on first image row profile                ← działa
  ├── build_center_strip_max() → per-digit center-strip MAX raw [0-255] ← działa
  ├── detect_y_positions() via find_peaks() na raw brightness           ← naprawione
  └── detect_bx_from_images()
```

## Konfiguracje

| setup  | rozdzielczość | ay   | gy  | b_digit0 | plik testowy                   |
|--------|---------------|------|-----|----------|--------------------------------|
| size_2 | 640×480       | 143  | 249 | 140      | tests/test_integration_size2.py |
| size_3 | 800×600       | 230  | 357 | 172      | tests/test_integration_size3.py |
| size_4 | 800×600       | TBD  | TBD | TBD      | tests/test_integration_size4.py |

size_3 wartości = aktualny `config.yaml` (przed zmianą ustawienia kamery).
