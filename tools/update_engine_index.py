"""Refresh the local engine-page index; never reads upstream repositories."""

import ast
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- ENGINE_INDEX_START -->"
END = "<!-- ENGINE_INDEX_END -->"
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
        references = set(re.findall(r"python/(?:engines|archives)/[\w/.-]+\.py", text))
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
    skill = ROOT / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    if text.count(START) != 1 or text.count(END) != 1:
        raise SystemExit("SKILL.md must contain one engine index marker pair")
    rows = ["| 引擎/格式族 | 页面 |", "|---|---|"]
    for engine in engines:
        label = engine["title"].replace("|", "\\|").replace("\n", " ")
        rows.append(f"| {label} | [{engine['id']}]({engine['document']}) |")
    before, rest = text.split(START, 1)
    _, after = rest.split(END, 1)
    skill.write_text(before + START + "\n" + "\n".join(rows) + "\n" + END + after, encoding="utf-8")
    print(f"Indexed {len(engines)} engine pages; no runtime capability inferred.")


if __name__ == "__main__":
    main()
