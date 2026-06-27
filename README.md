# simulateFSC
食品サプライチェーンのシミュレーションモデル in Python

## 概要

ビアゲーム（Beer Game）の多段階サプライチェーンに，食品の**鮮度低下**と**廃棄期限**を導入したシミュレーションモデルです。各在庫点で製品を生産からの経過時間（age）別に管理し，廃棄ロスを含むコスト評価が可能です。詳細は [docs/getting_started.md](docs/getting_started.md) を参照してください。

## セットアップ

uv の利用を想定しています。

```bash
uv sync
```

仮想環境を明示的に使う場合：

```bash
source .venv/bin/activate
deactivate
```

uv では仮想環境に入らなくても実行できます：

```bash
uv run your_script.py
```

## 実行

```bash
# シミュレーション実行（結果を data/ フォルダにCSV出力）
uv run examples/lbg_run.py

# Pygame可視化付きシミュレーション（リアルタイム動画表示）
uv run examples/lbg_movie.py
```

## ドキュメント

- [docs/getting_started.md](docs/getting_started.md) — プロジェクト概要・セットアップ・最初の実行
- [docs/parameters.md](docs/parameters.md) — シミュレーションパラメータ一覧
- [docs/customization.md](docs/customization.md) — 発注ロジック・需要・生産のカスタマイズ方法

## 開発者向け

```bash
# テスト実行
uv run pytest
```
