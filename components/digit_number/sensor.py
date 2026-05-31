import esphome.codegen as cg
import esphome.config_validation as cv
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
CONF_LAST_SUCCESSFUL_READ = "last_successful_read"
CONF_LAST_STATE = "last_state"

DigitAnchors = digit_number_ns.struct("DigitAnchors")

DIGIT_SCHEMA = cv.Schema({
    cv.Required("a"): cv.All([cv.uint16_t], cv.Length(min=2, max=2)),
    cv.Required("g"): cv.All([cv.uint16_t], cv.Length(min=2, max=2)),
    cv.Required("b"): cv.uint16_t,
})

CONFIG_SCHEMA = (
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
            cv.Length(min=4, max=4, msg="Exactly 4 digits required"),
        ),
        cv.Optional(CONF_SAMPLE_RADIUS, default=2): cv.uint8_t,
        cv.Optional(CONF_THRESHOLD, default="auto"): cv.Any(
            "auto", cv.int_range(min=0, max=255)
        ),
        cv.Optional(CONF_DISPLAY_OFF_THRESHOLD, default=10): cv.uint8_t,
        cv.Optional(CONF_UPDATE_INTERVAL, default="5s"): cv.update_interval,
        cv.Optional(CONF_LAST_SUCCESSFUL_READ): sensor.sensor_schema(
            unit_of_measurement="s",
            accuracy_decimals=0,
            state_class=STATE_CLASS_MEASUREMENT,
            icon="mdi:clock-alert-outline",
        ),
        cv.Optional(CONF_LAST_STATE): text_sensor.text_sensor_schema(
            icon="mdi:information-outline",
        ),
    })
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
            ("gx", digit["g"][0]),
            ("gy", digit["g"][1]),
            ("bx", digit["b"]),
        )
        cg.add(var.add_digit(anchors))

    cg.add(var.set_sample_radius(config[CONF_SAMPLE_RADIUS]))

    threshold = config[CONF_THRESHOLD]
    cg.add(var.set_threshold(-1 if threshold == "auto" else int(threshold)))

    cg.add(var.set_display_off_threshold(config[CONF_DISPLAY_OFF_THRESHOLD]))

    if CONF_LAST_SUCCESSFUL_READ in config:
        stale = await sensor.new_sensor(config[CONF_LAST_SUCCESSFUL_READ])
        cg.add(var.set_staleness_sensor(stale))

    if CONF_LAST_STATE in config:
        ts = await text_sensor.new_text_sensor(config[CONF_LAST_STATE])
        cg.add(var.set_last_state_sensor(ts))
