"""Cinematic fast-forward keeps simulation but defers unpublished RenderWorld state."""
from pathlib import Path
import importlib.util
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]


def load_wrapper():
    path=ROOT/'tools/vita/stage_gamelibs_vita.py'
    spec=importlib.util.spec_from_file_location('vita_stage',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def function(text, signature):
    start=text.index(signature); opening=text.index('{',start); depth=0
    for i in range(opening,len(text)):
        if text[i]=='{': depth+=1
        elif text[i]=='}':
            depth-=1
            if depth==0:return text[start:i+1]
    raise AssertionError(signature)


class CinematicPresentationGateTest(unittest.TestCase):
    def test_staged_game_exposes_exact_skip_state_without_timing_changes(self):
        wrapper=load_wrapper()
        with tempfile.TemporaryDirectory(prefix='voq-vita-game-') as directory:
            root=Path(directory)
            game=root/'src/game';game.mkdir(parents=True)
            (game/'Game.h').write_text(
                'class idGame {\npublic:\n\tvirtual bool\t\t\t\tInCinematic( void ) = 0;\n};\n')
            (game/'Game_local.h').write_text(
                'class idGameLocal {\npublic:\n\tbool\t\t\t\t\tInCinematic( void ) { return inCinematic; }\n'
                'bool inCinematic; bool skipCinematic;\n};\n')
            wrapper.apply_vita_game_patches(root)
            interface=(game/'Game.h').read_text()
            local=(game/'Game_local.h').read_text()
            self.assertEqual(interface.count('IsCinematicFastForwarding'),1)
            self.assertIn('IsCinematicFastForwarding( void ) { return skipCinematic; }',local)
            combined=interface+local
            for forbidden in ('time +=','GetMSec()','RunFrame(','com_ticNumber','cinematicMaxSkipTime ='):
                self.assertNotIn(forbidden,combined)

    def test_source_drift_fails_instead_of_fuzzy_patch(self):
        wrapper=load_wrapper()
        with tempfile.TemporaryDirectory(prefix='voq-vita-game-drift-') as directory:
            root=Path(directory);game=root/'src/game';game.mkdir(parents=True)
            (game/'Game.h').write_text('changed upstream interface\n')
            (game/'Game_local.h').write_text('changed upstream local\n')
            with self.assertRaises(RuntimeError):
                wrapper.apply_vita_game_patches(root)

    def test_renderworld_gates_only_add_update_publication(self):
        text=(ROOT/'src/renderer/RenderWorld.cpp').read_text()
        helper=function(text,'static ID_INLINE bool R_DeferCinematicFastForwardPresentation( void )')
        self.assertIn('game->IsCinematicFastForwarding()',helper)
        add_entity=function(text,'qhandle_t idRenderWorldLocal::AddEntityDef(')
        update_entity=function(text,'void idRenderWorldLocal::UpdateEntityDef(')
        add_light=function(text,'qhandle_t idRenderWorldLocal::AddLightDef(')
        update_light=function(text,'void idRenderWorldLocal::UpdateLightDef(')
        self.assertIn('return -1;',add_entity)
        self.assertIn('return;',update_entity)
        self.assertIn('return -1;',add_light)
        self.assertIn('return;',update_light)
        for signature in ('void idRenderWorldLocal::FreeEntityDef(', 'void idRenderWorldLocal::FreeLightDef(',
                          'bool idRenderWorldLocal::UpdateEffectDef('):
            self.assertNotIn('R_DeferCinematicFastForwardPresentation',function(text,signature))

    def test_vita_only_uses_adapted_stage(self):
        meson=(ROOT/'meson.build').read_text()
        marker="if host_system == 'vita'"
        start=meson.index(marker,meson.index('game_stage_script ='))
        block=meson[start:meson.index('game_stage_result =',start)]
        self.assertIn("tools' / 'vita' / 'stage_gamelibs_vita.py",block)
        self.assertIn("tools' / 'build' / 'stage_gamelibs.py",meson[:start])

if __name__=='__main__':
    unittest.main()
