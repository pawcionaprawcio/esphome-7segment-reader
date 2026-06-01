import esphome.codegen as cg
import esphome.config_validation as cv
from esphome import automation
from esphome.const import CONF_ID

digit_number_ns = cg.esphome_ns.namespace("digit_number")
DigitNumber = digit_number_ns.class_("DigitNumber", cg.Component)
TriggerMeasurementAction = digit_number_ns.class_(
    "TriggerMeasurementAction", automation.Action
)

DIGIT_NUMBER_TRIGGER_MEASUREMENT_SCHEMA = automation.maybe_simple_id({
    cv.Required(CONF_ID): cv.use_id(DigitNumber),
})


@automation.register_action(
    "digit_number.trigger_measurement",
    TriggerMeasurementAction,
    DIGIT_NUMBER_TRIGGER_MEASUREMENT_SCHEMA,
)
async def trigger_measurement_to_code(config, action_id, template_arg, args):
    paren = await cg.get_variable(config[CONF_ID])
    var = cg.new_Pvariable(action_id, template_arg, paren)
    return var
