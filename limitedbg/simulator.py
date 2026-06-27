import math
from typing import Any

import pygame as pg

from .models import Chain, StageState, StageSummary

Dx, Dy = 75, 50  # 描画の縦横の単位
Adj = 25  # 円の大きさの調整係数
Line_Col = (191, 191, 191)  # フレームの線の色
Text_Col = (0, 0, 0)  # フレームの文字の色
Stock_Col = (0, 191, 191)  # 在庫量の円の色
Waste_Col = (191, 0, 0)  # 廃棄量の円の色
Out_Col = (191, 0, 191)  # 受注残量の円の色
In_Col = (191, 191, 0)  # 発注残量の円の色
Order_Col = (0, 0, 191)  # 発注量の円の色
Over_Col = (0, 0, 0)  # 量が基準値を超えたときの色

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
def set_screen_size(chain: Chain) -> tuple[int, int]:
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    # 全段階の手元在庫と入出荷ロットが描画できるように画面の幅を設定
    width = (chain.length +sum(chain.lead_times) +1) *Dx
    # 製品の全ageの在庫と廃棄量，受注残，発注残，発注量が描画できるように画面の高さを設定
    height = (chain.life +4) *Dy
    return width, height

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
def blit_text(screen: pg.Surface, x: float, y: float, text: str, font: pg.font.Font) -> None:
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    # render(テキスト, アンチエイリアス, 前景色, 背景色（Noneなら透明）)
    label_surf = font.render(text, True, Text_Col, None)
    label_rect = label_surf.get_rect()
    label_rect.center = (x, y)
    screen.blit(label_surf, label_rect)

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
def draw_frame(screen: pg.Surface, chain: Chain, font: pg.font.Font) -> None:
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    x = 1.25  # フレームの左余白
    for id in reversed(range(chain.length)):  # サプライチェーンの段階を逆順に取得
        for lab in ['En route', 'Stage' +str(id), 'Cargo']:
            blit_text(screen, x *Dx, 0.25 *Dy, lab, font)  # x軸ラベル
            pg.draw.aaline(screen, Line_Col, (x *Dx, 0.65 *Dy), (x *Dx, screen.get_height() -0.5 *Dy))  # 縦線
            x += 1  # 右に1単位ずらす
    y = 1  # フレームの上余白
    blit_text(screen, 0.5 *Dx, y *Dy, 'Order', font)  # y軸ラベル（発注量）
    y += 1  # 下に1単位ずらす
    for age in range(chain.life):  # 在庫のageを順に取得
        blit_text(screen, 0.5 *Dx, y *Dy, str(age), font)  # y軸ラベル（在庫）
        y += 1  # 下に1単位ずらす
    blit_text(screen, 0.5 *Dx, y *Dy, '-> |', font)  # y軸ラベル（発注残）
    y += 1  # 下に1単位ずらす
    blit_text(screen, 0.5 *Dx, y *Dy, '| ->', font)  # y軸ラベル（受注残）
    y += 1  # 下に1単位ずらす
    for y in range(1, chain.life +4):
        pg.draw.aaline(screen, Line_Col, (0.85 *Dx, y *Dy), (screen.get_width() -0.5 *Dx, y *Dy))  # 横線

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
def draw_state(screen: pg.Surface, offset: int, life: int, limit: int, state: StageState | StageSummary) -> None:
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    x = 1.25 +offset  # 0.25はフレームの左余白，offsetはこの段階より左側に描画される縦棒の数
    # 前期までの発送された配送中の在庫（en_route）
    for age in range(life):
        radius = math.sqrt(state['en_route_vols'][age]) *Dy /Adj
        pg.draw.circle(screen, Stock_Col, (x *Dx, (age +2) *Dy), radius)
    x += 1
    # 今期末の手元在庫（on_hand）
    radius = math.sqrt(state['order_out']) *Dy /Adj  # 前期の発注量
    pg.draw.circle(screen, Order_Col, (x *Dx, 1 *Dy), radius)
    for age in range(life):
        radius = math.sqrt(state['on_hand_vols'][age]) *Dy /Adj
        pg.draw.circle(screen, Stock_Col, (x *Dx, (age +2) *Dy), radius)
    if life > 0: # 無期限でなければ
        radius = math.sqrt(state['waste']) *Dy /Adj  # 廃棄量
        pg.draw.circle(screen, Waste_Col, (x *Dx, (limit +2) *Dy), radius)
    radius = math.sqrt(state['to_receive']) *Dy /Adj  # 発注残
    pg.draw.circle(screen, In_Col, (x *Dx, (life +2) *Dy), radius)
    radius = math.sqrt(state['to_send']) *Dy /Adj  # 受注残
    pg.draw.circle(screen, Out_Col, (x *Dx, (life +3) *Dy), radius)
    x += 1
    # 今期の出荷分（cargo）
    for age in range(life):
        radius = math.sqrt(state['cargo_vols'][age]) *Dy /Adj
        pg.draw.circle(screen, Stock_Col, (x *Dx, (age +2) *Dy), radius)

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
def draw_states(screen: pg.Surface, chain: Chain, summary: bool = False) -> None:
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    for stage in chain.stages:
        if summary:
            summarized_state = stage.summarize_state()
            draw_state(screen,
                (chain.length -1 -stage.id) *3,  #　最上流を0として降順に3単位ずつ右にずらす
                chain.life, stage.limit, summarized_state)
        else:
            draw_state(screen,
                (chain.length -1 -stage.id) *3,  # 最上流を0として降順に3単位ずつ右にずらす
                chain.life, stage.limit, stage.states[-1])

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
def simulate(horizon: int = 100, fr: int = 30, **kwargs: Any) -> None:
    """Pygame によるリアルタイム可視化付きでシミュレーションを実行する。

    `dry_run()` でウォームアップ後，1期ごとに画面を更新する。
    シミュレーション終了後は全期間の平均状態を表示し，ログを `data/` に出力する。

    Args:
        horizon: シミュレーション期間数（デフォルト 100）。
        fr: フレームレート（デフォルト 30）。値を小さくすると動作を遅くして観察しやすくなる。
        **kwargs: `Chain.__init__` に渡すキーワード引数（`exp_age`, `seed` など）。
    """
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    chain = Chain(**kwargs)
    chain.dry_run()
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    pg.init()  # Pygameの初期化
    clock = pg.time.Clock()  # Clockの作成（フレームレート管理のために必要）
    screen = pg.display.set_mode(set_screen_size(chain))
    pg.display.set_caption("Extended Beer Game Simulator")
    font = pg.font.SysFont('Arial', 16)
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    running_simulation = True  # シミュレーション実行中
    showing_results = False  # 結果表示中
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    period = 0  # シミュレーション時間の初期化
    while running_simulation:
        for event in pg.event.get():
            if event.type == pg.QUIT:  # 閉じるボタン押下
                running_simulation = False  # シミュレーションを途中終了

        period += 1  # シミュレーション時間の進行
        if period > horizon:  # シミュレーション期間の終了判定
            chain.dump_log()  # シミュレーションログを出力
            running_simulation = False  # シミュレーションを正常終了
            showing_results = True  # 結果表示モードへ移行

        chain.operate()  # シミュレーションを1期間分だけ進行

        screen.fill((255, 255, 255))  # 白背景で画面全体を再初期化
        draw_frame(screen, chain, font)  # 画面フレームの描画
        draw_states(screen, chain)  # サプライチェーンの状態の描画

        pg.display.flip()  # 画面更新
        clock.tick(fr)  # フレームレート

    while showing_results:
        for event in pg.event.get():
            if event.type == pg.QUIT:  # 閉じるボタン押下
                showing_results = False  # 結果表示モードを終了

        screen.fill((255, 255, 255))  # 白背景で画面全体を再初期化
        draw_frame(screen, chain, font)  # 画面フレームの描画
        draw_states(screen, chain, summary=True)  # サプライチェーンの状態の描画

        pg.display.flip()  # 画面更新
        clock.tick(fr)  # フレームレート

    pg.quit()  # Pygameの終了
