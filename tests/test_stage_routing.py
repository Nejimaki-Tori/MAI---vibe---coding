import sys
from unittest.mock import MagicMock

sys.modules['wiki_extract'] = MagicMock()

import unittest
from unittest.mock import patch, AsyncMock, MagicMock
import json
import asyncio
from pathlib import Path
import tempfile

repo_root = Path(__file__).resolve().parent.parent
src_dir = repo_root / 'src'
sys.path.insert(0, str(src_dir))

import run_bench


def _make_bench_mock():
    bench = MagicMock()
    bench.rank_query = AsyncMock(return_value=(0.5, 0.3))
    bench.rank_outline = AsyncMock(return_value=(0.8, 0.1, 0.9, 0.7, 0.1, 0.8, 0.75, 0.1, 0.85))
    bench.rank_sections = AsyncMock(return_value=(0.8, 0.1, 0.9, 0.7, 0.1, 0.8, 0.75, 0.1, 0.85, 0.6, 0.1, 0.7, 0.5, 0.1, 0.6))
    bench.load_enviroment = MagicMock()
    bench.prepare_env = MagicMock()
    return bench


class TestStageRouting(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.output_dir = self.tmpdir.name

    def tearDown(self):
        self.tmpdir.cleanup()

    def _run(self, stage):
        bench = _make_bench_mock()
        patcher_wb = patch('run_bench.WikiBench', return_value=bench)
        patcher_be = patch('run_bench.build_encoder', return_value=MagicMock())
        patcher_rd = patch('run_bench.resolve_device', return_value=MagicMock())
        patcher_wb.start()
        patcher_be.start()
        patcher_rd.start()
        try:
            metrics = asyncio.run(run_bench.run_wiki_benchmark(
                api='http://test',
                key='test',
                model_name='test-model',
                concurrency=1,
                output_dir=self.output_dir,
                number_of_articles=1,
                encoder_name='test',
                device='cpu',
                prepare_env=False,
                stage=stage,
            ))
            return bench, metrics
        finally:
            patcher_wb.stop()
            patcher_be.stop()
            patcher_rd.stop()

    def test_stage_all_calls_all(self):
        bench, metrics = self._run('all')
        bench.rank_query.assert_called_once()
        bench.rank_outline.assert_called_once()
        bench.rank_sections.assert_called_once()
        self.assertIn('ranking', metrics)
        self.assertIn('outline', metrics)
        self.assertIn('sections', metrics)

    def test_stage_ranking_calls_only_ranking(self):
        bench, metrics = self._run('ranking')
        bench.rank_query.assert_called_once()
        bench.rank_outline.assert_not_called()
        bench.rank_sections.assert_not_called()
        self.assertIn('ranking', metrics)
        self.assertNotIn('outline', metrics)
        self.assertNotIn('sections', metrics)

    def test_stage_outline_calls_only_outline(self):
        bench, metrics = self._run('outline')
        bench.rank_query.assert_not_called()
        bench.rank_outline.assert_called_once()
        bench.rank_sections.assert_not_called()
        self.assertNotIn('ranking', metrics)
        self.assertIn('outline', metrics)
        self.assertNotIn('sections', metrics)

    def test_stage_sections_calls_only_sections(self):
        bench, metrics = self._run('sections')
        bench.rank_query.assert_not_called()
        bench.rank_outline.assert_not_called()
        bench.rank_sections.assert_called_once()
        self.assertNotIn('ranking', metrics)
        self.assertNotIn('outline', metrics)
        self.assertIn('sections', metrics)

    def test_config_saves_stage(self):
        self._run('outline')
        config_path = Path(self.output_dir) / 'test-model' / 'config.json'
        self.assertTrue(config_path.exists())
        with open(config_path, 'r') as f:
            config = json.load(f)
        self.assertEqual(config.get('stage'), 'outline')

    def test_default_stage_is_all(self):
        bench = _make_bench_mock()
        patcher_wb = patch('run_bench.WikiBench', return_value=bench)
        patcher_be = patch('run_bench.build_encoder', return_value=MagicMock())
        patcher_rd = patch('run_bench.resolve_device', return_value=MagicMock())
        patcher_wb.start()
        patcher_be.start()
        patcher_rd.start()
        try:
            metrics = asyncio.run(run_bench.run_wiki_benchmark(
                api='http://test',
                key='test',
                model_name='test-model',
                concurrency=1,
                output_dir=self.output_dir,
                number_of_articles=1,
                encoder_name='test',
                device='cpu',
                prepare_env=False,
            ))
            bench.rank_query.assert_called_once()
            bench.rank_outline.assert_called_once()
            bench.rank_sections.assert_called_once()
        finally:
            patcher_wb.stop()
            patcher_be.stop()
            patcher_rd.stop()

    def test_flatten_metrics_does_not_crash_on_partial_stage(self):
        metrics = {
            'model_name': 'test-model',
            'number_of_articles': 3,
            'outline': {
                'precision': {'mean': 0.8, 'ci_low': 0.1, 'ci_high': 0.9},
                'recall': {'mean': 0.7, 'ci_low': 0.1, 'ci_high': 0.8},
                'f1': {'mean': 0.75, 'ci_low': 0.1, 'ci_high': 0.85},
            },
        }
        flat = run_bench.flatten_metrics(metrics)
        self.assertEqual(flat['model_name'], 'test-model')
        self.assertIsNone(flat['ranking_ndcg_mean'])
        self.assertIsNotNone(flat['outline_precision_mean'])
        self.assertIsNone(flat['sections_precision_mean'])
        self.assertIsNone(flat['sections_rouge_l_mean'])
        self.assertIsNone(flat['sections_bleu_mean'])


if __name__ == '__main__':
    unittest.main()