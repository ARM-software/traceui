import json
from pathlib import Path


def _config_path_value(key, value):
    path_value = str(value).strip() if value is not None else ""
    if not path_value:
        raise ValueError(f"devicepaths.{key} must be a non-empty string.")
    return path_value


def apply_devicepaths_config(devicepaths, handlers):
    if not isinstance(devicepaths, dict):
        raise ValueError("'devicepaths' must be a JSON object.")

    unknown_keys = set(devicepaths.keys()) - set(handlers.keys())
    if unknown_keys:
        raise ValueError(f"Unknown devicepaths in capture config: {sorted(unknown_keys)}")

    for key, raw_value in devicepaths.items():
        handlers[key](_config_path_value(key, raw_value))


def load_capture_config_sections(path, plugin_name, legacy_plugin_keys=None):
    config_path = Path(path)
    with open(config_path, "r") as infile:
        data = json.load(infile)
    if not isinstance(data, dict):
        raise ValueError("Capture config must be a JSON object.")

    legacy_plugin_keys = set(legacy_plugin_keys or ())
    if legacy_plugin_keys and set(data.keys()) & legacy_plugin_keys:
        return {}, data, True

    allowed_top_level = {"devicepaths", "plugin"}
    unknown_top_level = set(data.keys()) - allowed_top_level
    if unknown_top_level:
        raise ValueError(
            f"Unknown top-level keys in capture config: {sorted(unknown_top_level)}"
        )

    devicepaths = data.get("devicepaths", {})
    plugin_sections = data.get("plugin", {})
    if not isinstance(plugin_sections, dict):
        raise ValueError("'plugin' must be a JSON object.")

    plugin_config_present = plugin_name in plugin_sections
    plugin_config = plugin_sections.get(plugin_name, {})
    return devicepaths, plugin_config, plugin_config_present


def load_plugin_capture_config(
    path,
    plugin_name,
    apply_devicepaths,
    plugin_config_handler=None,
    legacy_plugin_keys=None,
):
    devicepaths, plugin_config, plugin_config_present = load_capture_config_sections(
        path,
        plugin_name,
        legacy_plugin_keys=legacy_plugin_keys,
    )
    apply_devicepaths(devicepaths)
    if not plugin_config_present:
        return
    if not isinstance(plugin_config, dict):
        raise ValueError(f"'plugin.{plugin_name}' must be a JSON object.")
    if plugin_config_handler:
        plugin_config_handler(plugin_config)
