#!/usr/bin/env python3
"""Exercise the same guest-side formatter used by Sys_*Printf."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
CODE = r'''
#include "vita_safe_printf.h"
#ifdef VOQ_TEST_POISON
#ifndef vsnprintf
#error "platform adapter must restore the engine poison macro"
#endif
#else
#ifdef vsnprintf
#error "platform adapter must not define a previously absent macro"
#endif
#endif
#include <assert.h>
#include <string.h>
static void check(char *out, size_t cap, const char *format, ...) {
    va_list ap; va_start(ap,format);
    VitaFormatPrint(out,cap,format,ap);
    // va_copy must keep the caller's va_list reusable.
    char second[4096]; VitaFormatPrint(second,sizeof(second),format,ap);
    if (cap>1) assert(strncmp(out,second,cap-1)==0);
    va_end(ap);
}
int main(void) {
    char out[4096];
    check(out,sizeof(out),"%s %d %u %.2f %lld %%", "texture", -7, 42u, 3.5, 1234567890123LL);
    assert(strcmp(out,"texture -7 42 3.50 1234567890123 %")==0);
    check(out,sizeof(out),"%s", "%s %n is data, not another format");
    assert(strcmp(out,"%s %n is data, not another format")==0);
    check(out,5,"%s","abcdefghi"); assert(strcmp(out,"abcd")==0);
    check(out,1,"%s","abcdefghi"); assert(out[0]==0);
    out[0]='Z'; check(out,0,"ignored"); assert(out[0]=='Z');
    check(out,sizeof(out),NULL); assert(out[0]==0);
    check(NULL,0,"ignored");
    puts("PASS: guest varargs strings, integers, double, 64-bit, percent, truncation, null, va_copy");
}
'''
class SafePrintfTest(unittest.TestCase):
    def test_formatting(self):
        self._formatting(False)

    def test_force_included_engine_macro(self):
        self._formatting(True)

    def _formatting(self, poisoned):
        cc = os.environ.get("HOST_CC") or shutil.which("clang") or shutil.which("cc")
        if not cc:
            self.skipTest("native C/C++ compiler required")
        with tempfile.TemporaryDirectory(prefix="voq-print-") as directory:
            root = pathlib.Path(directory)
            source = root / "test.c"
            source.write_text(CODE, encoding="utf-8")
            poison = root / "engine_poison.h"
            poison.write_text(
                '#include <stdio.h>\n'
                '#define vsnprintf use_idStr_vsnPrintf\n', encoding="utf-8")
            for language, standard in (("c", "c99"), ("c++", "c++20")):
                with self.subTest(language=language, force_include=poisoned):
                    command = [cc, "-x", language, "-std=" + standard, "-O1", "-g",
                               "-I", str(ROOT / "src/sys/vita"), str(source),
                               "-o", str(root / "test")]
                    if poisoned:
                        command += ["-include", str(poison), "-DVOQ_TEST_POISON=1"]
                    if os.environ.get("VOQ_MIP_SANITIZE") == "1":
                        command += ["-fsanitize=address,undefined"]
                    build = subprocess.run(command, capture_output=True, text=True)
                    self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
                    run = subprocess.run([str(root / "test")], capture_output=True, text=True)
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                    print(f"{language} force_include={poisoned}: {run.stdout.strip()}")
    def test_no_va_list_hle_bridge(self):
        source=(ROOT/"src/sys/vita/vita_system.cpp").read_text(encoding="utf-8")
        self.assertNotIn("sceClibVprintf(",source)
        self.assertNotIn("sceClibVsnprintf(",source)
        self.assertIn('sceClibPrintf( "%s", text )',source)
if __name__ == "__main__": unittest.main()
