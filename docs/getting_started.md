# Getting Started

## プロジェクト概要

**simulateFSC** は，食品サプライチェーンの在庫管理をシミュレーションするPythonライブラリです。

ベースとなる**ビアゲーム**（Beer Game）は，多段階サプライチェーン（小売 → 卸 → 配送センター → 工場）における需要増幅（ブルウィップ効果）を体験するための教育ゲームです。このモデルでは，食品特有の**鮮度低下**と各段階での**廃棄期限**を加え，ログから廃棄ロスを含む総費用や社会的余剰を評価できます．

### できること

- 多段階サプライチェーンの在庫・欠品・廃棄をシミュレーション
- 賞味期限・廃棄期限・リードタイム・ロットサイズなどのパラメータ実験
- 結果をCSVで出力し，総費用・社会的余剰を外部で評価
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

`data/stage0.csv` 〜 `data/stage3.csv` と `data/params.json` が生成されれば成功です。

---

## 最初の実行

### CSV出力のみ

```bash
uv run examples/lbg_run.py
```

`data/` フォルダに各段階（stage0〜stage3）のCSVが出力されます。

列の意味と記録のタイミングは [docs/log_format.md](log_format.md) を参照してください（`data/params.json` の `columns` にも同じ説明が出力されます）．

### 総費用・社会的余剰の評価

```bash
uv run examples/lbg_evaluate.py          # data/ のログを評価
uv run examples/lbg_evaluate.py out_dir/ # 別のフォルダのログを評価
```

単価・価値関数・消費者の負の便益などの仮定は，スクリプト内の `Assumptions` で変更できます．

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
# 賞味期限 12期（examples で使っている値）
chain = lbg.Chain(exp_age=12)

# 賞味期限 7期（廃棄が増える．デフォルトのリードタイムでは7期が下限）
chain = lbg.Chain(exp_age=7)

# 無期限（廃棄なし）
chain = lbg.Chain()
```

### リードタイムを変える

```python
# 最下流（stage 0）の補充リードタイムを 3 に変更
chain = lbg.Chain(exp_age=12, supply_lead_times=[(0, 3)])

# 最下流（stage 0）の発注リードタイムを 1 に変更
chain = lbg.Chain(exp_age=12, order_lead_times=[(0, 1)])
```

### 小売の欠品を失注にする

```python
chain = lbg.Chain(exp_age=12, stockout_mode='lost_sales')
```

### 乱数シードを固定して再現可能にする

```python
chain = lbg.Chain(exp_age=12, seed=42)
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

chain = lbg.Chain(exp_age=12, agents=[MyAgent() for _ in range(4)])
chain.dry_run()
chain.run(500)
chain.dump_log()
```
