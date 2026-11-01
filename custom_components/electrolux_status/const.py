"""The electrolux Status constants."""

import re

from homeassistant.const import Platform

# Base component constants
NAME = "Electrolux status"
DOMAIN = "electrolux_status"
DOMAIN_DATA = f"{DOMAIN}_data"
COMPONENTS_DIRECTORY = "custom_components"
LOOKUP_DIRECTORY = "appliance_definitions"
LOOKUP_DIRECTORY_PATH = f"{COMPONENTS_DIRECTORY}/{DOMAIN}/{LOOKUP_DIRECTORY}/"

# Platforms
BINARY_SENSOR = Platform.BINARY_SENSOR
BUTTON = Platform.BUTTON
CLIMATE = Platform.CLIMATE
NUMBER = Platform.NUMBER
SELECT = Platform.SELECT
SENSOR = Platform.SENSOR
SWITCH = Platform.SWITCH
PLATFORMS = [BINARY_SENSOR, BUTTON, CLIMATE, NUMBER, SELECT, SENSOR, SWITCH]

# Configuration and options
CONF_LANGUAGE = "language"
CONF_RENEW_INTERVAL = "renew_interval"
CONF_NOTIFICATION_DEFAULT = "notifications"
CONF_NOTIFICATION_DIAG = "notifications_diagnostic"
CONF_NOTIFICATION_WARNING = "notifications_warning"

# Defaults
DEFAULT_LANGUAGE = "English"
DEFAULT_COUNTRY_CODE = "us"
DEFAULT_WEBSOCKET_RENEWAL_DELAY = 43200  # 12 hours

# these are attributes that appear in the state file but not in the capabilities.
# defining them here and in the catalog will allow these devices to be added dynamically
STATIC_ATTRIBUTES = [
    "connectivityState",
    "networkInterface/linkQualityIndicator",
    "applianceMode",
]

# Icon mappings for default executeCommands
icon_mapping = {
    "OFF": "mdi:power-off",
    "ON": "mdi:power-on",
    "START": "mdi:play",
    "STOPRESET": "mdi:stop",
    "PAUSE": "mdi:pause",
    "RESUME": "mdi:play-pause",
}

# List of supported Mobile App languages
# refer to https://emea-production.api.electrolux.net/masterdata-service/api/v1/languages
languages = {
    "български": "bul",
    "český": "ces",
    "Dansk": "dan",
    "Deutsch": "deu",
    "ελληνικός": "ell",
    "English": "eng",
    "eesti": "est",
    "Soome": "fin",
    "Français": "fra",
    "Hrvatski": "hrv",
    "magyar": "hun",
    "Italiano": "ita",
    "lettone": "lav",
    "lituano": "lit",
    "Luxembourgish": "ltz",
    "nederlands": "nld",
    "Norsk": "nor",
    "Polski": "pol",
    "Português": "por",
    "Română": "ron",
    "rusesc": "rus",
    "slovenský": "slk",
    "slovinský": "slv",
    "Español": "spa",
    "Svenska": "swe",
    "Türk": "tur",
    "Ukrayna": "ukr",
}

# List of attributes to ignore and that won't be added as entities (regex format)
ATTRIBUTES_BLACKLIST: list[str] = ["^fCMiscellaneous.+",
                                   "fcOptisenseLoadWeight.*",
                                   "applianceCareAndMaintenance.*",
                                   "applianceMainBoardSwVersion",
                                   "coolingValveState",
                                   "networkInterface",
                                   "temperatureRepresentation",
                                   ]

ATTRIBUTES_WHITELIST: list[str] = [".*waterUsage",
                                   ".*tankAReserve",
                                   ".*tankBReserve"]

# Rules to simplify the naming of entities
RENAME_RULES: list[str] = [r"^userSelections\/[^_]+_", r"^userSelections\/",
                           r"^fCMiscellaneousState\/[^_]+_", r"^fCMiscellaneousState\/"]

# Entities whose name is translated through the translation files
# (entity.<platform>.<key>.name). The key is the generated English name, lowercased with
# underscores ("Auto sense mode" -> "auto_sense_mode"). Other entities keep the generated name.
TRANSLATED_ENTITY_NAMES: frozenset[str] = frozenset(
    {
        "alerts",
        "appliance_state",
        "auto_sense_mode",
        "clean_air_mode",
        "comfort_air",
        "connectivity_state",
        "evaporator_defrost_state",
        "filter_state",
        "sleep_mode",
        "sound_volume",
        "stop_time",
    }
)

# Climate: when an appliance gets a climate entity, do not create the entities that only
# duplicate it (ON/OFF buttons, mode, fan speed, target temperature, flap oscillation and
# flap position). Entities that the climate cannot fully replace are kept.
CLIMATE_REMOVE_REDUNDANT_ENTITIES = True

# Climate: controls (switch, select, number, button) that remain on an appliance with a climate
# entity are given the "configuration" category, so they stay out of the default controls
# (dashboards, voice assistants) and the climate is the single control of the appliance.
CLIMATE_KEPT_CONTROLS_AS_CONFIG = True

# Climate: HVAC modes the API lists but a given appliance model does not really support
# (e.g. "HEAT" on a cooling-only air conditioner). Key: appliance model as shown on the device
# page, value: raw API mode values to hide.
CLIMATE_HIDDEN_MODES: dict[str, list[str]] = {
    "YI12F": ["HEAT"],
}

# List of entity names that need to be updated to 0 manually when they are close to 0
TIME_ENTITIES_TO_UPDATE = ["timeToEnd"]
