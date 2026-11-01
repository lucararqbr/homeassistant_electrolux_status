"""Climate platform for Electrolux Status.

Builds one native ``climate`` entity for air conditioners from the attributes
the appliance already reports (``mode``, ``targetTemperatureC``,
``fanSpeedSetting``, ``executeCommand`` ...). Option lists are read from the
capabilities returned by the API instead of being hard coded, so a model that
exposes fewer (or more) modes simply gets a shorter (or longer) list.
"""

import asyncio
import logging
import re
from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    SWING_OFF,
    SWING_ON,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_TENTHS, PRECISION_WHOLE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import BUTTON, CLIMATE, CLIMATE_HIDDEN_MODES, DOMAIN, NUMBER, SELECT, SWITCH
from .entity import ElectroluxEntity

_LOGGER: logging.Logger = logging.getLogger(__package__)

DEFAULT_MIN_TEMP = 16.0
DEFAULT_MAX_TEMP = 30.0
DEFAULT_TEMP_STEP = 1.0
# Pause between two consecutive commands sent to the cloud API
COMMAND_DELAY = 1

# Normalized (lowercase, letters and digits only) API value -> HVAC mode
_RAW_MODE_TO_HVAC: dict[str, HVACMode] = {
    "auto": HVACMode.AUTO,
    "cool": HVACMode.COOL,
    "dry": HVACMode.DRY,
    "heat": HVACMode.HEAT,
    "fanonly": HVACMode.FAN_ONLY,
    "fan": HVACMode.FAN_ONLY,
}

# Normalized API fan speed -> Home Assistant fan mode (others are exposed in lowercase)
_RAW_FAN_TO_HA: dict[str, str] = {
    "auto": FAN_AUTO,
    "low": FAN_LOW,
    "middle": FAN_MEDIUM,
    "medium": FAN_MEDIUM,
    "high": FAN_HIGH,
}

# Flap position -> preset. The meaning of a position depends on whether the flap
# is oscillating (a range) or fixed (an angle).
_OSCILLATE_PRESETS: dict[int, str] = {
    0: "oscillate_wide",
    1: "oscillate_up",
    2: "oscillate_middle",
    3: "oscillate_down",
}
_FIXED_PRESETS: dict[int, str] = {
    1: "fixed_up",
    2: "fixed_up_middle",
    3: "fixed_above_middle",
    4: "fixed_below_middle",
    5: "fixed_down_middle",
    6: "fixed_down",
}

_TRUE_VALUES = {"on", "true", "1", "yes", "enabled"}


def _norm(value: Any) -> str:
    """Normalize an API value for comparison (case, underscores and spaces ignored)."""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _as_bool(value: Any) -> bool | None:
    """Convert a boolean or ON/OFF style value to bool."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return _norm(value) in _TRUE_VALUES


def _enabled_values(capability: dict[str, Any]) -> list[str]:
    """Return the selectable values of a capability, skipping disabled ones."""
    values = capability.get("values")
    if not isinstance(values, dict):
        return []
    return [
        key
        for key, entry in values.items()
        if not (isinstance(entry, dict) and "disabled" in entry)
    ]


def _digits(value: Any) -> int | None:
    """Extract the integer found in a value such as ``POSITION_3``."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if match := re.search(r"-?\d+", str(value)):
        return int(match.group())
    return None


def appliance_supports_climate(appliance: Any) -> bool:
    """Return True when the appliance looks like an air conditioner."""
    data = getattr(appliance, "data", None)
    capabilities = getattr(data, "capabilities", None)
    if not isinstance(capabilities, dict):
        return False
    if "mode" not in capabilities or "targetTemperatureC" not in capabilities:
        return False
    return "fanSpeedSetting" in capabilities or appliance.appliance_type == "AC"


def build_climate_entities(appliance: Any) -> list["ElectroluxClimate"]:
    """Create the climate entity of an appliance (empty list if not supported)."""
    if not appliance_supports_climate(appliance):
        return []
    coordinator = appliance.coordinator
    return [
        ElectroluxClimate(
            coordinator=coordinator,
            name=appliance.name,
            config_entry=coordinator.config_entry,
            pnc_id=appliance.pnc_id,
            entity_type=CLIMATE,
            entity_name="climate",
            entity_attr="climate",
            entity_source="",
            capability={},
            unit=UnitOfTemperature.CELSIUS,
            device_class=None,
            entity_category=None,
            icon="mdi:air-conditioner",
            catalog_entry=None,
        )
    ]


def demote_controls_to_config(entities: list[ElectroluxEntity]) -> None:
    """Give the configuration category to the controls that have no category yet."""
    for entity in entities:
        if entity.entity_type in (BUTTON, NUMBER, SELECT, SWITCH) and entity.entity_category is None:
            entity._entity_category = EntityCategory.CONFIG  # noqa: SLF001


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configure climate platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if appliances := coordinator.data.get("appliances", None):
        for appliance_id, appliance in appliances.appliances.items():
            entities = [entity for entity in appliance.entities if entity.entity_type == CLIMATE]
            _LOGGER.debug(
                "Electrolux add %d CLIMATE entities to registry for appliance %s",
                len(entities),
                appliance_id,
            )
            async_add_entities(entities)


class ElectroluxClimate(ElectroluxEntity, ClimateEntity):
    """Electrolux Status climate class (air conditioners)."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_translation_key = "electrolux_ac"

    @property
    def entity_domain(self) -> str:
        """Entity domain for the entry. Used for consistent entity_id."""
        return CLIMATE

    @property
    def name(self) -> None:
        """Use the device name as entity name."""
        return None

    # ------------------------------------------------------------------
    # Helpers reading the reported state and the capabilities
    # ------------------------------------------------------------------

    def _reported(self, attr: str) -> Any:
        """Return a root level reported attribute."""
        if getattr(self, "appliance_status", None) is None:
            return None
        return self.reported_state.get(attr)

    def _capability(self, attr: str) -> dict[str, Any]:
        """Return the capability definition of a root level attribute."""
        capabilities = getattr(self.get_appliance.data, "capabilities", None) or {}
        capability = capabilities.get(attr)
        return capability if isinstance(capability, dict) else {}

    def _has(self, attr: str) -> bool:
        """Return True if the appliance exposes the attribute."""
        return bool(self._capability(attr)) or self._reported(attr) is not None

    def _hidden_modes(self) -> set[str]:
        """Normalized raw modes hidden for this appliance model."""
        return {
            _norm(mode)
            for model, modes in CLIMATE_HIDDEN_MODES.items()
            if _norm(model) == _norm(self.get_appliance.model)
            for mode in modes
        }

    def _hvac_options(self) -> dict[HVACMode, str]:
        """HVAC mode -> raw API value, from the ``mode`` capability."""
        options: dict[HVACMode, str] = {}
        hidden = self._hidden_modes()
        for raw in _enabled_values(self._capability("mode")):
            if _norm(raw) in hidden:
                continue
            hvac_mode = _RAW_MODE_TO_HVAC.get(_norm(raw))
            if hvac_mode is not None and hvac_mode not in options:
                options[hvac_mode] = raw
        return options

    def _fan_options(self) -> dict[str, str]:
        """Fan mode -> raw API value, from the ``fanSpeedSetting`` capability."""
        options: dict[str, str] = {}
        for raw in _enabled_values(self._capability("fanSpeedSetting")):
            ha_mode = _RAW_FAN_TO_HA.get(_norm(raw), str(raw).lower().replace(" ", "_"))
            options.setdefault(ha_mode, raw)
        return options

    def _position_options(self) -> dict[int, Any]:
        """Flap position number -> raw API value."""
        capability = self._capability("flapPosition")
        positions: dict[int, Any] = {}
        for raw in _enabled_values(capability):
            if (number := _digits(raw)) is not None:
                positions.setdefault(number, raw)
        if not positions and capability.get("min") is not None and capability.get("max") is not None:
            positions = {n: n for n in range(int(capability["min"]), int(capability["max"]) + 1)}
        return positions

    def _preset_options(self) -> dict[str, tuple[bool, Any]]:
        """Preset -> (oscillate, raw flap position)."""
        if not (self._has("flapOscillate") and self._has("flapPosition")):
            return {}
        positions = self._position_options()
        presets: dict[str, tuple[bool, Any]] = {}
        for number, name in _OSCILLATE_PRESETS.items():
            if number in positions:
                presets[name] = (True, positions[number])
        for number, name in _FIXED_PRESETS.items():
            if number in positions:
                presets[name] = (False, positions[number])
        return presets

    def _command_value(self, attr: str, wanted: str) -> str | None:
        """Find the raw value of a capability matching ``wanted`` (e.g. ON / OFF)."""
        for raw in _enabled_values(self._capability(attr)):
            if _norm(raw) == _norm(wanted):
                return raw
        return None

    @property
    def _is_power_off(self) -> bool:
        """Return True when the appliance reports it is switched off."""
        state = self._reported("applianceState")
        return state is not None and _norm(state) == "off"

    @property
    def _is_clean_air_on(self) -> bool:
        """Return True while the Clean Air cycle runs (the unit is otherwise off)."""
        return bool(_as_bool(self._reported("cleanAirMode")))

    def covers(self, entity: ElectroluxEntity) -> bool:
        """Return True when ``entity`` only duplicates what this climate entity offers.

        Used to avoid creating redundant entities. An entity is only reported as
        covered when the climate really exposes everything the entity could do.
        """
        if entity.pnc_id != self.pnc_id or entity.entity_source:
            return False
        attr, kind = entity.entity_attr, entity.entity_type
        if kind == BUTTON and attr == "executeCommand":
            return (
                _norm(getattr(entity, "val_to_send", "")) in ("on", "off")
                and self._command_value("executeCommand", "ON") is not None
                and self._command_value("executeCommand", "OFF") is not None
            )
        if kind == NUMBER and attr == "targetTemperatureC":
            return True
        if kind == SELECT and attr == "fanSpeedSetting":
            return bool(self._fan_options())
        if kind == SELECT and attr == "mode":
            hidden = self._hidden_modes()
            return bool(self._hvac_options()) and all(
                _norm(raw) in hidden or _norm(raw) in _RAW_MODE_TO_HVAC
                for raw in _enabled_values(self._capability("mode"))
            )
        if kind == SWITCH and attr == "flapOscillate":
            return True
        if kind == SELECT and attr == "flapPosition":
            return bool(self._preset_options()) and all(
                number in _OSCILLATE_PRESETS or number in _FIXED_PRESETS for number in self._position_options()
            )
        return False

    async def _send(self, command: dict[str, Any]) -> None:
        """Send a command to the appliance."""
        _LOGGER.debug("Electrolux climate command %s", command)
        result = await self.api.execute_appliance_command(self.pnc_id, command)
        _LOGGER.debug("Electrolux climate command result %s", result)

    # ------------------------------------------------------------------
    # Features
    # ------------------------------------------------------------------

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the supported features, depending on the appliance capabilities."""
        features = ClimateEntityFeature.TARGET_TEMPERATURE
        if self._command_value("executeCommand", "ON") and self._command_value("executeCommand", "OFF"):
            features |= ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        if self._fan_options():
            features |= ClimateEntityFeature.FAN_MODE
        if self._has("flapOscillate"):
            features |= ClimateEntityFeature.SWING_MODE
        if self._preset_options():
            features |= ClimateEntityFeature.PRESET_MODE
        return features

    # ------------------------------------------------------------------
    # HVAC mode / action
    # ------------------------------------------------------------------

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the available HVAC modes."""
        return [HVACMode.OFF, *self._hvac_options()]

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current HVAC mode."""
        # While Clean Air runs the unit is considered off
        if self._is_power_off or self._is_clean_air_on:
            return HVACMode.OFF
        raw = self._reported("mode")
        if raw is None:
            return None
        return _RAW_MODE_TO_HVAC.get(_norm(raw))

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return what the unit is currently doing."""
        if self._is_clean_air_on:
            return HVACAction.DRYING
        if self._is_power_off:
            return HVACAction.OFF
        state = self._reported("applianceState")
        if state is None or _norm(state) != "running":
            return HVACAction.IDLE
        match self.hvac_mode:
            case HVACMode.HEAT:
                return HVACAction.HEATING
            case HVACMode.DRY:
                return HVACAction.DRYING
            case HVACMode.FAN_ONLY:
                return HVACAction.FAN
            case HVACMode.AUTO:
                current, target = self.current_temperature, self.target_temperature
                if (
                    HVACMode.HEAT in self._hvac_options()
                    and current is not None
                    and target is not None
                    and current < target
                ):
                    return HVACAction.HEATING
                return HVACAction.COOLING
            case _:
                return HVACAction.COOLING

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode (switching the unit on or off when needed)."""
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return
        raw_mode = self._hvac_options().get(hvac_mode)
        if raw_mode is None:
            raise ServiceValidationError(f"HVAC mode {hvac_mode} is not supported by this appliance")
        if self._is_power_off or self._is_clean_air_on:
            await self.async_turn_on()
            # Setting the mode right after power on keeps the requested mode
            if _norm(self._reported("mode")) != _norm(raw_mode):
                await asyncio.sleep(COMMAND_DELAY)
                await self._send({"mode": raw_mode})
            return
        await self._send({"mode": raw_mode})

    async def async_turn_on(self) -> None:
        """Switch the unit on.

        Only the ON command is sent: the appliance resumes the mode it had when it
        was switched off.
        """
        value = self._command_value("executeCommand", "ON")
        if value is None:
            raise HomeAssistantError("This appliance does not support the ON command")
        await self._send({"executeCommand": value})

    async def async_turn_off(self) -> None:
        """Switch the unit off."""
        value = self._command_value("executeCommand", "OFF")
        if value is None:
            raise HomeAssistantError("This appliance does not support the OFF command")
        await self._send({"executeCommand": value})

    # ------------------------------------------------------------------
    # Temperature
    # ------------------------------------------------------------------

    @property
    def current_temperature(self) -> float | None:
        """Return the temperature measured by the unit."""
        value = self._reported("ambientTemperatureC")
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        value = self._reported("targetTemperatureC")
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    @property
    def min_temp(self) -> float:
        """Return the minimum target temperature."""
        return float(self._capability("targetTemperatureC").get("min", DEFAULT_MIN_TEMP))

    @property
    def max_temp(self) -> float:
        """Return the maximum target temperature."""
        return float(self._capability("targetTemperatureC").get("max", DEFAULT_MAX_TEMP))

    @property
    def target_temperature_step(self) -> float:
        """Return the target temperature step."""
        return float(self._capability("targetTemperatureC").get("step", DEFAULT_TEMP_STEP))

    @property
    def precision(self) -> float:
        """Return the precision of the temperatures."""
        return PRECISION_WHOLE if self.target_temperature_step >= 1 else PRECISION_TENTHS

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            await self.async_set_hvac_mode(hvac_mode)
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        temperature = min(max(float(temperature), self.min_temp), self.max_temp)
        value: float | int = int(round(temperature)) if self.target_temperature_step >= 1 else temperature
        await self._send({"targetTemperatureC": value})

    # ------------------------------------------------------------------
    # Fan
    # ------------------------------------------------------------------

    @property
    def fan_modes(self) -> list[str] | None:
        """Return the available fan modes."""
        return list(self._fan_options()) or None

    @property
    def fan_mode(self) -> str | None:
        """Return the current fan mode."""
        raw = self._reported("fanSpeedSetting")
        if raw is None:
            return None
        return _RAW_FAN_TO_HA.get(_norm(raw), str(raw).lower().replace(" ", "_"))

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode."""
        raw = self._fan_options().get(fan_mode)
        if raw is None:
            raise ServiceValidationError(f"Fan mode {fan_mode} is not supported by this appliance")
        await self._send({"fanSpeedSetting": raw})

    # ------------------------------------------------------------------
    # Flap: oscillation (swing) and position (presets)
    # ------------------------------------------------------------------

    @property
    def swing_modes(self) -> list[str] | None:
        """Return the swing modes (flap oscillation on/off)."""
        return [SWING_OFF, SWING_ON] if self._has("flapOscillate") else None

    @property
    def swing_mode(self) -> str | None:
        """Return the current swing mode."""
        oscillating = _as_bool(self._reported("flapOscillate"))
        if oscillating is None:
            return None
        return SWING_ON if oscillating else SWING_OFF

    async def _set_oscillation(self, enabled: bool) -> None:
        """Switch the flap oscillation on or off."""
        capability = self._capability("flapOscillate")
        value: Any = enabled
        # Electrolux bug - some appliances need ON/OFF strings instead of booleans
        if "values" in capability:
            value = self._command_value("flapOscillate", "ON" if enabled else "OFF") or ("ON" if enabled else "OFF")
        await self._send({"flapOscillate": value})

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set the swing mode."""
        await self._set_oscillation(swing_mode == SWING_ON)

    @property
    def preset_modes(self) -> list[str] | None:
        """Return the flap presets."""
        return list(self._preset_options()) or None

    @property
    def preset_mode(self) -> str | None:
        """Return the current flap preset."""
        oscillating = _as_bool(self._reported("flapOscillate"))
        position = _digits(self._reported("flapPosition"))
        if oscillating is None or position is None:
            return None
        table = _OSCILLATE_PRESETS if oscillating else _FIXED_PRESETS
        preset = table.get(position)
        return preset if preset in self._preset_options() else None

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the flap preset (oscillation and position)."""
        option = self._preset_options().get(preset_mode)
        if option is None:
            raise ServiceValidationError(f"Preset {preset_mode} is not supported by this appliance")
        oscillate, raw_position = option
        await self._set_oscillation(oscillate)
        await asyncio.sleep(COMMAND_DELAY)
        await self._send({"flapPosition": raw_position})
