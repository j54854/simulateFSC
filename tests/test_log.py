import csv
import importlib.util
import json
import math
from pathlib import Path

import limitedbg as lbg

ROOT = Path(__file__).resolve().parent.parent


def _dump(tmp_path: Path, **kwargs) -> lbg.Chain:
    chain = lbg.Chain(exp_age=9, seed=0, **kwargs)
    chain.dry_run(20)
    chain.run(30)
    chain.dump_log(str(tmp_path))
    return chain


def test_csv_header_matches_log_columns(tmp_path):
    chain = _dump(tmp_path)
    for stage_id in range(chain.length):
        with open(tmp_path / f'stage{stage_id}.csv', newline='') as f:
            assert next(csv.reader(f)) == lbg.log_header(chain.life)


def test_period_numbering(tmp_path):
    chain = _dump(tmp_path)
    for stage in chain.stages:
        assert [s['period'] for s in stage.states] == list(range(1, 31))


def test_params_json(tmp_path):
    chain = _dump(tmp_path, stockout_mode='lost_sales')
    params = json.loads((tmp_path / 'params.json').read_text(encoding='utf-8'))
    assert params['columns'] == lbg.LOG_COLUMNS
    assert params['stockout_mode'] == 'lost_sales'
    assert params['limits'] == chain.limits
    assert params['warmup_periods'] == 20
    assert params['run_periods'] == 30


def test_docs_cover_log_columns():
    text = (ROOT / 'docs' / 'log_format.md').read_text(encoding='utf-8')
    for key in lbg.LOG_COLUMNS:
        assert f'`{key}`' in text


def test_evaluate_script(tmp_path):
    spec = importlib.util.spec_from_file_location('lbg_evaluate', ROOT / 'examples' / 'lbg_evaluate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for mode in ['backorder', 'lost_sales']:
        out = tmp_path / mode
        _dump(out, stockout_mode=mode)
        params, logs = module.load_log(out)
        result = module.evaluate(params, logs, module.Assumptions())
        assert all(math.isfinite(v) for v in result.values())
        assert result['consumer_value'] > 0


def test_default_value_function():
    spec = importlib.util.spec_from_file_location('lbg_evaluate', ROOT / 'examples' / 'lbg_evaluate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    value = module.default_value
    params = {'exp_age': 12, 'supply_lead_times': [2, 2, 2, 2]}
    assert value(0, params) == value(6, params) == 10  # a_fresh = max(12 // 2, 6) = 6 まで一定
    assert 0 < value(12, params) < value(7, params) < 10  # 賞味期限ちょうどでは正の値
    assert value(13, params) == 0  # 販売できなくなる age で0
    params = {'exp_age': 20, 'supply_lead_times': [2, 2, 2, 2]}
    assert value(10, params) == 10 and value(11, params) < 10  # a_fresh = max(20 // 2, 6) = 10
    assert value(100, {'exp_age': None, 'supply_lead_times': [2, 2, 2, 2]}) == 10  # 無期限

def test_to_receive_decomposition(tmp_path):
    chain = _dump(tmp_path)
    for stage, upstream in zip(chain.stages[:-1], chain.stages[1:]):
        for s, u in zip(stage.states, upstream.states):
            assert s['to_receive'] == s['order_pipeline'] +u['to_send'] +s['supply_pipeline']


def test_value_assumptions(tmp_path):
    spec = importlib.util.spec_from_file_location('lbg_evaluate', ROOT / 'examples' / 'lbg_evaluate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _dump(tmp_path)
    params, logs = module.load_log(tmp_path)
    base = module.evaluate(params, logs, module.Assumptions())['consumer_value']
    doubled = module.evaluate(params, logs, module.Assumptions(v_max=20))['consumer_value']
    assert math.isclose(doubled, 2 *base)  # 価値は v_max に比例
    custom = module.evaluate(params, logs, module.Assumptions(value=lambda age, p: 1.0, v_max=20))
    assert custom['consumer_value'] == sum(row['cargo'] for row in logs[0])  # 独自関数では v_max は無視
