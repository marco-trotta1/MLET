"""Acquire only the two checksum-verified archives used by the ML paper."""
from pathlib import Path
from fetch_data import load_manifest, _ensure, extract_zip

ROOT=Path(__file__).resolve().parents[1]


def main():
    manifest=load_manifest(str(ROOT/"data/manifest.json"))
    for key,subdir in [("openet_model_et","openet_phase2"),("flux_benchmark","flux_et")]:
        source=manifest["sources"][key]
        path=ROOT/"data/raw"/source["filename"]
        if not _ensure(source["url"],str(path),source["md5"],False):
            raise RuntimeError("Source checksum verification fails")
        extract_zip(str(path),str(ROOT/"data/raw"/subdir))


if __name__=="__main__":main()
