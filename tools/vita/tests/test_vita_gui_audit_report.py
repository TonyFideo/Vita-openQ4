"""Streaming diagnostics: observations, incomplete evidence, and bounded output."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('audit_report',
    Path(__file__).resolve().parents[1] / 'analyze_runtime_audit.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def state(index=1):
    return (f'[VOQ4][clear-audit] sample={index} drawFbo=0 mask=0x4000 '
            'rgba=0.000,0.000,0.000,1.000 writes=1111 scissor=0 box=0,0,960,544')


def pixels(phase='after', value='0,0,0,255', index=1):
    return (f'[VOQ4][clear-audit] sample={index} phase={phase} ' +
            ' '.join(f'{p}={value}' for p in mod.POINTS))


class AuditReportTest(unittest.TestCase):
    def test_empty_is_not_a_pass(self):
        result = mod.analyze([])
        self.assertEqual(result['clear_samples'], [])
        self.assertEqual(result['memory_records'], 0)
        self.assertTrue(any('unmeasured' in w for w in result['warnings']))

    def test_sampled_match_and_later_color_remain_distinct(self):
        result = mod.analyze([state(), pixels(), pixels('present', '255,255,0,255')])
        sample = result['clear_samples'][0]
        self.assertEqual(sample['clear_observation'], 'matches_requested_at_sampled_points')
        self.assertEqual(sample['present']['L'], [255,255,0,255])
        self.assertNotIn('fixed', str(result))

    def test_failed_clear_points(self):
        sample = mod.analyze([state(), pixels(value='255,255,0,255')])['clear_samples'][0]
        self.assertEqual(sample['clear_observation'], 'differs_from_requested')
        self.assertEqual(sample['different_points'], list(mod.POINTS))

    def test_incomplete_or_partial_clear_not_qualified(self):
        for header in [state().replace('1111', '0000'),
                       state().replace('scissor=0', 'scissor=1'),
                       state().replace('drawFbo=0', 'drawFbo=7'),
                       state().replace('0x4000', '0x100'),
                       state().replace('rgba=0.000', 'rgba=nan')]:
            sample = mod.analyze([header, pixels()])['clear_samples'][0]
            self.assertEqual(sample['clear_observation'], 'insufficient_state_or_pixels')
        for row in [pixels().replace('L=0,0,0,255', 'L=0,0'), pixels(value='-1,0,0,255')]:
            sample = mod.analyze([state(), row])['clear_samples'][0]
            self.assertEqual(sample['clear_observation'], 'insufficient_state_or_pixels')

    def test_memory_not_traffic_and_exact_request(self):
        result = mod.analyze([
            '[VOQ4][memory] allocation-traffic failed=0 count=1 size=33554432 heapUsed=100 heapFree=300',
            '[VOQ4][memory] calloc failed=1 count=2 size=4294967295 overflow=1 caller=0x81000001 heapUsed=220 heapFree=180',
        ])
        self.assertEqual(result['peak_heap_used'], 220)
        self.assertEqual(result['minimum_heap_free'], 180)
        self.assertEqual(result['failed_reservations'][0]['requested_bytes_mathematical'], 8589934590)
        self.assertEqual(result['failed_reservations'][0]['fields']['overflow'], '1')

    def test_old_log_oom_does_not_invent_allocation(self):
        result = mod.analyze(['FATAL: Out of memory'])
        self.assertEqual(result['failed_reservation_count'], 0)
        self.assertIsNone(result['peak_heap_used'])
        self.assertTrue(any('without a captured' in w for w in result['warnings']))

    def test_builds_do_not_mix_samples(self):
        result = mod.analyze(['[VOQ4][load] build action=249 commit=aaa', state(), pixels(),
            '[VOQ4][load] build action=250 commit=bbb', state(), pixels(value='128,128,128,255')])
        self.assertEqual(len(result['clear_samples']), 2)
        self.assertNotEqual(result['clear_samples'][0]['session'], result['clear_samples'][1]['session'])

    def test_large_logs_have_bounded_detail(self):
        def records():
            for i in range(mod.LIMIT+10):
                yield state(i)
                yield '[VOQ4][memory] malloc failed=1 count=1 size=42'
        result = mod.analyze(records())
        self.assertTrue(result['truncated'])
        self.assertEqual(result['failed_reservation_count'], mod.LIMIT+10)
        self.assertEqual(len(result['failed_reservations']), mod.LIMIT)
        self.assertEqual(len(result['clear_samples']), mod.LIMIT)


if __name__ == '__main__': unittest.main()
