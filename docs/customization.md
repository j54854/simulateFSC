# カスタマイズガイド

`Agent`・`Market`・`Factory` をサブクラス化し，`Chain` に渡すことで，シミュレーションの挙動をカスタマイズできます。

---

## Agent のカスタマイズ（発注ロジック）

`Agent.get_order(stage)` をオーバーライドして，独自の発注ロジックを実装します。

### シグネチャ

```python
def get_order(self, stage: lbg.Stage) -> float
```

### `stage` から参照できる属性

| 属性 | 型 | 内容 |
|------|-----|------|
| `stage.order_in` | `int` | 今期の受注量（stage 0 は欠品分を含む市場の需要量） |
| `stage.cargo` | `Batch` | 今期の出荷ロット（`stage.cargo.total()` で出荷量） |
| `stage.lost` | `int` | 今期の失注量（失注モードの stage 0 のみ） |
| `stage.on_hand` | `Batch` | 手元在庫（`stage.on_hand.total()` で合計量） |
| `stage.order_pipeline` | `list[int]` | 上流へ届く途中の発注量のキュー（先頭が次に届く） |
| `stage.supply_pipeline` | `list[Batch]` | 入荷予定ロットのキュー（先頭が次に入荷する） |
| `stage.to_send` | `int` | 受注残（未出荷の積み残し） |
| `stage.to_receive` | `int` | 発注残（届く途中の発注，上流の受注残，輸送中の製品の合計） |
| `stage.order_lead_time` | `int` | 発注リードタイム |
| `stage.supply_lead_time` | `int` | 補充リードタイム |
| `stage.lot_size` | `int` | 最小発注単位 |
| `stage.limit` | `int` | 廃棄期限 |

`get_order()` は出荷準備と廃棄の後に呼ばれるので，今期の `cargo` と `lost` は確定しています．

### 実装例

```python
import limitedbg as lbg

# 例1：受注量をそのまま発注（バッファなし）
class PassThroughAgent(lbg.Agent):
    def get_order(self, stage):
        return stage.order_in

# 例2：定量発注（常に固定量を発注）
class FixedOrderAgent(lbg.Agent):
    def __init__(self, fixed_qty: int = 10) -> None:
        super().__init__()
        self.fixed_qty = fixed_qty

    def get_order(self, stage):
        return self.fixed_qty

# 例3：費用の単価を使う発注（単価はエージェント自身が持つ）
class CostAwareAgent(lbg.Agent):
    def __init__(self, holding: float = 1, stockout: float = 1) -> None:
        super().__init__()
        self.ratio = stockout /(holding +stockout)  # 欠品単価が高いほど安全在庫を厚くする

    def get_order(self, stage):
        self.forecast = (1 -self.alpha) *self.forecast +self.alpha *stage.order_in
        up_to = self.forecast *(stage.order_lead_time +stage.supply_lead_time +2 *self.ratio)
        net_stock = stage.to_receive +stage.on_hand.total() -stage.to_send
        return max(0, up_to -net_stock)

# 使い方
chain = lbg.Chain(
    exp_age=12,
    agents=[PassThroughAgent() for _ in range(4)]
)
```

> **注意:** 費用の単価は `Chain` のパラメータではありません．発注の判断に単価を使う場合は，例3のようにエージェントのコンストラクタで受け取ってください．評価用の単価はログから外部で与えます（`examples/lbg_evaluate.py`）．

### 失注モードでの需要予測

失注モード（`stockout_mode='lost_sales'`）でも，stage 0 の `order_in` は欠品分を含む本当の需要です．デフォルトの `Agent` はこれを使って予測します．実際の店舗のように，販売量しか観測できない状況を再現したい場合は，`order_in` の代わりに `stage.cargo.total()`（= `order_in - lost`）を使って予測してください．

```python
class SalesBasedAgent(lbg.Agent):
    def get_order(self, stage):
        sales = stage.cargo.total()  # 観測できるのは販売量のみ
        self.forecast = (1 -self.alpha) *self.forecast +self.alpha *sales
        up_to = self.forecast *(stage.order_lead_time +stage.supply_lead_time +1)
        net_stock = stage.to_receive +stage.on_hand.total() -stage.to_send
        return max(0, up_to -net_stock)
```

---

## Market のカスタマイズ（需要パターン）

`Market.get_demand()` をオーバーライドして，独自の需要パターンを実装します。

### シグネチャ

```python
def get_demand(self) -> int
```

### 実装例

```python
import limitedbg as lbg
import numpy as np

# 例1：一様分布による需要
class UniformMarket(lbg.Market):
    def __init__(self, low: int = 5, high: int = 15) -> None:
        super().__init__()
        self.low = low
        self.high = high

    def get_demand(self) -> int:
        return int(self.rng.integers(self.low, self.high + 1))

# 例2：季節変動あり需要（sin波でスパイク）
class SeasonalMarket(lbg.Market):
    def __init__(self, base: int = 10, amplitude: int = 5, period: int = 52) -> None:
        super().__init__()
        self.base = base
        self.amplitude = amplitude
        self.period = period
        self._t = 0

    def get_demand(self) -> int:
        mean = self.base + self.amplitude * np.sin(2 * np.pi * self._t / self.period)
        self._t += 1
        return int(self.rng.poisson(max(1, mean)))

# 使い方
chain = lbg.Chain(exp_age=12, market=UniformMarket(5, 15))
```

> **注意:** `market` を明示指定した場合，`Chain(seed=...)` は無効になります。  
> 乱数を制御したい場合は `Market.__init__` 内で `self.rng` を設定してください。

---

## Factory のカスタマイズ（生産能力）

`Factory.process(required)` をオーバーライドして，生産能力制約などを実装します。

`required` は今期に工場に届いた発注量で，最上流の段階がその発注リードタイム（デフォルト1期）前に発注した量です．返した生産量は，最上流の補充リードタイム（デフォルト2期）後に入荷します．生産量はログの `produced` 列に記録されます．

### シグネチャ

```python
def process(self, required: int) -> int
```

> **注意:** `process()` が `required` より少ない量を返した場合，不足分を工場側で持ち越さないと，最上流の `to_receive`（発注残）が0に戻らなくなります．下の例のように受注残を管理してください．工場の受注残は，最上流のログの `to_receive - order_pipeline - supply_pipeline` で計算できます．

### 実装例

```python
import limitedbg as lbg

# 例：生産能力に上限あり（作れなかった分は受注残として持ち越す）
class CapacitatedFactory(lbg.Factory):
    def __init__(self, capacity: int = 20) -> None:
        super().__init__()
        self.capacity = capacity
        self.backlog = 0  # 工場の受注残

    def process(self, required: int) -> int:
        total = required +self.backlog  # 今期に届いた発注と受注残の合計
        output = min(total, self.capacity)
        self.backlog = total -output  # 作れなかった分を持ち越す
        return output

# 使い方
chain = lbg.Chain(exp_age=12, factory=CapacitatedFactory(capacity=15))
```

---

## 複数のカスタマイズを組み合わせる

```python
import limitedbg as lbg

chain = lbg.Chain(
    exp_age=12,
    seed=42,
    market=UniformMarket(5, 15),
    factory=CapacitatedFactory(capacity=15),
    agents=[PassThroughAgent() for _ in range(4)],
)
chain.dry_run(periods=100)
chain.run(periods=500)
chain.dump_log()
```
