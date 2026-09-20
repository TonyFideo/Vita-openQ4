"""Exercise the patched C query, including a no-op Vita3K stats implementation."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('memory_patch', ROOT / 'tools/vita/patch_vitagl_vita3k.py')
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)


class MemoryQueryTest(unittest.TestCase):
    def compile_and_run(self, prelude, checks, define=''):
        root = os.environ.get('VOQ_VITAGL_SOURCE')
        if not root:
            self.skipTest('patched pinned VitaGL required')
        source = (Path(root) / 'source/utils/mem_utils.c').read_text()
        a, b = patch.function_span(source, 'int voq_vgl_query_free_pools(')
        code = source[a:b]
        cc = shutil.which('cc')
        self.assertIsNotNone(cc, 'native C compiler required')
        with tempfile.TemporaryDirectory(prefix='voq-pool-query-') as directory:
            out = Path(directory)
            (out / 'test.c').write_text(
                '#include <stddef.h>\n#include <stdint.h>\n#include <assert.h>\n#include <stdio.h>\n' +
                define + '\n' + prelude + '\n' + code + '\n' + checks)
            result = subprocess.run([cc, '-std=c11', '-Wall', '-Wextra', '-Werror',
                str(out / 'test.c'), '-o', str(out / 'test')], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(out / 'test')], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout.strip())

    def test_mspace_void_query_and_unimplemented_hle(self):
        self.compile_and_run(r'''
typedef enum { VGL_MEM_VRAM, VGL_MEM_RAM, VGL_MEM_PHYCONT } vglMemType;
static size_t mempool_size[3] = {2000,1000,0};
static void *mempool_mspace[3] = {(void *)1,(void *)2,0};
typedef struct { unsigned capacity, peak_in_use, current_in_use; } SceClibMspaceStats;
static SceClibMspaceStats observed[3] = {{1900,0,400},{950,0,450},{0,0,0}};
static unsigned calls;
static int noop;
static void sceClibMspaceMallocStats(void *space, SceClibMspaceStats *stats) {
    ++calls;
    assert(stats->capacity==0 && stats->current_in_use==0 && stats->peak_in_use==0);
    if (!noop) *stats=observed[(uintptr_t)space-1];
}
''', r'''
int main(void) {
    size_t free_bytes[3] = {42,43,44};
    assert(!voq_vgl_query_free_pools(NULL) && calls==0);
    assert(voq_vgl_query_free_pools(free_bytes));
    assert(free_bytes[0]==500 && free_bytes[1]==1500 && free_bytes[2]==0 && calls==2);
    noop=1;
    assert(!voq_vgl_query_free_pools(free_bytes));
    assert(free_bytes[0]==0 && free_bytes[1]==0 && free_bytes[2]==0);
    noop=0;
    observed[0].capacity=0; /* failure after the first bank succeeded */
    assert(!voq_vgl_query_free_pools(free_bytes) && free_bytes[0]==0);
    observed[0].capacity=2001;
    assert(!voq_vgl_query_free_pools(free_bytes));
    observed[0].capacity=1900;observed[0].current_in_use=1901;
    assert(!voq_vgl_query_free_pools(free_bytes));
    observed[0].current_in_use=1900;
    assert(voq_vgl_query_free_pools(free_bytes) && free_bytes[1]==0);
    mempool_mspace[1]=0;
    assert(!voq_vgl_query_free_pools(free_bytes));
    mempool_size[0]=mempool_size[1]=0;
    unsigned before=calls;
    assert(voq_vgl_query_free_pools(free_bytes) && calls==before);
    assert(free_bytes[0]==0 && free_bytes[1]==0 && free_bytes[2]==0);
    puts("PASS mspace: void SDK query, initialized output, no-op HLE, bounds, empty/full pools, atomic publication");
}
''')

    def test_custom_heap_bounds(self):
        self.compile_and_run(r'''
typedef enum { VGL_MEM_VRAM, VGL_MEM_RAM, VGL_MEM_PHYCONT } vglMemType;
static size_t mempool_size[3] = {2000,1000,0};
static size_t tm_free[3] = {1200,600,0};
''', r'''
int main(void) {
    size_t out[3];
    assert(voq_vgl_query_free_pools(out));
    assert(out[0]==600 && out[1]==1200 && out[2]==0);
    tm_free[0]=2001;
    assert(!voq_vgl_query_free_pools(out));
    assert(out[0]==0 && out[1]==0 && out[2]==0);
    puts("PASS custom heap query bounds without altering its allocator");
}
''', '#define HAVE_CUSTOM_HEAP 1')

    def test_unbounded_physical_mode_unavailable(self):
        self.compile_and_run('', r'''
int main(void) {
    size_t out[3] = {7,8,9};
    assert(!voq_vgl_query_free_pools(out));
    assert(out[0]==0 && out[1]==0 && out[2]==0);
    puts("PASS on-demand physical mode is not misreported as a bounded pool");
}
''', '#define PHYCONT_ON_DEMAND 1')


if __name__ == '__main__': unittest.main()
