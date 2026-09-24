from __future__ import annotations

import colorsys
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml
from xml.etree import ElementTree as ET

REQUIRED_GROUPS = ("hair","visor_frame","visor_lens","face","eye_l","eye_r","brow_l","brow_r","mouth_upper","mouth_lower","mouth_inner","neck","jacket","underlayer","arm_l_upper","arm_l_fore","hand_l","arm_r_upper","arm_r_fore","hand_r","orb_shell","orb_core")
COLOR_GROUPS = {"hair":"silver","visor_lens":"cyan","eye_l":"blue","eye_r":"blue","face":"skin","neck":"skin","hand_l":"neutral","hand_r":"neutral","jacket":"neutral","underlayer":"neutral","orb_core":"cyan"}
FORBIDDEN_GROUPS = {"headband","extra_headband","aura","halo","background","workboard"}
HEX = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
RGB_FN = re.compile(r"^rgba?\(\s*([^)]*)\)$", re.IGNORECASE)
URL_REF = re.compile(r"^url\(\s*#([^)\s]+)\s*\)$")
NUMBERS = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
# CSS named colours an SVG tool can emit. A name outside this table is not guessed at: it is
# reported as UNVERIFIABLE_COLOR so an identity-locked group can never hide behind it.
NAMED = {"black":"#000000","white":"#ffffff","silver":"#c0c0c0","gray":"#808080","grey":"#808080","dimgray":"#696969","dimgrey":"#696969","darkgray":"#a9a9a9","darkgrey":"#a9a9a9","lightgray":"#d3d3d3","lightgrey":"#d3d3d3","gainsboro":"#dcdcdc","whitesmoke":"#f5f5f5","snow":"#fffafa","ghostwhite":"#f8f8ff","navy":"#000080","blue":"#0000ff","darkblue":"#00008b","midnightblue":"#191970","royalblue":"#4169e1","dodgerblue":"#1e90ff","deepskyblue":"#00bfff","skyblue":"#87ceeb","lightblue":"#add8e6","steelblue":"#4682b4","cyan":"#00ffff","aqua":"#00ffff","darkcyan":"#008b8b","teal":"#008080","turquoise":"#40e0d0","darkturquoise":"#00ced1","brown":"#a52a2a","saddlebrown":"#8b4513","sienna":"#a0522d","chocolate":"#d2691e","peru":"#cd853f","tan":"#d2b48c","burlywood":"#deb887","red":"#ff0000","green":"#008000","yellow":"#ffff00","orange":"#ffa500","purple":"#800080","magenta":"#ff00ff","fuchsia":"#ff00ff","pink":"#ffc0cb"}
# Values that paint nothing, or inherit a colour the linter checks where it is actually set.
NO_PAINT = {"none","transparent","inherit","currentcolor",""}
ROOT = Path(__file__).resolve().parents[2]
TOPOLOGY_BUDGETS = ROOT / "visual-authority" / "character-forge" / "00-source" / "production-v3" / "TOPOLOGY_BUDGETS.yaml"

def _topology_budgets() -> dict[str, Any]:
    if not TOPOLOGY_BUDGETS.is_file():
        return {"policy":{"hard_total_paths":1200,"hard_total_numeric_nodes":30000},"groups":{},"extra_group_policy":{"prefix":"extra_","default_max_paths":24,"default_max_numeric_nodes":900}}
    data = yaml.safe_load(TOPOLOGY_BUDGETS.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}

def _group_topology(group: ET.Element) -> tuple[int, int]:
    paths = 0
    nodes = 0
    for node in group.iter():
        if _local(node.tag) != "path":
            continue
        paths += 1
        nodes += len(NUMBERS.findall((node.attrib.get("d") or "").strip()))
    return paths, nodes

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
    """Parse one concrete colour. Returns None for no-paint values; raises ValueError when a
    value paints but cannot be parsed, so the caller can refuse rather than skip it."""
    raw=(value or "").strip()
    if raw.lower() in NO_PAINT: return None
    raw=NAMED.get(raw.lower(),raw)
    match=HEX.match(raw)
    if match:
        hexes=match.group(1)
        if len(hexes)==3: hexes="".join(ch*2 for ch in hexes)
        return tuple(int(hexes[i:i+2],16)/255.0 for i in (0,2,4))
    match=RGB_FN.match(raw)
    if match:
        parts=[p.strip() for p in match.group(1).replace("/"," ").replace(","," ").split()]
        if len(parts)>=3:
            channels=[]
            for part in parts[:3]:
                number=float(part.rstrip("%"))
                channels.append(number/100.0 if part.endswith("%") else number/255.0)
            if all(0.0<=c<=1.0 for c in channels): return tuple(channels)
    raise ValueError(raw)

def _paints(node: ET.Element, gradients: dict[str, list[str]]) -> list[str]:
    """Every fill colour a node paints with (§11.2 governs fills; strokes are line work),
    with gradient references resolved to their stops (following href chains)."""
    values=[]
    for name in ("fill","stop-color"):
        value=_style_value(node,name)
        if value is None: continue
        ref=URL_REF.match(value.strip())
        if ref:
            stops=gradients.get(ref.group(1))
            values.extend(stops if stops is not None else [f"url(#{ref.group(1)})"])
        else:
            values.append(value)
    return values

def _gradient_stops(root: ET.Element) -> dict[str, list[str]]:
    direct={}; links={}
    for node in root.iter():
        if _local(node.tag) not in {"linearGradient","radialGradient"}: continue
        gid=node.attrib.get("id")
        if not gid: continue
        direct[gid]=[_style_value(stop,"stop-color") or "#000000" for stop in node if _local(stop.tag)=="stop"]
        href=node.attrib.get("href") or node.attrib.get("{http://www.w3.org/1999/xlink}href") or ""
        if href.startswith("#"): links[gid]=href[1:]
    resolved={}
    for gid in direct:
        seen=set(); current=gid
        while not direct.get(current) and current in links and current not in seen:
            seen.add(current); current=links[current]
        resolved[gid]=direct.get(current) or []
    return resolved

def _allowed(family: str, rgb) -> bool:
    h,s,v=colorsys.rgb_to_hsv(*rgb); deg=h*360.0
    if family=="silver": return s<=0.30 and v>=0.55
    if family=="cyan": return 165<=deg<=225 and s>=0.25 and v>=0.35
    if family=="blue": return 185<=deg<=245 and s>=0.25 and v>=0.30
    if family=="skin": return 10<=deg<=45 and 0.38<=s<=0.78 and 0.45<=v<=0.82
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
        if name in FORBIDDEN_GROUPS: findings.append(f"FORBIDDEN_IDENTITY_GROUP:{name}")
        if name and name not in REQUIRED_GROUPS and not name.startswith("extra_"): findings.append(f"UNSCOPED_EXTRA_GROUP:{name}")
    palette={}; gradients=_gradient_stops(root)
    topology_cfg=_topology_budgets(); group_topology={}
    group_budgets=topology_cfg.get("groups") or {}; extra_policy=topology_cfg.get("extra_group_policy") or {}
    extra_prefix=str(extra_policy.get("prefix") or "extra_")
    for group_name,group in groups.items():
        paths,nodes=_group_topology(group); group_topology[group_name]={"paths":paths,"numeric_nodes":nodes}
        budget=group_budgets.get(group_name)
        if budget is None and group_name.startswith(extra_prefix):
            budget={"max_paths":int(extra_policy.get("default_max_paths",24)),"max_numeric_nodes":int(extra_policy.get("default_max_numeric_nodes",900))}
        if isinstance(budget,dict):
            max_paths=int(budget.get("max_paths",0) or 0); max_nodes=int(budget.get("max_numeric_nodes",0) or 0)
            if max_paths and paths>max_paths: findings.append(f"GROUP_PATH_BUDGET_EXCEEDED:{group_name}:{paths}>{max_paths}")
            if max_nodes and nodes>max_nodes: findings.append(f"GROUP_NODE_BUDGET_EXCEEDED:{group_name}:{nodes}>{max_nodes}")
    for group_name,family in COLOR_GROUPS.items():
        group=groups.get(group_name)
        if group is None: continue
        colors=[]
        for node in group.iter():
            for value in _paints(node,gradients):
                try: rgb=_rgb(value)
                except ValueError:
                    findings.append(f"UNVERIFIABLE_COLOR:{group_name}:{value}"); continue
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
    policy=topology_cfg.get("policy") or {}; hard_paths=int(policy.get("hard_total_paths",1200)); hard_nodes=int(policy.get("hard_total_numeric_nodes",30000))
    metrics={"path_count":path_count,"node_count":node_count,"file_size":path.stat().st_size if path.is_file() else 0,"palette":palette,"required_group_count":len(REQUIRED_GROUPS),"group_topology":group_topology,"hard_total_paths":hard_paths,"hard_total_numeric_nodes":hard_nodes}
    if path_count>hard_paths: findings.append(f"PATH_BUDGET_EXCEEDED:{path_count}>{hard_paths}")
    if node_count>hard_nodes: findings.append(f"NODE_BUDGET_EXCEEDED:{node_count}>{hard_nodes}")
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
