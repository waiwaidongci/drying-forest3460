"""炉序失准监控的顺序概率比核心（SPRT，纯标准库，不依赖Web/数据库）。

业务口径：
- 开测时定下误报上限 alpha 与各炉有序试件清单；炉数为 N。
- 每条实测按清单顺序计入，累乘“失准率三成对一成”的似然比：
  失准乘 P1/P0 = 0.30/0.10，不失准乘 (1-P1)/(1-P0) = 0.70/0.90。
  内部以对数似然比累加实现，与累乘完全等价且不会浮点溢出。
- 首次达到“炉数除以误报上限”（对数口径 ln(N/alpha)）即报警，报警锁定。
- 实测与预计相差超过 threshold_minutes 分钟记为失准。
"""
import math

P0 = 0.10  # 原假设失准率：一成
P1 = 0.30  # 备择失准率：三成
LOG_STEP_INACCURATE = math.log(P1 / P0)
LOG_STEP_ACCURATE = math.log((1 - P1) / (1 - P0))
EPS = 1e-12  # 浮点容差，避免边界值误判


def alarm_boundary(furnace_count, alpha):
    """报警界限（对数口径）：ln(炉数 / 误报上限)。"""
    if furnace_count < 1:
        raise ValueError('至少需要1台炉')
    if not 0 < alpha < 1:
        raise ValueError('误报上限需在(0,1)之间')
    return math.log(furnace_count / alpha)


def is_inaccurate(actual_minutes, predicted_minutes, threshold_minutes):
    """实测与预计相差超过给定分钟数记为失准。"""
    return abs(actual_minutes - predicted_minutes) > threshold_minutes


def step(llr, inaccurate):
    """计入一条实测后的对数似然比。"""
    return llr + (LOG_STEP_INACCURATE if inaccurate else LOG_STEP_ACCURATE)


class FurnaceEngine:
    """单炉顺序核对引擎：乱序补报缓冲、缺号等待、累乘似然比、首次报警锁定。

    只依赖构造时传入的初始状态，持久化层从数据库装载/回写即可；
    各炉互不影响，一炉缺号只阻塞本炉。重试安全：已计入序号
    (seq < next_seq) 与缓冲中已有序号都会被忽略，不会重复计入。
    """

    def __init__(self, boundary, next_seq=1, llr=0.0, counted=0,
                 inaccurate_count=0, alarmed=False, alarm_seq=None):
        self.boundary = boundary
        self.next_seq = next_seq
        self.llr = llr
        self.counted = counted
        self.inaccurate_count = inaccurate_count
        self.alarmed = alarmed
        self.alarm_seq = alarm_seq
        self.pending = {}

    def buffer(self, seq, inaccurate):
        """登记一条待计入实测；重复或已计入序号返回False且不覆盖。"""
        if seq < self.next_seq or seq in self.pending:
            return False
        self.pending[seq] = bool(inaccurate)
        return True

    def drain(self):
        """按清单顺序计入已连续到达的序号；缺号停在缺号处等待。

        返回 (本次计入的序号列表, 首次报警序号或None)。报警只触发一次，
        之后继续计入但不再重复报警。
        """
        counted = []
        first_alarm = None
        while self.next_seq in self.pending:
            inaccurate = self.pending.pop(self.next_seq)
            self.llr = step(self.llr, inaccurate)
            self.counted += 1
            if inaccurate:
                self.inaccurate_count += 1
            counted.append(self.next_seq)
            if not self.alarmed and self.llr >= self.boundary - EPS:
                self.alarmed = True
                self.alarm_seq = self.next_seq
                first_alarm = self.next_seq
            self.next_seq += 1
        return counted, first_alarm
