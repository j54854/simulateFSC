# パラメータ一覧

`Chain.__init__` で受け取るすべてのパラメータの説明です。

---

## Chain パラメータ

| パラメータ | デフォルト | 型 | 説明 |
|---|---|---|---|
| `length` | `4` | `int` | サプライチェーンの段階数。stage ID は 0（最下流）〜 length-1（最上流）。 |
| `order_lead_times` | `None`（中間段階 2，最上流 1） | `list[tuple[int, int]] \| None` | 発注リードタイム（発注が上流に届くまでの期数）を変更する `[(stage_id, lead_time), ...]`．最上流の値は工場への発注に適用される．1以上 |
| `supply_lead_times` | `None`（全段階 2） | `list[tuple[int, int]] \| None` | 補充リードタイム（上流の出荷から入荷までの期数．最上流は工場の生産期間）を変更する `[(stage_id, lead_time), ...]`．1以上 |
| `lot_sizes` | `None`（全段階 1） | `list[tuple[int, int]] \| None` | 最小発注単位を指定する `[(stage_id, lot_size), ...]`。発注量はこの倍数に切り上げられる。 |
| `exp_age` | `None`（無期限） | `int \| None` | 製品の賞味期限（期）。最下流の廃棄期限として使われ，上流へは各段階の補充リードタイム分ずつ短縮される．`sum(supply_lead_times[:-1])` より大きくなければならない（デフォルトのリードタイムでは7以上．下の「廃棄期限の自動計算」を参照）。 |
| `extra_limits` | `None` | `list[tuple[int, int]] \| None` | 各段階の廃棄期限を個別に厳しくする `[(stage_id, limit), ...]`。自動計算値より厳しい場合のみ有効．絞った段階より上流の期限も連動して短くなる． |
| `stockout_mode` | `'backorder'` | `Literal['backorder', 'lost_sales']` | 最下流（小売）の欠品の扱い．`'backorder'` は受注残として持ち越し，`'lost_sales'` は失注とする．中間段階は常にバックオーダー |
| `market` | `None` → `Market()` | `Market \| None` | 需要生成モデル。カスタマイズする場合は `Market` のサブクラスを渡す。 |
| `factory` | `None` → `Factory()` | `Factory \| None` | 生産モデル。カスタマイズする場合は `Factory` のサブクラスを渡す。 |
| `agents` | `None` → 各段階に `Agent()` | `list[Agent] \| None` | 発注エージェントのリスト（長さ = `length`）。カスタマイズする場合は `Agent` のサブクラスを渡す。 |
| `seed` | `None`（非決定的） | `int \| None` | 乱数シード。`market` を明示指定した場合は無効。 |

### 廃棄期限の自動計算

`exp_age` を指定すると，各段階の廃棄期限 `limit` が以下のように自動計算されます。

```
stage 0 (最下流) の limit = exp_age
stage 1 の limit          = exp_age - supply_lead_time[0]
stage 2 の limit          = exp_age - supply_lead_time[0] - supply_lead_time[1]
...
```

`extra_limits` でさらに厳しい期限を個別指定できます（自動計算値より厳しい場合のみ反映）。絞った段階より上流は，絞った後の期限から補充リードタイム分ずつ短縮されます．たとえば `exp_age=12, extra_limits=[(0, 10)]` では `limits = [10, 8, 6, 4]` になります．

初期化時に，最上流の期限が1以上であること（`limits[-1] >= 1`）を確認します．期限は上流ほど短いので，これで全段階について輸送中に期限切れにならないことが保証されます．`extra_limits` を指定しない場合は `exp_age > sum(supply_lead_times[:-1])` と同じ条件です．

発注リードタイムの間は製品がまだ存在しないため，劣化せず，廃棄期限の計算にも使われません．

### リードタイムのデフォルト

オリジナルのビアゲームに合わせています．

| 段階 | 発注リードタイム | 補充リードタイム |
|---|---|---|
| 中間段階（stage 0〜length-2） | 2 | 2 |
| 最上流（stage length-1） | 1（工場への生産指示） | 2（工場の生産期間） |

t 期の発注は t + 発注リードタイム 期に上流に届きます．最上流の発注は，1期後に工場で生産され，さらに2期後に入荷します．

### 欠品の扱いと費用

費用（在庫費・欠品費・廃棄費）や社会的余剰はシミュレータでは計算しません．ログの数量から外部で算出します（[log_format.md](log_format.md)，`examples/lbg_evaluate.py` を参照）．

### 使用例

```python
import limitedbg as lbg

# 基本：4段階，賞味期限12期，シード固定
chain = lbg.Chain(exp_age=12, seed=42)

# リードタイム変更：stage 0 の発注リードタイムを 1 に，補充リードタイムを 3 に
chain = lbg.Chain(exp_age=12, order_lead_times=[(0, 1)], supply_lead_times=[(0, 3)])

# 小売の欠品を失注として扱う
chain = lbg.Chain(exp_age=12, stockout_mode='lost_sales')

# ロットサイズ変更：stage 3（最上流）の最小発注単位を 10 に
chain = lbg.Chain(exp_age=12, lot_sizes=[(3, 10)])

# 廃棄期限を個別指定：stage 1 の廃棄期限を 6 に制限（上流も連動して limits = [12, 6, 4, 2]）
chain = lbg.Chain(exp_age=12, extra_limits=[(1, 6)])
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
