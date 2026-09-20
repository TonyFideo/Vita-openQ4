from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
DEBUG_H = (ROOT / "src/sys/vita/vita_debug_screen.h").read_text(encoding="utf-8")
DEBUG_CPP = (ROOT / "src/sys/vita/vita_debug_screen.cpp").read_text(encoding="utf-8")
HUD = (ROOT / "src/sys/vita/vita_loading_hud.cpp").read_text(encoding="utf-8")
GLIMP = (ROOT / "src/sys/vita/vita_glimp.cpp").read_text(encoding="utf-8")
DC_H = (ROOT / "src/ui/DeviceContext.h").read_text(encoding="utf-8")
DC_CPP = (ROOT / "src/ui/DeviceContext.cpp").read_text(encoding="utf-8")
WINDOW = (ROOT / "src/ui/Window.cpp").read_text(encoding="utf-8")


class VitaDisplayOwnershipTests(unittest.TestCase):
    def test_release_requires_display_detach(self):
        self.assertIn("bool VitaDiagScreen_ReleaseBackingIfDetached", DEBUG_H)
        self.assertIn("sceDisplayGetFrameBuf", DEBUG_CPP)
        self.assertIn("activeFrame.base == vitaDisplayFrame.base", DEBUG_CPP)
        compare = DEBUG_CPP.index("activeFrame.base == vitaDisplayFrame.base")
        free = DEBUG_CPP.index("sceKernelFreeMemBlock( vitaDisplayBlock )", compare)
        self.assertGreater(free, compare)

    def test_failed_ownership_check_keeps_handoff_pending(self):
        start = HUD.index("void VitaLoadingHud_EndRendererHandoff")
        end = HUD.index("bool VitaLoadingHud_RendererHandoffComplete", start)
        block = HUD[start:end]
        self.assertIn("if ( !VitaDiagScreen_ReleaseBackingIfDetached() )", block)
        self.assertIn("return;", block)
        self.assertGreater(block.index("rendererHandoffComplete = true"), block.index("ReleaseBackingIfDetached"))

    def test_swap_retries_until_display_confirms_handoff(self):
        start = GLIMP.index("void GLimp_SwapBuffers")
        end = GLIMP.index("void GLimp_SetGamma", start)
        block = GLIMP[start:end]
        self.assertLess(block.index("vglSwapBuffers"), block.index("VitaLoadingHud_EndRendererHandoff"))
        self.assertIn("!VitaLoadingHud_RendererHandoffComplete()", block)

    def test_defineicon_keeps_engine_semantics(self):
        self.assertNotIn("bool preload = true", DC_H)
        start = DC_CPP.index("void idDeviceContext::RegisterIcon")
        end = DC_CPP.index("void idDeviceContext::RegisterBuiltinIcons", start)
        block = DC_CPP[start:end]
        self.assertIn("EnsureNotPurged", block)
        self.assertNotIn("ICON deferred", block)

        start = WINDOW.index('else if (token == "defineicon")')
        end = WINDOW.index("// jmarshall end", start)
        block = WINDOW[start:end]
        self.assertIn("dc->RegisterIcon( keyToken.c_str(), valueToken.c_str(), iconX, iconY, iconW, iconH );", block)
        self.assertNotIn("defineicon diferido", block)
        self.assertNotIn(", false )", block)


if __name__ == "__main__":
    unittest.main()
