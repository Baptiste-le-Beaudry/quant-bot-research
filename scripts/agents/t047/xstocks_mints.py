"""Read decimals, Token-2022 scaled-UI multiplier and authority extensions for each quoted mint (public RPC, read-only)."""
import json, sys, time, requests
sys.path.insert(0, sys.argv[1])
paths = sys.argv[2:-1]
out_path = sys.argv[-1]
mints = {}
for p in paths:
    src = open(p, encoding="utf-8").read()
    ns = {}
    start = src.index("TOK = {")
    end = src.index("}\n", start) + 1
    exec(src[start:end], ns)
    fam = "backpack_or_other" if "bp" in p else "xstocks"
    for k, v in ns["TOK"].items():
        mints[v] = {"sym": k, "family": "xstocks" if v.startswith("Xs") else "backpack"}
for m, rec in mints.items():
    r = requests.post("https://api.mainnet-beta.solana.com", json={"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
                      "params": [m, {"encoding": "jsonParsed"}]}, timeout=20)
    info = r.json()["result"]["value"]["data"]["parsed"]["info"]
    rec["decimals"] = info["decimals"]
    rec["freezeAuthority"] = info.get("freezeAuthority")
    ext = {e["extension"]: e.get("state") for e in info.get("extensions", [])}
    rec["extensions"] = sorted(ext)
    s = ext.get("scaledUiAmountConfig")
    if s:
        now = time.time()
        eff = float(s["newMultiplier"]) if int(s.get("newMultiplierEffectiveTimestamp") or 0) <= now else float(s["multiplier"])
        rec["multiplier"] = eff
    else:
        rec["multiplier"] = 1.0
    print(rec["sym"], rec["family"], rec["decimals"], round(rec["multiplier"], 6), rec["extensions"], flush=True)
    time.sleep(1.0)
json.dump(mints, open(out_path, "w"), indent=1)
