"""Evaluate satellite ET correction on frozen station and time partitions."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import time
import warnings
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mlet.build_dataset import build_dataset
from mlet.experiments.phase2_openet_value import _load_observations
from mlet.evaluate import field_withheld_folds
from mlet.sources.stations import load_station_metadata

SEED = 20260713
FEATURES = ["openet", "eto", "doy_sin", "doy_cos", "t_avg", "vpd", "ws"]
OUT = ROOT / "docs/results/ml_transfer"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def proximity_groups(metadata: dict, stations: list[str]) -> dict[str, str]:
    """Link sites within 10 km, including transitive links."""
    parent = {s: s for s in stations}
    def root(s: str) -> str:
        while parent[s] != s:
            s = parent[s]
        return s
    for i, a in enumerate(stations):
        for b in stations[i + 1:]:
            p, q = metadata[a], metadata[b]
            lat1, lat2 = np.radians([p.latitude, q.latitude])
            dl = np.radians(q.longitude - p.longitude)
            v = np.sin((lat2-lat1)/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dl/2)**2
            distance = 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(v, 0, 1)))
            if distance <= 10:
                parent[root(b)] = root(a)
    return {s: root(s) for s in stations}


def station_weights(stations: np.ndarray) -> np.ndarray:
    _, inverse, counts = np.unique(stations, return_inverse=True, return_counts=True)
    return 1.0 / counts[inverse]


def gate(residual: np.ndarray, correction: np.ndarray, stations: np.ndarray) -> float:
    w = station_weights(stations)
    denominator = np.sum(w * correction**2)
    if denominator <= np.finfo(float).eps:
        return 0.0
    return float(np.clip(np.sum(w * residual * correction) / denominator, 0, 1))


def macro_mae(y: np.ndarray, prediction: np.ndarray, stations: np.ndarray) -> float:
    return float(np.average(np.abs(y-prediction), weights=station_weights(stations)))


def fit_predict(x: np.ndarray, y: np.ndarray, test: np.ndarray, kind: str,
                *, alpha: float = 1, seed: int = SEED) -> tuple[np.ndarray, dict]:
    start = time.perf_counter()
    scaler = StandardScaler().fit(x)
    z = scaler.transform(x)
    target_mean = float(y.mean())
    target_scale = max(float(y.std()), 1e-12)
    if kind == "ridge":
        model = Ridge(alpha=alpha)
    elif kind == "affine":
        model = LinearRegression()
    elif kind == "hgb":
        model = HistGradientBoostingRegressor(max_iter=150, learning_rate=.05,
                    max_leaf_nodes=7, min_samples_leaf=30, l2_regularization=10,
                    early_stopping=False, random_state=seed)
    elif kind == "mlp":
        model = MLPRegressor(hidden_layer_sizes=(32,32), activation="relu",
                    solver="adam", alpha=.001, batch_size=256, learning_rate_init=.001,
                    max_iter=120, early_stopping=False, n_iter_no_change=121,
                    tol=0, random_state=seed)
    else:
        raise ValueError(f"Unknown model: {kind}")
    # Target standardization is confined to neural models.
    target = (y-target_mean)/target_scale if kind == "mlp" else y
    with warnings.catch_warnings(record=True) as observed:
        warnings.simplefilter("always", ConvergenceWarning)
        model.fit(z, target)
    train_seconds = time.perf_counter()-start
    inference_start = time.perf_counter()
    pred = model.predict(scaler.transform(test))
    if kind == "mlp":
        pred = pred*target_scale+target_mean
    return pred, {"fit_seconds": train_seconds,
                  "predict_seconds": time.perf_counter()-inference_start,
                  "test_rows": len(test), "train_rows": len(x),
                  "warnings": [str(w.message) for w in observed]}


def inner_partitions(train: pd.DataFrame, forward: bool) -> list[tuple[np.ndarray,np.ndarray]]:
    groups = sorted(train.group.unique())
    parts = []
    for a,b in field_withheld_folds(groups, min(3,len(groups)), SEED):
        fit = train.group.isin(a).to_numpy(copy=True)
        val = train.group.isin(b).to_numpy(copy=True)
        if forward:
            fit &= (train.date < "2016-01-01").to_numpy()
            val &= (train.date >= "2016-01-01").to_numpy()
        if fit.sum() < 30 or val.sum() == 0:
            continue
        assert not set(train.loc[fit,"group"]) & set(train.loc[val,"group"])
        if forward:
            assert train.loc[fit,"date"].max() < train.loc[val,"date"].min()
        parts.append((np.flatnonzero(fit),np.flatnonzero(val)))
    if not parts:
        raise ValueError("No valid inner partitions")
    return parts


def nested_choices(train: pd.DataFrame, forward: bool) -> dict:
    x = train[FEATURES].to_numpy(); y = train.y.to_numpy()
    oof = {str(a): np.full(len(train),np.nan) for a in [1,10,100,1000]}
    residual = np.full(len(train),np.nan)
    started = time.perf_counter()
    inner_records = []
    for a,b in inner_partitions(train,forward):
        for alpha in [1,10,100,1000]:
            oof[str(alpha)][b], _ = fit_predict(x[a],y[a],x[b],"ridge",alpha=alpha)
        residual[b], _ = fit_predict(x[a],y[a]-x[a,0],x[b],"hgb")
        inner_records.append({"train_row_ids":train.iloc[a].row_id.tolist(),
                              "validation_row_ids":train.iloc[b].row_id.tolist()})
    valid = np.isfinite(residual)
    errors = {a:macro_mae(y[valid],p[valid],train.station.to_numpy()[valid]) for a,p in oof.items()}
    alpha = min(errors,key=errors.get)
    g = gate(y[valid]-x[valid,0],residual[valid],train.station.to_numpy()[valid])
    return {"alpha":int(alpha),"lambda":g,"inner_mae":errors,
            "inner_rows":int(valid.sum()),"selection_seconds":time.perf_counter()-started,
            "inner_partitions":inner_records}


def bootstrap(d: pd.DataFrame, baseline: str, model: str) -> dict:
    """Resample proximity components with all their stations and rows intact."""
    e = d.assign(delta=np.abs(d.y-d[baseline])-np.abs(d.y-d[model]))
    site = e.groupby(["group","station"]).delta.mean().reset_index()
    grouped = site.groupby("group").delta.agg(["sum","count"])
    rng = np.random.default_rng(20260922)
    idx = rng.integers(0,len(grouped),(2000,len(grouped)))
    draws = grouped["sum"].to_numpy()[idx].sum(axis=1)/grouped["count"].to_numpy()[idx].sum(axis=1)
    lo,hi = np.quantile(draws,[.025,.975])
    return {"delta_macro_mae":float(site.delta.mean()),"ci95":[float(lo),float(hi)],
            "stations":len(site),"groups":len(grouped),"n":len(d),
            "wins":int((site.delta > 0).sum())}


def summarize(d: pd.DataFrame, models: list[str]) -> dict:
    result = {}
    for name in models:
        err = d[name]-d.y
        site = d.assign(a=np.abs(err),sq=err**2).groupby("station")[["a","sq"]].mean()
        result[name] = {"mae":float(np.abs(err).mean()),"macro_mae":float(site.a.mean()),
                        "rmse":float(np.sqrt(np.mean(err**2))),"bias":float(err.mean()),
                        "macro_mse":float(site.sq.mean()),
                        "vs_direct":bootstrap(d,"OpenET",name),
                        "vs_affine":bootstrap(d,"Affine",name)}
    return result


def load_data() -> pd.DataFrame:
    raw = ROOT/"data/raw"
    o = raw/"openet_phase2/OpenET_PhaseII_model_ET_dataset"
    flux = next(p for p in (raw/"flux_et").rglob("*_daily_data.csv")).parent
    stats = build_dataset(str(o/"daily_data.dat"),str(flux),str(o/"Station_metadata.xlsx"),str(ROOT/"data/interim"))
    print("Build:",stats,flush=True)
    observations = _load_observations(str(ROOT/"data/interim"))
    meta = load_station_metadata(str(o/"Station_metadata.xlsx"))
    groups = proximity_groups(meta,sorted(observations))
    rows = [{"station":s,"date":r.date.isoformat(),"group":groups[s],
             "landcover":meta[s].land_cover,"latitude":meta[s].latitude,
             "longitude":meta[s].longitude,**r.sample} for s,rs in observations.items() for r in rs]
    d = pd.DataFrame(rows).sort_values(["station","date"]).reset_index(drop=True)
    d.insert(0,"row_id",np.arange(len(d)))
    assert len(d)==7923 and d.station.nunique()==85
    assert not d.duplicated(["station","date"]).any()
    assert np.isfinite(d[FEATURES+["y"]].to_numpy()).all()
    return d


def main() -> None:
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/"results.json").exists():
        raise RuntimeError("A completed experiment exists; do not overwrite it")
    start = time.perf_counter()
    d = load_data()
    d.to_csv(OUT/"cohort.csv",index=False)
    receipt = {"seed":SEED,"neural_seeds":[SEED,SEED+1,SEED+2],
               "python":sys.version,"platform":platform.platform(),"processor":platform.processor(),
               "versions":{"numpy":np.__version__,"pandas":pd.__version__,"sklearn":sklearn.__version__},
               "protocol_sha256":sha(ROOT/"docs/evaluation/ML_TRANSFER_PROTOCOL.md"),
               "code_sha256":sha(Path(__file__)),"cohort_sha256":sha(OUT/"cohort.csv"),
               "paid_compute_usd":0,"electricity_cost_usd":None,"thread_limit":1,
               "source_sha256":{p.name:sha(p) for p in (ROOT/"data/raw").glob("*.zip")}}
    (OUT/"run_receipt.json").write_text(json.dumps(receipt,indent=2))
    result = {}; splits=[]; timings=[]
    for regime in ["station","proximity","joint"]:
        unit = "station" if regime=="station" else "group"
        partitions=field_withheld_folds(sorted(d[unit].unique()),10,SEED)
        predictions=[]
        for fold,(a,b) in enumerate(partitions):
            train=d[d[unit].isin(a)].copy(); test=d[d[unit].isin(b)].copy()
            if regime=="joint":
                train=train[train.date<"2019-01-01"]
                test=test[test.date>="2019-01-01"]
            if test.empty:
                continue
            assert not set(train.station)&set(test.station)
            if regime!="station":
                assert not set(train.group)&set(test.group)
            if regime=="joint":
                assert train.date.max()<test.date.min()
            choice=nested_choices(train,regime=="joint")
            splits.append({"regime":regime,"fold":fold,"train_row_ids":train.row_id.tolist(),
                           "test_row_ids":test.row_id.tolist(),**choice})
            x=train[FEATURES].to_numpy(); z=test[FEATURES].to_numpy(); y=train.y.to_numpy()
            p=test.copy(); p["fold"]=fold
            p["Median"]=np.median(y); p["OpenET"]=z[:,0]
            p["CropCoefficient"]=np.mean(y[x[:,1]>0]/x[x[:,1]>0,1])*z[:,1]
            specs=[("Affine","affine",[0],False,1),
                   ("WeatherRidge","ridge",list(range(1,7)),False,1),
                   ("CombinedRidge","ridge",list(range(7)),False,1),
                   ("TunedRidge","ridge",list(range(7)),False,choice["alpha"]),
                   ("WeatherHGB","hgb",list(range(1,7)),False,1),
                   ("DirectHGB","hgb",list(range(7)),False,1),
                   ("ResidualHGB","hgb",list(range(7)),True,1)]
            for name,kind,cols,residual,alpha in specs:
                target=y-x[:,0] if residual else y
                pred,timing=fit_predict(x[:,cols],target,z[:,cols],kind,alpha=alpha)
                p[name]=pred+z[:,0] if residual else pred
                timings.append({"regime":regime,"fold":fold,"model":name,**timing})
            p["GatedHGB"]=z[:,0]+choice["lambda"]*(p.ResidualHGB-z[:,0])
            for residual in [False,True]:
                names=[]
                for seed in [SEED,SEED+1,SEED+2]:
                    name=("ResidualMLP" if residual else "DirectMLP")+f"_{seed}"
                    pred,timing=fit_predict(x,y-x[:,0] if residual else y,z,"mlp",seed=seed)
                    p[name]=pred+z[:,0] if residual else pred
                    names.append(name)
                    timings.append({"regime":regime,"fold":fold,"model":name,**timing})
                p["ResidualMLP" if residual else "DirectMLP"]=p[names].mean(axis=1)
            # Weather support is descriptive and uses training inputs only.
            mu=x[:,1:].mean(axis=0); sd=np.maximum(x[:,1:].std(axis=0),1e-12)
            p["weather_max_z"]=np.max(np.abs((z[:,1:]-mu)/sd),axis=1)
            models=[c for c in p.columns if c not in [*test.columns,"fold","weather_max_z"]]
            assert np.isfinite(p[models].to_numpy()).all()
            predictions.append(p)
            print(regime,fold,"train",len(train),"test",len(test),"lambda",round(choice["lambda"],3),flush=True)
        merged=pd.concat(predictions).sort_values("row_id")
        assert not merged.row_id.duplicated().any()
        merged.to_csv(OUT/f"predictions_{regime}.csv",index=False)
        result[regime]={"models":summarize(merged,models),"n":len(merged),
                        "stations":merged.station.nunique(),"groups":merged.group.nunique(),
                        "croplands":summarize(merged[merged.landcover=="Croplands"],models)}
        (OUT/"partial_results.json").write_text(json.dumps(result,indent=2))
    receipt["total_seconds"]=time.perf_counter()-start
    (OUT/"run_receipt.json").write_text(json.dumps(receipt,indent=2))
    (OUT/"splits.json").write_text(json.dumps(splits))
    (OUT/"timings.json").write_text(json.dumps(timings,indent=2))
    (OUT/"results.json").write_text(json.dumps(result,indent=2))
    print("Completed in",receipt["total_seconds"],"seconds",flush=True)


if __name__=="__main__":
    with threadpool_limits(limits=1):
        main()
