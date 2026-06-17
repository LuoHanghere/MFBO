"""Build the no-film C3X fluid domain in SpaceClaim."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bofm.cad.run_spaceclaim import run_journal

root = Path(__file__).resolve().parents[1]
journal = root / "bofm" / "cad" / "journals" / "build_fluid_domain.py"
passage = root / "configs" / "c3x_passage.json"
out = root / "runs" / "fluid" / "c3x_fluid_nofilm.scdoc"

# Thin no-film validation slice: one baseline hole pitch (p/D=4, D=0.99 mm).
SPAN_MM = 3.96

print("building no-film fluid domain in SpaceClaim ...", flush=True)
res = run_journal(
    journal,
    out_scdoc=out,
    env_extra={"BOFM_PASSAGE_JSON": passage.resolve(), "BOFM_SPAN_MM": SPAN_MM},
    headless=True,
    timeout_s=600,
)

print("returncode:", res.returncode)
print("scdoc:", res.out_scdoc, "exists:", res.out_scdoc.exists() if res.out_scdoc else None)
print("status:")
print(res.status)
raise SystemExit(0 if res.ok else 1)
