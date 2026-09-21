"""Run the actual GLimp_Init/priming code with mocked VitaGL and image state."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    for end in range(opening + 1, len(source)):
        depth += (source[end] == '{') - (source[end] == '}')
        if not depth:
            return source[start:end + 1]
    raise AssertionError('unterminated function ' + signature)


HARNESS = r'''
#include <cassert>
#include <cstring>
#include <cstddef>
struct ImageManager {
    bool reductionModified = true, samplingModified = true;
    int primes = 0;
    void PrimeCvars() { ++primes; reductionModified = samplingModified = false; }
};
ImageManager manager;
ImageManager *globalImages = &manager;
struct Common { void Printf(const char *, ...) {} } console;
Common *common = &console;
struct Config { int vidWidth, vidHeight; bool isFullscreen; } glConfig, engineWindowState;
struct glimpParms_t {};
using GLboolean = bool;
constexpr bool GL_TRUE = true;
constexpr int GL_VERSION = 1, SCE_GXM_MULTISAMPLE_NONE = 0;
static bool vitaGLReady = false, versionValid = true, unrelatedModified = true;
static bool poolReady = true;
extern "C" int voq_vgl_memory_init_ok() { return poolReady; }
static int nativeInits = 0, checkpoints = 0;
void VitaGLimp_Log(const char *) {}
void VitaLoadingHud_SetCheckpoint(const char *message) {
    assert(std::strcmp(message, "IMAGE policy primed before upload") == 0);
    ++checkpoints;
}
void VitaLoadingHud_BeginRendererHandoff() {}
void VitaLoadingHud_RendererInitialized() {}
void VitaLoadingHud_LogError(const char *) {}
void vglSetCircularPoolSize(int) {}
void vglSetParamBufferSize(int) {}
bool vglInitWithCustomThreshold(int,int,int,int ram,int cdram,int phy,int dialog,int) {
    assert(ram == 10 * 1024 * 1024 && cdram == 0 && phy == 0 && dialog == 0x8C6000);
    ++nativeInits; return false;
}
void vglWaitVblankStart(bool) {}
const char *glGetString(int) { return versionValid ? "test" : nullptr; }
__FUNCTIONS__
int main() {
    // Pool failure must stop before enabling a context or priming image state.
    poolReady = false;
    assert(!GLimp_Init({}) && !vitaGLReady && manager.primes == 0);
    poolReady = true;
    // Failed initialization must not consume pending configuration changes.
    versionValid = false;
    assert(!GLimp_Init({}));
    assert(!vitaGLReady && manager.primes == 0 && manager.reductionModified && manager.samplingModified);
    // Successful initialization consumes only the image policy flags.
    vitaGLReady = false; versionValid = true;
    assert(GLimp_Init({}));
    assert(manager.primes == 1 && !manager.reductionModified && !manager.samplingModified);
    assert(unrelatedModified && checkpoints == 1);
    // Later genuine changes survive per-frame context checks and screen parms.
    manager.reductionModified = true;
    assert(GLimp_EnsureActiveContext("frame"));
    assert(GLimp_SetScreenParms({}));
    assert(manager.reductionModified && manager.primes == 1);
    // vid_restart reuses the context and primes the policy for its full reload.
    const int before = nativeInits;
    assert(GLimp_Init({}));
    assert(nativeInits == before && manager.primes == 2 && !manager.reductionModified);
    // Startup probes with no image manager must remain harmless.
    globalImages = nullptr;
    assert(GLimp_Init({}));
    assert(manager.primes == 2);
}
'''


class GLimpPolicyTests(unittest.TestCase):
    def test_native_lifecycle(self):
        compiler = os.environ.get('HOST_CXX') or shutil.which('clang++') or shutil.which('c++')
        if not compiler:
            self.skipTest('native C++ compiler required')
        source = (ROOT / 'src/sys/vita/vita_glimp.cpp').read_text()
        signatures = ('static void VitaGLimp_PrimeImagePolicy( void )',
                      'bool GLimp_Init( glimpParms_t parms )',
                      'bool GLimp_SetScreenParms( glimpParms_t parms )',
                      'bool GLimp_EnsureActiveContext( const char *operation )')
        code = HARNESS.replace('__FUNCTIONS__', '\n'.join(function(source, s) for s in signatures))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'test.cpp').write_text(code)
            command = [compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-O1', '-g',
                       str(root / 'test.cpp'), '-o', str(root / 'test')]
            if os.environ.get('VOQ_POLICY_SANITIZE') == '1':
                command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
            built = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            run = subprocess.run([str(root / 'test')], text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_not_primed_per_frame(self):
        source = (ROOT / 'src/sys/vita/vita_glimp.cpp').read_text()
        for signature in ('void GLimp_SwapBuffers( void )', 'bool GLimp_EnsureActiveContext( const char *operation )'):
            self.assertNotIn('PrimeImagePolicy', function(source, signature))


if __name__ == '__main__':
    unittest.main()
