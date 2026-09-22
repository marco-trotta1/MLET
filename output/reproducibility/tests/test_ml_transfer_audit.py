"""Check partition isolation and the algebra behind correction diagnostics."""
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

path=Path(__file__).resolve().parents[1]/"scripts/ml_transfer_audit.py"
spec=importlib.util.spec_from_file_location("audit",path)
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_gate_minimizes_station_weighted_squared_loss():
    rng=np.random.default_rng(13)
    for _ in range(30):
        r=rng.normal(size=80); g=.3*r+rng.normal(size=80)
        sites=np.repeat(["a","b","c","d"],[5,15,20,40])
        weight=audit.station_weights(sites)
        selected=audit.gate(r,g,sites)
        score=np.average((r-selected*g)**2,weights=weight)
        grid=np.linspace(0,1,101)
        assert score<=min(np.average((r-lam*g)**2,weights=weight) for lam in grid)+1e-12
        np.testing.assert_allclose(np.average(r*r-(r-selected*g)**2,weights=weight),
            2*selected*np.average(r*g,weights=weight)-selected**2*np.average(g*g,weights=weight),atol=1e-12)


def test_orthogonal_rotation_preserves_isotropic_ridge():
    rng=np.random.default_rng(3)
    x=rng.normal(size=(80,7)); y=rng.normal(size=80); z=rng.normal(size=(20,7))
    q,_=np.linalg.qr(rng.normal(size=(7,7)))
    a=Ridge(alpha=10).fit(x,y).predict(z)
    b=Ridge(alpha=10).fit(x@q,y).predict(z@q)
    np.testing.assert_allclose(a,b,rtol=1e-11,atol=1e-12)


def test_inner_forward_split_excludes_future_and_groups():
    d=pd.DataFrame([{"group":f"g{i}","station":f"s{i}","date":date}
         for i in range(9) for date in ["2014-01-01"]*20+["2017-01-01"]*20])
    for a,b in audit.inner_partitions(d,True):
        assert not set(d.iloc[a].group)&set(d.iloc[b].group)
        assert d.iloc[a].date.max()<d.iloc[b].date.min()


def test_bootstrap_preserves_identical_pairing():
    d=pd.DataFrame({"group":["a","a","b"],"station":["a1","a2","b"],
                    "y":[0.,2.,3.],"a":[1.,1.,1.],"b":[1.,1.,1.]})
    r=audit.bootstrap(d,"a","b")
    np.testing.assert_allclose([r["delta_macro_mae"],*r["ci95"]],[0,0,0],atol=1e-12)
