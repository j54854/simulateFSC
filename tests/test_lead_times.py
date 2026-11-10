import pytest

import limitedbg as lbg


class PulseAgent(lbg.Agent):
    """指定した期にだけ一定量を発注するエージェント"""

    def __init__(self, period: int, qty: int) -> None:
        super().__init__()
        self.period = period
        self.qty = qty
        self.t = 0

    def get_order(self, stage):
        self.t += 1
        return self.qty if self.t == self.period else 0


class PassThroughAgent(lbg.Agent):
    """受注量をそのまま発注するエージェント"""

    def get_order(self, stage):
        return stage.order_in


def _pulse_chain(**kwargs) -> lbg.Chain:
    agents = [PulseAgent(period=3, qty=7)] +[PassThroughAgent() for _ in range(3)]
    chain = lbg.Chain(agents=agents, seed=0, **kwargs)
    chain.run(20)
    return chain


def _first_positive(values: list) -> int:
    return next(t for t, v in enumerate(values, start=1) if v > 0)


def test_default_lead_times():
    chain = lbg.Chain()
    assert chain.order_lead_times == [2, 2, 2, 1]
    assert chain.supply_lead_times == [2, 2, 2, 2]


def test_order_delay():
    chain = _pulse_chain()
    arrivals = [_first_positive([s['order_in'] for s in stage.states]) for stage in chain.stages[1:]]
    assert arrivals == [5, 7, 9]  # 中間段階の発注リードタイムは2期
    assert _first_positive([s['produced'] for s in chain.stages[-1].states]) == 10  # 工場へは1期


def test_custom_order_delay():
    chain = _pulse_chain(order_lead_times=[(0, 4)])
    assert _first_positive([s['order_in'] for s in chain.stages[1].states]) == 7


def test_factory_to_receipt():
    chain = _pulse_chain()
    top = chain.stages[-1]
    # 最上流が9期目に発注し，工場が10期目に生産して，12期目に入荷する（発注残が0に戻る）
    to_receive = [s['to_receive'] for s in top.states]
    assert to_receive[8:11] == [7, 7, 7]
    assert to_receive[11] == 0


def test_order_pipeline_logged():
    chain = _pulse_chain()
    # stage 0 は3期目に発注し，5期目に上流へ届くまでパイプラインに残る
    assert [s['order_pipeline'] for s in chain.stages[0].states][2:5] == [7, 7, 0]


@pytest.mark.parametrize('kwargs', [
    {'order_lead_times': [(1, 0)]},
    {'supply_lead_times': [(0, 0)]},
])
def test_lead_time_must_be_positive(kwargs):
    with pytest.raises(AssertionError):
        lbg.Chain(**kwargs)
