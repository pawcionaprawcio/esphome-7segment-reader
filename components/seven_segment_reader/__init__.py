import esphome.codegen as cg
import esphome.config_validation as cv
from esphome import automation
from esphome.const import CONF_ID

seven_segment_reader_ns = cg.esphome_ns.namespace("seven_segment_reader")
SevenSegmentReader = seven_segment_reader_ns.class_("SevenSegmentReader", cg.Component)
TriggerMeasurementAction = seven_segment_reader_ns.class_(
    "TriggerMeasurementAction", automation.Action
)

SEVEN_SEGMENT_READER_TRIGGER_MEASUREMENT_SCHEMA = automation.maybe_simple_id({
    cv.Required(CONF_ID): cv.use_id(SevenSegmentReader),
})


@automation.register_action(
    "seven_segment_reader.trigger_measurement",
    TriggerMeasurementAction,
    SEVEN_SEGMENT_READER_TRIGGER_MEASUREMENT_SCHEMA,
)
async def trigger_measurement_to_code(config, action_id, template_arg, args):
    paren = await cg.get_variable(config[CONF_ID])
    var = cg.new_Pvariable(action_id, template_arg, paren)
    return var
