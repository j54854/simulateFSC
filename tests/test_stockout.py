import pytest

import limitedbg as lbg


def _run(stockout_mode: str) -> lbg.Chain:
    chain = lbg.Chain(exp_age=9, seed=1, stockout_mode=stockout_mode)
    chain.dry_run(50)
    chain.run(200)
    return chain


def test_lost_sales():
    chain = _run('lost_sales')
    retail = chain.stages[0].states
    assert all(s['cargo'] +s['lost'] == s['order_in'] for s in retail)
    assert all(s['to_send'] == 0 for s in retail)
    assert sum(s['lost'] for s in retail) > 0
    for stage in chain.stages[1:]:  # 中間段階は常にバックオーダー
        assert all(s['lost'] == 0 for s in stage.states)


def test_backorder():
    chain = _run('backorder')
    for stage in chain.stages:
        assert all(s['lost'] == 0 for s in stage.states)
    assert sum(s['to_send'] for s in chain.stages[0].states) > 0


def test_unknown_mode():
    with pytest.raises(AssertionError):
        lbg.Chain(stockout_mode='partial')
