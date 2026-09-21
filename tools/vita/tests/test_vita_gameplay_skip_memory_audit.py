"""Target diagnostics for cinematic-skip memory growth remain observational."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[3]

def function(text, signature):
    start=text.index(signature)
    opening=text.index('{',start)
    depth=0
    for i in range(opening,len(text)):
        if text[i]=='{': depth+=1
        elif text[i]=='}':
            depth-=1
            if depth==0:return text[start:i+1]
    raise AssertionError(signature)

class GameplaySkipMemoryAuditTest(unittest.TestCase):
    def test_allocator_failure_reports_immediate_mem_caller(self):
        text=(ROOT/'src/idlib/Heap.cpp').read_text()
        alloc=function(text,'void *Mem_Alloc( const size_t size, byte tag )')
        alloc16=function(text,'void *Mem_Alloc16( const size_t size, byte tag )')
        local=function(text,'void *local_malloc(')
        self.assertIn('"mem-alloc-origin"',alloc)
        self.assertIn('"mem-alloc16-origin"',alloc16)
        self.assertIn('__builtin_return_address(0)',alloc16)
        self.assertIn('VitaRuntimeAudit_Memory( auditReason, 1, size, auditCaller, true )',local)
        self.assertEqual(local.count('malloc(size)'),1)
        self.assertIn('common->FatalError( "Out of memory" )',local)

    def test_frame_arena_probe_does_not_change_allocator_policy(self):
        text=(ROOT/'src/renderer/tr_main.cpp').read_text()
        alloc=function(text,'void *R_FrameAlloc( int bytes )')
        toggle=function(text,'void R_ToggleSmpFrame( void )')
        self.assertIn('#define\tMEMORY_BLOCK_SIZE\t0x100000',text)
        self.assertIn('size = MEMORY_BLOCK_SIZE;',alloc)
        self.assertIn('Mem_Alloc16( size + sizeof( *block ) )',alloc)
        self.assertIn('"frame-arena-grow"',alloc)
        self.assertIn('__builtin_return_address(0)',alloc)
        self.assertNotIn('Mem_Free16',alloc)
        self.assertIn('"frame-arena-reset"',toggle)
        self.assertIn('block->used = 0;',toggle)
        self.assertNotIn('Mem_Free16',toggle)

    def test_gameplay_traffic_window_is_rearmed_after_load_ready(self):
        session=(ROOT/'src/framework/Session.cpp').read_text()
        ready=session.index('VitaRuntimeAudit_Memory( "load:ready"')
        reset=session.index('VitaRuntimeAudit_ResetTrafficWindow( "gameplay:traffic-reset"')
        self.assertLess(ready,reset)
        main=(ROOT/'src/sys/vita/vita_main.cpp').read_text()
        body=function(main,'void VitaRuntimeAudit_ResetTrafficWindow(')
        self.assertIn('__sync_lock_test_and_set(&vitaAuditRequested, 0u)',body)
        self.assertIn('__sync_lock_test_and_set(&vitaAuditSnapshots, 0u)',body)
        self.assertNotIn('malloc(',body)

    def test_skip_input_has_before_and_after_observation_only(self):
        session=(ROOT/'src/framework/Session.cpp').read_text()
        process=function(session,'bool idSessionLocal::ProcessEvent(')
        before=process.index('"input:escape-or-start"')
        call=process.index('game->HandleESC( &gui )')
        after_ignore=process.index('"input:handled-ignore"')
        after_consume=process.index('"input:cinematic-consumed"')
        self.assertLess(before,call)
        self.assertLess(call,after_ignore)
        self.assertLess(call,after_consume)
        block=process[before:max(after_ignore,after_consume)+300]
        for forbidden in ('R_ToggleSmpFrame','Mem_Free','skipCinematic =','com_ticNumber++'):
            self.assertNotIn(forbidden,block)

if __name__=='__main__':
    unittest.main()
