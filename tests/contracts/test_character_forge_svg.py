from pathlib import Path
from tools.character_forge.svg_lint import REQUIRED_GROUPS, lint_svg

def _svg(groups,hair="#eeeeee"):
    body=[]
    for name in groups:
        fill=hair if name=="hair" else "#00bcd4" if name in {"visor_lens","orb_core"} else "#2196f3" if name in {"eye_l","eye_r"} else "#8d5524" if name in {"face","neck","hand_l","hand_r"} else "#222222"
        body.append(f'<g id="{name}"><path fill="{fill}" d="M 10 10 L 90 10 L 90 90 Z"/></g>')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'+"".join(body)+"</svg>"

def test_svg_lint_accepts_structural_contract_without_geometry_host(tmp_path:Path):
    path=tmp_path/"van.svg"; path.write_text(_svg(list(REQUIRED_GROUPS)),encoding="utf-8"); report=lint_svg(path,require_geometry=False); assert report.ok,report.findings

def test_svg_lint_rejects_missing_required_group(tmp_path:Path):
    path=tmp_path/"van.svg"; path.write_text(_svg(list(REQUIRED_GROUPS)[1:]),encoding="utf-8"); assert "MISSING_GROUP:hair" in lint_svg(path,require_geometry=False).findings

def test_svg_lint_rejects_dark_hair(tmp_path:Path):
    path=tmp_path/"van.svg"; path.write_text(_svg(list(REQUIRED_GROUPS),hair="#111111"),encoding="utf-8"); assert any(x.startswith("PALETTE_OUTSIDE_LOCK:hair:") for x in lint_svg(path,require_geometry=False).findings)

def test_svg_lint_rejects_raster_and_text(tmp_path:Path):
    path=tmp_path/"van.svg"; path.write_text(_svg(list(REQUIRED_GROUPS)).replace("</svg>",'<image href="data:image/png;base64,AA=="/><text>x</text></svg>'),encoding="utf-8"); report=lint_svg(path,require_geometry=False); assert "RASTER_IMAGE_ELEMENT" in report.findings and "TEXT_OR_FONT_ELEMENT" in report.findings
