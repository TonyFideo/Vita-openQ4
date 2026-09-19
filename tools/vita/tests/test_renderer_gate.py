import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("build_engine", Path(__file__).resolve().parents[1] / "build_engine.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

class RendererGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "compile_commands.json"

    def objects(self, entries):
        self.database.write_text(json.dumps(entries), encoding="utf-8")
        return build.renderer_objects(self.database, "openQ4-client_armv7")

    def test_filters_target_source_and_duplicates(self):
        entry = {"file": "../../src/renderer/ModernClusteredLighting.cpp", "output": "openQ4-client_armv7.p/cluster.o"}
        self.assertEqual(self.objects([entry, entry,
            {"file": entry["file"], "output": "openQ4-ded_armv7.p/cluster.o"},
            {"file": "src/sound/snd_system.cpp", "output": "openQ4-client_armv7.p/sound.o"}]), [entry["output"]])

    def test_arguments_and_subdirectories(self):
        output = "openQ4-client_armv7.p/texture.o"
        self.assertEqual(self.objects([{"file": "src/renderer/OpenGL/gl_Image.cpp", "arguments": ["cc", "-o", output]}]), [output])

    def test_quoted_command_and_absolute_output(self):
        output = "/build with spaces/openQ4-client_armv7.p/shader.o"
        self.assertEqual(self.objects([{"file": "src/renderer/GLES_D3/gles_program.cpp", "command": "cc -o '" + output + "'"}]), [output])

    def test_windows_separators(self):
        self.assertEqual(self.objects([{"file": "src\\renderer\\GLStateCache.cpp", "output": "openQ4-client_armv7.p\\state.o"}]), ["openQ4-client_armv7.p/state.o"])

    def test_no_renderer_is_failure(self):
        with self.assertRaises(ValueError): self.objects([])

    def test_missing_output_is_failure(self):
        with self.assertRaises(ValueError): self.objects([{"file": "src/renderer/GLStateCache.cpp", "command": "cc -c x.cpp"}])

if __name__ == "__main__": unittest.main()
