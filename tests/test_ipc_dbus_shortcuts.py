# ABOUTME: Tests for KGlobalAccel shortcut parsing in D-Bus IPC
# ABOUTME: Verifies shortcut string parsing to Qt key codes and signal handling

import pytest
from PyQt6.QtCore import Qt
from eloGraf.ipc_dbus import IPCDBus


@pytest.fixture
def ipc_dbus():
    """Create IPCDBus instance for testing"""
    return IPCDBus(app_id="elograf_test")


def test_parse_simple_key(ipc_dbus):
    """Test parsing single key without modifiers"""
    result = ipc_dbus._parse_shortcut("D")
    assert result is not None
    assert len(result) == 1
    assert result[0] == Qt.Key.Key_D.value


def test_parse_meta_alt_d(ipc_dbus):
    """Test parsing Meta+Alt+D shortcut"""
    result = ipc_dbus._parse_shortcut("Meta+Alt+D")
    assert result is not None
    assert len(result) == 3
    assert Qt.KeyboardModifier.MetaModifier.value in result
    assert Qt.KeyboardModifier.AltModifier.value in result
    assert Qt.Key.Key_D.value in result


def test_parse_ctrl_shift_f1(ipc_dbus):
    """Test parsing Ctrl+Shift+F1 shortcut"""
    result = ipc_dbus._parse_shortcut("Ctrl+Shift+F1")
    assert result is not None
    assert len(result) == 3
    assert Qt.KeyboardModifier.ControlModifier.value in result
    assert Qt.KeyboardModifier.ShiftModifier.value in result
    assert Qt.Key.Key_F1.value in result


def test_parse_super_synonym_for_meta(ipc_dbus):
    """Test that Super is treated as Meta"""
    result = ipc_dbus._parse_shortcut("Super+D")
    assert result is not None
    assert Qt.KeyboardModifier.MetaModifier.value in result
    assert Qt.Key.Key_D.value in result


def test_parse_control_synonym_for_ctrl(ipc_dbus):
    """Test that Control is treated as Ctrl"""
    result = ipc_dbus._parse_shortcut("Control+D")
    assert result is not None
    assert Qt.KeyboardModifier.ControlModifier.value in result
    assert Qt.Key.Key_D.value in result


def test_parse_case_insensitive_modifiers(ipc_dbus):
    """Test that modifiers are case-insensitive"""
    result1 = ipc_dbus._parse_shortcut("CTRL+ALT+D")
    result2 = ipc_dbus._parse_shortcut("ctrl+alt+d")
    result3 = ipc_dbus._parse_shortcut("Ctrl+Alt+D")

    assert result1 is not None
    assert result2 is not None
    assert result3 is not None
    # All should have same modifiers
    assert Qt.KeyboardModifier.ControlModifier.value in result1
    assert Qt.KeyboardModifier.AltModifier.value in result1


def test_parse_empty_string(ipc_dbus):
    """Test parsing empty shortcut string"""
    result = ipc_dbus._parse_shortcut("")
    assert result is None


def test_parse_none(ipc_dbus):
    """Test parsing None"""
    result = ipc_dbus._parse_shortcut(None)
    assert result is None


def test_parse_unknown_key(ipc_dbus):
    """Test parsing shortcut with unknown key"""
    result = ipc_dbus._parse_shortcut("Ctrl+InvalidKey")
    assert result is None


def test_parse_function_keys(ipc_dbus):
    """Test parsing function keys F1-F12"""
    for i in range(1, 13):
        result = ipc_dbus._parse_shortcut(f"F{i}")
        assert result is not None
        assert len(result) == 1
        expected_key = getattr(Qt.Key, f"Key_F{i}").value
        assert result[0] == expected_key


def test_parse_whitespace_handling(ipc_dbus):
    """Test that whitespace around + is handled correctly"""
    result1 = ipc_dbus._parse_shortcut("Ctrl+Alt+D")
    result2 = ipc_dbus._parse_shortcut("Ctrl + Alt + D")
    result3 = ipc_dbus._parse_shortcut("Ctrl  +  Alt  +  D")

    assert result1 is not None
    assert result2 is not None
    assert result3 is not None
    # All should be equivalent
    assert set(result1) == set(result2) == set(result3)


def test_modifier_map_contains_expected_keys(ipc_dbus):
    """Test that MODIFIER_MAP has expected entries"""
    assert 'ctrl' in IPCDBus.MODIFIER_MAP
    assert 'control' in IPCDBus.MODIFIER_MAP
    assert 'alt' in IPCDBus.MODIFIER_MAP
    assert 'shift' in IPCDBus.MODIFIER_MAP
    assert 'meta' in IPCDBus.MODIFIER_MAP
    assert 'super' in IPCDBus.MODIFIER_MAP


def test_supports_global_shortcuts_caching(ipc_dbus):
    """Test that supports_global_shortcuts caches result"""
    # First call should check D-Bus
    result1 = ipc_dbus.supports_global_shortcuts()

    # Second call should use cached value
    result2 = ipc_dbus.supports_global_shortcuts()

    # Results should be consistent
    assert result1 == result2
    assert ipc_dbus._kglobalaccel_available is not None


def test_signal_handler_signature(ipc_dbus):
    """Test that _on_global_shortcut has correct signature for qlonglong timestamp"""
    # Verify the method exists and accepts the right parameters
    handler = ipc_dbus._on_global_shortcut
    assert callable(handler)

    # The handler should accept component (str), unique_name (str), timestamp (int/qlonglong)
    # We can't easily test the pyqtSlot decorator signature, but we can verify the method signature
    import inspect
    sig = inspect.signature(handler)
    params = list(sig.parameters.keys())
    assert 'component' in params
    assert 'unique_name' in params
    assert 'timestamp' in params
