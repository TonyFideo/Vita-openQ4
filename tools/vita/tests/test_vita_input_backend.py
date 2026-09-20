import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVENTS = ROOT / "src" / "sys" / "vita" / "vita_events.cpp"
PROFILE = ROOT / "content" / "baseoq4" / "pak0" / "openq4_profile_vita.cfg"
COMMON = ROOT / "src" / "framework" / "Common.cpp"


class VitaInputBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events = EVENTS.read_text(encoding="utf-8")
        cls.profile = PROFILE.read_text(encoding="utf-8")
        cls.common = COMMON.read_text(encoding="utf-8")

    def test_uses_native_scectrl_analog_wide_sampling(self):
        self.assertIn("#include <psp2/ctrl.h>", self.events)
        self.assertIn("sceCtrlSetSamplingMode( SCE_CTRL_MODE_ANALOG_WIDE )", self.events)
        self.assertIn("sceCtrlPeekBufferPositive( 0, &pad, 1 )", self.events)

    def test_menu_button_identity_matches_controller_translation(self):
        expected = {
            "SCE_CTRL_CROSS": "K_JOY3",
            "SCE_CTRL_CIRCLE": "K_JOY4",
            "SCE_CTRL_START": "K_JOY7",
            "SCE_CTRL_SELECT": "K_JOY8",
            "SCE_CTRL_UP": "K_JOY9",
            "SCE_CTRL_DOWN": "K_JOY10",
            "SCE_CTRL_RIGHT": "K_JOY11",
            "SCE_CTRL_LEFT": "K_JOY12",
        }
        for physical, logical in expected.items():
            pattern = rf"Vita_SetLogicalKey\( logicalKeys, {logical}, \( buttons & {physical} \) != 0 \)"
            self.assertRegex(self.events, pattern)

    def test_button_transitions_reach_gui_and_usercmd_paths(self):
        transition_block = re.search(
            r"if \( queueTransitions \) \{(?P<body>.*?)\n\t\}",
            self.events,
            re.DOTALL,
        )
        self.assertIsNotNone(transition_block)
        body = transition_block.group("body")
        self.assertIn("Vita_QueueSystemKeyLocked", body)
        self.assertIn("Vita_QueueUsercmdKeyLocked", body)

    def test_joystick_exports_all_idtech_axes(self):
        expected = {
            "AXIS_SIDE": "lookX",
            "AXIS_FORWARD": "lookY",
            "AXIS_UP": "0",
            "AXIS_ROLL": "127",
            "AXIS_YAW": "moveX",
            "AXIS_PITCH": "moveY",
        }
        for axis, value in expected.items():
            self.assertIn(f"vitaJoystickAxisState[{axis}] = {value};", self.events)

    def test_vita_profile_is_accepted_and_auto_selected(self):
        self.assertIn('sanitized.Icmp( "vita" )', self.common)
        self.assertIn('com_platformProfile.SetString( "vita" )', self.common)
        self.assertIn('bind "JOY2" "_attack"', self.profile)
        self.assertIn('bind "JOY1" "_zoom"', self.profile)

    def test_handheld_profile_preserves_menu_face_button_identity(self):
        self.assertIn('bind "JOY3" "_moveup"', self.profile)
        self.assertIn('bind "JOY4" "_movedown"', self.profile)
        self.assertIn('bind "JOY7" "togglemenu"', self.profile)
        self.assertIn('bind "JOY8" "_impulse19"', self.profile)


if __name__ == "__main__":
    unittest.main()
