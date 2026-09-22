"""Measure the paired neural response to omission of the suspect covariate."""
import json
import time
from pathlib import Path
import pandas as pd
from threadpoolctl import threadpool_limits
import ml_transfer_audit as audit


def main():
    out=audit.OUT
    if (out/"neural_sensitivity_results.json").exists():
        raise RuntimeError("Do not overwrite the completed experiment")
    d=pd.read_csv(out/"cohort.csv"); results={};timings=[];start=time.perf_counter()
    splits=json.loads((out/"splits.json").read_text())
    columns=[c for c in audit.FEATURES if c!="vpd"]
    for regime in ["station","proximity","joint"]:
        predictions=[]
        for split in [s for s in splits if s["regime"]==regime]:
            train=d[d.row_id.isin(split["train_row_ids"])];test=d[d.row_id.isin(split["test_row_ids"])]
            x=train[columns].to_numpy();z=test[columns].to_numpy();y=train.y.to_numpy()
            p=test.copy();p["OpenET"]=z[:,0];p["fold"]=split["fold"]
            p["Affine"],_=audit.fit_predict(x[:,[0]],y,z[:,[0]],"affine")
            for residual in [False,True]:
                family="ResidualMLP_noVPD" if residual else "DirectMLP_noVPD"
                names=[]
                for seed in [audit.SEED,audit.SEED+1,audit.SEED+2]:
                    name=family+f"_{seed}"; names.append(name)
                    pred,timing=audit.fit_predict(x,y-x[:,0] if residual else y,z,"mlp",seed=seed)
                    p[name]=pred+z[:,0] if residual else pred
                    timings.append({"regime":regime,"fold":split["fold"],"model":name,**timing})
                p[family]=p[names].mean(axis=1)
            predictions.append(p)
        merged=pd.concat(predictions).sort_values("row_id")
        merged.to_csv(out/f"neural_sensitivity_{regime}.csv",index=False)
        models=[c for c in merged.columns if c not in [*d.columns,"fold"]]
        results[regime]={"models":audit.summarize(merged,models),
                        "croplands":audit.summarize(merged[merged.landcover=="Croplands"],models)}
        print(regime,"complete",flush=True)
    (out/"neural_sensitivity_results.json").write_text(json.dumps(results,indent=2))
    (out/"neural_sensitivity_receipt.json").write_text(json.dumps({"seconds":time.perf_counter()-start,
        "code_sha256":audit.sha(Path(__file__)),
        "protocol_sha256":audit.sha(audit.ROOT/"docs/evaluation/ML_NEURAL_SENSITIVITY.md"),
        "timings":timings},indent=2))


if __name__=="__main__":
    with threadpool_limits(limits=1): main()
