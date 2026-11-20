"""炉序失准监控 SPRT 核心 oracle 测试（仅标准库，无需安装依赖）。

被测模块：backend/src/services/monitor_sprt.py（纯Python顺序概率比核心）。
运行：python3 test-artifacts/gb-0044/test_monitor_sprt.py
"""
import importlib.util
import math
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[2] / 'backend' / 'src' / 'services' / 'monitor_sprt.py'
spec = importlib.util.spec_from_file_location('monitor_sprt', MODULE)
sprt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sprt)

LN3 = math.log(0.30 / 0.10)
LN79 = math.log(0.70 / 0.90)


class TestBoundaryAndStep(unittest.TestCase):
    def test_boundary_is_log_furnaces_over_alpha(self):
        # 报警界限 = 炉数 ÷ 误报上限（对数口径）
        self.assertAlmostEqual(sprt.alarm_boundary(3, 0.1), math.log(30))
        self.assertAlmostEqual(sprt.alarm_boundary(5, 0.05), math.log(100))
        self.assertAlmostEqual(sprt.alarm_boundary(1, 0.5), math.log(2))

    def test_boundary_rejects_bad_input(self):
        for bad in ((0, 0.1), (3, 0.0), (3, 1.0), (3, -0.1), (3, 1.5)):
            with self.assertRaises(ValueError):
                sprt.alarm_boundary(*bad)

    def test_step_is_likelihood_ratio_30_vs_10_percent(self):
        # 失准率三成对一成：失准乘 0.3/0.1，不失准乘 0.7/0.9
        self.assertAlmostEqual(sprt.step(0.0, True), LN3)
        self.assertAlmostEqual(sprt.step(0.0, False), LN79)

    def test_log_accumulation_matches_product_form(self):
        seq = [True, False, True, True, False, False, True]
        llr, product = 0.0, 1.0
        for bad in seq:
            llr = sprt.step(llr, bad)
            product *= (0.30 / 0.10) if bad else (0.70 / 0.90)
        self.assertAlmostEqual(math.exp(llr), product)


class TestInaccuracy(unittest.TestCase):
    def test_over_threshold_is_inaccurate(self):
        self.assertTrue(sprt.is_inaccurate(91.1, 83.0, 8.0))
        self.assertTrue(sprt.is_inaccurate(74.9, 83.0, 8.0))

    def test_exactly_threshold_is_not_inaccurate(self):
        # “相差超过给定分钟数”：恰好等于阈值不算失准
        self.assertFalse(sprt.is_inaccurate(91.0, 83.0, 8.0))
        self.assertFalse(sprt.is_inaccurate(83.0, 83.0, 8.0))


class TestFurnaceEngine(unittest.TestCase):
    def engine(self, furnaces=3, alpha=0.1):
        return sprt.FurnaceEngine(sprt.alarm_boundary(furnaces, alpha))

    def test_first_alarm_at_boundary(self):
        # 3炉 α=0.1 → 界限 ln30≈3.401；连续失准在第4件首次越界报警
        eng = self.engine()
        for s in (1, 2, 3):
            eng.buffer(s, True)
        counted, alarm = eng.drain()
        self.assertEqual(counted, [1, 2, 3])
        self.assertIsNone(alarm)
        eng.buffer(4, True)
        counted, alarm = eng.drain()
        self.assertEqual(counted, [4])
        self.assertEqual(alarm, 4)
        self.assertEqual(eng.alarm_seq, 4)
        self.assertGreaterEqual(eng.llr, math.log(30))

    def test_alarm_latches_and_counting_continues(self):
        eng = self.engine()
        alarms = []
        for s in range(1, 7):
            eng.buffer(s, True)
            _, alarm = eng.drain()
            alarms.append(alarm)
        self.assertEqual(eng.alarm_seq, 4)   # 首警序号锁定不变
        self.assertEqual(eng.counted, 6)     # 报警后仍继续计入
        self.assertEqual(alarms, [None, None, None, 4, None, None])  # 不重复报警

    def test_out_of_order_waits_for_gap(self):
        eng = self.engine()
        eng.buffer(1, False)
        eng.buffer(3, True)   # 乱序补报先到
        eng.buffer(4, True)
        counted, _ = eng.drain()
        self.assertEqual(counted, [1])       # 缺第2件，停在缺号处
        self.assertEqual(eng.next_seq, 2)
        eng.buffer(2, False)                 # 缺号补报到达
        counted, _ = eng.drain()
        self.assertEqual(counted, [2, 3, 4])  # 连同暂存一起按序计入

    def test_gap_blocks_only_that_furnace(self):
        a, b = self.engine(), self.engine()
        a.buffer(2, True)   # a 缺第1件
        b.buffer(1, True)   # b 不缺号
        ca, _ = a.drain()
        cb, _ = b.drain()
        self.assertEqual(ca, [])   # 有缺号只等该炉
        self.assertEqual(cb, [1])

    def test_retry_does_not_double_count(self):
        eng = self.engine()
        self.assertTrue(eng.buffer(1, True))
        self.assertFalse(eng.buffer(1, True))  # 缓冲中重复登记被拒绝
        eng.drain()
        self.assertFalse(eng.buffer(1, True))  # 已计入序号再报被忽略
        eng.drain()
        self.assertEqual(eng.counted, 1)
        self.assertAlmostEqual(eng.llr, LN3)

    def test_resume_from_persisted_state(self):
        eng = self.engine()
        for s in (1, 2, 3):
            eng.buffer(s, True)
        eng.drain()
        # 模拟计入后中断：仅从持久化字段恢复，续跑不丢进度
        restored = sprt.FurnaceEngine(
            sprt.alarm_boundary(3, 0.1), next_seq=eng.next_seq, llr=eng.llr,
            counted=eng.counted, inaccurate_count=eng.inaccurate_count,
            alarmed=eng.alarmed, alarm_seq=eng.alarm_seq)
        restored.buffer(4, True)
        counted, alarm = restored.drain()
        self.assertEqual(counted, [4])
        self.assertEqual(alarm, 4)

    def test_accurate_readings_push_llr_down(self):
        eng = self.engine()
        for s in range(1, 6):
            eng.buffer(s, False)
        counted, alarm = eng.drain()
        self.assertEqual(counted, [1, 2, 3, 4, 5])
        self.assertIsNone(alarm)
        self.assertAlmostEqual(eng.llr, 5 * LN79)


class TestServiceContractScenario(unittest.TestCase):
    """用纯Python模拟服务层契约：乱序补报、重试、更正留痕、首警按当时读数。"""

    def setUp(self):
        self.eng = sprt.FurnaceEngine(sprt.alarm_boundary(3, 0.1))
        self.readings = {}      # seq -> {'actual':…, 'state':'buffered'|'counted'}
        self.corrections = []   # 留痕：(seq, old, new)
        self.alarms = []

    def report(self, seq, actual, predicted=100.0, threshold=8.0):
        if seq in self.readings:  # 同号重报
            r = self.readings[seq]
            if r['actual'] == actual:
                return 'duplicate'                      # 重试不重复计入
            if r['state'] == 'counted':
                self.corrections.append((seq, r['actual'], actual))
                return 'correction_logged'              # 留痕，不改引擎
            r['actual'] = actual                        # 缓冲中允许更新
            self.eng.pending[seq] = sprt.is_inaccurate(actual, predicted, threshold)
        else:
            self.readings[seq] = {'actual': actual, 'state': 'buffered'}
            self.eng.buffer(seq, sprt.is_inaccurate(actual, predicted, threshold))
        counted, alarm = self.eng.drain()
        for s in counted:
            self.readings[s]['state'] = 'counted'
        if alarm:
            self.alarms.append(alarm)
        return 'counted' if seq in counted else 'buffered'

    def test_full_scenario(self):
        # 连续失准：第4件首次报警（界限 ln30）
        self.assertEqual(self.report(1, 112.0), 'counted')
        self.assertEqual(self.report(2, 112.0), 'counted')
        self.assertEqual(self.report(4, 112.0), 'buffered')   # 缺第3件，乱序暂存
        self.assertEqual(self.report(3, 112.0), 'counted')    # 缺号补齐，3、4连续计入
        self.assertEqual(self.alarms, [4])
        # 重试同号同读数：不重复计入
        self.assertEqual(self.report(3, 112.0), 'duplicate')
        self.assertEqual(self.eng.counted, 4)
        # 已计入的第2件更正为在阈值内：留痕，报警仍按当时读数
        self.assertEqual(self.report(2, 95.0), 'correction_logged')
        self.assertEqual(self.corrections, [(2, 112.0, 95.0)])
        self.assertEqual(self.eng.alarm_seq, 4)
        self.assertAlmostEqual(self.eng.llr, 4 * LN3)         # 似然比未被更正改写
        # 报警后继续上报：计入但不重复报警
        self.assertEqual(self.report(5, 112.0), 'counted')
        self.assertEqual(self.alarms, [4])
        self.assertEqual(self.eng.counted, 5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
