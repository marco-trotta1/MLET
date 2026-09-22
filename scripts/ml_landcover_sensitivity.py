"""Evaluate a simple calibration using the archived land-cover class."""
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
import ml_transfer_audit as audit


def main():
    out=audit.OUT
    if (out/"landcover_results.json").exists():raise RuntimeError("Do not overwrite completed results")
    d=pd.read_csv(out/"cohort.csv");splits=json.loads((out/"splits.json").read_text())
    results={};fits=[];start=time.perf_counter()
    for regime in ["station","proximity","joint"]:
        parts=[]
        for split in [s for s in splits if s["regime"]==regime]:
            train=d[d.row_id.isin(split["train_row_ids"])];test=d[d.row_id.isin(split["test_row_ids"])]
            p=test.copy();p["OpenET"]=p.openet
            p["Affine"],_=audit.fit_predict(train[['openet']].to_numpy(),train.y.to_numpy(),test[['openet']].to_numpy(),"affine")
            p["LandcoverAffine"]=p.Affine
            for cover in test.landcover.unique():
                a=train[train.landcover==cover];sel=test.landcover==cover
                if len(a)>=3:
                    pred,t=audit.fit_predict(a[['openet']].to_numpy(),a.y.to_numpy(),test.loc[sel,['openet']].to_numpy(),"affine")
                    p.loc[sel,"LandcoverAffine"]=pred
                    fits.append({"regime":regime,"fold":split["fold"],"cover":cover,**t})
            parts.append(p)
        p=pd.concat(parts).sort_values('row_id');p.to_csv(out/f'landcover_{regime}.csv',index=False)
        results[regime]={key:audit.summarize(q,['OpenET','Affine','LandcoverAffine']) for key,q in
          [('models',p),('croplands',p[p.landcover=='Croplands']),('other',p[p.landcover!='Croplands'])]}
    (out/'landcover_results.json').write_text(json.dumps(results,indent=2))
    (out/'landcover_receipt.json').write_text(json.dumps({'seconds':time.perf_counter()-start,'fits':fits,
        'code_sha256':audit.sha(Path(__file__)),
        'protocol_sha256':audit.sha(audit.ROOT/'docs/evaluation/ML_LANDCOVER_SENSITIVITY.md')},indent=2))
    for regime,r in results.items():
        print(regime,r['models']['LandcoverAffine'])


if __name__=='__main__':
    with threadpool_limits(limits=1):main()
