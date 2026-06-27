# パラメータ一覧

`Chain.__init__` で受け取るすべてのパラメータの説明です。

---

## Chain パラメータ

| パラメータ | デフォルト | 型 | 説明 |
|---|---|---|---|
| `length` | `4` | `int` | サプライチェーンの段階数。stage ID は 0（最下流）〜 length-1（最上流）。 |
| `lead_times` | `None`（全段階 2） | `list[tuple[int, int]] \| None` | デフォルトと異なるリードタイムを指定する `[(stage_id, lead_time), ...]`。 |
| `lot_sizes` | `None`（全段階 1） | `list[tuple[int, int]] \| None` | 最小発注単位を指定する `[(stage_id, lot_size), ...]`。発注量はこの倍数に切り上げられる。 |
| `exp_age` | `None`（無期限） | `int \| None` | 製品の賞味期限（期）。最下流の廃棄期限として使われ，上流へは各段階のリードタイム分ずつ短縮される。 |
| `extra_limits` | `None` | `list[tuple[int, int]] \| None` | 各段階の廃棄期限を個別に厳しくする `[(stage_id, limit), ...]`。自動計算値より厳しい場合のみ有効。 |
| `unit_costs` | `None`（全段階 `[1, 1, 1]`） | `list[list[float]] \| None` | 各段階の単位コスト `[[在庫コスト, 欠品コスト, 廃棄コスト], ...]`。 |
| `market` | `None` → `Market()` | `Market \| None` | 需要生成モデル。カスタマイズする場合は `Market` のサブクラスを渡す。 |
| `factory` | `None` → `Factory()` | `Factory \| None` | 生産モデル。カスタマイズする場合は `Factory` のサブクラスを渡す。 |
| `agents` | `None` → 各段階に `Agent()` | `list[Agent] \| None` | 発注エージェントのリスト（長さ = `length`）。カスタマイズする場合は `Agent` のサブクラスを渡す。 |
| `seed` | `None`（非決定的） | `int \| None` | 乱数シード。`market` を明示指定した場合は無効。 |

### 廃棄期限の自動計算

`exp_age` を指定すると，各段階の廃棄期限 `limit` が以下のように自動計算されます。

```
stage 0 (最下流) の limit = exp_age
stage 1 の limit          = exp_age - lead_time[0]
stage 2 の limit          = exp_age - lead_time[0] - lead_time[1]
...
```

`extra_limits` でさらに厳しい期限を個別指定できます（自動計算値より厳しい場合のみ反映）。

### 使用例

```python
import limitedbg as lbg

# 基本：4段階，賞味期限9期，シード固定
chain = lbg.Chain(exp_age=9, seed=42)

# リードタイム変更：stage 0 のリードタイムを 4 に
chain = lbg.Chain(exp_age=9, lead_times=[(0, 4)])

# ロットサイズ変更：stage 3（最上流）の最小発注単位を 10 に
chain = lbg.Chain(exp_age=9, lot_sizes=[(3, 10)])

# コスト変更：stage 0 の廃棄コストを 5 に
chain = lbg.Chain(exp_age=9, unit_costs=[[1, 1, 5], [1, 1, 1], [1, 1, 1], [1, 1, 1]])

# 廃棄期限を個別指定：stage 1 の廃棄期限を 4 に制限
chain = lbg.Chain(exp_age=9, extra_limits=[(1, 4)])
```

---

## Market パラメータ

`Market` を直接インスタンス化して `Chain` に渡す場合。

| パラメータ | デフォルト | 型 | 説明 |
|---|---|---|---|
| `average_demand` | `10` | `int` | ポアソン分布の平均需要量。 |
| `rng` | `None` | `np.random.Generator \| None` | 乱数生成器。`None` のとき内部で生成。通常は `Chain(seed=...)` で制御する。 |

---

## simulate() パラメータ

Pygame可視化付き実行の場合。

| パラメータ | デフォルト | 型 | 説明 |
|---|---|---|---|
| `horizon` | `100` | `int` | シミュレーション期間数。 |
| `fr` | `30` | `int` | フレームレート。小さくすると動作が遅くなり観察しやすくなる。 |
| `**kwargs` | — | — | `Chain.__init__` に渡すキーワード引数（`exp_age`, `seed` など）。 |
