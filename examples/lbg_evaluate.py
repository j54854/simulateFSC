"""シミュレーションログから総費用と社会的余剰を算出する例。

使い方:
    uv run examples/lbg_evaluate.py [ログのフォルダ（デフォルト: data/）]

評価の仮定（単価，価値関数など）は `Assumptions` で与える。
列の意味は docs/log_format.md またはログフォルダの params.json の columns を参照。
"""
import csv
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
def default_value(age: int, params: dict, v_max: float = 10, a_fresh: int | None = None) -> float:
    """消費者が受け取った製品1単位の価値を返す（デフォルトの価値関数）。

    age が `a_fresh` 以下では `v_max` で一定，その後は線形に下がり，
    販売できなくなる最初の age（`exp_age + 1`）で0になる。無期限なら常に `v_max`。

    Args:
        age: 消費者が受け取った時点の age。
        params: `load_log()` が返すパラメータ（`exp_age` と `supply_lead_times` を使う）。
        v_max: 新鮮な製品の価値。
        a_fresh: 価値が下がり始める age。`None` のとき，賞味期限の半分（`exp_age // 2`）と，
            小売に届く最も早い age（`sum(supply_lead_times[:-1])`）の大きい方とする。

    Returns:
        製品1単位の価値。
    """
    exp_age = params['exp_age']
    if exp_age is None:  # 無期限なら劣化しない
        return v_max
    if a_fresh is None:  # 最短で小売に届いた製品は新鮮とみなす
        a_fresh = max(exp_age // 2, sum(params['supply_lead_times'][:-1]))
    if age <= a_fresh:  # 鮮度が保たれている間は一定
        return v_max
    return max(0.0, v_max *(exp_age +1 -age) /(exp_age +1 -a_fresh))  # 線形に低下

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
@dataclass
class Assumptions:
    """評価の仮定。

    単価はスカラー（全段階共通）または段階ごとのリスト（stage 0 から順）で与える。

    Attributes:
        holding: 在庫単価（1単位・1期あたり）。
        stockout: 欠品単価。バックオーダーでは受注残1単位・1期あたり，失注では失注1単位あたり。
        waste: 廃棄単価（1単位あたり）。
        holding_basis: 在庫費の基準。'end' は期末在庫（on_hand），
            'start' は入荷直後の期首在庫（on_hand + cargo + waste）。
        v_max: デフォルトの価値関数で使う，新鮮な製品の価値。
        a_fresh: デフォルトの価値関数で使う，価値が下がり始める age（`None` のとき自動で決める．
            `default_value()` を参照）。
        value: 独自の価値関数 `value(age, params)`。`params` は `load_log()` が返すパラメータ。
            `None`（デフォルト）のときは `default_value()` を `v_max` と `a_fresh` で使う。
            独自の価値関数を与えた場合，`v_max` と `a_fresh` は使われない。
        disutility: 消費者の負の便益の単価（社会的余剰の計算にのみ使う）。
            単位は，バックオーダーでは受注残1単位・1期あたり，失注では失注1単位あたり。
            `None`（デフォルト）のときはモードに応じて自動で決める。
            バックオーダーでは stage 0 の欠品単価を，すぐに受け取れない不便さの評価とみなして使う。
            失注では0とする（失った分の価値は，受け取り価値に計上されないことで反映済みのため）。
        production: 生産単価（工場の生産量1単位あたり）。
    """
    holding: float | list[float] = 1
    stockout: float | list[float] = 1
    waste: float | list[float] = 1
    holding_basis: Literal['end', 'start'] = 'end'
    v_max: float = 10
    a_fresh: int | None = None
    value: Callable[[int, dict], float] | None = None
    disutility: float | None = None
    production: float = 0

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
def per_stage(unit: float | list[float], length: int) -> list[float]:  # 単価を段階ごとのリストにそろえる
    if isinstance(unit, list):
        assert len(unit) == length, 'Unit costs should be given for every stage!'
        return unit
    return [unit] *length

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
def load_log(log_dir: str | Path = 'data/') -> tuple[dict, list[list[dict[str, float]]]]:
    """ログフォルダから params.json と各段階の CSV を読み込む。

    Args:
        log_dir: `Chain.dump_log()` の出力先フォルダ。

    Returns:
        パラメータの辞書と，段階ごとの行（列名→値の辞書）のリスト。
    """
    path = Path(log_dir)
    with open(path / 'params.json', encoding='utf-8') as f:
        params = json.load(f)
    logs = []
    for stage_id in range(params['length']):
        with open(path / f'stage{stage_id}.csv', newline='') as f:
            logs.append([{key: float(val) for key, val in row.items()} for row in csv.DictReader(f)])
    return params, logs

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
def evaluate(params: dict, logs: list[list[dict[str, float]]], assumptions: Assumptions) -> dict[str, float]:
    """総費用と社会的余剰を全期間の合計で算出する。

    総費用 = 全段階の（在庫費 + 欠品費 + 廃棄費）
    社会的余剰 = 消費者の受け取り価値 - 全段階の在庫費 - 全段階の廃棄費 - 消費者の負の便益 - 生産費

    Args:
        params: `load_log()` が返すパラメータ。
        logs: `load_log()` が返す段階ごとの行。
        assumptions: 評価の仮定。

    Returns:
        各指標の全期間合計の辞書。
    """
    a = assumptions
    length, life = params['length'], params['life']
    holding = per_stage(a.holding, length)
    stockout = per_stage(a.stockout, length)
    waste = per_stage(a.waste, length)
    is_backorder = (params['stockout_mode'] == 'backorder')
    # 在庫費・欠品費・廃棄費（欠品量は受注残と失注量の和．どちらか一方は常に0）
    result = {'holding': 0.0, 'stockout': 0.0, 'waste': 0.0}
    for stage_id, rows in enumerate(logs):
        for row in rows:
            stock = row['on_hand']
            if a.holding_basis == 'start':  # 期首在庫に戻す
                stock += row['cargo'] +row['waste']
            result['holding'] += stock *holding[stage_id]
            result['stockout'] += (row['to_send'] +row['lost']) *stockout[stage_id]
            result['waste'] += row['waste'] *waste[stage_id]
    result['total_cost'] = result['holding'] +result['stockout'] +result['waste']
    # 消費者の受け取り価値（最下流の出荷を受け取った時点の age で評価）
    if a.value is None:  # 独自の価値関数がなければデフォルトを使う
        values = [default_value(age, params, a.v_max, a.a_fresh) for age in range(life)]
    else:
        values = [a.value(age, params) for age in range(life)]
    result['consumer_value'] = sum(
        row[f'cargo_{age}'] *values[age] for row in logs[0] for age in range(life)
        )
    # 消費者の負の便益
    disutility = a.disutility
    if disutility is None:
        disutility = stockout[0] if is_backorder else 0.0
    shortage = 'to_send' if is_backorder else 'lost'
    result['disutility'] = sum(row[shortage] for row in logs[0]) *disutility
    # 生産費
    result['production'] = sum(row['produced'] for row in logs[-1]) *a.production
    result['social_surplus'] = (
        result['consumer_value'] -result['holding'] -result['waste']
        -result['disutility'] -result['production']
        )
    return result

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
def main() -> None:
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    log_dir = sys.argv[1] if len(sys.argv) > 1 else 'data/'
    params, logs = load_log(log_dir)
    result = evaluate(params, logs, Assumptions())
    periods = len(logs[0])
    print(f"stockout_mode: {params['stockout_mode']}, periods: {periods}")
    print(f"{'indicator':<16}{'total':>14}{'per period':>14}")
    for key, val in result.items():
        print(f'{key:<16}{val:>14.1f}{val /periods:>14.2f}')

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
if __name__ == '__main__':
    main()
