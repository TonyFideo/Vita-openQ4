"""Keep shader image units separate from fixed-function client texture state.

The GLES_D3 backend addresses several sampler image units, while VitaGL's FFP
compatibility layer intentionally implements only a few client texcoord arrays.
These tests preprocess the production functions so a future merge cannot put
sampler selection back through glClientActiveTexture or fixed-function target
enables. No limit is raised and no VitaGL error is suppressed.
"""
from pathlib import Path
import importlib.util
import os
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[3]


def function(path: Path, signature: str) -> str:
    spec = importlib.util.spec_from_file_location(
        'state_patch_util', ROOT / 'tools/vita/patch_vitagl_vita3k_linear.py')
    util = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(util)
    text = path.read_text()
    a, b = util.function_span(text, signature)
    return text[a:b]


def preprocess(source: str, gles: bool) -> str:
    cpp = ['cpp', '-P']
    if gles:
        cpp.append('-DOPENQ4_RENDERER_GLES_MODULE=1')
    result = subprocess.run(cpp, input=source, text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout


class ProgrammableTextureStateTest(unittest.TestCase):
    def test_sampler_selection_does_not_select_ffp_client_coordinates(self):
        body = function(ROOT / 'src/renderer/tr_backend.cpp', 'void GL_SelectTexture(')
        gles = preprocess(body, True)
        legacy = preprocess(body, False)
        self.assertIn('glActiveTextureARB', gles)
        self.assertNotIn('glClientActiveTextureARB', gles)
        self.assertIn('glActiveTextureARB', legacy)
        self.assertIn('glClientActiveTextureARB', legacy)

    def test_image_bind_does_not_toggle_fixed_function_targets_on_gles(self):
        body = function(ROOT / 'src/renderer/Image_load.cpp', 'void idImage::Bind()')
        gles = preprocess(body, True)
        legacy = preprocess(body, False)
        for call in ('glEnable(GL_TEXTURE_2D)', 'glDisable(GL_TEXTURE_2D)',
                     'glEnable(GL_TEXTURE_CUBE_MAP_EXT)', 'glDisable(GL_TEXTURE_CUBE_MAP_EXT)'):
            self.assertNotIn(call, re.sub(r'\s+', '', gles))
        compact_legacy = re.sub(r'\s+', '', legacy)
        self.assertIn('glEnable(GL_TEXTURE_2D)', compact_legacy)
        self.assertIn('glDisable(GL_TEXTURE_CUBE_MAP_EXT)', compact_legacy)
        self.assertIn('R_BindTextureToUnit', gles)

    def test_bind_null_unbinds_programmable_target_and_restores_server_unit(self):
        bind_null = function(ROOT / 'src/renderer/ImageManager.cpp', 'void idImageManager::BindNull()')
        unbind_all = function(ROOT / 'src/renderer/ImageManager.cpp', 'void idImageManager::UnbindAll()')
        gles = re.sub(r'\s+', '', preprocess(bind_null, True))
        legacy = re.sub(r'\s+', '', preprocess(bind_null, False))
        self.assertIn('glBindTexture(GL_TEXTURE_CUBE_MAP_EXT,0)', gles)
        self.assertIn('glBindTexture(GL_TEXTURE_2D,0)', gles)
        self.assertIn('tmu->currentCubeMap=0', gles)
        self.assertIn('tmu->current2DMap=0', gles)
        self.assertNotIn('glDisable(GL_TEXTURE_CUBE_MAP_EXT)', gles)
        self.assertIn('glDisable(GL_TEXTURE_CUBE_MAP_EXT)', legacy)
        self.assertIn('GL_SelectTextureNoClient(oldTMU)', re.sub(r'\s+', '', unbind_all))
        self.assertNotIn('backEnd.glState.currenttmu=oldTMU;', re.sub(r'\s+', '', unbind_all).split('else{',1)[0])

    def test_vitagl_image_units_are_not_ffp_coordinate_units(self):
        root = os.environ.get('VOQ_VITAGL_SOURCE')
        if not root:
            self.skipTest('patched pinned VitaGL source required')
        shared = (Path(root) / 'source/shared.h').read_text()
        image_units = int(re.search(r'#define TEXTURE_IMAGE_UNITS_NUM\s+(\d+)', shared)[1])
        normal_coords = int(re.search(r'#else\s*\n#define TEXTURE_COORDS_NUM\s+(\d+)', shared)[1])
        high_coords = int(re.search(r'#ifdef HAVE_HIGH_FFP_TEXUNITS\s*\n#define TEXTURE_COORDS_NUM\s+(\d+)', shared)[1])
        self.assertGreaterEqual(image_units, 6)
        self.assertLess(normal_coords, 6)
        self.assertLess(high_coords, 6)
        client = function(Path(root) / 'source/ffp.c', 'void glClientActiveTexture(')
        self.assertIn('TEXTURE_COORDS_NUM', client)
        print(f'PASS VitaGL separates {image_units} image units from {normal_coords}/{high_coords} FFP client-coordinate sets')


if __name__ == '__main__':
    unittest.main()
