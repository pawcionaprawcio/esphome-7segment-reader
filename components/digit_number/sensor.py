import esphome.codegen as cg
import esphome.config_validation as cv
import esphome.pins as pins
from esphome.components import sensor, esp32_camera, text_sensor
from esphome.const import STATE_CLASS_MEASUREMENT
from . import digit_number_ns, DigitNumber

AUTO_LOAD = ["text_sensor"]

CONF_CAMERA_ID = "camera_id"
CONF_DIGITS = "digits"
CONF_SAMPLE_RADIUS = "sample_radius"
CONF_THRESHOLD = "threshold"
CONF_DISPLAY_OFF_THRESHOLD = "display_off_threshold"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_LAST_STATE = "last_state"
CONF_TRIGGER_PIN = "trigger_pin"
CONF_BURST_MODE = "burst_mode"
CONF_BURST_COUNT = "count"
CONF_BURST_TRIGGER_INTERVAL = "trigger_interval"
CONF_BURST_REST_DURATION = "rest_duration"
CONF_TRIGGER_PULSE = "trigger_pulse"
CONF_TRIGGER_COLD_WAIT = "trigger_cold_wait"
CONF_TRIGGER_TIMEOUT_WARM = "trigger_timeout_warm"
CONF_TRIGGER_TIMEOUT_COLD = "trigger_timeout_cold"
CONF_DELTA_THRESHOLD = "delta_threshold"
CONF_DELTA_REST_DURATION = "delta_rest_duration"
CONF_MAX_VALUE = "max_value"

BURST_MODE_SCHEMA = cv.Schema({
    cv.Optional(CONF_BURST_COUNT, default=3): cv.positive_int,
    cv.Optional(CONF_BURST_TRIGGER_INTERVAL, default="10s"): cv.positive_time_period_milliseconds,
    cv.Optional(CONF_BURST_REST_DURATION, default="5min"): cv.positive_time_period_milliseconds,
    cv.Optional(CONF_TRIGGER_PULSE, default="300ms"): cv.positive_time_period_milliseconds,
    cv.Optional(CONF_TRIGGER_COLD_WAIT, default="2s"): cv.positive_time_period_milliseconds,
    cv.Optional(CONF_TRIGGER_TIMEOUT_WARM, default="6s"): cv.positive_time_period_milliseconds,
    cv.Optional(CONF_TRIGGER_TIMEOUT_COLD, default="15s"): cv.positive_time_period_milliseconds,
    cv.Optional(CONF_DELTA_THRESHOLD, default=5.0): cv.float_,
    cv.Optional(CONF_DELTA_REST_DURATION, default="60s"): cv.positive_time_period_milliseconds,
})


def _validate_burst_requires_trigger(config):
    if CONF_BURST_MODE in config and CONF_TRIGGER_PIN not in config:
        raise cv.Invalid("burst_mode requires trigger_pin")
    if CONF_TRIGGER_PIN in config and CONF_BURST_MODE not in config:
        raise cv.Invalid("trigger_pin requires burst_mode")
    return config


DigitAnchors = digit_number_ns.struct("DigitAnchors")

DIGIT_SCHEMA = cv.Schema({
    cv.Required("a"): cv.All([cv.uint16_t], cv.Length(min=2, max=2)),
    cv.Required("d"): cv.All([cv.uint16_t], cv.Length(min=2, max=2)),
    cv.Required("b"): cv.All([cv.uint16_t], cv.Length(min=2, max=2)),
})

CONFIG_SCHEMA = cv.All(
    sensor.sensor_schema(
        DigitNumber,
        unit_of_measurement="mm",
        accuracy_decimals=0,
        state_class=STATE_CLASS_MEASUREMENT,
    )
    .extend({
        cv.Required(CONF_CAMERA_ID): cv.use_id(esp32_camera.ESP32Camera),
        cv.Required(CONF_DIGITS): cv.All(
            cv.ensure_list(DIGIT_SCHEMA),
            cv.Length(min=1),
        ),
        cv.Optional(CONF_SAMPLE_RADIUS, default=2): cv.uint8_t,
        cv.Optional(CONF_THRESHOLD, default="auto"): cv.Any(
            "auto", cv.int_range(min=0, max=255)
        ),
        cv.Optional(CONF_DISPLAY_OFF_THRESHOLD, default=10): cv.uint8_t,
        cv.Optional(CONF_UPDATE_INTERVAL, default="5s"): cv.update_interval,
        cv.Optional(CONF_LAST_STATE): text_sensor.text_sensor_schema(
            icon="mdi:information-outline",
        ),
        cv.Optional(CONF_TRIGGER_PIN): pins.gpio_output_pin_schema,
        cv.Optional(CONF_BURST_MODE): BURST_MODE_SCHEMA,
        cv.Optional(CONF_MAX_VALUE): cv.positive_int,
    }),
    _validate_burst_requires_trigger,
)


async def to_code(config):
    var = await sensor.new_sensor(config)
    await cg.register_component(var, config)

    cam = await cg.get_variable(config[CONF_CAMERA_ID])
    cg.add(var.set_camera(cam))

    for digit in config[CONF_DIGITS]:
        anchors = cg.StructInitializer(
            DigitAnchors,
            ("ax", digit["a"][0]),
            ("ay", digit["a"][1]),
            ("dx", digit["d"][0]),
            ("dy", digit["d"][1]),
            ("bx", digit["b"][0]),
            ("by", digit["b"][1]),
        )
        cg.add(var.add_digit(anchors))

    cg.add(var.set_sample_radius(config[CONF_SAMPLE_RADIUS]))

    threshold = config[CONF_THRESHOLD]
    cg.add(var.set_threshold(-1 if threshold == "auto" else int(threshold)))

    cg.add(var.set_display_off_threshold(config[CONF_DISPLAY_OFF_THRESHOLD]))

    if CONF_LAST_STATE in config:
        ts = await text_sensor.new_text_sensor(config[CONF_LAST_STATE])
        cg.add(var.set_last_state_sensor(ts))

    if CONF_TRIGGER_PIN in config:
        pin = await cg.gpio_pin_expression(config[CONF_TRIGGER_PIN])
        cg.add(var.set_trigger_pin(pin))

    if CONF_BURST_MODE in config:
        bm = config[CONF_BURST_MODE]
        cg.add(var.set_burst_count(bm[CONF_BURST_COUNT]))
        cg.add(var.set_burst_trigger_interval(bm[CONF_BURST_TRIGGER_INTERVAL]))
        cg.add(var.set_burst_rest_duration(bm[CONF_BURST_REST_DURATION]))
        cg.add(var.set_trigger_pulse_ms(bm[CONF_TRIGGER_PULSE]))
        cg.add(var.set_trigger_cold_wait_ms(bm[CONF_TRIGGER_COLD_WAIT]))
        cg.add(var.set_trigger_timeout_warm_ms(bm[CONF_TRIGGER_TIMEOUT_WARM]))
        cg.add(var.set_trigger_timeout_cold_ms(bm[CONF_TRIGGER_TIMEOUT_COLD]))
        cg.add(var.set_delta_threshold(bm[CONF_DELTA_THRESHOLD]))
        cg.add(var.set_delta_rest_duration_ms(bm[CONF_DELTA_REST_DURATION]))

    if CONF_MAX_VALUE in config:
        cg.add(var.set_max_value(config[CONF_MAX_VALUE]))
