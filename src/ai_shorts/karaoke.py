"""字幕のカラオケ（読んでいるところに色を塗る）のための、1字ごとの時刻の見積もり。

timing.json には文の始まりと終わりしかないので、文の中は次のように見積もる。
1. voice.wav の文の範囲から、話し始め・話し終わりと、文の中の間（min_pause 秒以上の無音）を探す。
2. 読点などの句読点と、見つけた間を、時刻の近いものどうしで順に対応させる（間のない読点・読点のない間もある）。
3. 対応した間で文を区切り、区切りの中は字の重み（かな1、漢字 KANJI_WEIGHT、小さいかな・記号0）で時間を割る。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# 漢字1字の読みの長さ（モーラ）の目安。読みが分からないので平均で見積もる
KANJI_WEIGHT = 1.8
SMALL = set("ぁぃぅぇぉゃゅょゎァィゥェォャュョヮ")
PAUSE_AFTER = set("、。，．！？!?…")
# 対応させない（間を割り当てない）ときの罰（秒）。時刻のずれがこれより大きければ対応させない
SKIP_COST = 0.6


@dataclass(frozen=True)
class Speech:
    start: float
    end: float
    gaps: list[tuple[float, float]]  # 文の中の間（始まり, 終わり）


def char_weight(c: str) -> float:
    if c in SMALL:
        return 0.0
    if "ぁ" <= c <= "ヿ":   # ひらがな・カタカナ（ー・っ を含む）
        return 1.0
    if "一" <= c <= "鿿" or c in "々〆ヶ":
        return KANJI_WEIGHT
    if c.isdigit():
        return 1.5
    if c.isalpha():
        return 1.0
    return 0.0   # 句読点・かぎかっこ・空白


def find_speech(audio: np.ndarray, sr: int, start: float, end: float, *,
                min_pause: float = 0.15, floor_db: float = 35.0, hop: float = 0.01) -> Speech:
    """文の範囲 [start, end] の中で、声の出ているところと間を探す。
    無音 = 10ms ごとの音量が、その文のいちばん大きいところより floor_db 下回るところ。"""
    seg = audio[int(round(start * sr)):int(round(end * sr))]
    n_hop = max(1, int(round(sr * hop)))
    n = len(seg) // n_hop
    if n == 0:
        return Speech(start, end, [])
    rms = np.sqrt((seg[:n * n_hop].reshape(n, n_hop) ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    loud = db >= db.max() - floor_db
    idx = np.flatnonzero(loud)
    if idx.size == 0:
        return Speech(start, end, [])
    first, last = int(idx[0]), int(idx[-1]) + 1
    gaps: list[tuple[float, float]] = []
    i = first
    while i < last:
        if not loud[i]:
            j = i
            while j < last and not loud[j]:
                j += 1
            if (j - i) * hop >= min_pause:
                gaps.append((start + i * hop, start + j * hop))
            i = j
        else:
            i += 1
    return Speech(start + first * hop, start + last * hop, gaps)


def _align(expected: list[float], centers: list[float]) -> list[tuple[int, int]]:
    """句読点の見積もり時刻 expected と間の中心 centers を、順を保って対応させる（編集距離と同じ DP）。"""
    m, n = len(expected), len(centers)
    cost = [[0.0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        cost[i][0] = i * SKIP_COST
    for j in range(1, n + 1):
        cost[0][j] = j * SKIP_COST
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost[i][j] = min(cost[i - 1][j] + SKIP_COST, cost[i][j - 1] + SKIP_COST,
                             cost[i - 1][j - 1] + abs(expected[i - 1] - centers[j - 1]))
    pairs: list[tuple[int, int]] = []
    i, j = m, n
    while i > 0 and j > 0:
        if cost[i][j] == cost[i - 1][j - 1] + abs(expected[i - 1] - centers[j - 1]):
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif cost[i][j] == cost[i - 1][j] + SKIP_COST:
            i -= 1
        else:
            j -= 1
    return pairs[::-1]


def _spread(weights: list[float], t0: float, t1: float) -> list[tuple[float, float]]:
    total = sum(weights)
    if total <= 0:
        weights, total = [1.0] * len(weights), float(len(weights) or 1)
    out, t = [], t0
    for w in weights:
        d = (t1 - t0) * w / total
        out.append((t, t + d))
        t += d
    return out


def char_times(text: str, speech: Speech) -> list[tuple[float, float]]:
    """text の1字ごとの（読み始め, 読み終わり）。句読点は長さ0で、直前の字の読み終わりに置く。"""
    if not text:
        return []
    weights = [char_weight(c) for c in text]
    total = sum(weights) or 1.0
    span = speech.end - speech.start - sum(b - a for a, b in speech.gaps)
    # 句読点の位置（その字のあとで間が入りうる）と、間を無視して割ったときの時刻
    marks, expected, acc = [], [], 0.0
    for k, c in enumerate(text):
        acc += weights[k]
        if c in PAUSE_AFTER and k < len(text) - 1 and (k + 1 >= len(text) or text[k + 1] not in PAUSE_AFTER):
            marks.append(k)
            expected.append(acc / total)
    # 間の中心も、間を除いた時間の割合で表す（句読点の見積もりと同じ物差し）
    centers, removed = [], 0.0
    for a, b in speech.gaps:
        centers.append((a - speech.start - removed) / span if span > 0 else 0.0)
        removed += b - a
    scale = max(span, 1e-6)
    pairs = _align([e * scale for e in expected], [c * scale for c in centers])

    times: list[tuple[float, float]] = [(0.0, 0.0)] * len(text)
    lo, t = 0, speech.start
    for mark_i, gap_j in [*pairs, (None, None)]:
        hi = marks[mark_i] + 1 if mark_i is not None else len(text)
        t_end = speech.gaps[gap_j][0] if gap_j is not None else speech.end
        for k, tt in enumerate(_spread(weights[lo:hi], t, t_end), start=lo):
            times[k] = tt
        if gap_j is not None:
            t = speech.gaps[gap_j][1]
        lo = hi
    return times
