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
| `stage.order_in` | `int` | 今期の受注量 |
| `stage.on_hand` | `Batch` | 手元在庫（`stage.on_hand.total()` で合計量） |
| `stage.en_route` | `list[Batch]` | 入荷予定ロットのキュー |
| `stage.to_send` | `int` | 受注残（未出荷の積み残し） |
| `stage.to_receive` | `int` | 発注残（発注済未入荷の合計） |
| `stage.lead_time` | `int` | リードタイム |
| `stage.lot_size` | `int` | 最小発注単位 |
| `stage.limit` | `int` | 廃棄期限 |

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

# 使い方
chain = lbg.Chain(
    exp_age=9,
    agents=[PassThroughAgent() for _ in range(4)]
)
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
chain = lbg.Chain(exp_age=9, market=UniformMarket(5, 15))
```

> **注意:** `market` を明示指定した場合，`Chain(seed=...)` は無効になります。  
> 乱数を制御したい場合は `Market.__init__` 内で `self.rng` を設定してください。

---

## Factory のカスタマイズ（生産能力）

`Factory.process(required)` をオーバーライドして，生産能力制約などを実装します。

### シグネチャ

```python
def process(self, required: int) -> int
```

### 実装例

```python
import limitedbg as lbg

# 例：生産能力に上限あり
class CapacitatedFactory(lbg.Factory):
    def __init__(self, capacity: int = 20) -> None:
        super().__init__()
        self.capacity = capacity

    def process(self, required: int) -> int:
        return min(required, self.capacity)

# 使い方
chain = lbg.Chain(exp_age=9, factory=CapacitatedFactory(capacity=15))
```

---

## 複数のカスタマイズを組み合わせる

```python
import limitedbg as lbg

chain = lbg.Chain(
    exp_age=9,
    seed=42,
    market=UniformMarket(5, 15),
    factory=CapacitatedFactory(capacity=15),
    agents=[PassThroughAgent() for _ in range(4)],
)
chain.dry_run(periods=100)
chain.run(periods=500)
chain.dump_log()
```
