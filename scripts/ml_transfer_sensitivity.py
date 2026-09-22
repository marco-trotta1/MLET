"""Run the declared no-VPD and training-support sensitivity checks."""
from __future__ import annotations
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
import ml_transfer_audit as audit


def main() -> None:
    root=audit.ROOT; out=audit.OUT
    if (out/"sensitivity_results.json").exists():
        raise RuntimeError("Do not overwrite the completed sensitivity experiment")
    d=pd.read_csv(out/"cohort.csv")
    no_vpd=[i for i,k in enumerate(audit.FEATURES) if k!="vpd"]
    weather=[i for i in no_vpd if i!=0]
    start=time.perf_counter(); results={}; records=[]; timings=[]
    for regime in ["station","proximity","joint"]:
        unit="station" if regime=="station" else "group"
        predictions=[]
        for fold,(a,b) in enumerate(audit.field_withheld_folds(sorted(d[unit].unique()),10,audit.SEED)):
            train=d[d[unit].isin(a)].copy(); test=d[d[unit].isin(b)].copy()
            if regime=="joint":
                train=train[train.date<"2019-01-01"];test=test[test.date>="2019-01-01"]
            if test.empty: continue
            x=train[audit.FEATURES].to_numpy(); z=test[audit.FEATURES].to_numpy(); y=train.y.to_numpy()
            residual=np.full(len(train),np.nan)
            for fit,val in audit.inner_partitions(train,regime=="joint"):
                residual[val],_=audit.fit_predict(x[fit][:,no_vpd],y[fit]-x[fit,0],x[val][:,no_vpd],"hgb")
            valid=np.isfinite(residual)
            lam=audit.gate(y[valid]-x[valid,0],residual[valid],train.station.to_numpy()[valid])
            p=test.copy();p["fold"]=fold;p["OpenET"]=z[:,0]
            p["Affine"],_=audit.fit_predict(x[:,[0]],y,z[:,[0]],"affine")
            for name,kind,cols,res in [
                ("WeatherRidge_noVPD","ridge",weather,False),
                ("CombinedRidge_noVPD","ridge",no_vpd,False),
                ("WeatherHGB_noVPD","hgb",weather,False),
                ("DirectHGB_noVPD","hgb",no_vpd,False),
                ("ResidualHGB_noVPD","hgb",no_vpd,True)]:
                pred,timing=audit.fit_predict(x[:,cols],y-x[:,0] if res else y,z[:,cols],kind)
                p[name]=pred+z[:,0] if res else pred
                timings.append({"regime":regime,"fold":fold,"model":name,**timing})
            p["GatedHGB_noVPD"]=z[:,0]+lam*(p.ResidualHGB_noVPD-z[:,0])
            low=np.quantile(x[:,1:],.01,axis=0);high=np.quantile(x[:,1:],.99,axis=0)
            xc=x.copy();zc=z.copy();xc[:,1:]=np.clip(x[:,1:],low,high);zc[:,1:]=np.clip(z[:,1:],low,high)
            for name,cols in [("WeatherRidge_clipped",list(range(1,7))),
                              ("CombinedRidge_clipped",list(range(7)))]:
                p[name],timing=audit.fit_predict(xc[:,cols],y,zc[:,cols],"ridge")
                timings.append({"regime":regime,"fold":fold,"model":name,**timing})
            records.append({"regime":regime,"fold":fold,"lambda_noVPD":lam})
            models=[c for c in p.columns if c not in [*test.columns,"fold"]]
            predictions.append(p)
        merged=pd.concat(predictions).sort_values("row_id")
        merged.to_csv(out/f"sensitivity_{regime}.csv",index=False)
        results[regime]={"models":audit.summarize(merged,models),
                        "croplands":audit.summarize(merged[merged.landcover=="Croplands"],models)}
        print("Sensitivity",regime,"complete",flush=True)
    (out/"sensitivity_results.json").write_text(json.dumps(results,indent=2))
    (out/"sensitivity_receipt.json").write_text(json.dumps({"seconds":time.perf_counter()-start,
        "code_sha256":audit.sha(Path(__file__)),
        "protocol_sha256":audit.sha(root/"docs/evaluation/ML_TRANSFER_SENSITIVITY.md"),
        "timings":timings,"gates":records},indent=2))


if __name__=="__main__":
    with threadpool_limits(limits=1): main()
