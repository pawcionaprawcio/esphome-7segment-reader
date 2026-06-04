#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include "doctest.h"
#include "digit_number/digit_logic.h"

using namespace esphome::digit_number;

// ---- decode_digit ----

TEST_CASE("decode_digit: all 10 exact patterns") {
    CHECK(digit_logic::decode_digit(0b0111111) == 0);
    CHECK(digit_logic::decode_digit(0b0000110) == 1);
    CHECK(digit_logic::decode_digit(0b1011011) == 2);
    CHECK(digit_logic::decode_digit(0b1001111) == 3);
    CHECK(digit_logic::decode_digit(0b1100110) == 4);
    CHECK(digit_logic::decode_digit(0b1101101) == 5);
    CHECK(digit_logic::decode_digit(0b1111101) == 6);
    CHECK(digit_logic::decode_digit(0b0000111) == 7);
    CHECK(digit_logic::decode_digit(0b1111111) == 8);
    CHECK(digit_logic::decode_digit(0b1101111) == 9);
}

TEST_CASE("decode_digit: unknown bitmask returns -1") {
    CHECK(digit_logic::decode_digit(0b0000000) == -1);
    CHECK(digit_logic::decode_digit(0b1010101) == -1);
}

TEST_CASE("decode_digit: DASH_BITMASK returns -1") {
    CHECK(digit_logic::decode_digit(digit_logic::DASH_BITMASK) == -1);
}

TEST_CASE("decode_digit: 1-bit fuzzy match") {
    CHECK(digit_logic::decode_digit(0b0111110) == 0);   // digit 0, bit 0 off
    CHECK(digit_logic::decode_digit(0b1110111) == 8);   // digit 8, bit 3 off
    CHECK(digit_logic::decode_digit(0b0000100) == 1);   // digit 1, bit 1 off
}

// ---- derive_geometry ----

TEST_CASE("derive_geometry: symmetric no tilt") {
    // a=(100,10), d=(100,90), b=(130,30) → g=(100,50), down=(0,40)
    DigitAnchors a{100, 10, 100, 90, 130, 30};
    DigitGeometry geo = digit_logic::derive_geometry(a);
    CHECK(geo.seg[0].x == 100); CHECK(geo.seg[0].y == 10);   // a
    CHECK(geo.seg[1].x == 130); CHECK(geo.seg[1].y == 30);   // b
    CHECK(geo.seg[2].x == 130); CHECK(geo.seg[2].y == 70);   // c = b+(0,40)
    CHECK(geo.seg[3].x == 100); CHECK(geo.seg[3].y == 90);   // d
    CHECK(geo.seg[4].x == 70);  CHECK(geo.seg[4].y == 70);   // e = a+d-b
    CHECK(geo.seg[5].x == 70);  CHECK(geo.seg[5].y == 30);   // f = a+g-b
    CHECK(geo.seg[6].x == 100); CHECK(geo.seg[6].y == 50);   // g = midpoint a,d
}

TEST_CASE("derive_geometry: tilted display") {
    // a=(100,10), d=(120,90), b=(140,32) → g=(110,50), down=(10,40)
    DigitAnchors a{100, 10, 120, 90, 140, 32};
    DigitGeometry geo = digit_logic::derive_geometry(a);
    CHECK(geo.seg[2].x == 150); CHECK(geo.seg[2].y == 72);   // c = b+(10,40)
    CHECK(geo.seg[3].x == 120); CHECK(geo.seg[3].y == 90);   // d
    CHECK(geo.seg[4].x == 80);  CHECK(geo.seg[4].y == 68);   // e = a+d-b
    CHECK(geo.seg[5].x == 70);  CHECK(geo.seg[5].y == 28);   // f = a+g-b
    CHECK(geo.seg[6].x == 110); CHECK(geo.seg[6].y == 50);   // g
}

TEST_CASE("derive_geometry: seg[6] is midpoint of seg[0] and seg[3]") {
    DigitAnchors a{200, 20, 200, 100, 240, 40};
    DigitGeometry geo = digit_logic::derive_geometry(a);
    CHECK(geo.seg[6].x == (geo.seg[0].x + geo.seg[3].x) / 2);
    CHECK(geo.seg[6].y == (geo.seg[0].y + geo.seg[3].y) / 2);
}

// ---- sample_brightness GRAY ----

TEST_CASE("sample_brightness GRAY: single pixel radius=0") {
    uint8_t buf[1] = {128};
    CHECK(digit_logic::sample_brightness(buf, 1, 1, PixFmt::GRAY, 0, 0, 0) == 128);
}

TEST_CASE("sample_brightness GRAY: 3x3 average radius=1") {
    // all=10 except center(1,1)=100 → avg=(8*10+100)/9=180/9=20
    uint8_t buf[9] = {10, 10, 10, 10, 100, 10, 10, 10, 10};
    CHECK(digit_logic::sample_brightness(buf, 3, 3, PixFmt::GRAY, 1, 1, 1) == 20);
}

TEST_CASE("sample_brightness GRAY: boundary clamp at corner") {
    // 5x5 all=60, corner (0,0) radius=2 → only valid pixels sampled, avg still 60
    uint8_t buf[25];
    for (int i = 0; i < 25; i++) buf[i] = 60;
    CHECK(digit_logic::sample_brightness(buf, 5, 5, PixFmt::GRAY, 0, 0, 2) == 60);
}

TEST_CASE("sample_brightness GRAY: empty frame returns 0") {
    uint8_t dummy = 0;
    CHECK(digit_logic::sample_brightness(&dummy, 0, 0, PixFmt::GRAY, 0, 0, 0) == 0);
}

// ---- sample_brightness RGB565 ----

TEST_CASE("sample_brightness RGB565: pure red") {
    // 0xF800: rv=248, gv=0, bv=0 → luma=(77*248)>>8=74
    uint8_t buf[2] = {0xF8, 0x00};
    CHECK(digit_logic::sample_brightness(buf, 1, 1, PixFmt::RGB565, 0, 0, 0) == 74);
}

TEST_CASE("sample_brightness RGB565: pure green") {
    // 0x07E0: rv=0, gv=252, bv=0 → luma=(150*252)>>8=147
    uint8_t buf[2] = {0x07, 0xE0};
    CHECK(digit_logic::sample_brightness(buf, 1, 1, PixFmt::RGB565, 0, 0, 0) == 147);
}

TEST_CASE("sample_brightness RGB565: pure white") {
    // 0xFFFF: rv=248, gv=252, bv=248 → luma=(77*248+150*252+29*248)>>8=250
    uint8_t buf[2] = {0xFF, 0xFF};
    CHECK(digit_logic::sample_brightness(buf, 1, 1, PixFmt::RGB565, 0, 0, 0) == 250);
}
