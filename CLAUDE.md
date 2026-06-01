# esphome_digit_number component

ESPHome external component — reads 4-digit 7-segment display via ESP32-CAM, publishes mm integer sensor.

## Wersjonowanie

Patch version podbija się **automatycznie** przy każdym commicie (pre-commit hook w `.githooks/`).

Po sklonowaniu repo aktywuj hook raz:
```bash
git config core.hooksPath .githooks
```

MINOR i MAJOR podbijaj ręcznie w `components/digit_number/digit_number.h`:
```cpp
#define DIGIT_NUMBER_VERSION "X.Y.0"
```
- MINOR: nowa funkcja (np. `set_paused()`, nowy sensor)
- MAJOR: breaking change API/YAML

Wersja loguje się przy starcie (INFO) i co cykl przetwarzania (DEBUG) — pozwala potwierdzić że ESP flashował nowy kod.

## Testy

```bash
cd esphome_digit_number
pip install -r requirements-test.txt
pytest tests/ -v
python tests/validate.py --debug
```

## Struktura

- `components/digit_number/digit_number.h` — klasa + VERSION define
- `components/digit_number/digit_number.cpp` — logika odczytu segmentów
- `components/digit_number/sensor.py` — schemat YAML ESPHome
- `tests/` — pytest
- `test_cases/` — obrazy testowe
