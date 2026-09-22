"""Build paper tables and figures from saved out-of-fold predictions."""
from __future__ import annotations
import json
import os
from pathlib import Path
os.environ.setdefault("MPLCONFIGDIR",str(Path(__file__).resolve().parents[1]/".mplcache"))
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
import numpy as np
import pandas as pd
import ml_transfer_audit as audit

ROOT=audit.ROOT; DATA=audit.OUT; PAPER=ROOT/"manuscript/arxiv"; FIG=PAPER/"figures"
COLORS=["#6688A4","#B66A5B","#6C9D9A","#D1992D"]
# Plot layout and error-bar styling adapted from Chen Liu, figures4papers,
# figure_ImmunoStruct/plot_bars.py, commit 3c181f85e82c6f24948fcaaf3be6696102b41d8d.
# The upstream license is CC BY-NC 4.0. Data and scientific annotations are new.
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,
 "axes.spines.right":False,"axes.spines.top":False,"axes.linewidth":.8,
 "svg.fonttype":"none","pdf.fonttype":42,"axes.titleweight":"bold",
 "axes.labelcolor":"#333333","text.color":"#222222"})


def save(fig,name):
    fig.savefig(FIG/f"{name}.pdf",bbox_inches="tight")
    fig.savefig(FIG/f"{name}.png",dpi=180,bbox_inches="tight")
    plt.close(fig)


def merged(regime):
    d=pd.read_csv(DATA/f"predictions_{regime}.csv")
    for prefix in ["sensitivity","neural_sensitivity"]:
        extra=pd.read_csv(DATA/f"{prefix}_{regime}.csv")
        assert d.row_id.tolist()==extra.row_id.tolist()
        for c in extra:
            if c not in d: d[c]=extra[c]
    return d


def f(x): return f"{x:.3f}"


def table(rows,path,header):
    content=header+"\n"+"\n".join(" & ".join(row)+r" \\" for row in rows)+"\n"
    path.write_text(content)


def main():
    FIG.mkdir(parents=True,exist_ok=True)
    records={reg:merged(reg) for reg in ["station","proximity","joint"]}
    d=records["proximity"]; suspect=d.station=="manilacotton"
    models=["OpenET","Affine","WeatherRidge","CombinedRidge","TunedRidge",
            "WeatherHGB","DirectHGB","ResidualHGB","GatedHGB","DirectMLP","ResidualMLP"]
    names={"OpenET":"OpenET","Affine":"Affine calibration","WeatherRidge":"Weather ridge",
           "CombinedRidge":"Combined ridge","TunedRidge":"Tuned ridge","WeatherHGB":"Weather boosting",
           "DirectHGB":"Direct boosting","ResidualHGB":"Residual boosting","GatedHGB":"Gated boosting",
           "DirectMLP":"Direct neural","ResidualMLP":"Residual neural"}
    rows=[]
    for m in models:
        err=d[m]-d.y;delta=audit.bootstrap(d,"OpenET",m)
        rows.append([names[m],f(err.abs().mean()),f(np.sqrt((err**2).mean())),
                     f(audit.macro_mae(d.y.to_numpy(),d[m].to_numpy(),d.station.to_numpy())),
                     f(delta["delta_macro_mae"]),f"[{f(delta['ci95'][0])}, {f(delta['ci95'][1])}]"])
    table(rows,PAPER/"table_main.tex","")
    rows=[]
    for base in ["WeatherRidge","CombinedRidge","DirectHGB","ResidualHGB","GatedHGB","DirectMLP","ResidualMLP"]:
        for m,label in [(base,"Archived"),(base+"_noVPD","Omit VPD")]:
            e=d[m]-d.y;delta=audit.bootstrap(d,"OpenET",m)
            rows.append([names[base],label,f(e.abs().mean()),f(audit.macro_mae(d.y.to_numpy(),d[m].to_numpy(),d.station.to_numpy())),
                         f"[{f(delta['ci95'][0])}, {f(delta['ci95'][1])}]"])
    table(rows,PAPER/"table_sensitivity.tex","")
    j=records["joint"];rows=[]
    for m in ["OpenET","Affine","WeatherHGB","DirectHGB","ResidualHGB","GatedHGB","DirectMLP","ResidualMLP",
              "GatedHGB_noVPD","DirectMLP_noVPD","ResidualMLP_noVPD"]:
        e=j[m]-j.y;delta=audit.bootstrap(j,"OpenET",m)
        label=names.get(m,names.get(m.replace("_noVPD",""),m)+" (no VPD)")
        rows.append([label,f(e.abs().mean()),f(audit.macro_mae(j.y.to_numpy(),j[m].to_numpy(),j.station.to_numpy())),
                     f"[{f(delta['ci95'][0])}, {f(delta['ci95'][1])}]"])
    table(rows,PAPER/"table_joint.tex","")
    # Physical inconsistency and its error concentration.
    fig,axs=plt.subplots(1,2,figsize=(10.4,3.4),gridspec_kw={"width_ratios":[1,1.25]})
    humid=pd.read_csv(DATA/"humidity_audit.csv")
    good=humid.station!="manilacotton"
    axs[0].scatter(humid.loc[good,"vp_kpa"],humid.loc[good,"vpd_kpa"],s=7,alpha=.25,color=COLORS[0],label="Other stations")
    axs[0].scatter(humid.loc[~good,"vp_kpa"],humid.loc[~good,"vpd_kpa"],s=18,color=COLORS[1],label="manilacotton")
    axs[0].axvline(0,color="#555",lw=.8,ls="--");axs[0].set(xlabel="Archived actual vapor pressure (kPa)",ylabel="Archived VPD (kPa)",title="A  Physical validity")
    axs[0].legend(frameon=False,fontsize=8,loc="upper right")
    ms=["OpenET","CombinedRidge","WeatherRidge","DirectMLP","ResidualMLP"]
    vals=[float(((d.loc[suspect,m]-d.loc[suspect,"y"])**2).sum()/((d[m]-d.y)**2).sum()*100) for m in ms]
    bars=axs[1].barh(np.arange(len(ms)),vals,color=[COLORS[0],COLORS[0],COLORS[0],COLORS[1],COLORS[1]])
    axs[1].set_yticks(np.arange(len(ms)),[names[m] for m in ms]);axs[1].invert_yaxis()
    axs[1].set(xlim=(0,100),xlabel="Squared error from 32 suspect rows (%)",title="B  Error concentration")
    for b,v in zip(bars,vals):axs[1].text(v+1,b.get_y()+b.get_height()/2,f"{v:.1f}%",va="center",fontsize=9)
    fig.tight_layout(pad=1.5);save(fig,"figure_1_validity")
    # Paired confidence intervals.
    fig,axs=plt.subplots(1,2,figsize=(10.4,3.8),sharey=True)
    ms=["CombinedRidge","DirectHGB","ResidualHGB","GatedHGB","DirectMLP","ResidualMLP"]
    for ax,suffix,title,color in zip(axs,["","_noVPD"],["A  Archived weather inputs","B  VPD omitted; same target rows"],COLORS[:2]):
        for i,m in enumerate(ms):
            b=audit.bootstrap(d,"OpenET",m+suffix);v=b["delta_macro_mae"];lo,hi=b["ci95"]
            ax.errorbar(v,i,xerr=[[v-lo],[hi-v]],fmt="o",color=color,capsize=3,lw=1.3)
        ax.axvline(0,color="#555",lw=.8,ls="--");ax.set_title(title,fontsize=10)
        ax.set_xlabel("Station-macro MAE reduction (mm/day)")
        ax.grid(axis="x",alpha=.15)
    axs[0].set_yticks(range(len(ms)),[names[m] for m in ms]);axs[0].invert_yaxis()
    fig.tight_layout(pad=1.5);save(fig,"figure_2_ablation")
    # The exact correction-risk identity, with station-level empirical moments.
    fig,axs=plt.subplots(1,2,figsize=(10.4,3.6))
    moment_rows=[]
    for ax,reg,title in zip(axs,["proximity","joint"],["A  Unseen proximity groups","B  Unseen groups and later years"]):
        q=records[reg];r=q.y-q.OpenET;g=q.ResidualHGB-q.OpenET
        stats=q.assign(alignment=2*r*g,energy=g*g).groupby("station")[["alignment","energy"]].mean()
        crop=q.groupby("station").landcover.first().eq("Croplands")
        for selected,color,label in [(crop,COLORS[1],"Croplands"),(~crop,COLORS[0],"Other land covers")]:
            ax.scatter(stats.loc[selected,"energy"],stats.loc[selected,"alignment"],s=27,alpha=.75,color=color,label=label)
        hi=max(stats.energy.max(),stats.alignment.max(),.1)
        ax.plot([0,hi],[0,hi],"--",lw=1,color=COLORS[1],label="Equal MSE to OpenET")
        ax.axhline(0,color="#aaa",lw=.7);ax.set_title(title,fontsize=10)
        ax.set(xlabel=r"Correction energy $E_s[g^2]$",ylabel=r"Residual alignment $2E_s[rg]$")
        ax.legend(frameon=False,fontsize=8)
        for s,v in stats.iterrows():moment_rows.append({"regime":reg,"station":s,**v.to_dict()})
    fig.tight_layout(pad=1.5);save(fig,"figure_3_alignment")
    pd.DataFrame(moment_rows).to_csv(DATA/"correction_moments.csv",index=False)
    # Distinct evaluation estimands on the identical joint-transfer cohort.
    fig,axs=plt.subplots(1,2,figsize=(10.4,3.5),sharey=True)
    ms=["OpenET","DirectHGB","ResidualHGB","GatedHGB","DirectMLP","ResidualMLP"]
    for ax,macro,title in zip(axs,[False,True],["A  Equal weight per observation","B  Equal weight per station"]):
        values=[audit.macro_mae(j.y.to_numpy(),j[m].to_numpy(),j.station.to_numpy()) if macro else float((j[m]-j.y).abs().mean()) for m in ms]
        ax.barh(range(len(ms)),values,color=[COLORS[0] if i==0 else COLORS[2] for i in range(len(ms))])
        ax.axvline(values[0],ls="--",lw=.8,color="#555");ax.set(xlabel="MAE (mm/day)",title=title,xlim=(0,1.0))
        for i,v in enumerate(values):ax.text(v+.012,i,f(v),va="center",fontsize=9)
    axs[0].set_yticks(range(len(ms)),[names[m] for m in ms]);axs[0].invert_yaxis()
    fig.tight_layout(pad=1.5);save(fig,"figure_4_estimands")
    # Full machine-readable comparisons, including all seed results.
    full={}
    for reg,q in records.items():
        names_all=[c for c in q if c in models or c.endswith("_noVPD") or "MLP_202" in c or "noVPD_202" in c or c.endswith("_clipped")]
        full[reg]=audit.summarize(q,names_all)
    (DATA/"all_comparisons.json").write_text(json.dumps(full,indent=2))
    diagnostics={}
    for reg,q in records.items():
        bad=q.station=="manilacotton";v={}
        for m in models:
            e=q[m]-q.y
            v[m]={"suspect_n":int(bad.sum()),"suspect_sse_share":float((e[bad]**2).sum()/(e**2).sum()),
                  "suspect_mae":float(e[bad].abs().mean()) if bad.sum() else None,
                  "other_mae":float(e[~bad].abs().mean())}
        diagnostics[reg]=v
    (DATA/"influence.json").write_text(json.dumps(diagnostics,indent=2))
    rows=[]
    for reg,q in records.items():
        if reg=="station": continue
        for crop in [True,False]:
            sub=q[q.landcover.eq("Croplands")==crop]
            for m in ["OpenET","GatedHGB_noVPD","ResidualMLP_noVPD"]:
                b=audit.bootstrap(sub,"OpenET",m)
                rows.append([reg.title(),"Crop" if crop else "Other",str(b["stations"]),str(b["n"]),
                  names.get(m.replace("_noVPD",""),m),
                  f(audit.macro_mae(sub.y.to_numpy(),sub[m].to_numpy(),sub.station.to_numpy())),
                  f"[{f(b['ci95'][0])}, {f(b['ci95'][1])}]"])
    table(rows,PAPER/"table_strata.tex","")
    rows=[]
    for reg,q in records.items():
        for base in ["DirectMLP","ResidualMLP","DirectMLP_noVPD","ResidualMLP_noVPD"]:
            vals=[audit.macro_mae(q.y.to_numpy(),q[base+f'_{s}'].to_numpy(),q.station.to_numpy()) for s in [audit.SEED,audit.SEED+1,audit.SEED+2]]
            label=names[base.replace("_noVPD","")]+(" (no VPD)" if base.endswith("_noVPD") else "")
            rows.append([reg.title(),label,*[f(x) for x in vals]])
    table(rows,PAPER/"table_seeds.tex","")
    times=pd.DataFrame(json.loads((DATA/"timings.json").read_text()))
    times=times[times.regime=="proximity"].copy()
    times['family']=times.model.str.replace(r'_2026071[345]$','',regex=True)
    times=times.groupby(['family','fold'])[['fit_seconds','predict_seconds']].sum().reset_index()
    rows=[]
    for family,g in times.groupby('family'):
        fit=np.quantile(g.fit_seconds*1000,[.25,.5,.75]);pred=np.quantile(g.predict_seconds*1000,[.25,.5,.75])
        rows.append([names.get(family,family),f"{fit[1]:.2f} [{fit[0]:.2f}, {fit[2]:.2f}]",
                     f"{pred[1]:.3f} [{pred[0]:.3f}, {pred[2]:.3f}]"])
    table(rows,PAPER/"table_cost.tex","")
    print("Generated four vector figures, three tables, and comparison records.")


if __name__=="__main__":main()
