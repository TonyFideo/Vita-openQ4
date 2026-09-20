from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
LIST_HEADER = (ROOT / "src/ui/ListWindow.h").read_text(encoding="utf-8")
LIST_SOURCE = (ROOT / "src/ui/ListWindow.cpp").read_text(encoding="utf-8")
GUI_SCRIPT = (ROOT / "src/ui/GuiScript.cpp").read_text(encoding="utf-8")
WINDOW_SOURCE = (ROOT / "src/ui/Window.cpp").read_text(encoding="utf-8")
MAINMENU = (ROOT / "content/baseoq4/pak0/guis/mainmenu.gui").read_text(encoding="utf-8")


def function(text: str, signature: str) -> str:
    start = text.index(signature)
    opening = text.index("{", start)
    depth = 1
    for pos in range(opening + 1, len(text)):
        depth += (text[pos] == "{") - (text[pos] == "}")
        if depth == 0:
            return text[start:pos + 1]
    raise AssertionError("unterminated function: " + signature)


class VitaGuiMenuRuntimeTests(unittest.TestCase):
    def test_list_row_materials_are_preloaded(self):
        post_parse = function(LIST_SOURCE, "void idListWindow::PostParse()")
        draw = function(LIST_SOURCE, "void idListWindow::Draw(")
        self.assertIn("ResolveRowMaterials();", post_parse)
        self.assertIn("ResolveRowMaterials();", draw)
        self.assertIn("rowFocusMaterial", LIST_HEADER)
        self.assertIn("rowLineMaterial", LIST_HEADER)
        self.assertNotIn("openQ4_ListMaterial( backgroundFocus.c_str() )", draw)
        self.assertNotIn("openQ4_ListMaterial( backgroundLine.c_str() )", draw)
        self.assertNotIn("openQ4_ListMaterial( backgroundHover.c_str() )", draw)
        self.assertNotIn("openQ4_ListMaterial( backgroundGreyed.c_str() )", draw)

    def test_named_reset_time_never_falls_back_to_caller(self):
        reset_time = function(GUI_SCRIPT, "void Script_ResetTime(")
        named_branch = reset_time[reset_time.index("if ( src->Num() > 1 )"):]
        self.assertIn("target == NULL || target->win == NULL", named_branch)
        self.assertIn("was not found as a full window", named_branch)
        self.assertIn("return;", named_branch)
        self.assertIn("target->win->ResetTime", named_branch)
        self.assertIn("window->ResetTime", reset_time)
        self.assertLess(named_branch.index("target->win->ResetTime"), reset_time.rindex("window->ResetTime"))

    def test_zero_duration_transitions_apply_immediately(self):
        transition = function(GUI_SCRIPT, "void Script_Transition(")
        self.assertIn("if ( time <= 0 )", transition)
        self.assertIn("(*src)[0].var->Set( (*src)[2].var->c_str() );", transition)
        immediate = transition[transition.index("if ( time <= 0 )"):]
        self.assertLess(immediate.index("return;"), immediate.index("window->AddTransition"))

    def test_settings_container_is_activated_before_tab_branch(self):
        start = MAINMENU.index("windowDef anim_settingsIn")
        end = MAINMENU.index("windowDef anim_settingsOut", start)
        settings_in = MAINMENU[start:end]
        visible = 'set "p_settings::visible" "1" ;'
        first_tab = 'if ( "desktop::dest" == 4 )'
        self.assertEqual(settings_in.count(visible), 1)
        self.assertLess(settings_in.index(visible), settings_in.index(first_tab))

    def test_vita_settings_transition_has_runtime_markers(self):
        reset_time = function(GUI_SCRIPT, "void Script_ResetTime(")
        timeline = function(WINDOW_SOURCE, "void idWindow::Time()")
        redraw = function(WINDOW_SOURCE, "void idWindow::Redraw(float x, float y)")
        self.assertIn("[VOQ4][gui] resetTime", reset_time)
        self.assertIn("[VOQ4][gui] onTime", timeline)
        self.assertIn("anim_settingsIn", timeline)
        self.assertIn("destValue", timeline)
        self.assertIn("[VOQ4][gui] p_settings visible=", redraw)


if __name__ == "__main__":
    unittest.main()
