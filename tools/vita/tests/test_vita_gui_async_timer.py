"""Vita 60 Hz async-tic lifecycle and bounded gameplay diagnostics."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]

def function(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    depth = 0
    for i in range(opening, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise AssertionError(signature)

class VitaAsyncTimerTest(unittest.TestCase):
    def test_timer_starts_after_common_init_and_stops_before_primitives(self):
        main = (ROOT / 'src/sys/vita/vita_main.cpp').read_text()
        system = (ROOT / 'src/sys/vita/vita_system.cpp').read_text()
        public = (ROOT / 'src/sys/vita/vita_public.h').read_text()
        self.assertLess(main.index('common->Init('), main.index('Vita_StartAsyncTimer()'))
        self.assertLess(main.index('Vita_StartAsyncTimer()'), main.index('for ( ;; )'))
        shutdown = function(system, 'void Sys_Shutdown( void )')
        self.assertLess(shutdown.index('Vita_StopAsyncTimer()'), shutdown.index('Vita_ShutdownThreads()'))
        self.assertIn('bool Vita_StartAsyncTimer( void );', public)
        self.assertIn('void Vita_StopAsyncTimer( void );', public)

    def test_timer_callback_uses_engine_async_contract(self):
        text = (ROOT / 'src/sys/vita/vita_threads.cpp').read_text()
        body = function(text, 'static int Vita_AsyncTimerThread(')
        self.assertIn('common->Async();', body)
        self.assertIn('Sys_TriggerEvent( TRIGGER_EVENT_ONE );', body)
        self.assertLess(body.index('common->Async();'), body.index('Sys_TriggerEvent( TRIGGER_EVENT_ONE );'))
        self.assertIn('sceKernelGetSystemTimeWide()', body)
        self.assertIn('sceKernelDelayThread(', body)
        self.assertNotIn('game->RunFrame', body)
        self.assertNotIn('com_ticNumber++', body)

    def test_fractional_schedule_is_exact_60_hz(self):
        text = (ROOT / 'src/sys/vita/vita_threads.cpp').read_text()
        body = function(text, 'static uint32_t Vita_NextAsyncIntervalUsec(')
        cc = shutil.which('c++')
        self.assertIsNotNone(cc)
        source = (
            '#include <stdint.h>\n#include <assert.h>\n#include <stdio.h>\n'
            '#define USERCMD_HZ 60\n' + body +
            '\nint main(){uint32_t r=0;unsigned long long sum=0;'
            'for(int i=0;i<60;i++){uint32_t d=Vita_NextAsyncIntervalUsec(r);'
            'assert(d==16666||d==16667);sum+=d;}'
            'assert(sum==1000000ULL&&r==0);'
            'for(int i=0;i<540;i++)sum+=Vita_NextAsyncIntervalUsec(r);'
            'assert(sum==10000000ULL&&r==0);'
            'puts("PASS exact 60 Hz microsecond schedule");}\n'
        )
        with tempfile.TemporaryDirectory(prefix='voq-async-') as directory:
            root = Path(directory)
            (root / 'test.cpp').write_text(source)
            result = subprocess.run([cc, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                                     str(root / 'test.cpp'), '-o', str(root / 'test')],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout.strip())

    def test_gameplay_audit_observes_without_driving_simulation(self):
        session = (ROOT / 'src/framework/Session.cpp').read_text()
        marker = session.index('[VOQ4][gameplay]')
        start = session.rfind('static int vitaGameplayAuditNextMsec', 0, marker)
        self.assertGreaterEqual(start, 0)
        block = session[start:marker + 1000]
        for token in ('com_ticNumber', 'latchedTicNumber', 'lastGameTic',
                      'gameTicsToRun', 'game->InCinematic()', 'syncNextGameFrame'):
            self.assertIn(token, block)
        self.assertIn('vitaGameplayAuditReports < 30', block)
        self.assertNotIn('RunGameTic();', block)
        self.assertNotIn('++com_ticNumber', block)

if __name__ == '__main__':
    unittest.main()
