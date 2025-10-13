from eloGraf.base_settings import EngineSettings


def test_engine_settings_basic():
    settings = EngineSettings(engine_type="test-engine", device_name="test-device")
    assert settings.engine_type == "test-engine"
    assert settings.device_name == "test-device"


def test_engine_settings_default_device():
    settings = EngineSettings(engine_type="test-engine")
    assert settings.device_name == "default"
