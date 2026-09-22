from __future__ import annotations

import colorsys
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

REQUIRED_GROUPS = ("hair","visor_frame","visor_lens","face","eye_l","eye_r","brow_l","brow_r","mouth_upper","mouth_lower","mouth_inner","neck","jacket","underlayer","arm_l_upper","arm_l_fore","hand_l","arm_r_upper","arm_r_fore","hand_r","orb_shell","orb_core")
COLOR_GROUPS = {"hair":"silver","visor_lens":"cyan","eye_l":"blue","eye_r":"blue","face":"skin","neck":"skin","hand_l":"skin","hand_r":"skin","jacket":"neutral","underlayer":"neutral","orb_core":"cyan"}
HEX = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
NUMBERS = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

@dataclass
class LintReport:
    path: str
    findings: list[str]
    metrics: dict[str, Any]
    geometry_verified: bool
    @property
    def ok(self) -> bool: return not self.findings
    def as_dict(self) -> dict[str, Any]: return {"path":self.path,"ok":self.ok,"findings":self.findings,"metrics":self.metrics,"geometry_verified":self.geometry_verified}

def _local(tag: str) -> str: return tag.rsplit("}",1)[-1]

def _style_value(node: ET.Element, name: str) -> str | None:
    if name in node.attrib: return node.attrib[name]
    for part in node.attrib.get("style","").split(";"):
        if ":" in part:
            key,value=part.split(":",1)
            if key.strip()==name: return value.strip()
    return None

def _rgb(value: str | None):
    if not value or value in {"none","transparent","currentColor"}: return None
    match=HEX.match(value.strip())
    if not match: return None
    raw=match.group(1)
    if len(raw)==3: raw="".join(ch*2 for ch in raw)
    return tuple(int(raw[i:i+2],16)/255.0 for i in (0,2,4))

def _allowed(family: str, rgb) -> bool:
    h,s,v=colorsys.rgb_to_hsv(*rgb); deg=h*360.0
    if family=="silver": return s<=0.30 and v>=0.55
    if family=="cyan": return 165<=deg<=225 and s>=0.25 and v>=0.35
    if family=="blue": return 185<=deg<=245 and s>=0.25 and v>=0.30
    if family=="skin": return (deg<=55 or deg>=345) and 0.18<=s<=0.95 and 0.20<=v<=0.90
    if family=="neutral": return v<=0.38 or s<=0.18
    return True

def _viewbox(root):
    raw=root.attrib.get("viewBox")
    if not raw: return None
    vals=[float(x) for x in NUMBERS.findall(raw)]
    return tuple(vals[:4]) if len(vals)>=4 else None

def _inkscape_bounds(svg: Path):
    exe=shutil.which("inkscape")
    if not exe: raise RuntimeError("INKSCAPE_UNAVAILABLE")
    result=subprocess.run([exe,"--query-all",str(svg)],check=True,capture_output=True,text=True)
    out={}
    for line in result.stdout.splitlines():
        parts=line.split(",")
        if len(parts)==5:
            try: out[parts[0]]=tuple(float(x) for x in parts[1:5])
            except ValueError: pass
    return out

def lint_svg(path: Path, *, require_geometry: bool=True) -> LintReport:
    findings=[]
    try: tree=ET.parse(path)
    except (ET.ParseError,OSError) as exc: return LintReport(str(path),[f"SVG_PARSE_FAILED:{exc}"],{},False)
    root=tree.getroot(); ids={}; duplicates=set(); groups={}; path_count=0; node_count=0
    for node in root.iter():
        tag=_local(node.tag); node_id=node.attrib.get("id")
        if node_id:
            if node_id in ids: duplicates.add(node_id)
            ids[node_id]=node
        if tag=="g":
            if not node_id: findings.append("GROUP_WITHOUT_ID")
            else: groups[node_id]=node
        if tag=="image": findings.append("RASTER_IMAGE_ELEMENT")
        if tag=="text": findings.append("TEXT_OR_FONT_ELEMENT")
        for attr in ("href","{http://www.w3.org/1999/xlink}href"):
            href=node.attrib.get(attr)
            if href and not href.startswith("#"): findings.append(f"EXTERNAL_REFERENCE:{href}")
        if tag=="path":
            path_count+=1; d=(node.attrib.get("d") or "").strip()
            if not d: findings.append(f"EMPTY_PATH:{node_id or '<anonymous>'}")
            node_count+=len(NUMBERS.findall(d))
        transform=node.attrib.get("transform","").lower()
        if any(word in transform for word in ("nan","inf")): findings.append(f"NON_FINITE_TRANSFORM:{node_id or '<anonymous>'}")
    findings += [f"DUPLICATE_ID:{x}" for x in sorted(duplicates)]
    findings += [f"MISSING_GROUP:{name}" for name in REQUIRED_GROUPS if name not in groups]
    root_groups={child.attrib.get("id") for child in list(root) if _local(child.tag)=="g"}
    for name in sorted(root_groups):
        if name and name not in REQUIRED_GROUPS and not name.startswith("extra_"): findings.append(f"UNSCOPED_EXTRA_GROUP:{name}")
    palette={}
    for group_name,family in COLOR_GROUPS.items():
        group=groups.get(group_name)
        if group is None: continue
        colors=[]
        for node in group.iter():
            value=_style_value(node,"fill"); rgb=_rgb(value)
            if rgb is None: continue
            colors.append(str(value))
            if not _allowed(family,rgb): findings.append(f"PALETTE_OUTSIDE_LOCK:{group_name}:{value}")
        palette[group_name]=sorted(set(colors))
    geometry_verified=False; bbox={}
    if require_geometry:
        try: bbox=_inkscape_bounds(path); geometry_verified=True
        except Exception as exc: findings.append(f"GEOMETRY_UNVERIFIED:{exc}")
    viewbox=_viewbox(root)
    if geometry_verified and viewbox:
        vx,vy,vw,vh=viewbox; mx,my=vw*0.05,vh*0.05
        for name in REQUIRED_GROUPS:
            box=bbox.get(name)
            if not box: findings.append(f"NO_BOUNDS:{name}"); continue
            x,y,w,h=box
            if h<vh*0.005: findings.append(f"NOISE_BOUNDS:{name}")
            if x<vx-mx or y<vy-my or x+w>vx+vw+mx or y+h>vy+vh+my: findings.append(f"OUTSIDE_VIEWBOX:{name}")
    metrics={"path_count":path_count,"node_count":node_count,"file_size":path.stat().st_size if path.is_file() else 0,"palette":palette,"required_group_count":len(REQUIRED_GROUPS)}
    if path_count>1200: findings.append(f"PATH_BUDGET_EXCEEDED:{path_count}>1200")
    return LintReport(str(path),sorted(set(findings)),metrics,geometry_verified)

def render_layer_sheet(svg: Path, output: Path) -> None:
    exe=shutil.which("inkscape")
    if not exe: raise RuntimeError("INKSCAPE_UNAVAILABLE")
    root=ET.parse(svg).getroot()
    viewbox=root.attrib.get("viewBox") or f"0 0 {root.attrib.get('width','1000')} {root.attrib.get('height','1000')}"
    children="".join(ET.tostring(child,encoding="unicode") for child in list(root))
    items=list(REQUIRED_GROUPS)+["__composite__"]; tile_w,tile_h,cols=320,360,4; rows=(len(items)+cols-1)//cols; tiles=[]
    for index,name in enumerate(items):
        x=(index%cols)*tile_w; y=(index//cols)*tile_h
        body='<g>'+children+'</g>' if name=="__composite__" else f'<use href="#{name}"/>'
        tiles.append(f'<g transform="translate({x},{y})"><rect width="{tile_w}" height="{tile_h}" fill="#f4f6f8"/><svg x="8" y="8" width="{tile_w-16}" height="{tile_h-44}" viewBox="{viewbox}">{body}</svg><text x="12" y="{tile_h-12}" font-size="14" fill="#111">{name}</text></g>')
    sheet=f'<svg xmlns="http://www.w3.org/2000/svg" width="{cols*tile_w}" height="{rows*tile_h}" viewBox="0 0 {cols*tile_w} {rows*tile_h}"><defs>{children}</defs>'+''.join(tiles)+'</svg>'
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="van-layer-sheet-") as tmp:
        temp=Path(tmp)/"sheet.svg"; temp.write_text(sheet,encoding="utf-8")
        subprocess.run([exe,str(temp),f"--export-filename={output}","--export-type=png"],check=True,capture_output=True,text=True)
    if not output.is_file() or output.stat().st_size==0: raise RuntimeError("LAYER_SHEET_RENDER_FAILED")
