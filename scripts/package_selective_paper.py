"""Package the current paper and its saved scientific evidence."""
from pathlib import Path
import shutil
import tarfile
import zipfile
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def main():
    pdf = ROOT/'output/pdf/mlet_preprint.pdf'
    shutil.copy2(pdf, ROOT/'output/pdf/mlet_arxiv_preprint.pdf')
    tex = (ROOT/'manuscript/arxiv/mlet_preprint.tex').read_text()
    abstract = tex.split(r"\begin{quote}\small", 1)[1].split(r"\end{quote}", 1)[0]
    abstract = " ".join(abstract.replace(r"$\unit$", "mm/day").replace(r"\%", "%").split())
    reader = PdfReader(str(pdf))
    metadata = (
        f"Title: {reader.metadata.title}\nAuthor: {reader.metadata.author}\n"
        "Affiliation: Irrigant, Idaho, USA\nContact: m@irrigant.xyz\n"
        "Suggested primary category: cs.LG (Machine Learning)\n"
        f"Comments: {len(reader.pages)} pages.\n"
        "Main source file: mlet_preprint.tex\nLocally verified engine: Tectonic/XeTeX\n\n"
        f"Abstract:\n{abstract}\n\nSubmission status: Not submitted.\n"
        "The suggested category remains subject to arXiv moderation.\n"
        "The adapted graphics retain their separate CC BY-NC 4.0 attribution.\n"
    )
    (ROOT/'output/arxiv').mkdir(parents=True, exist_ok=True)
    (ROOT/'output/arxiv/arxiv_metadata.txt').write_text(metadata)
    repro = ROOT/'output/reproducibility'
    source = ROOT/'output/arxiv/mlet_preprint_source'
    # These are generated output directories, not source or experimental records.
    for path in [repro, source]:
        if path.exists(): shutil.rmtree(path)
        path.mkdir(parents=True)
    shutil.copytree(ROOT/'src/mlet', repro/'src/mlet', ignore=shutil.ignore_patterns('__pycache__'))
    (repro/'src/mlet/sources/__init__.py').write_text('"""Source adapters for the paper reproduction package."""\n')
    scripts = [
        'audit_code_provenance.py', 'ml_transfer_audit.recorded.py',
        'fetch_data.py', 'fetch_ml_sources.py', 'ml_transfer_audit.py',
        'ml_transfer_sensitivity.py', 'ml_neural_sensitivity.py',
        'ml_landcover_sensitivity.py', 'audit_ml_humidity.py',
        'build_ml_paper_artifacts.py', 'verify_ml_paper.py',
        'ml_selective_residual.py', 'build_selective_artifacts.py',
        'verify_selective_results.py', 'ml_tier1_gridmet.py',
        'ml_tier1_selective.py', 'ml_tier3_gridmet.py',
        'run_ml_tier1_selective_correction.py',
        'build_ml_tier1_selective_correction_artifacts.py',
        'run_ml_tier1_gridmet_stuck_correction.py',
        'analyze_ml_tier1_gridmet_stuck_correction.py',
        'acquire_gridmet_weather.py', 'build_ml_tier1_cohort.py',
        'build_ml_tier1_gridmet_cohort.py', 'build_ml_tier1_artifacts.py',
        'analyze_ml_tier1_gridmet.py', 'analyze_ml_tier1_gridmet_sensitivity.py',
        'run_ml_tier1_gridmet_sensitivity.py',
        'build_ml_tier1_gridmet_artifacts.py',
        'build_ml_tier1_gridmet_sensitivity_figure.py',
        'run_ml_tier1_cropland.py', 'analyze_ml_tier1_cropland.py',
        'build_ml_tier1_cropland_figure.py',
        'run_ml_tier1_natural_violations.py',
        'analyze_ml_tier1_natural_violations.py',
        'build_ml_tier1_natural_violations_figure.py',
        'analyze_ml_tier1_supportgain_directional_audit.py',
        'analyze_ml_tier1_supportgain_two_sided_audit.py',
        'build_ml_tier1_supportgain_directional_audit_figure.py',
        'run_ml_tier1_spatial_holdout.py',
        'run_ml_tier1_spatial_holdout_sensitivity.py',
        'build_ml_tier1_spatial_holdout_figure.py',
        'analyze_ml_tier3_gridmet.py',
        'analyze_ml_tier3_gridmet_risk_coverage.py',
        'build_ml_tier3_gridmet_risk_coverage_figure.py',
    ]
    for name in scripts:
        path = repro/'scripts'/name; path.parent.mkdir(exist_ok=True);shutil.copy2(ROOT/'scripts'/name,path)
    for name in [
        'test_ml_transfer_audit.py', 'test_ml_selective_residual.py',
        'test_baselines.py', 'test_build_dataset.py', 'test_evaluate.py',
        'test_ml_tier1_gridmet.py', 'test_ml_tier1_selective.py',
        'test_ml_tier3_gridmet.py', 'test_analyze_ml_tier1_gridmet.py',
        'test_analyze_ml_tier3_gridmet.py',
        'test_ml_tier1_gridmet_cohort.py',
        'test_ml_tier1_gridmet_artifacts.py',
        'test_ml_tier1_cohort.py', 'test_gridmet_weather.py',
    ]:
        path = repro/'tests'/name;path.parent.mkdir(exist_ok=True);shutil.copy2(ROOT/'tests'/name,path)
    for path in (ROOT/'docs/evaluation').glob('ML_*.md'):
        dest=repro/'docs/evaluation'/path.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
    for name in [
        'ml_transfer', 'ml_selective', 'ml_tier1',
        'ml_tier1_gridmet', 'ml_tier1_gridmet_10member',
        'ml_tier1_gridmet_sensitivity', 'ml_tier1_gridmet_stuck_corrected',
        'ml_tier1_selective',
        'ml_tier1_selective_corrected',
        'ml_tier1_cropland', 'ml_tier3_gridmet',
        'ml_tier1_natural_violations',
        'ml_tier1_supportgain_directional_audit',
        'ml_tier1_spatial_holdout',
        'ml_tier1_spatial_holdout_sensitivity',
        'ml_tier3_gridmet_risk_coverage',
    ]:
        shutil.copytree(ROOT/'docs/results'/name,repro/'docs/results'/name,
                        ignore=shutil.ignore_patterns(
                            'partial_results.json', 'progress.json',
                            'threshold_5km', 'threshold_10km', 'threshold_25km',
                        ))
    shutil.copy2(ROOT/'docs/results/phase2_openet_independent_reproduction_receipt.json',repro/'docs/results/')
    (repro/'data').mkdir();shutil.copy2(ROOT/'data/manifest.json',repro/'data/manifest.json')
    shutil.copy2(ROOT/'manuscript/REPRODUCIBILITY.md',repro/'README.md')
    shutil.copy2(ROOT/'requirements-paper.lock',repro/'requirements-paper.lock')
    shutil.copytree(ROOT/'manuscript/licenses',repro/'licenses')
    (repro/'pytest.ini').write_text('[pytest]\npythonpath = src\ntestpaths = tests\n')
    # Static original graphics are included so their preservation check is self-contained.
    figure_root = repro/'manuscript/arxiv/figures';figure_root.mkdir(parents=True)
    for name in ['figure_1_evidence_paths','figure_2_phase2_models','figure_3_boii_feasibility','figure_4_native_grid','figure_5_support_tensor']:
        shutil.copy2(ROOT/f'manuscript/arxiv/figures/{name}.pdf',figure_root/f'{name}.pdf')
    for suffix in ('pdf', 'png'):
        for stem in [
            'figure_18_tier1_cropland_training',
            'figure_19_tier1_natural_violations',
            'figure_20_tier1_gridmet_10member_weather_fault_response',
            'figure_21_tier1_supportgain_directional_audit',
            'figure_22_tier1_spatial_holdout',
            'figure_23_tier1_spatial_holdout_sensitivity',
        ]:
            name = f'{stem}.{suffix}'
            shutil.copy2(ROOT/'manuscript/arxiv/figures'/name, figure_root/name)
    shutil.copytree(
        ROOT/'manuscript/arxiv/figures/tier1_selective_corrected',
        figure_root/'tier1_selective_corrected',
    )
    (repro/'manuscript/assets').mkdir();shutil.copy2(ROOT/'manuscript/assets/irrigant_logo.png',repro/'manuscript/assets/irrigant_logo.png')
    from verify_arxiv_manuscript import _source_manifest
    for name,path in _source_manifest().items():
        dest=source/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
    archive=ROOT/'output/arxiv/mlet_preprint_source.tar.gz'
    with tarfile.open(archive,'w:gz',compresslevel=9) as tar:
        for path in sorted(source.rglob('*')):
            if path.is_file():tar.add(path,arcname=str(path.relative_to(source)))
    with zipfile.ZipFile(ROOT/'output/arxiv/mlet_reproducibility.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as zip_file:
        for path in sorted(repro.rglob('*')):
            if path.is_file():zip_file.write(path,'mlet_reproducibility/'+str(path.relative_to(repro)))
    print(f'Packaged source: {archive.stat().st_size} bytes')


if __name__ == '__main__':main()
