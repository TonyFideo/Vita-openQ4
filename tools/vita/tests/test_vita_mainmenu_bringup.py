from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[3]
FS = (ROOT / "src/framework/FileSystem.cpp").read_text(encoding="utf-8")
UI = (ROOT / "src/ui/UserInterface.cpp").read_text(encoding="utf-8")
SESSION = (ROOT / "src/framework/Session.cpp").read_text(encoding="utf-8")
WINDOW = (ROOT / "src/ui/Window.cpp").read_text(encoding="utf-8")
MESON = (ROOT / "meson.build").read_text(encoding="utf-8")


class VitaMainMenuBringupTests(unittest.TestCase):
    def test_gui_sources_use_pak_first_with_loose_fallback(self):
        self.assertIn("fs_vitaLooseGuiOverrides", FS)
        self.assertIn("FS_VitaPackedGuiPath", FS)
        self.assertIn('path.Icmpn( "guis/", 5 )', FS)
        self.assertIn('!ext.Icmp( "gui" )', FS)
        block = FS[FS.index("// GUI source files are normally shipped in PK4s"):FS.index("#endif", FS.index("// GUI source files are normally shipped in PK4s"))]
        self.assertIn("FSFLAG_SEARCH_PAKS", block)
        self.assertIn("if ( packedGui != NULL )", block)
        # A miss must not return NULL here: the normal dirs+packs call after
        # #endif remains the loose-development fallback.
        self.assertNotIn("return NULL", block)

    def test_mainmenu_has_memory_and_parser_checkpoints(self):
        for marker in (
            "MAINMENU: metadata",
            "MAINMENU: lexer LoadFile",
            "MAINMENU: parse desktop",
            "MAINMENU: FixupParms OK",
            "sceKernelGetFreeMemorySize",
        ):
            self.assertIn(marker, UI)
        self.assertIn("SceSysmem_stub", MESON)

    def test_session_and_window_progress_are_bounded(self):
        self.assertIn("SESSION: cargando mainmenu", SESSION)
        self.assertIn("SESSION: precarga mainmenu OK", SESSION)
        self.assertIn("MAINMENU parse: %d ventanas", WINDOW)
        self.assertRegex(WINDOW, r"vitaMainMenuWindowCount\s*%\s*32")
        self.assertIn("MAINMENU parse completo", WINDOW)


if __name__ == "__main__":
    unittest.main()
