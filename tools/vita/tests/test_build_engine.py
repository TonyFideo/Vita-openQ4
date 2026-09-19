"""Host regressions for the Vita build gate; no VitaSDK required."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "build_engine.py"
spec = importlib.util.spec_from_file_location("vita_build_engine", MODULE)
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class BuildDriverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def database(self, entries):
        path = self.root / "compile_commands.json"
        path.write_text(json.dumps(entries), encoding="utf-8")
        return path

    def test_filters_and_deduplicates_real_sound_objects(self):
        entries = [
            {"file": "../../src/sound/snd_system.cpp", "output": "snd.o"},
            {"file": "../../src/sound/snd_system.cpp", "output": "snd.o"},
            {"file": "../../src/framework/Common.cpp", "output": "common.o"},
        ]
        self.assertEqual(build.sound_objects(self.database(entries)), ["snd.o"])

    def test_command_fallback_handles_spaces(self):
        entries = [{"file": "../src/sound/snd_world.cpp", "command": "g++ -c a.cpp -o 'path with space/a.o'"}]
        self.assertEqual(build.sound_objects(self.database(entries)), ["path with space/a.o"])

    def test_argument_array_fallback(self):
        entries = [{"file": "../src/sound/snd_world.cpp", "arguments": ["g++", "-o", "world.o"]}]
        self.assertEqual(build.sound_objects(self.database(entries)), ["world.o"])

    def test_empty_sound_gate_is_an_error(self):
        with self.assertRaises(ValueError):
            build.sound_objects(self.database([]))

    def test_missing_output_is_an_error(self):
        with self.assertRaises(ValueError):
            build.sound_objects(self.database([{"file": "src/sound/voice.cpp", "command": "cc -c voice.cpp"}]))

    def run_child(self, code):
        output = io.StringIO()
        log = self.root / "run.log"
        with redirect_stdout(output):
            result = build.run_logged([sys.executable, "-c", code], log, "test")
        return result, log.read_text(), output.getvalue()

    def test_preserves_failure_and_keeps_complete_log(self):
        result, log, console = self.run_child("print('warning: background'); print('fatal error: missing.h'); raise SystemExit(7)")
        self.assertEqual(result, 7)
        self.assertIn("warning: background", log)
        self.assertIn("fatal error: missing.h", console)
        self.assertNotIn("warning: background", console)

    def test_success_is_not_inferred_from_warning_text(self):
        result, log, console = self.run_child("print('warning: this is not an error: example')")
        self.assertEqual(result, 0)
        self.assertIn("PASS", console)

    def test_failure_without_compiler_diagnostic_has_tail(self):
        result, log, console = self.run_child("print('compiler killed'); raise SystemExit(2)")
        self.assertEqual(result, 2)
        self.assertIn("compiler killed", console)

    def test_diagnostic_output_is_bounded_but_log_is_complete(self):
        result, log, console = self.run_child("[print('error: item', i) for i in range(200)]; raise SystemExit(1)")
        self.assertEqual(result, 1)
        self.assertEqual(sum(line.startswith("error: item") for line in log.splitlines()), 200)
        self.assertEqual(console.count("error: item"), 24)


if __name__ == "__main__":
    unittest.main()
