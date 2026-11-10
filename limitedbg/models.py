import csv
import json
import math
from pathlib import Path
from typing import Literal, TypedDict, cast, get_args

import numpy as np

StockoutMode = Literal['backorder', 'lost_sales']  # 最下流（小売）の欠品の扱い

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
# ログの列定義（CSV のヘッダーと params.json の columns はここから生成する）
# 記録は各期の処理がすべて終わり，劣化（elapse）させる直前に行う
# [フロー] はその期に生じた量，[ストック] はその期末の量（age は劣化前の値）
# '{age}' を含む列は age=0〜life-1 に展開され，値は '<名前>_vols' から取る
LOG_COLUMNS: dict[str, str] = {
    'period': '期番号（run() の中で1から始まる連番）',
    'order_in': '[フロー] 今期の受注量（stage 0 は市場の需要量）',
    'cargo': '[フロー] 今期の出荷量（stage 0 は消費者への販売量）',
    'lost': '[フロー] 今期の失注量（失注モードの stage 0 のみ．他は常に0）',
    'waste': '[フロー] 今期の廃棄量',
    'order_out': '[フロー] 今期の発注量（ロットまとめ後）',
    'produced': '[フロー] 今期の工場の生産量（最上流のみ．他は常に0）',
    'on_hand': '[ストック] 期末の手元在庫量（出荷・廃棄後）',
    'to_send': '[ストック] 期末の受注残（失注モードの stage 0 では常に0）',
    'to_receive': '[ストック] 期末の発注残（今期の発注を含む）',
    'order_pipeline': '[ストック] 期末に上流へ届く途中の発注量の合計',
    'supply_pipeline': '[ストック] 期末に輸送中（最上流は生産中）の製品量の合計（今期の発送分を含む）',
    'on_hand_{age}': '[ストック] on_hand の age 別内訳',
    'supply_pipeline_{age}': '[ストック] supply_pipeline の age 別内訳',
    'cargo_{age}': '[フロー] cargo の age 別内訳（出荷時の age）',
}

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
def log_header(life: int) -> list[str]:
    """CSV ログのヘッダー（age 別の列を展開した列名リスト）を返す。

    Args:
        life: 製品の age 段階数（`Chain.life`）。

    Returns:
        `LOG_COLUMNS` の順に並んだ列名のリスト。
    """
    header = []
    for key in LOG_COLUMNS:
        if key.endswith('_{age}'):  # age 別の列は展開する
            header += [key.replace('{age}', str(age)) for age in range(life)]
        else:
            header.append(key)
    return header

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
class StageState(TypedDict):
    period: int
    order_in: int
    cargo: int
    lost: int
    waste: int
    order_out: int
    produced: int
    on_hand: int
    to_send: int
    to_receive: int
    order_pipeline: int
    supply_pipeline: int
    on_hand_vols: list[int]
    supply_pipeline_vols: list[int]
    cargo_vols: list[int]

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
class StageSummary(TypedDict):
    order_in: float
    cargo: float
    lost: float
    waste: float
    order_out: float
    produced: float
    on_hand: float
    to_send: float
    to_receive: float
    order_pipeline: float
    supply_pipeline: float
    on_hand_vols: list[float]
    supply_pipeline_vols: list[float]
    cargo_vols: list[float]

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
class Agent:
    """在庫管理エージェント。

    指数平滑法で需要を予測し，安全在庫を1期分として定期発注方式で発注量を決定する。
    発注は期末，入荷は期首なので，発注LT＋補充LT の期間がサイクルタイムを含む補充の対象期間となる。
    サブクラスでオーバーライドして発注ロジックをカスタマイズできる。

    Attributes:
        alpha: 指数平滑法の平滑化定数（0〜1）。大きいほど直近の需要を重視する。
        forecast: 直近の需要予測値。
    """
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def __init__(self) -> None:
        self.alpha: float = 0.2  # 平滑化定数
        self.forecast: float = 0  # 予測値
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def get_order(self, stage: "Stage") -> float:
        """発注量を決定して返す。サブクラスでオーバーライドして発注ロジックをカスタマイズできる。

        Args:
            stage: 発注元の在庫点。`stage.on_hand`, `stage.to_send`, `stage.to_receive`,
                `stage.order_in`, `stage.lost`, `stage.order_lead_time`, `stage.supply_lead_time`,
                `stage.order_pipeline`, `stage.supply_pipeline` を参照できる。

        Returns:
            今期の発注量（ロットまとめ前の要求量）。
        """
        self.forecast = (1- self.alpha) *self.forecast +self.alpha *stage.order_in  # 需要予測（指数平滑法）
        # 補充の対象期間（発注LT＋補充LT，サイクルタイムを含む）に安全在庫1期分を加えた補充点
        up_to = self.forecast *(stage.order_lead_time +stage.supply_lead_time +1)
        net_stock = stage.to_receive +stage.on_hand.total() -stage.to_send  # 発注残と受注残を反映した正味在庫量
        return max(0, up_to -net_stock)  # 発注量が負にならないように調整

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
class Market:
    """市場モデル。

    平均値一定のポアソン分布で毎期の需要量を生成する。
    サブクラスでオーバーライドして需要パターンをカスタマイズできる。

    Attributes:
        mean: 需要量の平均値。
        rng: 乱数生成器。Chain の seed パラメータで初期化される。
    """
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def __init__(self, average_demand: int = 10, rng: np.random.Generator | None = None) -> None:
        self.mean: int = average_demand  # 平均需要量
        self.rng: np.random.Generator = rng if rng is not None else np.random.default_rng()
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def get_demand(self) -> int:
        """今期の需要量を生成して返す。サブクラスでオーバーライドして需要パターンをカスタマイズできる。

        Returns:
            今期の需要量（非負整数）。
        """
        return self.rng.poisson(self.mean)  # ポアソン分布

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
class Factory:
    """工場モデル。

    生産能力に限界はなく，工場に届いた発注量がそのまま生産量になる。
    サブクラスでオーバーライドして生産能力制約などをカスタマイズできる。
    """
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def __init__(self) -> None:
        pass
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def process(self, required: int) -> int:
        """今期の生産量を返す。サブクラスでオーバーライドして生産能力制約などをカスタマイズできる。

        Args:
            required: 今期に工場に届いた発注量（最上流段階が発注リードタイム前に発注した量）。

        Returns:
            今期の生産量。
        """
        return required   # 生産量は発注量に等しい

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
class Batch:
    """経過時間（age）別に管理された製品の集合。

    製品を生産からの経過時間（age）ごとに `vols` リストで管理する。
    `life=1` のとき「無期限」扱いとなり，劣化・廃棄は行われない。
    取り出しは FIFO（age の大きいものから先に出荷）。

    Attributes:
        life: age の段階数（age は 0〜life-1 の範囲）。
        is_unlimited: True のとき無期限製品（life=1）。
        vols: age 別の製品数リスト。vols[0] が最も新しい。
    """
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def __init__(self, life: int = 1) -> None:
        self.life: int = life  # ageの上限を決める値（age=0〜life-1）
        # ただし，life=1は，劣化しない無期限の製品で，常にage=0とする
        self.is_unlimited: bool = (life == 1)  # 無期限かどうか
        self.vols: list[int] = [0] *self.life  # age別の製品数
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def total(self) -> int:  # 総量
        return sum(self.vols)
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def add(self, vol: int = 1, age: int = 0) -> None:  # 数量とageを指定して追加
        assert 0 <= age < self.life, 'Age should be in [0, life-1]!'
        assert vol >= 0, 'You cannot add negative volume!'
        self.vols[age] += vol
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def merge(self, batch: "Batch") -> None:  # batchのvolsを統合
        self.vols = [a +b for a, b in zip(self.vols, batch.vols)]
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def take_out(self, vol: int) -> "Batch":  # 数量を指定してFIFOで取り出す
        assert vol >= 0, 'You cannot take out negative volume!'
        assert self.total() >= vol, 'You cannot take out more than you have!'
        batch = Batch(self.life)
        for age in reversed(range(self.life)):  # FIFOで取り出す
            out = min(self.vols[age], vol)  # ageの降順に出荷可能量を算出
            batch.vols[age], self.vols[age] = out, (self.vols[age] -out)
            vol -= out  # 出荷すべき残量
            if not vol:  # がなければ
                return batch
        assert False, 'There are not enough products in the batch!'
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def count(self, age: int) -> int:  # 指定ageの製品数を返す（副作用なし）
        if self.is_unlimited:
            return 0
        assert 0 <= age < self.life, 'age should be in [0, life-1]!'
        return self.vols[age]
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def discard(self, age: int) -> int:  # ageを指定して廃棄（廃棄量を返す）
        if self.is_unlimited:  # 無期限の製品は廃棄しない
            return  0
        else:  # 有期限なら
            assert 0 <= age < self.life, 'age should be in [0, life-1]!'
            discarded, self.vols[age] = self.vols[age], 0
            return discarded
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def elapse(self) -> None:  # 製品を1期分劣化させる
        if self.is_unlimited:  # 無期限の製品は劣化しない
            return
        else:  # 有期限なら
            assert self.vols[-1] == 0, 'You should discard expired products first!'
            self.vols = [0] +self.vols[:-1]  # 経過時間 += 1

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
class Stage:
    """サプライチェーンを構成する在庫点のモデル。

    手元在庫・入荷予定・出荷ロットをすべて `Batch` インスタンスで管理する。
    `Chain.operate()` から呼ばれる各メソッドが1期間の動作を実装する。

    Attributes:
        id: サプライチェーン内の連番（0 が最下流）。
        order_lead_time: 発注が上流（最上流は工場）に届くまでの期数。
        supply_lead_time: 上流が出荷（最上流は工場が生産）してから入荷するまでの期数。
        lot_size: 最小発注単位。
        limit: 廃棄期限（期末に age=limit の製品を廃棄する）。
        on_hand: 手元在庫（Batch）。
        order_pipeline: 上流へ届く途中の発注量のキュー（長さ = order_lead_time）。
        supply_pipeline: 入荷予定ロットのキュー（Batch のリスト，長さ = supply_lead_time）。
        cargo: 今期の出荷ロット（Batch）。
        to_send: 受注残（受注済未出荷量）。
        to_receive: 発注残（発注済未入荷量）。
        order_in: 今期の受注量。
        order_out: 今期の発注量。
        lost: 今期の失注量（失注モードの最下流のみ）。
        waste: 今期の廃棄量。
        produced: 今期の工場の生産量（最上流のみ）。
    """
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def __init__(
        self,
        chain: "Chain",  # サプライチェーンモデルへの参照
        stage_id: int,  # 下流からの連番
        order_lead_time: int,  # 発注が上流に届くまでのリードタイム
        supply_lead_time: int,  # 上流の出荷から入荷までのリードタイム
        lot_size: int,  # 最小発注単位（この定数倍へのロットまとめが必要）
        limit: int,  # 廃棄期限（期末にage=limitのものを廃棄する）
        agent: Agent  # 在庫管理エージェントへの参照
        ) -> None:
        self.chain = chain
        self.id = stage_id
        self.order_lead_time = order_lead_time
        self.supply_lead_time = supply_lead_time
        self.lot_size = lot_size
        self.limit = limit
        self.agent = agent
        self.on_hand = Batch(self.chain.life)  # 手元在庫
        self.order_pipeline = [0] *self.order_lead_time  # 上流へ届く途中の発注量のリスト
        self.supply_pipeline = [
            Batch(self.chain.life) for _ in range(self.supply_lead_time)
            ]  # 入荷予定ロットのリスト
        self.cargo = Batch(self.chain.life)  # 出荷ロット
        self.to_send = 0  # 受注残（受注済未出荷量）
        self.order_in = 0  # 受注量
        self.order_out = 0  # 発注量
        self.to_receive = 0  # 発注残（発注済未入荷量）
        self.lost = 0  # 失注量
        self.waste = 0  # 廃棄量
        self.produced = 0  # 工場の生産量（最上流のみ）
        self.states: list[StageState] = []  # 在庫点の状態
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def reset(self) -> None:  # 状態の初期化
        self.states = []
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def is_upmost(self) -> bool:  # 最上流（工場）かどうか
        return self.id == (len(self.chain.stages) -1)
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def supply_pipeline_all(self) -> Batch:  # 入荷予定ロットの合計
        total = Batch(self.chain.life)
        for batch in self.supply_pipeline:
            total.merge(batch)
        return total
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def receive(self) -> None:  # 入荷
        batch = self.supply_pipeline.pop(0)  # 最初の入荷予定ロット
        self.to_receive -= batch.total()  # 発注残の更新
        self.on_hand.merge(batch)  # 手元在庫に統合
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def pack_up(self) -> None:  # 出荷準備
        if self.id == 0 and self.chain.stockout_mode == 'lost_sales':  # 最下流の失注モードなら
            fulfilled = min(self.order_in, self.on_hand.total())  # 実際の出荷量
            self.lost = self.order_in -fulfilled  # 不足分は失注（持ち越さない）
        else:  # バックオーダーなら
            required = self.order_in +self.to_send  # 出荷すべき量
            self.to_send = max(0, required -self.on_hand.total())  # 欠品の更新
            fulfilled = required -self.to_send  # 実際の出荷量
        self.cargo = self.on_hand.take_out(fulfilled)  # 出荷ロット
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def discard(self) -> None:  # 廃棄
        self.waste = self.on_hand.discard(self.limit)  # 手元在庫の廃棄
        for batch in self.supply_pipeline:  # 入荷予定ロットの中に途中で廃棄されるものがないことを確認
            assert batch.count(self.limit) == 0, 'Supply pipeline contained expiring products!'
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def place_order(self) -> None:  # 発注
        required = self.agent.get_order(self)  # エージェントが要求量を決定
        # ロットまとめ（発注量を最小発注単位の定数倍にまとめる）
        self.order_out = math.ceil(required /self.lot_size) *self.lot_size
        self.order_pipeline.append(self.order_out)  # 上流へ届く途中の発注に追加
        self.to_receive += self.order_out  # 発注残の更新
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def elapse(self) -> None:  # 製品を1期分劣化させる
        self.on_hand.elapse()  # 手元在庫
        if not self.is_upmost():  # 最上流（工場）以外なら
            for batch in self.supply_pipeline:  # 入荷予定ロット
                batch.elapse()
        else:  # 最上流（工場）のsupply_pipelineは製造中なので劣化しない
            pass
        # cargoは発送済み（下流のsupply_pipeline内）なので下流に任せる
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def capture_state(self) -> None:  # 状態を記録
        supply = self.supply_pipeline_all()
        state: StageState = {  # 期末の状態（発注・発送は済み，劣化はまだ）
            'period': len(self.states) +1,  # 期番号
            'order_in': self.order_in,  # 今期の受注量
            'cargo': self.cargo.total(),  # 今期の出荷量
            'lost': self.lost,  # 今期の失注量
            'waste': self.waste,  # 今期の廃棄量
            'order_out': self.order_out,  # 今期の発注量
            'produced': self.produced,  # 今期の工場の生産量
            'on_hand': self.on_hand.total(),  # 出荷・廃棄後の手元在庫量
            'to_send': self.to_send,  # 期末の受注残
            'to_receive': self.to_receive,  # 今期の発注を含む発注残
            'order_pipeline': sum(self.order_pipeline),  # 上流へ届く途中の発注量
            'supply_pipeline': supply.total(),  # 今期の発送分を含む入荷予定量
            'on_hand_vols': self.on_hand.vols.copy(),  # 手元在庫の内訳
            'supply_pipeline_vols': supply.vols,  # 入荷予定量の内訳
            'cargo_vols': self.cargo.vols.copy()  # 出荷ロットの内訳
        }
        self.states.append(state)
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def summarize_state(self) -> StageSummary:  # 平均的な状態を算出
        n = len(self.states)
        summary = {}
        for key in StageSummary.__annotations__:
            if key.endswith('_vols'):  # age別の内訳
                summary[key] = [
                    sum(s[key][age] for s in self.states) /n for age in range(self.chain.life)
                    ]
            else:
                summary[key] = sum(s[key] for s in self.states) /n
        return cast(StageSummary, summary)
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def dump_log(self, output_dir: str = 'data/') -> None:  # 状態ログの出力
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        with open(path / f'stage{self.id}.csv', 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(log_header(self.chain.life))
            for state in self.states:
                row = []
                for key in LOG_COLUMNS:
                    if key.endswith('_{age}'):  # age別の列は内訳リストを展開
                        row += state[key.replace('{age}', 'vols')]
                    else:
                        row.append(state[key])
                writer.writerow(row)

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
class Chain:
    """サプライチェーン全体のモデル。

    複数の `Stage` を連結し，1期間の動作を `operate()` で実装する。
    `stages[0]` が最下流（小売），`stages[-1]` が最上流（工場直前）。

    Attributes:
        length: サプライチェーンの段階数。
        stages: 在庫点のリスト（stages[0] が最下流）。
        life: 製品の age 段階数（= 最下流の limit + 1）。
        limits: 各段階の廃棄期限リスト。
        order_lead_times: 各段階の発注リードタイムリスト。
        supply_lead_times: 各段階の補充リードタイムリスト。
        lot_sizes: 各段階の最小発注単位リスト。
        stockout_mode: 最下流の欠品の扱い（'backorder' または 'lost_sales'）。
        market: 需要生成モデル。
        factory: 生産モデル。
    """
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def __init__(
        self,
        length: int = 4,
        order_lead_times: list[tuple[int, int]] | None = None,
        supply_lead_times: list[tuple[int, int]] | None = None,
        lot_sizes: list[tuple[int, int]] | None = None,
        exp_age: int | None = None,
        extra_limits: list[tuple[int, int]] | None = None,
        stockout_mode: StockoutMode = 'backorder',
        market: Market | None = None,
        factory: Factory | None = None,
        agents: list[Agent] | None = None,
        seed: int | None = None
        ) -> None:
        """サプライチェーンを初期化する。

        リードタイムのデフォルトはオリジナルのビアゲームに合わせ，
        発注リードタイムは中間段階2期・最上流（工場への発注）1期，補充リードタイムは全段階2期とする。

        Args:
            length: サプライチェーンの段階数（デフォルト 4）。
            order_lead_times: デフォルトと異なる発注リードタイムを指定する場合の
                `[(stage_id, lead_time), ...]` リスト。1以上。
            supply_lead_times: デフォルトと異なる補充リードタイムを指定する場合の
                `[(stage_id, lead_time), ...]` リスト。1以上。
            lot_sizes: デフォルト（1単位）と異なる最小発注単位を指定する場合の
                `[(stage_id, lot_size), ...]` リスト。
            exp_age: 製品の賞味期限（期）。`None` のとき無期限。
            extra_limits: 廃棄期限を `exp_age` から自動計算される値より厳しくする場合の
                `[(stage_id, limit), ...]` リスト。
            stockout_mode: 最下流（小売）の欠品の扱い。'backorder' は受注残として持ち越し，
                'lost_sales' は失注とする。中間段階は常にバックオーダー。
            market: 需要生成モデル。`None` のとき `Market()` を使用。
            factory: 生産モデル。`None` のとき `Factory()` を使用。
            agents: 各段階の発注エージェントリスト。`None` のとき各段階に `Agent()` を使用。
            seed: 乱数シード。`None` のとき非決定的。`market` を明示指定した場合は無効。
        """
        self.length = length
        self.is_unlimited = (exp_age is None)  # 無期限かどうか
        # 各段階の発注リードタイム
        self.order_lead_times = [2] *(self.length -1) +[1]  # 基準値は中間段階2，工場への発注1
        if order_lead_times is not None:  # 変更指示があればそれを反映
            for stage_id, time in order_lead_times:
                self.order_lead_times[stage_id] = time
        assert all(time >= 1 for time in self.order_lead_times), 'Order lead times should be at least 1!'
        # 各段階の補充リードタイム
        self.supply_lead_times = [2] *self.length  # 基準値2
        if supply_lead_times is not None:  # 変更指示があればそれを反映
            for stage_id, time in supply_lead_times:
                self.supply_lead_times[stage_id] = time
        assert all(time >= 1 for time in self.supply_lead_times), 'Supply lead times should be at least 1!'
        self.exp_age = exp_age
        # 各段階の最小発注単位
        self.lot_sizes = [1] *self.length  # 基準値1
        if lot_sizes is not None:  # 変更指示があればそれを反映
            for stage_id, size in lot_sizes:
                self.lot_sizes[stage_id] = size
        # 各段階の廃棄期限
        if self.is_unlimited:  # 無期限なら
            self.limits = [0] *self.length  # 期限はすべて0
        else:  # 有期限なら
            self.limits = self.set_limits(exp_age, extra_limits)
            # 期限は上流ほど短いので，最上流で1期以上残っていれば全段階で輸送中に期限切れにならない
            # （extra_limitsで絞った後の値で確認する．絞らなければ exp_age > sum(supply_lead_times[:-1]) と同値）
            assert self.limits[-1] >= 1, 'Disposal limits are too short for the supply lead times!'
        # 在庫内の製品のageの段階数（life）を最下流の廃棄期限+1に設定する
        self.life = self.limits[0] +1
        # 最下流の欠品の扱い
        assert stockout_mode in get_args(StockoutMode), f'Unknown stockout mode: {stockout_mode}!'
        self.stockout_mode = stockout_mode
        # 市場のモデル
        self.seed = seed
        rng = np.random.default_rng(seed)
        if market is None:
            self.market = Market(rng=rng)
        else:
            self.market = market
        # 工場のモデル
        if factory is None:
            self.factory = Factory()
        else:
            self.factory = factory
        self.factory_order = 0  # 今期に工場に届いた発注量
        # 各段階の在庫管理エージェント
        if agents is None:
            self.agents = [Agent() for _ in range(self.length)]
        else:
            self.agents = agents
        self.stages = [  # サプライチェーンを構成する在庫点のリスト
            Stage(self, stage_id, order_lead_time, supply_lead_time, lot_size, limit, agent) for stage_id, (order_lead_time, supply_lead_time, lot_size, limit, agent) in enumerate(zip(self.order_lead_times, self.supply_lead_times, self.lot_sizes, self.limits, self.agents))
            ]
        self.warmup_periods = 0  # ログを破棄した期間数
        self.run_periods = 0  # ログに記録されている期間数
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def set_limits(self, exp_age: int, extra_limits: list[tuple[int, int]] | None) -> list[int]:  # 廃棄期限の設定
        # extra_limitsをidをキーとするリストextrasに変換
        extras = [None] *self.length
        if extra_limits is not None:
            for stage_id, limit in extra_limits:
                extras[stage_id] = limit
        limit = exp_age  # 最下流の期限を賞味期限に仮設定
        limits = []
        for stage_id in range(self.length):
            if extras[stage_id] is not None:  # 廃棄期限の指定があればそれを反映
                limit = min(limit, extras[stage_id])
            limits.append(limit)
            limit -= self.supply_lead_times[stage_id]  # 上流の期限は補充リードタイム分短縮
        return limits
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def get_demand(self) -> None:  # 各段階に需要を伝達
        # 最下流への需要は市場から
        self.stages[0].order_in = self.market.get_demand()
        for i in range(1, len(self.stages)):  # それ以外は直後の段階の発注のうち今期に届くものから
            self.stages[i].order_in = self.stages[i-1].order_pipeline.pop(0)
        self.factory_order = self.stages[-1].order_pipeline.pop(0)  # 工場に届く発注
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def ship_out(self) -> None:  # 各段階からの出荷ロットの発送
        output = self.factory.process(self.factory_order)  # 工場の生産量
        self.stages[-1].produced = output
        cargo = Batch(self.life)  # 最上流は工場から
        cargo.add(output)
        self.stages[-1].supply_pipeline.append(cargo)  # 入荷予定に追加
        for i in range(1, len(self.stages)):  # それ以外は直前の段階から
            self.stages[i-1].supply_pipeline.append(self.stages[i].cargo)
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def operate(self) -> None:
        for stage in self.stages:
            stage.receive()  # 入荷
        self.get_demand()  # 受注（発注リードタイム前の発注分）
        for stage in self.stages:
            stage.pack_up()  # 出荷準備
        for stage in self.stages:
            stage.discard()  # 廃棄
            stage.place_order()  # 発注
        self.ship_out()  # 出荷ロットの発送
        for stage in self.stages:
            stage.capture_state()  # 状態の記録（下流の劣化でcargoが変わる前に全段階を記録する）
        for stage in self.stages:
            stage.elapse()  # 劣化を進める
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def dry_run(self, periods: int = 100) -> None:
        """ウォームアップ用のシミュレーションを実行し，状態ログを破棄する。

        エージェントの予測値や在庫水準を定常状態に収束させるために使う。
        終了後に各段階の `states` リストをリセットするため，本計測に影響しない。

        Args:
            periods: ウォームアップ期間数。
        """
        for _ in range(periods):
            self.operate()
        for stage in self.stages:
            stage.reset()  # 状態の初期化
        self.warmup_periods += self.run_periods +periods  # それまでの記録分も破棄される
        self.run_periods = 0
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def run(self, periods: int = 100) -> None:
        """本計測のシミュレーションを実行する。

        各期の状態は各段階の `states` リストに蓄積される。
        `dry_run()` でウォームアップ後に呼ぶことを推奨する。

        Args:
            periods: 計測期間数。
        """
        for _ in range(periods):
            self.operate()
        self.run_periods += periods
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def params(self) -> dict:
        """ログの解釈に必要なパラメータと列定義を辞書で返す。

        Returns:
            `params.json` に書き出す内容の辞書。
        """
        return {
            'length': self.length,
            'order_lead_times': self.order_lead_times,
            'supply_lead_times': self.supply_lead_times,
            'lot_sizes': self.lot_sizes,
            'exp_age': self.exp_age,
            'limits': self.limits,
            'life': self.life,
            'stockout_mode': self.stockout_mode,
            'seed': self.seed,
            'warmup_periods': self.warmup_periods,
            'run_periods': self.run_periods,
            'market': type(self.market).__name__,
            'factory': type(self.factory).__name__,
            'agents': [type(agent).__name__ for agent in self.agents],
            'columns': LOG_COLUMNS,
        }
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def dump_log(self, output_dir: str = 'data/') -> None:
        """各段階の状態ログを CSV ファイルに，パラメータを JSON ファイルに出力する。

        `stage{id}.csv` と `params.json` を `output_dir` に書き出す。
        ディレクトリが存在しない場合は作成する。列の意味は `LOG_COLUMNS` を参照。

        Args:
            output_dir: 出力先ディレクトリ（デフォルト: 'data/'）。
        """
        for stage in self.stages:
            stage.dump_log(output_dir)
        with open(Path(output_dir) / 'params.json', 'w', encoding='utf-8') as f:
            json.dump(self.params(), f, ensure_ascii=False, indent=2)
