"""Verify the selective experiment without refitting its neural models."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import ml_transfer_audit as audit
from ml_selective_residual import METHODS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/results/ml_selective"


def main():
    receipt = json.loads((OUT / 'receipt.json').read_text())
    checks = {'code_sha256': ROOT/'scripts/ml_selective_residual.py',
              'audit_code_sha256': ROOT/'scripts/ml_transfer_audit.py',
              'protocol_sha256': ROOT/'docs/evaluation/ML_SELECTIVE_RESIDUAL_PROTOCOL.md',
              'cohort_sha256': audit.OUT/'cohort.csv', 'split_sha256': audit.OUT/'splits.json'}
    for key, path in checks.items():
        assert receipt[key] == audit.sha(path), f'Stale experiment file: {path}'
    analysis = json.loads((OUT/'analysis_receipt.json').read_text())
    assert analysis['code_sha256'] == audit.sha(ROOT/'scripts/build_selective_artifacts.py')
    assert analysis['protocol_sha256'] == audit.sha(ROOT/'docs/evaluation/ML_MATCHED_SELECTION_ANALYSIS.md')
    assert analysis['result_sha256'] == audit.sha(OUT/'results.json')
    cohort = pd.read_csv(audit.OUT/'cohort.csv')
    humidity = pd.read_csv(audit.OUT/'humidity_audit.csv')
    eligible = set(map(tuple, humidity.loc[humidity.vp_kpa >= 0, ['station','date']].to_numpy()))
    splits = json.loads((audit.OUT/'splits.json').read_text())
    results = json.loads((OUT/'results.json').read_text())
    inner_count = 0; ensemble_count = 0
    for record in receipt['records']:
        split = next(s for s in splits if s['regime'] == record['regime'] and s['fold'] == record['fold'])
        features = 7 if record['specification'] == 'archived' else 6
        inner = pd.read_csv(OUT/f"inner_{record['regime']}_{features}_{record['fold']}.csv")
        assert set(inner.row_id) <= set(split['train_row_ids'])
        assert not set(inner.row_id) & set(split['test_row_ids'])
        assert not inner.row_id.duplicated().any()
        for index, part in enumerate(split['inner_partitions']):
            actual = set(inner.loc[inner.inner_fold == index, 'row_id'])
            assert actual == set(part['validation_row_ids'])
            fit = cohort[cohort.row_id.isin(part['train_row_ids'])]
            val = cohort[cohort.row_id.isin(actual)]
            assert not set(fit.group) & set(val.group)
            if record['regime'] == 'joint': assert fit.date.max() < val.date.min()
            inner_count += 1
        ensemble_count += sum(t['part'] in ['inner','outer'] for t in record['timings'])
    assert len(receipt['records']) == 40 and inner_count == 120 and ensemble_count == 160
    prediction_rows = 0
    for key, conditions in results.items():
        natural = pd.read_csv(OUT/f'predictions_{key}_natural.csv')
        probe_ids = set(natural.loc[[(s,date) in eligible for s,date in zip(natural.station,natural.date)], 'row_id'])
        for condition, reported in conditions.items():
            frame = pd.read_csv(OUT/f'predictions_{key}_{condition}.csv')
            assert not frame.row_id.duplicated().any()
            expected = set(natural.row_id) if condition == 'natural' else probe_ids
            assert set(frame.row_id) == expected
            truth = cohort.set_index('row_id').loc[frame.row_id]
            np.testing.assert_allclose(frame.y, truth.y, rtol=0, atol=1e-12)
            np.testing.assert_allclose(frame.OpenET, truth.openet, rtol=0, atol=1e-12)
            masks = {'Full': np.ones(len(frame),dtype=bool),
                     'Spread95': frame.spread <= frame.spread_threshold,
                     'Support95': frame.distance <= frame.support_threshold,
                     'Gain': frame.predicted_gain > 0,
                     'SupportGain': (frame.distance <= frame.support_threshold) & (frame.predicted_gain > 0)}
            for method, mask in masks.items():
                np.testing.assert_array_equal(frame['accept_'+method], mask)
                np.testing.assert_allclose(frame[method], frame.OpenET+mask*frame.correction, rtol=1e-12, atol=1e-12)
            for name in METHODS:
                value = audit.macro_mae(frame.y, frame[name], frame.station.to_numpy())
                np.testing.assert_allclose(value, reported['models'][name]['macro_mae'], rtol=1e-11, atol=1e-12)
            prediction_rows += len(frame)
        if key.endswith('noVPD'):
            clean = pd.read_csv(OUT/f'predictions_{key}_probe_clean.csv')
            fault = pd.read_csv(OUT/f'predictions_{key}_vpd_x10.csv')
            np.testing.assert_array_equal(clean[METHODS], fault[METHODS])
    matched = pd.read_csv(OUT/'matched_coverage.csv')
    np.testing.assert_allclose(matched.budget, matched.coverage, rtol=0, atol=1e-12)
    for name, digest in json.loads((OUT/'original_visuals.json').read_text()).items():
        assert audit.sha(ROOT/name) == digest, f'The original visual changed: {name}'
    summary = {'status':'passed', 'outer_configurations':40, 'inner_partitions':inner_count,
               'neural_fits':ensemble_count*3, 'prediction_rows':prediction_rows,
               'negative_controls':'exact', 'matched_budgets':'exact', 'original_visuals':'unchanged',
               'experiment_and_analysis_hashes':'match'}
    (OUT/'verification.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))


if __name__ == '__main__': main()
