"""Refresh catalog/engines.json and catalog/engines.md; never reads upstream repositories."""

import ast
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
# Search aliases only, not claims of complete support for every related dialect.
ALIASES = {
    "artemis": ["Artemis", "Mikage"],
    "artemis-scp": ["Artemis SCP", "Artemis TXT", "SCP text"],
    "artemis-ast": ["Artemis AST", "Artemis astver", "AST text", "PFS AST"],
    "kirikiri": ["KiriKiri", "KAG", "吉里吉里", "TJS2"],
    "willplus": ["WillPlus", "AdvHD", "Pulltop"],
    "bgi": ["BGI", "Ethornell", "Buriko"],
    "catsystem2": ["CatSystem", "CatSystem2", "CST", "CSTL"],
    "favorite": ["Favorite", "FVP", "HCB"],
    "nscripter": ["NScripter", "ONScripter", "SAR", "NSA"],
    "siglus": ["Siglus", "SiglusEngine", "Scene.pck"],
    "renpy": ["Ren'Py", "RenPy", "RPA", "RPY"],
    "silky": ["Silky's", "Silky's Plus", "AI6WIN", "Silky_map"],
    "entis-gls": ["EntisGLS", "Entis GLS", "CSX", "SRCXML"],
    "escude": ["Escu:de", "Escude"],
    "exhibit": ["ExHibit", "RLD"],
    "arcgameengine": ["ArcGameEngine", "AGE"],
    "yaneurao": ["Yaneurao", "Itufuru"],
    "cyberworks": ["Cyberworks", "C,system"],
    "kaguya": ["KaGuYa", "Kaguya", "TBLSTR", "SCR-MESSAGE"],
    "rpgmaker": ["RPG Maker", "RPGMV", "RPGVX", "RPG VX Ace"],
    "nexas": ["NeXAS", "GIGA", "Nexas_asm"],
    "shsystem": ["SHSystem", "ShSystem"],
    "bluegale": ["BlueGale", "BlueGale_bdt"],
    "gxengine": ["GxEngine", "GxEngine_mwb"],
    "unity": ["UTAGE", "Unity UTAGE mono DAT"],
    "systemnnn": ["SystemNNN", "NNN", "SPT"],
    "system-epsilon": ["SYSTEM-ε", "System Epsilon"],
    "livemaker": ["LiveMaker", "CSV_Livemaker"],
    "yuka": ["YukaSystem", "YKC", "YKS"],
}


def main() -> None:
    engines = []
    for page in sorted((ROOT / "engines").glob("*.md")):
        text = page.read_text(encoding="utf-8")
        heading = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        title = heading.group(1).strip() if heading else page.stem
        # Subpages under engines/<id>/ belong to the same engine entry.
        sources = [text, *(sub.read_text(encoding="utf-8")
                           for sub in sorted((ROOT / "engines" / page.stem).rglob("*.md")))]
        references = {ref for source in sources
                      for ref in re.findall(r"python/(?:engines|archives)/[\w/.-]+\.py", source)}
        # A naming fallback records the actual shipped module, not a capability.
        for kind in ("engines", "archives"):
            candidate = f"python/{kind}/{page.stem.replace('-', '_')}.py"
            if (ROOT / candidate).is_file():
                references.add(candidate)
        apis = {}
        for name in sorted(references):
            path = ROOT / name
            if path.is_file():
                tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=name)
                apis[name] = [node.name for node in tree.body
                              if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                              and not node.name.startswith("_")]
        engines.append({
            "id": page.stem, "title": title, "aliases": ALIASES.get(page.stem, [page.stem]),
            "document": page.relative_to(ROOT).as_posix(),
            "python_references": sorted(references), "public_symbols": apis,
            "scope": "version/stage-limited references; read the engine page",
            "evidence": "per-module provenance and synthetic tests; not blanket game verification",
        })
    target = ROOT / "catalog" / "engines.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps({"schema": "galgame-engine-index/1", "count": len(engines),
                                 "engines": engines}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = ["# 引擎页目录", "",
            "由 `tools/update_engine_index.py` 生成，勿手改。先运行探测，再按候选引擎名、扩展名或魔数",
            "搜索 `engines/`；本表只用于浏览，不代表版本、阶段或游戏已验证支持。", "",
            "| 引擎/格式族 | 页面 |", "|---|---|"]
    for engine in engines:
        label = engine["title"].replace("|", "\\|").replace("\n", " ")
        rows.append(f"| {label} | [{engine['id']}](../{engine['document']}) |")
    (ROOT / "catalog" / "engines.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"Indexed {len(engines)} engine pages; no runtime capability inferred.")


if __name__ == "__main__":
    main()
