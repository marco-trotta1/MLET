"""Verify saved scientific outputs without fitting another model."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs/results/ml_transfer"


def main():
    d=pd.read_csv(OUT/"cohort.csv").set_index("row_id")
    splits=json.loads((OUT/"splits.json").read_text())
    count=0
    for split in splits:
        train=d.loc[split["train_row_ids"]];test=d.loc[split["test_row_ids"]]
        assert not set(train.index)&set(test.index)
        assert not set(train.station)&set(test.station)
        if split["regime"]!="station":assert not set(train.group)&set(test.group)
        if split["regime"]=="joint":assert train.date.max()<test.date.min()
        for inner in split["inner_partitions"]:
            count+=1
            assert set(inner["train_row_ids"]+inner["validation_row_ids"])<=set(train.index)
            a=d.loc[inner["train_row_ids"]];b=d.loc[inner["validation_row_ids"]]
            assert not set(a.group)&set(b.group)
            if split["regime"]=="joint":assert a.date.max()<b.date.min()
    expected=json.loads((ROOT/"docs/results/phase2_openet_independent_reproduction_receipt.json").read_text())
    expected=expected["result"]["field_withheld"]["models"]
    actual=json.loads((OUT/"results.json").read_text())["station"]["models"]
    mapping={"B1_CropCoefficient":"CropCoefficient","B2_WeatherRidge":"WeatherRidge",
             "M1_OpenETDirect":"OpenET","M2_OpenETRecal":"Affine","M3_OpenETRidge":"CombinedRidge"}
    for row in expected:
        if row["name"] in mapping:
            a=actual[mapping[row["name"]]]
            np.testing.assert_allclose([a["mae"],a["rmse"],a["bias"]],
                [row["mae_mm"],row["rmse_mm"],row["bias_mm"]],rtol=1e-11,atol=1e-12)
    checks=[("run_receipt.json","ml_transfer_audit.py","ML_TRANSFER_PROTOCOL.md"),
            ("sensitivity_receipt.json","ml_transfer_sensitivity.py","ML_TRANSFER_SENSITIVITY.md"),
            ("neural_sensitivity_receipt.json","ml_neural_sensitivity.py","ML_NEURAL_SENSITIVITY.md"),
            ("landcover_receipt.json","ml_landcover_sensitivity.py","ML_LANDCOVER_SENSITIVITY.md")]
    for receipt,script,protocol in checks:
        r=json.loads((OUT/receipt).read_text())
        for key,path in [("code_sha256",ROOT/"scripts"/script),("protocol_sha256",ROOT/"docs/evaluation"/protocol)]:
            assert r[key]==hashlib.sha256(path.read_bytes()).hexdigest()
    run=json.loads((OUT/"run_receipt.json").read_text())
    assert run["cohort_sha256"]==hashlib.sha256((OUT/"cohort.csv").read_bytes()).hexdigest()
    for regime,n in [("station",7923),("proximity",7923),("joint",649)]:
        original=pd.read_csv(OUT/f"predictions_{regime}.csv")
        assert len(original)==n and not original.row_id.duplicated().any()
        for prefix in ["sensitivity","neural_sensitivity","landcover"]:
            q=pd.read_csv(OUT/f"{prefix}_{regime}.csv")
            assert q.row_id.tolist()==original.row_id.tolist()
            np.testing.assert_allclose(q.y,original.y,rtol=0,atol=1e-12)
    h=json.loads((OUT/"humidity_summary.json").read_text())
    assert h["negative_vp_rows"]==50 and h["by_station"]["manilacotton"]["n"]==32
    summary={"outer_folds":len(splits),"inner_partitions":count,"original_models_reproduced":5,
      "protocol_and_code_hashes":"match","cohort_hash":"match","sensitivity_rows_and_targets":"match",
      "humidity_audit":"verified","status":"passed"}
    (OUT/"verification.json").write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))


if __name__=="__main__":main()
