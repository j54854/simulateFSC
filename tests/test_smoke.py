import math

import limitedbg as lbg


def test_default_run():
    chain = lbg.Chain(seed=0)
    chain.dry_run(periods=10)
    chain.run(periods=10)
    for stage in chain.stages:
        assert len(stage.states) == 10


def test_with_expiry():
    chain = lbg.Chain(exp_age=9, seed=0)
    chain.dry_run(periods=10)
    chain.run(periods=10)
    for stage in chain.stages:
        assert len(stage.states) == 10


def test_no_nan(tmp_path):
    chain = lbg.Chain(exp_age=9, seed=0)
    chain.dry_run(periods=10)
    chain.run(periods=50)
    for stage in chain.stages:
        for state in stage.states:
            assert not math.isnan(state['on_hand'])
            assert not math.isnan(state['waste'])
            for c in state['costs']:
                assert not math.isnan(c)


def test_dump_log(tmp_path):
    chain = lbg.Chain(exp_age=9, seed=0)
    chain.dry_run(periods=10)
    chain.run(periods=10)
    chain.dump_log(str(tmp_path))
    for i in range(4):
        csv_path = tmp_path / f'stage{i}.csv'
        assert csv_path.exists()
        lines = csv_path.read_text().strip().splitlines()
        assert len(lines) == 11  # ヘッダー + 10期分


def test_on_hand_nonnegative():
    chain = lbg.Chain(exp_age=9, seed=0)
    chain.dry_run(periods=10)
    chain.run(periods=50)
    for stage in chain.stages:
        for state in stage.states:
            assert state['on_hand'] >= 0
            assert state['waste'] >= 0
            assert state['to_send'] >= 0
