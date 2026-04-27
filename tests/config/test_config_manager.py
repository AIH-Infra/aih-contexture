from aih_contexture.utils.config_manager import ConfigManager


def test_app_settings_round_trip(tmp_path):
    manager = ConfigManager(config_dir=str(tmp_path))

    assert manager.load_app_settings() == {}

    assert manager.save_app_settings({"output_dir": "saved-output"})
    assert manager.load_app_settings() == {"output_dir": "saved-output"}


def test_list_configs_excludes_reserved_app_settings(tmp_path):
    manager = ConfigManager(config_dir=str(tmp_path))

    assert manager.save_app_settings({"output_dir": "saved-output"})
    assert manager.save_config(
        "demo",
        {"global": {"conversion_mode": "pipeline"}, "pipeline": {}},
        overwrite=True,
    )

    names = [config["name"] for config in manager.list_configs()]

    assert "demo" in names
    assert manager.APP_SETTINGS_NAME not in names
