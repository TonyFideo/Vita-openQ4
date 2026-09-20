"""Render production material GLSL with Mesa/EGL; no Quake assets required.

These tests validate pixel semantics, not VitaGL's GLSL-to-Cg translator or GXM.
The GUI CI job sets VOQ_REQUIRE_GPU_TESTS=1 so missing EGL cannot pass silently.
"""
import ctypes as C
import ctypes.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
P = C.c_void_p
I = C.c_int
U = C.c_uint
F = C.c_float


def shader_source(name):
    text = (ROOT / "src/renderer/GLES_D3/glsl" / name).read_text()
    return text.split('R"(', 1)[1].rsplit(')"', 1)[0]


class OffscreenGL:
    def __init__(self):
        os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
        library = ctypes.util.find_library("EGL")
        if not library:
            raise RuntimeError("libEGL not found")
        self.egl = C.CDLL(library)
        self.display = self.surface = self.context = None
        self.bind_egl("eglGetProcAddress", P, C.c_char_p)
        get_display = self.proc("eglGetPlatformDisplayEXT", P, U, P, P)
        self.bind_egl("eglInitialize", U, P, C.POINTER(I), C.POINTER(I))
        self.bind_egl("eglBindAPI", U, U)
        self.bind_egl("eglChooseConfig", U, P, C.POINTER(I), C.POINTER(P), I, C.POINTER(I))
        self.bind_egl("eglCreatePbufferSurface", P, P, P, C.POINTER(I))
        self.bind_egl("eglCreateContext", P, P, P, P, C.POINTER(I))
        self.bind_egl("eglMakeCurrent", U, P, P, P, P)
        self.bind_egl("eglDestroyContext", U, P, P)
        self.bind_egl("eglDestroySurface", U, P, P)
        self.bind_egl("eglTerminate", U, P)
        try:
            self.display = get_display(0x31DD, None, None)  # EGL_PLATFORM_SURFACELESS_MESA
            major, minor = I(), I()
            if not self.egl.eglInitialize(self.display, C.byref(major), C.byref(minor)):
                raise RuntimeError("surfaceless EGL initialization failed")
            if not self.egl.eglBindAPI(0x30A0):  # EGL_OPENGL_ES_API
                raise RuntimeError("EGL cannot bind OpenGL ES")
            config, count = P(), I()
            attribs = (I * 13)(0x3024, 8, 0x3023, 8, 0x3022, 8, 0x3021, 8,
                               0x3033, 1, 0x3040, 0x40, 0x3038)
            if not self.egl.eglChooseConfig(self.display, attribs, C.byref(config), 1, C.byref(count)) or not count.value:
                raise RuntimeError("no RGBA8 ES3 pbuffer configuration")
            self.surface = self.egl.eglCreatePbufferSurface(self.display, config, (I * 5)(0x3057, 4, 0x3056, 1, 0x3038))
            self.context = self.egl.eglCreateContext(self.display, config, None, (I * 3)(0x3098, 3, 0x3038))
            if not self.surface or not self.context or not self.egl.eglMakeCurrent(self.display, self.surface, self.surface, self.context):
                raise RuntimeError("cannot create/make current ES3 offscreen context")
        except Exception:
            self.close()
            raise
        signatures = {
            "glGetString": (C.c_char_p, U), "glGetError": (U,),
            "glCreateShader": (U, U), "glShaderSource": (None, U, I, C.POINTER(C.c_char_p), P),
            "glCompileShader": (None, U), "glGetShaderiv": (None, U, U, C.POINTER(I)),
            "glGetShaderInfoLog": (None, U, I, P, P), "glDeleteShader": (None, U),
            "glCreateProgram": (U,), "glAttachShader": (None, U, U),
            "glLinkProgram": (None, U), "glGetProgramiv": (None, U, U, C.POINTER(I)),
            "glGetProgramInfoLog": (None, U, I, P, P), "glUseProgram": (None, U),
            "glDeleteProgram": (None, U), "glGetUniformLocation": (I, U, C.c_char_p),
            "glUniform1f": (None, I, F), "glUniform1i": (None, I, I),
            "glUniform4f": (None, I, F, F, F, F),
            "glUniformMatrix4fv": (None, I, I, C.c_ubyte, C.POINTER(F)),
            "glGenVertexArrays": (None, I, C.POINTER(U)), "glBindVertexArray": (None, U),
            "glGenBuffers": (None, I, C.POINTER(U)), "glBindBuffer": (None, U, U),
            "glBufferData": (None, U, C.c_ssize_t, P, U),
            "glEnableVertexAttribArray": (None, U),
            "glVertexAttribPointer": (None, U, I, U, C.c_ubyte, I, P),
            "glVertexAttrib4f": (None, U, F, F, F, F),
            "glGenTextures": (None, I, C.POINTER(U)), "glBindTexture": (None, U, U),
            "glTexImage2D": (None, U, I, I, I, I, I, U, U, P),
            "glTexParameteri": (None, U, U, I), "glViewport": (None, I, I, I, I),
            "glClearColor": (None, F, F, F, F), "glClear": (None, U),
            "glEnable": (None, U), "glDisable": (None, U),
            "glBlendFunc": (None, U, U), "glDrawArrays": (None, U, I, I),
            "glReadPixels": (None, I, I, I, I, U, U, P),
        }
        for name, sig in signatures.items():
            setattr(self, name, self.proc(name, *sig))

    def bind_egl(self, name, result, *args):
        fn = getattr(self.egl, name)
        fn.restype, fn.argtypes = result, args

    def proc(self, name, result, *args):
        address = self.egl.eglGetProcAddress(name.encode())
        if not address:
            raise RuntimeError("missing GL/EGL entry point: " + name)
        return C.CFUNCTYPE(result, *args)(address)

    def close(self):
        if self.display and hasattr(self.egl, "eglTerminate"):
            self.egl.eglMakeCurrent(self.display, None, None, None)
            if self.context:
                self.egl.eglDestroyContext(self.display, self.context)
            if self.surface:
                self.egl.eglDestroySurface(self.display, self.surface)
            self.egl.eglTerminate(self.display)
            self.display = self.context = self.surface = None

    def program(self, alpha_test=False):
        p = self.glCreateProgram()
        for kind, name in ((0x8B31, "materialShaderVP.cpp"), (0x8B30, "materialShaderFP.cpp")):
            source = shader_source(name)
            if alpha_test:
                source = source.replace("#version 300 es", "#version 300 es\n#define GLESD3_ALPHATEST", 1)
            s = self.glCreateShader(kind)
            strings = (C.c_char_p * 1)(source.encode())
            self.glShaderSource(s, 1, strings, None)
            self.glCompileShader(s)
            status = I()
            self.glGetShaderiv(s, 0x8B81, C.byref(status))
            if not status.value:
                log = C.create_string_buffer(8192)
                self.glGetShaderInfoLog(s, len(log), None, log)
                raise AssertionError(name + ": " + log.value.decode())
            self.glAttachShader(p, s)
            self.glDeleteShader(s)
        status = I()
        self.glLinkProgram(p)
        self.glGetProgramiv(p, 0x8B82, C.byref(status))
        if not status.value:
            log = C.create_string_buffer(8192)
            self.glGetProgramInfoLog(p, len(log), None, log)
            raise AssertionError("material link: " + log.value.decode())
        return p


class GuiMaterialPixels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.g = OffscreenGL()
        except (OSError, RuntimeError) as exc:
            if os.environ.get("VOQ_REQUIRE_GPU_TESTS") == "1":
                raise
            raise unittest.SkipTest(str(exc)) from exc
        g = cls.g
        print("\nGUI pixel renderer:", g.glGetString(0x1F01).decode(), g.glGetString(0x1F02).decode())
        cls.programs = [g.program(), g.program(True)]
        vao, buffer, texture = U(), U(), U()
        g.glGenVertexArrays(1, C.byref(vao)); g.glBindVertexArray(vao)
        g.glGenBuffers(1, C.byref(buffer)); g.glBindBuffer(0x8892, buffer)
        vertices = (F * 30)(-1,-1,0,0,0, 1,-1,0,1,0, 1,1,0,1,1,
                            -1,-1,0,0,0, 1,1,0,1,1, -1,1,0,0,1)
        g.glBufferData(0x8892, C.sizeof(vertices), vertices, 0x88E4)
        g.glEnableVertexAttribArray(0); g.glVertexAttribPointer(0, 3, 0x1406, 0, 20, None)
        g.glEnableVertexAttribArray(5); g.glVertexAttribPointer(5, 2, 0x1406, 0, 20, P(12))
        g.glGenTextures(1, C.byref(texture)); g.glBindTexture(0x0DE1, texture)
        for param in (0x2800, 0x2801):
            g.glTexParameteri(0x0DE1, param, 0x2600)  # nearest
        for param in (0x2802, 0x2803):
            g.glTexParameteri(0x0DE1, param, 0x812F)  # clamp-to-edge
        cls.texels = [(7,0,123,255), (17,64,144,255), (61,128,88,255), (19,255,97,255)]
        data = (C.c_ubyte * 16)(*(v for pixel in cls.texels for v in pixel))
        g.glTexImage2D(0x0DE1, 0, 0x8058, 4, 1, 0, 0x1908, 0x1401, data)
        g.glViewport(0,0,4,1)

    @classmethod
    def tearDownClass(cls):
        for p in cls.programs:
            cls.g.glDeleteProgram(p)
        cls.g.close()

    def render(self, decode=1, native=False, color=(1,1,1,1), vertex=(1,1,1,1),
               packing=(0,1,0,1), blend=False, alpha_test=False, background=(0,0,0,1)):
        g = self.g
        p = self.programs[int(alpha_test)]
        g.glUseProgram(p)
        location = lambda name: g.glGetUniformLocation(p, name.encode())
        g.glUniform1i(location("uTexture0"), 0)
        g.glUniform1f(location("uTextureGreenAlpha"), decode)
        g.glUniform1f(location("uAlphaTest"), 0.6)
        g.glUniform4f(location("uColor"), *color)
        g.glUniform4f(location("uVertexColor"), *packing)
        g.glUniform4f(location("uTexMatrixS"), 1,0,0,0)
        g.glUniform4f(location("uTexMatrixT"), 0,1,0,0)
        g.glUniformMatrix4fv(location("uMVP"), 1, 0, (F * 16)(1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1))
        g.glVertexAttrib4f(1, *vertex)
        # Reference hardware swizzle vs the shader implementation; same texels.
        components = (1,1,1,0x1904) if native else (0x1903,0x1904,0x1905,0x1906)
        for param, value in zip((0x8E42,0x8E43,0x8E44,0x8E45), components):
            g.glTexParameteri(0x0DE1, param, value)
        g.glDisable(0x0BE2)
        g.glClearColor(*background); g.glClear(0x4000)
        if blend:
            g.glEnable(0x0BE2); g.glBlendFunc(0x0302,0x0303)
        g.glDrawArrays(0x0004, 0, 6)
        result = (C.c_ubyte * 16)()
        g.glReadPixels(0,0,4,1,0x1908,0x1401,result)
        self.assertEqual(g.glGetError(), 0)
        return [tuple(result[i:i+4]) for i in range(0,16,4)]

    def test_green_coverage_matches_native_swizzle(self):
        pixels = self.render()
        self.assertEqual(pixels, [(255,255,255,t[1]) for t in self.texels])
        self.assertEqual(pixels, self.render(decode=0, native=True))

    def test_switch_back_to_ordinary_rgba_does_not_leak(self):
        self.render(decode=1)
        self.assertEqual(self.render(decode=0), self.texels)

    def test_alpha_test_reads_decoded_coverage(self):
        self.assertEqual(self.render(alpha_test=True), [(0,0,0,255)] * 3 + [(255,255,255,255)])

    def test_tint_vertex_alpha_and_blending_follow_decode(self):
        args = dict(color=(0.8,0.4,0.2,0.5), vertex=(0.5,0.75,1.0,0.5),
                    packing=(1,0,1,0), blend=True, background=(0.1,0.2,0.3,1))
        pixels = self.render(**args)
        self.assertEqual(pixels, self.render(decode=0, native=True, **args))
        for pixel, texel in zip(pixels, self.texels):
            coverage = texel[1] / 255 * 0.5 * 0.5
            for channel, tint, bg in zip(pixel[:3], (0.4,0.3,0.2), (0.1,0.2,0.3)):
                self.assertAlmostEqual(channel, 255*(tint*coverage+bg*(1-coverage)), delta=2)


if __name__ == "__main__":
    unittest.main()
