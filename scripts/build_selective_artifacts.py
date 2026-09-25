"""Build selector comparisons and figures from saved predictions."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import ml_transfer_audit as audit
from ml_selective_residual import METHODS

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/results/ml_selective"
PAPER = ROOT / "manuscript/arxiv"
FIG = PAPER / "figures"
COLORS = {"Full": "#171717", "Spread95": "#B66A5B", "Support95": "#6688A4", "Gain": "#D1992D",
          "SupportGain": "#6C9D9A", "Uniform": "#8B799B", "Clip": "#888888", "OpenET": "#171717"}
# Typography and restrained error bars follow the attributed figures4papers adaptation.
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.labelcolor": "#333333", "axes.edgecolor": "#777777",
                     "pdf.fonttype": 42, "savefig.bbox": "tight"})


def budget_probabilities(score, weights, fraction):
    """Match the weighted acceptance budget with one randomized boundary."""
    order = np.argsort(score, kind="stable")
    w = weights[order]
    before = np.cumsum(w) - w
    accepted = np.clip((fraction * w.sum() - before) / w, 0, 1)
    answer = np.empty(len(score))
    answer[order] = accepted
    return answer


def paired_loss_interval(frame, first, second):
    site = frame.assign(delta=first-second).groupby(["group", "station"]).delta.mean().reset_index()
    blocks = site.groupby("group").delta.agg(["sum", "count"])
    rng = np.random.default_rng(20260922)
    index = rng.integers(0, len(blocks), (2000, len(blocks)))
    samples = blocks["sum"].to_numpy()[index].sum(axis=1) / blocks["count"].to_numpy()[index].sum(axis=1)
    return {"difference": float(site.delta.mean()), "ci95": np.quantile(samples, [.025, .975]).tolist()}


def matched_analysis():
    rows = []; comparisons = {}
    for path in sorted(DATA.glob("predictions_*.csv")):
        key = path.stem.removeprefix("predictions_")
        d = pd.read_csv(path)
        w = audit.station_weights(d.station.to_numpy())
        baseline = np.abs(d.y-d.OpenET).to_numpy(); neural = np.abs(d.y-d.Full).to_numpy()
        scores = {"Spread": d.spread / d.spread_threshold,
                  "Support": d.distance / d.support_threshold, "Gain": -d.predicted_gain}
        losses_at_half = {}
        for name, score in scores.items():
            for q in np.linspace(0, 1, 11):
                p = budget_probabilities(score.to_numpy(), w, q)
                loss = p * neural + (1-p) * baseline
                coverage = float(np.average(p, weights=w))
                if abs(coverage-q) > 1e-12:
                    raise ValueError("The matched acceptance budget is inconsistent")
                rows.append({"case": key, "selector": name, "budget": float(q), "coverage": coverage,
                             "macro_mae": float(np.average(loss, weights=w)),
                             "rows": len(d), "stations": d.station.nunique(), "groups": d.group.nunique()})
                if np.isclose(q, .5): losses_at_half[name] = loss
        comparisons[key] = {"spread_minus_support": paired_loss_interval(d, losses_at_half["Spread"], losses_at_half["Support"]),
                            "gain_minus_support": paired_loss_interval(d, losses_at_half["Gain"], losses_at_half["Support"])}
    curves = pd.DataFrame(rows)
    curves.to_csv(DATA / "matched_coverage.csv", index=False)
    (DATA / "matched_comparisons.json").write_text(json.dumps(comparisons, indent=2))
    return curves


def save(fig, stem):
    fig.savefig(FIG / (stem+'.pdf'), metadata={"CreationDate": None})
    fig.savefig(FIG / (stem+'.png'), dpi=180)
    plt.close(fig)


def design():
    fig, ax = plt.subplots(figsize=(10, 3.1)); ax.set_xlim(0, 10); ax.set_ylim(0, 3); ax.axis('off')
    boxes = [(.2, 1.7, 2.05, .95, 'Outer training groups', 'Inner group splits\ntrain neural ensemble', '#EEF3F6'),
             (2.65, 1.7, 2.05, .95, 'Held-out inner rows', 'Residual + spread\nsupport + realized gain', '#EEF3F6'),
             (5.1, 1.7, 2.05, .95, 'Fit the selector', 'Fix thresholds or\nlearn relative benefit', '#EEF3F6'),
             (7.55, 1.7, 2.05, .95, 'Unseen outer group', 'Refit neural ensemble\napply fixed selector', '#EEF3F6'),
             (5.1, .05, 2.05, 1.05, 'Accept correction', r'$\hat y=o+\bar g$', '#EDF4F3'),
             (7.55, .05, 2.05, 1.05, 'Reject correction', r'$\hat y=o$', '#F7EFED')]
    for x,y,w,h,title,body,color in boxes:
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.025',facecolor=color,edgecolor='#A0A0A0',lw=.6))
        ax.text(x+w/2,y+h-.20,title,ha='center',weight='bold',fontsize=9)
        ax.text(x+w/2,y+.33,body,ha='center',va='center',fontsize=12 if '$' in body else 9,
                math_fontfamily='stix')
    for a,b in [(2.30,2.60),(4.75,5.05),(7.20,7.50)]:
        ax.annotate('',xy=(b,2.18),xytext=(a,2.18),arrowprops={'arrowstyle':'->','color':'#777777'})
    ax.annotate('',xy=(8.575,1.12),xytext=(8.575,1.67),arrowprops={'arrowstyle':'->','color':'#777777'})
    ax.annotate('',xy=(6.125,1.12),xytext=(8.2,1.67),arrowprops={'arrowstyle':'->','color':'#777777'})
    ax.text(.3,.73,'Selection target',weight='bold',fontsize=10)
    ax.text(.3,.36,r'$D=|y-o|-|y-o-\bar g|$',fontsize=14,math_fontfamily='stix')
    save(fig,'figure_6_selective_design')


def natural(results):
    fig, axes = plt.subplots(2,2,figsize=(10,6.3),sharey=True)
    names=METHODS[1:]
    for ax,key,title in zip(axes.flat,['proximity_archived','proximity_noVPD','joint_archived','joint_noVPD'],
                           ['A  Spatial groups / archived inputs','B  Spatial groups / no VPD',
                            'C  Groups + later years / archived inputs','D  Groups + later years / no VPD']):
        for i,name in enumerate(names):
            m=results[key]['natural']['models'][name]['vs_openet'];v=m['delta_macro_mae'];lo,hi=m['ci95']
            ax.errorbar(v,i,xerr=[[v-lo],[hi-v]],fmt='o',color=COLORS[name],ms=4,capsize=2,lw=.9)
        ax.axvline(0,color='#999999',ls='--',lw=.8);ax.set_yticks(range(len(names)),names);ax.set_ylim(len(names)-.5,-.5)
        ax.set_title(title,loc='left',fontsize=10,weight='bold');ax.set_xlabel('Station MAE reduction vs OpenET (mm/day)')
        ax.grid(axis='x',alpha=.15)
    fig.tight_layout(w_pad=3,h_pad=2)
    save(fig,'figure_7_selective_transfer')


def faults(results):
    fig,axes=plt.subplots(1,2,figsize=(10,3.35),sharey=True)
    names=['Full','Spread95','Support95','Gain','SupportGain','Uniform','Clip']
    for ax,condition,title in zip(axes,['wind_x10','temperature_plus20'],['A  Wind multiplied by 10','B  Temperature increased by 20 C']):
        key='proximity_noVPD';data=results[key][condition]['models'];base=data['OpenET']['macro_mae']
        for i,name in enumerate(names):
            value=data[name]['macro_mae'];ax.barh(i,value,color=COLORS[name],height=.7,alpha=.9)
            ax.text(value+.008,i,f'{value:.3f}',va='center',fontsize=8)
        ax.axvline(base,color='#555555',ls='--',lw=1)
        ax.set_yticks(range(len(names)),names);ax.set_ylim(len(names)-.5,-.5);ax.set_xlim(0,1.55)
        ax.set_title(title,loc='left',weight='bold',fontsize=10);ax.set_xlabel('Complete-system station MAE (mm/day)')
    fig.tight_layout(w_pad=2)
    save(fig,'figure_8_input_faults')


def matched(curves):
    fig,axes=plt.subplots(2,2,figsize=(10,6.0))
    for ax,regime,condition,title in zip(axes.flat,['proximity','proximity','joint','joint'],
      ['wind_x10','temperature_plus20','wind_x10','temperature_plus20'],
      ['A  Spatial groups / wind fault','B  Spatial groups / temperature fault',
       'C  Groups + later years / wind fault','D  Groups + later years / temperature fault']):
        subset=curves[curves['case']==f'{regime}_noVPD_{condition}']
        for name,color in [('Spread',COLORS['Spread95']),('Support',COLORS['Support95']),('Gain',COLORS['Gain'])]:
            d=subset[subset.selector==name];ax.plot(d.coverage,d.macro_mae,'o-',label=name,color=color,ms=3,lw=1.2)
        ax.set_title(title,loc='left',weight='bold',fontsize=10);ax.set_xlabel('Station-weighted acceptance budget')
        ax.set_ylabel('Expected station MAE (mm/day)');ax.grid(alpha=.15)
    axes[0,0].legend(frameon=False,fontsize=8)
    fig.tight_layout(w_pad=2,h_pad=2)
    save(fig,'figure_9_matched_acceptance')


def tables(results):
    natural=[];fault=[];crop=[]
    for name in METHODS:
        cells=[name]
        for key in ['proximity_archived','proximity_noVPD','joint_archived','joint_noVPD']:
            m=results[key]['natural']['models'][name];lo,hi=m['vs_openet']['ci95']
            cells.append(f"{m['macro_mae']:.3f} [{lo:.3f}, {hi:.3f}]")
        natural.append(' & '.join(cells)+r' \\')
        cells=[name]
        for key in ['proximity_noVPD','joint_noVPD']:
            for condition in ['probe_clean','vpd_x10','wind_x10','temperature_plus20']:
                cells.append(f"{results[key][condition]['models'][name]['macro_mae']:.3f}")
        fault.append(' & '.join(cells)+r' \\')
        cells=[name]
        for key in ['proximity_archived','proximity_noVPD','joint_archived','joint_noVPD']:
            m=results[key]['natural']['croplands'][name];lo,hi=m['vs_openet']['ci95']
            cells.append(f"{m['macro_mae']:.3f} [{lo:.3f}, {hi:.3f}]")
        crop.append(' & '.join(cells)+r' \\')
    for name,lines in [('selective_natural',natural),('selective_faults',fault),('selective_crop',crop)]:
        (PAPER/f'table_{name}.tex').write_text('\n'.join(lines)+'\n')


def main():
    FIG.mkdir(parents=True,exist_ok=True)
    results=json.loads((DATA/'results.json').read_text())
    curves=matched_analysis()
    design();natural(results);faults(results);matched(curves);tables(results)
    receipt={'code_sha256':audit.sha(Path(__file__)),
      'protocol_sha256':audit.sha(ROOT/'docs/evaluation/ML_MATCHED_SELECTION_ANALYSIS.md'),
      'result_sha256':audit.sha(DATA/'results.json')}
    (DATA/'analysis_receipt.json').write_text(json.dumps(receipt,indent=2))
    print('Built four selective figures, three tables, and all matched-acceptance comparisons.')


if __name__=='__main__':main()
