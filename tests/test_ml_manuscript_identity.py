"""Prevent regression of author identity and the retained visual evidence."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_current_manuscript_keeps_brand_email_and_original_figures():
    text = (ROOT / 'manuscript/arxiv/mlet_preprint.tex').read_text()
    assert 'mailto:m@irrigant.xyz' in text
    assert 'marcotrotta909@gmail.com' not in text
    assert re.search(r'\\includegraphics\[[^]]+\]\{irrigant_logo.png\}', text)
    first_page = text.split('\\section{')[0]
    assert 'Meetpal' not in first_page
    assert 'pdfauthor={Marco Trotta}' in text
    assert 'Meetpal S. Kukal' in text
    for stem in ['figure_1_evidence_paths', 'figure_2_phase2_models', 'figure_3_boii_feasibility',
                 'figure_4_native_grid', 'figure_5_support_tensor']:
        assert stem + '.pdf' in text


def test_published_pdf_matches_the_current_manuscript():
    current = ROOT / "output/pdf/mlet_preprint.pdf"
    published = ROOT / "output/pdf/mlet_arxiv_preprint.pdf"
    assert published.read_bytes() == current.read_bytes(), "The published paper is stale"


def test_references_follow_all_manuscript_sections():
    text = (ROOT / "manuscript/arxiv/mlet_preprint.tex").read_text()
    bibliography = text.index(r"\bibliography{references}")
    assert bibliography > text.rindex(r"\section{")
    assert bibliography > text.rindex(r"\end{figure}")
