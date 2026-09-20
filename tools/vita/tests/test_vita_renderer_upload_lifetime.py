from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[3]
CPP = (ROOT / "src/renderer/RendererUpload.cpp").read_text(encoding="utf-8")
HDR = (ROOT / "src/renderer/RendererUpload.h").read_text(encoding="utf-8")
DEBUG = (ROOT / "src/sys/vita/vita_debug_screen.cpp").read_text(encoding="utf-8")


class VitaRendererUploadLifetimeTests(unittest.TestCase):
    def test_vita_uses_vitagl_presentation_clock(self):
        self.assertIn("vglGetFrameNumber()", CPP)
        self.assertIn("SelectVitaFrameBufferForFrame", CPP)
        self.assertIn("vitaLastUseFrame", HDR)
        self.assertIn("VITA_RENDERER_UPLOAD_REUSE_WINDOW = 4u", CPP)

    def test_slot_age_is_checked_before_reuse(self):
        start = CPP.index("bool idUploadManager::SelectVitaFrameBufferForFrame")
        end = CPP.index("bool idUploadManager::SelectFrameBufferForFrame", start)
        block = CPP[start:end]
        self.assertIn("vitaFrame - lastUse", block)
        self.assertIn("> VITA_RENDERER_UPLOAD_REUSE_WINDOW", block)
        self.assertIn("glFinish()", block)
        self.assertIn("VITA_RENDERER_UPLOAD_UNUSED_FRAME", block)

    def test_frame_stream_maps_existing_backing_instead_of_subdata_cow(self):
        start = CPP.index("bool idUploadManager::AllocFrameTemp")
        end = CPP.index("bool idUploadManager::AllocStaticBuffer", start)
        block = CPP[start:end]
        vita_start = block.index("#if defined(VITA) || defined(__vita__)")
        vita_end = block.index("#else", vita_start)
        vita = block[vita_start:vita_end]
        self.assertIn("glMapBufferRange", vita)
        self.assertIn("glUnmapBuffer", vita)
        self.assertNotIn("glBufferSubDataARB", vita)
        self.assertIn("frame.vitaLastUseFrame = vglGetFrameNumber()", vita)

    def test_ring_profile_still_preserves_quality_and_capacity(self):
        self.assertIn("VITA_RENDERER_UPLOAD_MAX_MEGS = 4", CPP)
        self.assertIn("VITA_RENDERER_UPLOAD_FRAME_BUFFERS = 5", CPP)
        self.assertNotIn("defineicon", CPP.lower())

    def test_display_comment_does_not_repeat_disproved_queue_race(self):
        self.assertIn("executes the display callback before removing it from the queue", DEBUG)
        self.assertNotIn("removes a callback from the queue before executing it", DEBUG)


if __name__ == "__main__":
    unittest.main()
