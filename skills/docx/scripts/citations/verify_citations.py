from pathlib import Path
import runpy

# Single source of truth shared with the standalone citation-verifier skill.
_CANONICAL = Path(__file__).resolve().parents[3] / "citation-verifier" / "scripts" / "verify_citations.py"
if __name__ == "__main__":
    runpy.run_path(str(_CANONICAL), run_name="__main__")
else:
    globals().update(runpy.run_path(str(_CANONICAL), run_name="office_agent_citation_verifier"))