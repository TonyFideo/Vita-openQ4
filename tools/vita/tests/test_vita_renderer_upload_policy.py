from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "src/renderer/RendererUpload.cpp"


def extract_function(text: str, signature: str) -> str:
    start = text.index(signature)
    opening = text.index("{", start)
    depth = 1
    for pos in range(opening + 1, len(text)):
        depth += (text[pos] == "{") - (text[pos] == "}")
        if depth == 0:
            return text[start:pos + 1]
    raise AssertionError("unterminated function")


class VitaRendererUploadPolicyTests(unittest.TestCase):
    def setUp(self):
        self.text = SOURCE.read_text(encoding="utf-8")

    def test_vita_budget_and_rotation_cover_vitagl_gc_window(self):
        megs = int(re.search(r"VITA_RENDERER_UPLOAD_MAX_MEGS\s*=\s*(\d+)", self.text).group(1))
        slots = int(re.search(r"VITA_RENDERER_UPLOAD_FRAME_BUFFERS\s*=\s*(\d+)", self.text).group(1))
        # Pinned VitaGL has FRAME_PURGE_FREQ=4. A slot reused after five
        # presented frames is outside its copy-on-write/GC protection window.
        self.assertEqual(megs, 4)
        self.assertEqual(slots, 5)
        self.assertGreater(slots, 4)
        self.assertLessEqual(megs * slots, 20)
        # Previous defaults reserved 64 MiB, then attempted another 16 MiB
        # orphan at BeginFrame. Keep the new persistent footprint far below it.
        self.assertLess(megs * slots, 16 * 4)

    def test_vita_begin_frame_does_not_orphan_full_ring(self):
        begin = extract_function(self.text, "void idUploadManager::BeginFrame( int frameCount )")
        marker = "#if defined(VITA) || defined(__vita__)"
        self.assertIn(marker, begin)
        vita = begin.split(marker, 1)[1].split("#else", 1)[0]
        desktop = begin.split("#else", 1)[1].split("#endif", 1)[0]
        self.assertNotIn("glBufferDataARB", vita)
        self.assertIn("(void)frame;", vita)
        self.assertIn("glBufferDataARB", desktop)

    def test_platform_cap_does_not_mutate_public_cvars(self):
        init = extract_function(self.text, "void idUploadManager::Init( const renderBackendCaps_t &caps )")
        self.assertIn("ringMegs = Min( ringMegs, VITA_RENDERER_UPLOAD_MAX_MEGS );", init)
        self.assertIn("frameBufferCount = VITA_RENDERER_UPLOAD_FRAME_BUFFERS;", init)
        self.assertNotIn("r_rendererUploadMegs.Set", init)
        self.assertNotIn("r_rendererUploadFrameBuffers.Set", init)


if __name__ == "__main__":
    unittest.main()
