import limitedbg as lbg


def _run(periods: int = 50, **kwargs) -> list[list]:
    chain = lbg.Chain(**kwargs)
    chain.dry_run(periods=50)
    chain.run(periods=periods)
    return [[s['on_hand'] for s in stage.states] for stage in chain.stages]


def test_seed_reproducibility():
    result1 = _run(seed=42, exp_age=9)
    result2 = _run(seed=42, exp_age=9)
    assert result1 == result2


def test_different_seeds_differ():
    result1 = _run(seed=1, exp_age=9)
    result2 = _run(seed=2, exp_age=9)
    assert result1 != result2


def test_shorter_expiry_increases_waste():
    def total_waste(exp_age):
        chain = lbg.Chain(exp_age=exp_age, seed=42)
        chain.dry_run(50)
        chain.run(200)
        return sum(s['waste'] for stage in chain.stages for s in stage.states)

    assert total_waste(7) > total_waste(15)


def test_unlimited_has_no_waste():
    chain = lbg.Chain(seed=42)  # exp_age=None で無期限
    chain.dry_run(50)
    chain.run(200)
    for stage in chain.stages:
        assert all(s['waste'] == 0 for s in stage.states)


def test_lot_size_respected():
    chain = lbg.Chain(exp_age=9, lot_sizes=[(0, 5)], seed=42)
    chain.dry_run(50)
    chain.run(100)
    for s in chain.stages[0].states:
        assert s['order_out'] % 5 == 0
