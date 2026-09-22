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
        f"Comments: {len(reader.pages)} pages; code and saved predictions in ancillary files.\n"
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
    scripts = ['fetch_data.py','fetch_ml_sources.py','ml_transfer_audit.py','ml_transfer_sensitivity.py',
      'ml_neural_sensitivity.py','ml_landcover_sensitivity.py','audit_ml_humidity.py','build_ml_paper_artifacts.py',
      'verify_ml_paper.py','ml_selective_residual.py','build_selective_artifacts.py','verify_selective_results.py']
    for name in scripts:
        path = repro/'scripts'/name; path.parent.mkdir(exist_ok=True);shutil.copy2(ROOT/'scripts'/name,path)
    for name in ['test_ml_transfer_audit.py','test_ml_selective_residual.py','test_baselines.py','test_build_dataset.py','test_evaluate.py']:
        path = repro/'tests'/name;path.parent.mkdir(exist_ok=True);shutil.copy2(ROOT/'tests'/name,path)
    for path in (ROOT/'docs/evaluation').glob('ML_*.md'):
        dest=repro/'docs/evaluation'/path.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
    for name in ['ml_transfer','ml_selective']:
        shutil.copytree(ROOT/'docs/results'/name,repro/'docs/results'/name,
                        ignore=shutil.ignore_patterns('partial_results.json','progress.json'))
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
