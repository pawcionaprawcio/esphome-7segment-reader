# Lista poprawek do zrobienia

## ✅ [P1] Per-digit max-gap threshold

**Problem:** C++ używa globalnego progu `(min + max) / 2` z 28 sampli wszystkich cyfr.  
**Skutek:** Zawodzi gdy jedna cyfra jest jaśniejsza od innych (nierównomierne oświetlenie).  
**Zrobione:** `max_gap_threshold_()` w `digit_number.cpp` — per-digit, szuka największej przerwy jasności.

---

## ⏳ [P1] Własność bufora kamery — użyj przekazanego `image`

**Problem:** `on_camera_image` ignoruje przekazany parametr i wywołuje `esp_camera_fb_get()` bezpośrednio.  
**Skutek:** Potencjalny konflikt własności buforów; pobrana klatka może być *inna* niż dostarczona przez ESPHome.  
**Odroczone:** Wymaga znajomości wewnętrznego API `camera::CameraImage` (brak w projekcie). Rozwiązanie: użyj `image->get_data_buffer()` / `image->get_width()` / `image->get_height()` zamiast raw ESP-IDF API.

---

## ✅ [P2] Cache geometrii cyfr — przeliczyć raz w `setup()`

**Problem:** `derive_geometry_()` wywoływana dla każdej cyfry na każdej klatce, mimo że kotwice (`digits_`) nigdy się nie zmieniają.  
**Zrobione:** `std::array<DigitGeometry, 4> geometries_` wypełniane w `setup()`.

---

## ✅ [P2] Asynchroniczny retry dashów

**Problem:** Retry `all_dash` działał w ciasnej pętli (`continue`) w obrębie jednego wywołania `process_image_()`.  
**Skutek:** Kamera nie dostarcza innej klatki w ciągu mikrosekund — retry był bezużyteczny.  
**Zrobione:** Usunięta tight loop i `ready_max_retries`. Stan `ready` publikowany natychmiast; kolejna klatka (za `update_interval`) sprawdza ponownie.

---

## ✅ [P3] Fixed arrays zamiast `vector` w hot path

**Problem:** `std::vector<std::array<uint8_t,7>> brightness(num_digits)` i `std::vector<uint8_t> bitmasks(num_digits)` alokowane na stercie przy każdym wywołaniu `process_image_()`.  
**Zrobione:** `std::array<std::array<uint8_t,7>,4>` i `std::array<uint8_t,4>` na stosie.

---

## ✅ [P3] Deduplikacja publikowania stanu

**Problem:** Blok publish pojawiał się 4 razy w `process_image_()`.  
**Zrobione:** Metoda pomocnicza `publish_all_(const char *state)`.

---

## ✅ [P3] Wagi RGB565 → grayscale

**Problem:** `(rv * 30 + gv * 59 + bv * 11) / 100` — dzielenie całkowite, lekko odbiegające od BT.601.  
**Zrobione:** `(77u * rv + 150u * gv + 29u * bv) >> 8` — BT.601, bez dzielenia.

---

## ✅ [P3] Usunąć martwe pola `frame_width` / `frame_height` z schematu

**Problem:** `set_frame_width` i `set_frame_height` to no-opy. Komponent czyta wymiary z `fb->width`/`fb->height`.  
**Zrobione:** Usunięte z `sensor.py` i `.h`. Przy okazji usunięto też `ready_max_retries` (obsolete po async retry).
