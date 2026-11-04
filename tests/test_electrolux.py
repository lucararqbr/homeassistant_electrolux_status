"""Tests of the local electrolux_status modifications, using real diagnostics data.

Run from the repository root (see CLAUDE.md, "Testes"): python -P -m pytest tests
(-P is needed: the integration has a select.py that would shadow Python's own module.)
"""

import asyncio
import copy
import json
import pathlib
import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import ClientResponseError

TESTS_DIR = pathlib.Path(__file__).resolve().parent
# Local repository: the integration is the repository root (folder "electrolux_status").
# Fork (branch "modificado"): the integration is in custom_components/electrolux_status.
INTEGRATION_DIR = TESTS_DIR.parent / "custom_components" / "electrolux_status"
if not INTEGRATION_DIR.is_dir():
    INTEGRATION_DIR = TESTS_DIR.parent
assert INTEGRATION_DIR.name == "electrolux_status", INTEGRATION_DIR
sys.path.insert(0, str(INTEGRATION_DIR.parent))

from electrolux_status import const  # noqa: E402
from electrolux_status.api import Appliance, Appliances, ElectroluxLibraryEntity  # noqa: E402
from electrolux_status.binary_sensor import ElectroluxBinarySensor  # noqa: E402
from electrolux_status.button import ElectroluxReconnectButton  # noqa: E402
from electrolux_status.climate import ElectroluxClimate  # noqa: E402
from electrolux_status.coordinator import ElectroluxCoordinator  # noqa: E402
from electrolux_status.sensor import ElectroluxSensor  # noqa: E402

from homeassistant.components.binary_sensor import BinarySensorDeviceClass  # noqa: E402
from homeassistant.const import EntityCategory, Platform  # noqa: E402

FIXTURE = TESTS_DIR / "fixtures" / "diagnostics_ar_condicionado.json"


def load_diagnostics():
    """appliances_info / appliances_list / appliances_detail of the two air conditioners."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def build_appliances(api=None):
    """Build the appliances exactly as coordinator.setup_entities does, from the diagnostics."""
    data = load_diagnostics()
    coordinator = SimpleNamespace(
        api=api or SimpleNamespace(),
        config_entry=SimpleNamespace(entry_id="test-entry"),
        data=None,
    )
    appliances = Appliances({})
    coordinator.data = {"appliances": appliances}
    infos = {info["pnc"]: info for info in data["appliances_info"]}
    for appliance_json in data["appliances_list"]:
        appliance_id = appliance_json["applianceId"]
        detail = data["appliances_detail"][appliance_id]
        state = copy.deepcopy(detail["state"])
        info = infos[appliance_id.split("_")[0]]
        appliance = Appliance(
            coordinator=coordinator,
            pnc_id=appliance_id,
            name=appliance_json["applianceData"]["applianceName"],
            brand=info["brand"],
            model=info["model"],
            state=state,
        )
        appliances.appliances[appliance_id] = appliance
        appliance.setup(
            ElectroluxLibraryEntity(
                name=appliance.name,
                status=appliance_json["connectionState"],
                state=state,
                appliance_info=info,
                capabilities=copy.deepcopy(detail["capabilities"]),
            )
        )
    return coordinator, appliances


def by_attr(appliance, attr):
    return [e for e in appliance.entities if e.entity_attr == attr]


# ---------------------------------------------------------------- entities


def test_fixture_has_two_air_conditioners():
    assert len(load_diagnostics()["appliances_list"]) == 2


@pytest.mark.parametrize("index", [0, 1])
def test_entities_created(index):
    _, appliances = build_appliances()
    appliance = list(appliances.appliances.values())[index]
    types = {}
    for e in appliance.entities:
        types.setdefault(e.entity_type, []).append(e.entity_attr)
    print(appliance.name, appliance.model, {k: sorted(v) for k, v in types.items()})

    # one climate entity
    climates = [e for e in appliance.entities if isinstance(e, ElectroluxClimate)]
    assert len(climates) == 1

    # unique ids must be unique
    ids = [e.unique_id for e in appliance.entities]
    assert len(ids) == len(set(ids)), "duplicate unique_id"
    eids = [e.entity_id for e in appliance.entities]
    assert len(eids) == len(set(eids)), "duplicate entity_id"


@pytest.mark.parametrize("attr,device_class", [("applianceState", BinarySensorDeviceClass.POWER), ("cleanAirMode", None)])
def test_binary_sensors(attr, device_class):
    _, appliances = build_appliances()
    for appliance in appliances.appliances.values():
        entities = by_attr(appliance, attr)
        assert len(entities) == 1, entities
        entity = entities[0]
        assert isinstance(entity, ElectroluxBinarySensor)
        assert not isinstance(entity, ElectroluxSensor)
        assert entity.entity_type == Platform.BINARY_SENSOR
        assert entity.device_class == device_class
        assert entity.entity_registry_enabled_default is True
        assert entity._attr_translation_key in ("appliance_state", "clean_air_mode")

        reported = appliance.reported_state
        for value, expected in [("OFF", False), ("RUNNING", True), ("IDLE", True), ("ON", True), ("off", False)]:
            reported[attr] = value
            entity.update(appliance.state)
            assert entity.is_on is expected, (attr, value)


def test_catalog_not_mutated():
    """The catalog entry of applianceState must stay a disabled text sensor for other appliances."""
    from electrolux_status.catalog_core import CATALOG_BASE

    build_appliances()
    entry = CATALOG_BASE["applianceState"]
    assert entry.entity_platform is None
    assert entry.state_off_values is None
    assert entry.entity_registry_enabled_default is False


def test_reconnect_button():
    _, appliances = build_appliances()
    for appliance in appliances.appliances.values():
        buttons = [e for e in appliance.entities if isinstance(e, ElectroluxReconnectButton)]
        assert len(buttons) == 1
        button = buttons[0]
        assert button.entity_type == Platform.BUTTON
        assert button.entity_category == EntityCategory.CONFIG
        assert button.available is True
        assert button._attr_translation_key == "reconnect_api"
        assert button.entity_registry_visible_default is True  # config entities no longer hidden
        print(button.entity_id, button.unique_id)


def test_config_entities_visible():
    _, appliances = build_appliances()
    for appliance in appliances.appliances.values():
        for e in appliance.entities:
            assert e.entity_registry_visible_default is True


def test_translations_have_new_keys():
    base = INTEGRATION_DIR
    for name in ["strings.json", "translations/en.json", "translations/pt_br.json", "translations/pt-BR.json", "translations/pt.json"]:
        data = json.loads((base / name).read_text(encoding="utf-8"))["entity"]
        assert data["button"]["reconnect_api"]["name"]
        assert set(data["binary_sensor"]["appliance_state"]["state"]) == {"on", "off"}
        assert set(data["binary_sensor"]["clean_air_mode"]["state"]) == {"on", "off"}


# ---------------------------------------------------------------- API check


def make_coordinator(api):
    """Coordinator without hass: only the attributes used by async_check_api / reconnect."""
    coordinator = ElectroluxCoordinator.__new__(ElectroluxCoordinator)
    coordinator.api = api
    coordinator._check_lock = asyncio.Lock()
    coordinator._last_push = time.monotonic()
    coordinator._websocket = None
    coordinator._token = None
    coordinator.updates = 0

    def set_updated(data):
        coordinator.updates += 1

    coordinator.async_set_updated_data = set_updated
    _, appliances = build_appliances(api)
    coordinator.data = {"appliances": appliances}
    return coordinator, appliances


def cloud_list(appliances, changes=None):
    """What get_appliances_list returns: current reported state, optionally changed."""
    result = []
    for appliance_id, appliance in appliances.appliances.items():
        reported = copy.deepcopy(appliance.reported_state)
        reported.update((changes or {}).get(appliance_id, {}))
        result.append({"applianceId": appliance_id, "properties": {"reported": reported}})
    return result


def fake_api():
    api = SimpleNamespace()
    api.get_appliances_list = AsyncMock()
    api.disconnect_websocket = AsyncMock()
    api.connect_websocket = AsyncMock()
    api._user_token = None
    return api


async def _run(coro):
    return await coro


def run(coro):
    return asyncio.run(_run(coro))


def test_check_up_to_date_no_reconnect():
    api = fake_api()
    coordinator, appliances = make_coordinator(api)
    api.get_appliances_list.return_value = cloud_list(appliances)
    coordinator._last_push = time.monotonic() - 3 * const.API_CHECK_INTERVAL  # silent
    run(coordinator.async_check_api())
    api.connect_websocket.assert_not_called()
    assert coordinator.updates == 0


def test_check_outdated_and_silent_reconnects():
    async def scenario():
        api = fake_api()
        coordinator, appliances = make_coordinator(api)
        appliance_id = next(iter(appliances.appliances))
        api.get_appliances_list.return_value = cloud_list(appliances, {appliance_id: {"targetTemperatureC": 18.0}})
        coordinator._last_push = time.monotonic() - const.API_CHECK_INTERVAL - 1
        await coordinator.async_check_api()
        await asyncio.sleep(0)
        return api, coordinator, appliances, appliance_id

    api, coordinator, appliances, appliance_id = asyncio.run(scenario())
    assert appliances.get_appliance(appliance_id).reported_state["targetTemperatureC"] == 18.0
    assert coordinator.updates == 1
    api.disconnect_websocket.assert_awaited_once()
    api.connect_websocket.assert_called_once()
    assert sorted(api.connect_websocket.call_args.args[0]) == sorted(appliances.appliances)


def test_check_outdated_but_websocket_active_no_reconnect():
    api = fake_api()
    coordinator, appliances = make_coordinator(api)
    appliance_id = next(iter(appliances.appliances))
    api.get_appliances_list.return_value = cloud_list(appliances, {appliance_id: {"fanSpeedSetting": "LOW"}})
    coordinator._last_push = time.monotonic()  # websocket just sent something
    run(coordinator.async_check_api())
    assert appliances.get_appliance(appliance_id).reported_state["fanSpeedSetting"] == "LOW"
    assert coordinator.updates == 1
    api.connect_websocket.assert_not_called()


def test_check_ignores_countdowns_and_nested():
    api = fake_api()
    coordinator, appliances = make_coordinator(api)
    appliance_id = next(iter(appliances.appliances))
    api.get_appliances_list.return_value = cloud_list(
        appliances, {appliance_id: {"stopTime": 1234, "networkInterface": {"linkQualityIndicator": "POOR"}}}
    )
    coordinator._last_push = time.monotonic() - 3 * const.API_CHECK_INTERVAL
    run(coordinator.async_check_api())
    assert coordinator.updates == 0
    api.connect_websocket.assert_not_called()


def test_force_reconnect_from_button():
    async def scenario():
        api = fake_api()
        coordinator, appliances = make_coordinator(api)
        api.get_appliances_list.return_value = cloud_list(appliances)
        appliance = next(iter(appliances.appliances.values()))
        button = next(e for e in appliance.entities if isinstance(e, ElectroluxReconnectButton))
        button.coordinator = coordinator
        await button.async_press()
        return api

    api = asyncio.run(scenario())
    api.connect_websocket.assert_called_once()


def test_force_reconnect_even_if_api_fails():
    api = fake_api()
    coordinator, _ = make_coordinator(api)
    api.get_appliances_list.side_effect = RuntimeError("cloud down")
    run(coordinator.async_check_api(force_reconnect=True))
    api.connect_websocket.assert_called_once()


def test_api_failure_without_force_is_logged_only():
    api = fake_api()
    coordinator, _ = make_coordinator(api)
    api.get_appliances_list.side_effect = RuntimeError("cloud down")
    run(coordinator.async_check_api())
    api.connect_websocket.assert_not_called()


def test_relogin_on_401():
    api = fake_api()
    coordinator, appliances = make_coordinator(api)
    error = ClientResponseError(request_info=SimpleNamespace(real_url="x"), history=(), status=401)
    api.get_appliances_list.side_effect = [error, cloud_list(appliances)]
    api._user_token = SimpleNamespace(expiresAt=None)
    coordinator.async_login = AsyncMock(return_value=True)
    run(coordinator.async_check_api())
    coordinator.async_login.assert_awaited_once()
    assert api.get_appliances_list.await_count == 2
    assert api._user_token.expiresAt is not None


def test_reconnect_cancels_previous_task():
    async def scenario():
        api = fake_api()
        coordinator, _ = make_coordinator(api)
        started = asyncio.Event()

        async def forever():
            started.set()
            await asyncio.sleep(3600)

        coordinator._websocket = asyncio.create_task(forever())
        await started.wait()
        old = coordinator._websocket
        await coordinator.reconnect_websocket()
        await asyncio.sleep(0)
        return old, coordinator, api

    old, coordinator, api = asyncio.run(scenario())
    assert old.cancelled()
    assert coordinator._websocket is not old
    api.connect_websocket.assert_called_once()


def test_concurrent_checks_do_not_overlap():
    async def scenario():
        api = fake_api()
        coordinator, appliances = make_coordinator(api)

        async def slow():
            await asyncio.sleep(0.05)
            return cloud_list(appliances)

        api.get_appliances_list.side_effect = slow
        await asyncio.gather(coordinator.async_check_api(), coordinator.async_check_api())
        return api

    api = asyncio.run(scenario())
    assert api.get_appliances_list.await_count == 1
