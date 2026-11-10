# ログの形式

`Chain.dump_log(output_dir)` は，出力先フォルダ（デフォルト `data/`）に次のファイルを書き出します．

- `stage{id}.csv`：各段階の毎期の状態（`stage0.csv` が最下流）
- `params.json`：ログの解釈に必要なパラメータと列の定義

列の定義は `limitedbg.LOG_COLUMNS` に1か所でまとめて定義されており，CSV のヘッダーと `params.json` の `columns` はそこから生成されます．ログだけを見返すときは `params.json` の `columns` を確認してください．

---

## 記録のタイミング

1期の処理は次の順に進み，**すべての処理が終わってから劣化させる直前**に記録します．

```
t 期: 入荷 → 受注 → 出荷準備 → 廃棄 → 発注 → 発送 → 【記録】 → 劣化
       receive  get_demand  pack_up  discard  place_order  ship_out  capture_state  elapse
```

列は次の2種類に分かれます．

- **フロー**：t 期に生じた量（受注，出荷，失注，廃棄，発注，生産）
- **ストック**：t 期末に存在する量．age は劣化させる前の値

---

## CSV の列

| 列名 | 種類 | 内容 |
|---|---|---|
| `period` | — | 期番号（`run()` の中で1から始まる連番．`dry_run()` の分は含まない） |
| `order_in` | フロー | 今期の受注量．stage 0 は市場の需要量（失注モードでも欠品分を含む本当の需要） |
| `cargo` | フロー | 今期の出荷量．stage 0 は消費者への販売量 |
| `lost` | フロー | 今期の失注量．失注モードの stage 0 のみ値を持ち，他は常に0 |
| `waste` | フロー | 今期の廃棄量（age が廃棄期限に達した手元在庫） |
| `order_out` | フロー | 今期の発注量（ロットまとめ後） |
| `produced` | フロー | 今期の工場の生産量．最上流の段階のみ値を持ち，他は常に0 |
| `on_hand` | ストック | 期末の手元在庫量（出荷・廃棄後） |
| `to_send` | ストック | 期末の受注残．失注モードの stage 0 では常に0 |
| `to_receive` | ストック | 期末の発注残（今期の発注を含む）．`order_pipeline`，上流の受注残，`supply_pipeline` の合計に等しい |
| `order_pipeline` | ストック | 期末に上流へ届く途中の発注量の合計 |
| `supply_pipeline` | ストック | 期末に輸送中の製品量の合計（今期に上流から発送された分を含む）．最上流では生産中の量 |
| `on_hand_{age}` | ストック | `on_hand` の age 別内訳（age = 0〜life-1） |
| `supply_pipeline_{age}` | ストック | `supply_pipeline` の age 別内訳 |
| `cargo_{age}` | フロー | `cargo` の age 別内訳（出荷時の age）．stage 0 では消費者が受け取った時点の age |

### 補足

- 期首（入荷直後）の手元在庫は `on_hand + cargo + waste` で計算できます
- バックオーダーの受注残を「単位×期」で数えるには，stage 0 の `to_send` を合計します
- 上流の受注残は，`to_receive - order_pipeline - supply_pipeline` で計算できます

---

## params.json

| キー | 内容 |
|---|---|
| `length` | 段階数 |
| `order_lead_times` | 各段階の発注リードタイム |
| `supply_lead_times` | 各段階の補充リードタイム |
| `lot_sizes` | 各段階の最小発注単位 |
| `exp_age` | 賞味期限（無期限なら `null`） |
| `limits` | 各段階の廃棄期限 |
| `life` | age の段階数（age 別の列の数） |
| `stockout_mode` | 最下流の欠品の扱い（`backorder` または `lost_sales`） |
| `seed` | 乱数シード（`null` なら非決定的） |
| `warmup_periods` | `dry_run()` で破棄した期間数 |
| `run_periods` | ログに記録されている期間数 |
| `market`，`factory`，`agents` | 使用したクラスの名前 |
| `columns` | 列名と説明の辞書（`LOG_COLUMNS`） |

費用の単価はシミュレータのパラメータではないため，記録されません．評価の仮定として外部で与えます（`examples/lbg_evaluate.py` を参照）．
