from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[3]
DC_H = (ROOT / "src/ui/DeviceContext.h").read_text(encoding="utf-8")
DC_CPP = (ROOT / "src/ui/DeviceContext.cpp").read_text(encoding="utf-8")
WINDOW = (ROOT / "src/ui/Window.cpp").read_text(encoding="utf-8")
IMAGE = (ROOT / "src/renderer/Image_load.cpp").read_text(encoding="utf-8")


class VitaLazyDefineIconTests(unittest.TestCase):
    def test_register_icon_supports_deferred_residency(self):
        self.assertIn("bool preload = true", DC_H)
        self.assertIn("if ( preload )", DC_CPP)
        self.assertIn("ICON deferred:", DC_CPP)

    def test_vita_defineicon_is_registered_without_preload(self):
        block = WINDOW[WINDOW.index('else if (token == "defineicon")'):WINDOW.index('// jmarshall end', WINDOW.index('else if (token == "defineicon")'))]
        self.assertIn("RegisterIcon( keyToken.c_str(), valueToken.c_str(), iconX, iconY, iconW, iconH, false )", block)
        self.assertIn("MAINMENU defineicon diferido", block)

    def test_first_use_makes_lazy_icon_resident(self):
        start = DC_CPP.index("bool idDeviceContext::FindIcon")
        end = DC_CPP.index("float idDeviceContext::GetIconDisplayWidth", start)
        block = DC_CPP[start:end]
        self.assertIn("EnsureNotPurged", block)
        self.assertIn("ICON lazy load:", block)
        self.assertIn("SizeIcon( *foundIcon )", block)

    def test_gui_upload_has_mip_checkpoints(self):
        self.assertIn("GPU plan:", IMAGE)
        self.assertIn("GPU mip %d/%d:", IMAGE)
        self.assertIn("GPU mip OK %d/%d:", IMAGE)
        self.assertIn('idStr::Icmpn( GetName(), "gfx/guis/", 9 )', IMAGE)

    def test_mainmenu_progress_is_more_granular(self):
        self.assertRegex(WINDOW, r"vitaMainMenuWindowCount\s*%\s*32")


if __name__ == "__main__":
    unittest.main()
