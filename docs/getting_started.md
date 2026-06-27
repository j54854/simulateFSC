# Getting Started

## プロジェクト概要

**simulateFSC** は，食品サプライチェーンの在庫管理をシミュレーションするPythonライブラリです。

ベースとなる**ビアゲーム**（Beer Game）は，多段階サプライチェーン（小売 → 卸 → 配送センター → 工場）における需要増幅（ブルウィップ効果）を体験するための教育ゲームです。このモデルでは，食品特有の**鮮度低下**と各段階での**廃棄期限**を加え，廃棄ロスを含むコスト評価が可能になっています。

### できること

- 多段階サプライチェーンの在庫・欠品・廃棄をシミュレーション
- 賞味期限・廃棄期限・リードタイム・ロットサイズなどのパラメータ実験
- 結果をCSVで出力して分析
- Pygameによるリアルタイム可視化
- 発注ロジック・需要パターン・生産能力のカスタマイズ

---

## セットアップ

```bash
# 依存パッケージのインストール
uv sync

# 動作確認
uv run examples/lbg_run.py
```

`data/stage0.csv` 〜 `data/stage3.csv` が生成されれば成功です。

---

## 最初の実行

### CSV出力のみ

```bash
uv run examples/lbg_run.py
```

`data/` フォルダに各段階（stage0〜stage3）のCSVが出力されます。

| 列名 | 内容 |
|------|------|
| `order_out` | 発注量 |
| `order_in` | 受注量 |
| `cargo` | 出荷量 |
| `to_send` | 欠品量（未出荷の残注文） |
| `on_hand` | 手元在庫量 |
| `waste` | 廃棄量 |
| `c_holding` | 在庫コスト |
| `c_stockout` | 欠品コスト |
| `c_waste` | 廃棄コスト |
| `on_hand_0`, `on_hand_1`, ... | age別の手元在庫量 |

### Pygame可視化

```bash
uv run examples/lbg_movie.py
```

各段階の在庫・廃棄・発注量が円で描画されます（円の面積が量に比例）。シミュレーション終了後は全期間の平均状態に切り替わります。ウィンドウを閉じると終了します。

---

## パラメータを変えてみる

`examples/lbg_run.py` の `Chain` 引数を変えることで，さまざまな条件を試せます。

### 賞味期限を変える

```python
# 賞味期限 9期（デフォルト）
chain = lbg.Chain(exp_age=9)

# 賞味期限 5期（廃棄が増える）
chain = lbg.Chain(exp_age=5)

# 無期限（廃棄なし）
chain = lbg.Chain()
```

### リードタイムを変える

```python
# 最下流（stage 0）のリードタイムを 4 に変更
chain = lbg.Chain(exp_age=9, lead_times=[(0, 4)])
```

### 乱数シードを固定して再現可能にする

```python
chain = lbg.Chain(exp_age=9, seed=42)
```

パラメータの詳細は [docs/parameters.md](parameters.md) を参照してください。

---

## カスタマイズ

発注ロジック・需要パターン・生産能力はサブクラスでカスタマイズできます。詳細は [docs/customization.md](customization.md) を参照してください。

```python
import limitedbg as lbg

class MyAgent(lbg.Agent):
    def get_order(self, stage):
        # 独自の発注ロジックをここに実装
        return stage.order_in  # 例: 受注量をそのまま発注

chain = lbg.Chain(exp_age=9, agents=[MyAgent() for _ in range(4)])
chain.dry_run()
chain.run(500)
chain.dump_log()
```
