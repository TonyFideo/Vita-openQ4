from __future__ import annotations
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location("compact", Path(__file__).resolve().parents[1] / "compact_vita3k_log.py")
compact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compact)
BOOT = b"[01:02:03.000] |I| [load_app_impl]: CPU Optimisation state: true\n"


class CompactLogTests(unittest.TestCase):
    def test_concatenated_partial_launch(self):
        data = BOOT + b"old\n[00:00:00.000] |I| [old]: partial" + BOOT + b"NEW\xff"
        latest, count, offset = compact.split_latest(data)
        self.assertEqual(count, 2)
        self.assertEqual(latest, BOOT + b"NEW\xff")
        self.assertEqual(data[offset:], latest)

    def test_unknown_format_is_not_discarded(self):
        self.assertEqual(compact.split_latest(b"unknown"), (b"unknown", 0, 0))

    def test_only_known_noise_is_grouped(self):
        log = BOOT + (
            '[01:02:04.000] |E| [stat_file]: Missing file at "optional.dds"\n'
            '[01:02:04.000] |W| [io_error_impl]: stat_file returned 0x80010002\n'
            '[01:02:04.000] |T| [read_dir]: item\n'
            '[01:02:04.000] |I| [export_sceIoOpen]: Opening file: x -> fd 7\n'
            '[01:02:04.000] |I| [export_sceIoOpen]: Opening file: x -> FAILED 0x80010009\n'
            '[01:02:04.000] |W| [io_error_impl]: stat_file returned 0x80010009\n'
            '[01:02:04.000] |E| [engine]: Unknown error\n'
            '[01:02:04.000] |C| [exception_handler]: Access violation\n'
            'PC=0x81000000\nLR=0x81001000\nbacktrace\n'
        ).encode()
        text, stats = compact.compact_view(log, 0)
        self.assertNotIn('"optional.dds"', text)
        self.assertIn('expected_missing_path', text)
        self.assertIn('FAILED 0x80010009', text)
        self.assertIn('stat_file returned 0x80010009', text)
        self.assertIn('PC=0x81000000\nLR=0x81001000\nbacktrace', text)
        self.assertEqual(sum(stats['suppressed_events'].values()), 4)

    def test_tail_includes_trace_and_partial_line(self):
        tail = b'[01:02:04.000] |T| [open_file]: partial'
        text, _ = compact.compact_view(BOOT + tail, 1)
        self.assertTrue(text.endswith(tail.decode()))

    def test_zip_is_lossless_and_input_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.log'
            data = BOOT + b'old' + BOOT + b'new\r\n\xffpartial'
            source.write_bytes(data)
            attachment = root / 'loading.log'
            attachment.write_bytes(b'loading')
            report = compact.build_report(source, root / 'report', [attachment])
            with zipfile.ZipFile(root / 'report/diagnostics.zip') as z:
                self.assertEqual(z.read('latest_boot.full.log'), BOOT + b'new\r\n\xffpartial')
                self.assertEqual(z.read('attachments/01_loading.log'), b'loading')
            self.assertEqual(source.read_bytes(), data)
            self.assertEqual(report['source_sha256'], hashlib.sha256(data).hexdigest())
            with self.assertRaises(FileExistsError):
                compact.build_report(source, root / 'report', [])

    def test_cannot_replace_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'latest_boot.compact.log'
            source.write_bytes(BOOT)
            with self.assertRaises(ValueError):
                compact.build_report(source, root, [], overwrite=True)
            self.assertEqual(source.read_bytes(), BOOT)

    def test_empty_and_invalid_tail(self):
        text, stats = compact.compact_view(b'')
        self.assertIn('TIMELINE', text)
        self.assertEqual(stats['last_launch_bytes'], 0)
        with self.assertRaises(ValueError):
            compact.compact_view(BOOT, -1)


if __name__ == '__main__':
    unittest.main()
