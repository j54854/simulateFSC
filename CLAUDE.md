# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 概要

ビアゲーム型の多段階サプライチェーンに，食品の鮮度低下（age 管理）と各段階の廃棄期限を加えたシミュレーションモデル．配布名は `simulatefsc` だが，import するパッケージ名は `limitedbg`（`import limitedbg as lbg`）

シミュレータは数量のログだけを出力し，費用や社会的余剰は計算しない．評価は `examples/lbg_evaluate.py` のように，ログを使って外部で行う．評価の仮定はシミュレータに持ち込まない

## コマンド

パッケージ管理は uv．linter / formatter の設定はない

```bash
uv sync                                              # 依存関係と limitedbg パッケージ（hatchling）をインストール
uv run pytest                                        # 全テスト
uv run pytest tests/test_smoke.py::test_default_run  # 単一テスト
uv run examples/lbg_run.py                           # 実行して data/ に stage{id}.csv と params.json を出力
uv run examples/lbg_evaluate.py [log_dir]            # ログから総費用・社会的余剰を算出
uv run examples/lbg_movie.py                         # Pygame 可視化付き実行（GUI ウィンドウが開く）
```

`examples/` などサブディレクトリのスクリプトで `limitedbg` が import できない場合は `uv sync` でパッケージを再インストールする

## アーキテクチャ

- `limitedbg/models.py`：モデル本体（`Batch`，`Stage`，`Chain` とカスタマイズ用の `Agent`，`Market`，`Factory`）と，ログの列定義 `LOG_COLUMNS`
- `limitedbg/simulator.py`：Pygame 可視化．`simulate(horizon, fr, **kwargs)` が `kwargs` を `Chain` に渡す

### 主要な概念

- **段階の向き**：`stages[0]` が最下流（小売，市場から受注），`stages[-1]` が最上流（工場へ発注し，工場から入荷）
- **`Batch`**：`vols[age]` で製品を age 別に保持し，出荷は age の大きい順（FIFO）．`life == 1` は無期限製品を表し，劣化・廃棄しない
- **2種類のリードタイム**（どちらも1以上．デフォルトはオリジナルのビアゲームに合わせてある）
  - `order_lead_time`：発注が上流に届くまでの期数．デフォルトは中間段階が2，最上流（工場への発注）が1．`Stage.order_pipeline: list[int]` で管理する
  - `supply_lead_time`：上流の出荷から入荷までの期数．デフォルトは全段階2．`Stage.supply_pipeline: list[Batch]` で管理する．最上流の `supply_pipeline` は工場で生産中の分とみなし，劣化させない
  - 発注リードタイムの間は製品が存在しないので，廃棄期限の計算（`Chain.set_limits()`）と期限のチェック（最上流の期限 `limits[-1] >= 1`．`extra_limits` で絞った後の値で確認）には補充リードタイムだけを使う
- **廃棄期限**：最下流の期限を `exp_age` とし，上流に行くごとに補充リードタイム分だけ短くする．`extra_limits` はこれより厳しくする方向にしか効かず，絞った段階より上流の期限も連動して短くなる．`life = limits[0] + 1`
- **欠品モード**：`Chain(stockout_mode='backorder' | 'lost_sales')`．効くのは stage 0 だけで，中間段階は常にバックオーダー．失注では不足分を `lost` に記録し，`to_send` は0のまま
- **発注残**：`to_receive` は発注した時点で増え，届く途中の発注，上流の受注残，輸送中の製品をすべて含む

### 1期間の処理順序（`Chain.operate()`）

```
receive → get_demand → pack_up → discard → place_order → ship_out → capture_state → elapse
```

- `get_demand()`：各段階の受注は，下流の `order_pipeline` の先頭を取り出したもの．工場に届く発注も，最上流の `order_pipeline` から取り出して `Chain.factory_order` に置く
- `ship_out()`：`factory.process(factory_order)` の結果を `produced` に記録する
- `capture_state()` は全段階をまとめて記録してから `elapse()` を呼ぶ．上流の `cargo` は下流の `supply_pipeline` と同じ `Batch` オブジェクトなので，段階ごとに記録と劣化を交互に行うと，記録される `cargo_vols` がずれる

### ログ

- ログには数量だけを記録する．フローは「その期の量」，ストックは「期末の量（age は劣化前）」というルールに揃えてある
- 列の定義は `models.py` の `LOG_COLUMNS` だけにある．CSV のヘッダー（`log_header()`），`params.json` の `columns`，`StageSummary` はこれに従う
- 列を追加・変更するときは，`LOG_COLUMNS`，`StageState`/`StageSummary`，`capture_state()`，`docs/log_format.md` をあわせて更新する（`tests/test_log.py` が docs との整合を確認する）

### カスタマイズと再現性

- 挙動の変更は `Agent.get_order(stage)`，`Market.get_demand()`，`Factory.process(required)` をサブクラスでオーバーライドし，`Chain(agents=..., market=..., factory=...)` に渡す（詳細は `docs/customization.md`）
- `place_order()` がエージェントの返り値を `lot_size` の倍数に切り上げる
- 費用の単価は `Chain` のパラメータではない．発注の判断に単価が必要な `Agent` は，単価を自分のコンストラクタで受け取る
- `seed` で作る乱数生成器はデフォルトの `Market` だけが使う．`market` を明示的に渡すと `seed` は効かない
- `dry_run()` はウォームアップ後に `states` をリセットする．記録が残るのは `run()` の分だけ

### 公開 API

`limitedbg/__init__.py` の `__all__` が公開範囲．`Stage` や `Batch` を変更する場合は，`docs/customization.md` と `docs/parameters.md` の属性表との整合も確認する

## コードスタイル（既存コードに合わせる）

- メソッド・関数の間に `# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----` の区切り行を入れる
- 二項演算子は `a *b`，`x +1`，`self.forecast *(stage.supply_lead_time +1)` のように前にだけスペースを入れる（`=` と比較演算子は前後にスペース）
- コメントは行末の短い日本語コメントが中心．docstring は Google スタイルで日本語
