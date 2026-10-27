import hashlib, json
from pathlib import Path

root=Path(__file__).resolve().parents[2]/'outputs'/'strategy_a_equity'/'portfolio'
files=sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in {'.csv','.json','.md'})
out={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(root/'equity_portfolio_artifact_hashes.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2))
