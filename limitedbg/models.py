import csv
import math
from pathlib import Path
from typing import TypedDict

import numpy as np

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
class StageState(TypedDict):
    order_out: int
    order_in: int
    cargo: int
    to_send: int
    to_receive: int
    en_route: int
    waste: int
    on_hand: int
    costs: list[float]
    on_hand_vols: list[int]
    en_route_vols: list[int]
    cargo_vols: list[int]

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
class StageSummary(TypedDict):
    order_out: float
    order_in: float
    cargo: float
    to_send: float
    to_receive: float
    en_route: float
    waste: float
    on_hand: float
    costs: list[float]
    on_hand_vols: list[float]
    en_route_vols: list[float]
    cargo_vols: list[float]

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
class Agent:
    """在庫管理エージェント。

    指数平滑法で需要を予測し，安全在庫を1期分として定期発注方式で発注量を決定する。
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
            stage: 発注元の在庫点。`stage.on_hand`, `stage.en_route`, `stage.to_send`,
                `stage.to_receive`, `stage.lead_time`, `stage.order_in` を参照できる。

        Returns:
            今期の発注量（ロットまとめ前の要求量）。
        """
        self.forecast = (1- self.alpha) *self.forecast +self.alpha *stage.order_in  # 需要予測（指数平滑法）
        up_to = self.forecast *(stage.lead_time +2)  # サイクルタイム1期分と安全在庫1期分を加えた補充点
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

    生産能力に限界はなく，毎期の発注量がそのまま生産量になる。
    サブクラスでオーバーライドして生産能力制約などをカスタマイズできる。
    """
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def __init__(self) -> None:
        pass
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def process(self, required: int) -> int:
        """今期の生産量を返す。サブクラスでオーバーライドして生産能力制約などをカスタマイズできる。

        Args:
            required: 最上流段階からの発注量。

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
        lead_time: 上流への発注から入荷までの期数。
        lot_size: 最小発注単位。
        limit: 廃棄期限（期末に age=limit の製品を廃棄する）。
        on_hand: 手元在庫（Batch）。
        en_route: 入荷予定ロットのキュー（Batch のリスト，長さ = lead_time）。
        cargo: 今期の出荷ロット（Batch）。
        to_send: 受注残（受注済未出荷量）。
        to_receive: 発注残（発注済未入荷量）。
        order_in: 今期の受注量。
        order_out: 前期の発注量。
        waste: 今期の廃棄量。
        costs: 今期のコスト [在庫, 欠品, 廃棄]。
    """
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def __init__(
        self,
        chain: "Chain",  # サプライチェーンモデルへの参照
        stage_id: int,  # 下流からの連番
        lead_time: int,  # 上流への発注から補充までのリードタイム
        lot_size: int,  # 最小発注単位（この定数倍へのロットまとめが必要）
        limit: int,  # 廃棄期限（期末にage=limitのものを廃棄する）
        unit_cost: list[float],  # 単位コストのリスト [0: 在庫，1: 欠品，2: 廃棄]
        agent: Agent  # 在庫管理エージェントへの参照
        ) -> None:
        self.chain = chain
        self.id = stage_id
        self.lead_time = lead_time
        self.lot_size = lot_size
        self.limit = limit
        self.uc = unit_cost
        self.agent = agent
        self.on_hand = Batch(self.chain.life)  # 手元在庫
        self.en_route = [
            Batch(self.chain.life) for _ in range(self.lead_time)
            ]  # 入荷予定ロットのリスト
        self.cargo = Batch(self.chain.life)  # 出荷ロット
        self.to_send = 0  # 受注残（受注済未出荷量）
        self.order_in = 0  # 受注量
        self.order_out = 0  # 発注量
        self.to_receive = 0  # 発注残（発注済未入荷量）
        self.waste = 0  # 廃棄量
        self.costs: list[float] = [0] *3  # コストのリスト [0: 在庫，1: 欠品，2: 廃棄]
        self.states: list[StageState] = []  # 在庫点の状態
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def reset(self) -> None:  # 状態の初期化
        self.states = []
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def is_upmost(self) -> bool:  # 最上流（工場）かどうか
        return self.id == (len(self.chain.stages) -1)
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def en_route_all(self) -> Batch:  # 入荷予定ロットの合計
        total = Batch(self.chain.life)
        for batch in self.en_route:
            total.merge(batch)
        return total
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def receive(self) -> None:  # 入荷
        batch = self.en_route.pop(0)  # 最初の入荷予定ロット
        self.to_receive -= batch.total()  # 発注残の更新
        self.on_hand.merge(batch)  # 手元在庫に統合
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def pack_up(self) -> None:  # 出荷準備
        required = self.order_in +self.to_send  # 出荷すべき量
        self.to_send = max(0, required -self.on_hand.total())  # 欠品の更新
        fulfilled = required -self.to_send  # 実際の出荷量
        self.cargo = self.on_hand.take_out(fulfilled)  # 出荷ロット
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def discard(self) -> None:  # 廃棄
        self.waste = self.on_hand.discard(self.limit)  # 手元在庫の廃棄
        for batch in self.en_route:  # 入荷予定ロットの中に途中で廃棄されるものがないことを確認
            assert batch.count(self.limit) == 0, 'En route contained expiring products!'
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def costing(self) -> None:  # コスト計上
        self.costs[0] = self.on_hand.total() *self.uc[0]  # 在庫コストの計上
        self.costs[1] = self.to_send *self.uc[1]  # 欠品コストの計上
        self.costs[2] = self.waste *self.uc[2]  # 廃棄コストの計上
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def place_order(self) -> None:  # 発注
        required = self.agent.get_order(self)  # エージェントが要求量を決定
        # ロットまとめ（発注量を最小発注単位の定数倍にまとめる）
        self.order_out = math.ceil(required /self.lot_size) *self.lot_size
        self.to_receive += self.order_out  # 発注残の更新
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def elapse(self) -> None:  # 製品を1期分劣化させる
        self.on_hand.elapse()  # 手元在庫
        if not self.is_upmost():  # 最上流（工場）以外なら
            for batch in self.en_route:  # 入荷予定ロット
                batch.elapse()
        else:  # 最上流（工場）のen_routeは製造前なので劣化しない
            pass
        # cargoは発送済み（下流のen_route内）なので下流に任せる
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def capture_state(self) -> None:  # 状態を記録
        state: StageState = {  # 発注時点の状態（廃棄は済み，発送・劣化はまだ）
            'order_out': self.order_out,  # 前期の発注量
            'order_in': self.order_in,  # 今期の受注量
            'cargo': self.cargo.total(),  # 今期の出荷量
            'to_send': self.to_send,  # 今期の欠品量
            'to_receive': self.to_receive,  # 発注前の発注残
            'en_route': self.en_route_all().total(),  # 今期出荷分を除く合計入荷予定量
            'waste': self.waste,  # 今期の廃棄量
            'on_hand': self.on_hand.total(),  # 出荷・廃棄後の手元在庫量
            'costs': self.costs.copy(),  # 今期のコスト [0: 在庫，1: 欠品，2: 廃棄]
            'on_hand_vols': self.on_hand.vols.copy(),  # 手元在庫の内訳
            'en_route_vols': self.en_route_all().vols,  # 合計入荷予定量の内訳
            'cargo_vols': self.cargo.vols.copy()  # 出荷ロットの内訳
        }
        self.states.append(state)
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def summarize_state(self) -> StageSummary:  # 平均的な状態を算出
        n = len(self.states)
        summary: StageSummary = {
            'order_out': sum(s['order_out'] for s in self.states) /n,
            'order_in': sum(s['order_in'] for s in self.states) /n,
            'cargo': sum(s['cargo'] for s in self.states) /n,
            'to_send': sum(s['to_send'] for s in self.states) /n,
            'to_receive': sum(s['to_receive'] for s in self.states) /n,
            'en_route': sum(s['en_route'] for s in self.states) /n,
            'waste': sum(s['waste'] for s in self.states) /n,
            'on_hand': sum(s['on_hand'] for s in self.states) /n,
            'costs': [
                sum(s['costs'][i] for s in self.states) /n for i in range(3)
                ],
            'on_hand_vols': [
                sum(s['on_hand_vols'][age] for s in self.states) /n for age in range(self.chain.life)
                ],
            'en_route_vols': [
                sum(s['en_route_vols'][age] for s in self.states) /n for age in range(self.chain.life)
                ],
            'cargo_vols': [
                sum(s['cargo_vols'][age] for s in self.states) /n for age in range(self.chain.life)
                ]
        }
        return summary
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def dump_log(self, output_dir: str = 'data/') -> None:  # 状態ログの出力
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        with open(path / f'stage{self.id}.csv', 'w', newline='') as f:
            writer = csv.writer(f)
            header = ['order_out', 'order_in', 'cargo', 'to_send', 'to_receive', 'en_route', 'waste', 'on_hand', 'c_holding', 'c_stockout', 'c_waste']
            header += ['on_hand_' +str(age) for age in range(self.chain.life)]
            header += ['en_route_' +str(age) for age in range(self.chain.life)]
            header += ['cargo_' +str(age) for age in range(self.chain.life)]
            writer.writerow(header)
            for state in self.states:
                row = [state['order_out'], state['order_in'], state['cargo'], state['to_send'], state['to_receive'], state['en_route'], state['waste'], state['on_hand']] +state['costs'] +state['on_hand_vols'] +state['en_route_vols'] +state['cargo_vols']
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
        lead_times: 各段階のリードタイムリスト。
        lot_sizes: 各段階の最小発注単位リスト。
        market: 需要生成モデル。
        factory: 生産モデル。
    """
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def __init__(
        self,
        length: int = 4,
        lead_times: list[tuple[int, int]] | None = None,
        lot_sizes: list[tuple[int, int]] | None = None,
        exp_age: int | None = None,
        extra_limits: list[tuple[int, int]] | None = None,
        unit_costs: list[list[float]] | None = None,
        market: Market | None = None,
        factory: Factory | None = None,
        agents: list[Agent] | None = None,
        seed: int | None = None
        ) -> None:
        """サプライチェーンを初期化する。

        Args:
            length: サプライチェーンの段階数（デフォルト 4）。
            lead_times: デフォルト（2期）と異なるリードタイムを指定する場合の
                `[(stage_id, lead_time), ...]` リスト。
            lot_sizes: デフォルト（1単位）と異なる最小発注単位を指定する場合の
                `[(stage_id, lot_size), ...]` リスト。
            exp_age: 製品の賞味期限（期）。`None` のとき無期限。
            extra_limits: 廃棄期限を `exp_age` から自動計算される値より厳しくする場合の
                `[(stage_id, limit), ...]` リスト。
            unit_costs: 各段階の単位コストリスト `[[在庫, 欠品, 廃棄], ...]`。
                `None` のとき全段階 `[1, 1, 1]`。
            market: 需要生成モデル。`None` のとき `Market()` を使用。
            factory: 生産モデル。`None` のとき `Factory()` を使用。
            agents: 各段階の発注エージェントリスト。`None` のとき各段階に `Agent()` を使用。
            seed: 乱数シード。`None` のとき非決定的。`market` を明示指定した場合は無効。
        """
        self.length = length
        self.is_unlimited = (exp_age is None)  # 無期限かどうか
        # 各段階のリードタイム
        self.lead_times = [2] *self.length  # 基準値2
        if lead_times is not None:  # 変更指示があればそれを反映
            for stage_id, time in lead_times:
                self.lead_times[stage_id] = time
        if not self.is_unlimited:  # 有期限なら
            assert exp_age > sum(self.lead_times[:-1]), 'Expiration date is too short!'
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
        # 在庫内の製品のageの段階数（life）を最下流の廃棄期限+1に設定する
        self.life = self.limits[0] +1
        # 各段階の単位コスト [在庫，欠品，廃棄]
        if unit_costs is None:
            self.unit_costs = [[1, 1, 1] for _ in range(self.length)]
        else:
            self.unit_costs = unit_costs
        # 市場のモデル
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
        # 各段階の在庫管理エージェント
        if agents is None:
            self.agents = [Agent() for _ in range(self.length)]
        else:
            self.agents = agents
        self.stages = [  # サプライチェーンを構成する在庫点のリスト
            Stage(self, stage_id, lead_time, lot_size, limit, unit_cost, agent) for stage_id, (lead_time, lot_size, limit, unit_cost, agent) in enumerate(zip(self.lead_times, self.lot_sizes, self.limits, self.unit_costs, self.agents))
            ]
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
            limit -= self.lead_times[stage_id]  # 上流の期限はリードタイム分短縮
        return limits
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def get_demand(self) -> None:  # 各段階に需要を伝達
        # 最下流への需要は市場から
        self.stages[0].order_in = self.market.get_demand()
        for i in range(1, len(self.stages)):  # それ以外は直後の段階から
            self.stages[i].order_in = self.stages[i-1].order_out
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def ship_out(self) -> None:  # 各段階からの出荷ロットの発送
        output = self.factory.process(self.stages[-1].order_out)  # 工場の生産量
        cargo = Batch(self.life)  # 最上流は工場から
        cargo.add(output)
        self.stages[-1].en_route.append(cargo)  # 入荷予定に追加
        for i in range(1, len(self.stages)):  # それ以外は直前の段階から
            self.stages[i-1].en_route.append(self.stages[i].cargo)
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def operate(self) -> None:
        for stage in self.stages:
            stage.receive()  # 入荷
        self.get_demand()  # 受注（前期発注分）
        for stage in self.stages:
            stage.pack_up()  # 出荷準備
        for stage in self.stages:
            stage.discard()  # 廃棄
            stage.costing()  # コスト計上
            stage.capture_state()  # 状態の記録
            stage.place_order()  # 発注
        self.ship_out()  # 出荷ロットの発送
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
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    def dump_log(self, output_dir: str = 'data/') -> None:
        """各段階の状態ログを CSV ファイルに出力する。

        `stage{id}.csv` を `output_dir` に書き出す。ディレクトリが存在しない場合は作成する。
        列構成は `order_out`, `order_in`, `cargo`, `to_send`, `to_receive`, `en_route`,
        `waste`, `on_hand`, `c_holding`, `c_stockout`, `c_waste`，続いて age 別の内訳。

        Args:
            output_dir: 出力先ディレクトリ（デフォルト: 'data/'）。
        """
        for stage in self.stages:
            stage.dump_log(output_dir)
