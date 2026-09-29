#!/usr/bin/env python3
"""
Checking Agent self-test: runs document pairs whose correct answers are known and
prints PASS / FAIL for every field, plus whether the answers stay the same across repeats.

  python3 selftest.py https://checking-agent-857404761329.us-central1.run.app  ~/pdfs  3

Arguments: base URL, folder holding 1_Binder.pdf, 1_Binder_Changed.pdf and 1_Policy.pdf,
and how many times to repeat each pair (default 3). Standard library only.
Each run makes one real model call, so it costs a small amount of tokens.
"""
import json, os, re, sys, time, urllib.error, urllib.request, uuid

GL = ["gl-declarations", "gl-limits", "policy-language"]
LIMITS = {
    "General Aggregate Limit (Other Than Products-Completed Operations)": "2154",
    "Products-Completed Operations Aggregate Limit": "54",
    "Personal and Advertising Injury Limit": "4545",
    "Each Occurrence Limit": "4878",
    "Damage to Premises Rented to You Limit": "78784",
    "Medical Expense Limit": "5487",
}


def E(status, absent=False, conflict=None, left=None, right=None, right_digits=None):
    return dict(status=status, absent=absent, conflict=conflict, left=left, right=right, right_digits=right_digits)


def limits_only_in_policy():
    return {f: E("missing", right_digits=d) for f, d in LIMITS.items()}


# (title, left file, left type, right file, right type, checklists, expected rows)
PAIRS = [
    ("Changed binder vs Policy", "1_Binder_Changed.pdf", "Binder", "1_Policy.pdf", "Policy", GL, {
        "Named Insured": E("mismatch", conflict=True, left="roshni", right="wilson"),
        "Policy Number": E("mismatch", conflict=True, left="pol-370-33", right="pol-370-02"),
        "Policy Effective Date": E("mismatch", conflict=True, left="2027", right="2026"),
        "Policy Expiration Date": E("mismatch", conflict=True, left="2028", right="2027"),
        "Total Premium": E("match", conflict=False),
        **limits_only_in_policy(),
        "Waiver of Subrogation": E("missing", absent=True),
    }),
    ("Binder vs Changed binder", "1_Binder.pdf", "Binder", "1_Binder_Changed.pdf", "Binder", ["gl-declarations"], {
        "Named Insured": E("mismatch", conflict=True, left="wilson", right="roshni"),
        "Policy Number": E("mismatch", conflict=True, left="pol-370-02", right="pol-370-33"),
        "Policy Effective Date": E("mismatch", conflict=True, left="2026", right="2027"),
        "Policy Expiration Date": E("mismatch", conflict=True, left="2027", right="2028"),
        "Total Premium": E("match", conflict=False),
    }),
    ("Binder vs Policy", "1_Binder.pdf", "Binder", "1_Policy.pdf", "Policy", GL, {
        "Named Insured": E("match", conflict=False),
        "Policy Number": E("match", conflict=False),
        "Policy Effective Date": E("match", conflict=False),
        "Policy Expiration Date": E("match", conflict=False),
        "Total Premium": E("match", conflict=False),
        **limits_only_in_policy(),
        "Waiver of Subrogation": E("missing", absent=True),
    }),
]


def post_compare(base, folder, left, ltype, right, rtype, checklists):
    boundary = "----ca" + uuid.uuid4().hex
    parts = []
    def field(name, value):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    def file(name, fname):
        data = open(os.path.join(folder, fname), "rb").read()
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{fname}"\r\n'
                     f'Content-Type: application/pdf\r\n\r\n'.encode() + data + b"\r\n")
    file("fileLeft", left); file("fileRight", right)
    field("account", "selftest"); field("runOwner", "selftest")
    field("typeLeft", ltype); field("typeRight", rtype)
    field("checklists", json.dumps(checklists))
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(base + "/api/compare", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=330) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Server said {e.code}: {e.read().decode()[:400]}")


def check_row(field, row, exp):
    """List of problems (empty = pass)."""
    if row is None:
        return ["no row returned"]
    bad = []
    if row["status"] != exp["status"]: bad.append(f"status {row['status']!r}, expected {exp['status']!r}")
    if bool(row.get("absent")) != exp["absent"]: bad.append(f"absent={row.get('absent')}, expected {exp['absent']}")
    if exp["conflict"] is not None and bool(row.get("conflict")) != exp["conflict"]:
        bad.append(f"conflict {'reported' if row.get('conflict') else 'not reported'}, expected {'reported' if exp['conflict'] else 'none'}")
    if exp["left"] and exp["left"] not in row["binder"].lower(): bad.append(f"left value {row['binder']!r} lacks {exp['left']!r}")
    if exp["right"] and exp["right"] not in row["policy"].lower(): bad.append(f"right value {row['policy']!r} lacks {exp['right']!r}")
    if exp["right_digits"] and re.sub(r"\D", "", row["policy"]) != exp["right_digits"]:
        bad.append(f"right value {row['policy']!r}, expected digits {exp['right_digits']}")
    return bad


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    base, folder = sys.argv[1].rstrip("/"), os.path.expanduser(sys.argv[2])
    repeats = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    missing = [f for f in ("1_Binder.pdf", "1_Binder_Changed.pdf", "1_Policy.pdf") if not os.path.exists(os.path.join(folder, f))]
    if missing:
        raise SystemExit(f"Not found in {folder}: {', '.join(missing)}")

    failures, tokens, latencies, mode, retried_runs = 0, [], [], None, 0
    for title, left, ltype, right, rtype, lists, expected in PAIRS:
        print(f"\n=== {title}  ({len(expected)} fields, {repeats} run{'s' if repeats != 1 else ''}) ===")
        outcomes = {f: [] for f in expected}
        for i in range(1, repeats + 1):
            run = post_compare(base, folder, left, ltype, right, rtype, lists)
            rows = {r["field"]: r for r in run["results"]}
            u = run.get("usage") or {}
            mode = u.get("mode", mode); tokens.append(u.get("total_tokens", 0)); latencies.append(u.get("latency_s", 0))
            attempts = u.get("attempts", 1)
            problems = {f: check_row(f, rows.get(f), exp) for f, exp in expected.items()}
            failed = {f: p for f, p in problems.items() if p}
            retry_note = f", needed {attempts} model attempts (an earlier answer looked incomplete)" if attempts > 1 else ""
            print(f"  run {i}: {len(expected) - len(failed)}/{len(expected)} fields correct"
                  f"  ({u.get('total_tokens', '?')} tokens, {u.get('latency_s', '?')} s{retry_note})")
            for f, p in failed.items():
                print(f"    FAIL {f}: " + "; ".join(p))
            failures += len(failed)
            if attempts > 1:
                retried_runs += 1
            for f in expected:
                r = rows.get(f) or {}
                outcomes[f].append((r.get("status"), bool(r.get("absent")), bool(r.get("conflict")),
                                    re.sub(r"[^0-9a-z]", "", str(r.get("binder", "")).lower()),
                                    re.sub(r"[^0-9a-z]", "", str(r.get("policy", "")).lower())))
        changed = [f for f, o in outcomes.items() if len(set(o)) > 1]
        print("  stable across runs: " + ("yes, identical answers every time" if not changed
              else "NO, these fields changed between runs: " + ", ".join(changed)))
        failures += len(changed)

    n = len(tokens)
    print(f"\nMode: {mode}.  Average {sum(tokens) // max(n, 1)} tokens and {sum(latencies) / max(n, 1):.1f} s per run over {n} runs.")
    if retried_runs:
        print(f"{retried_runs} of {n} run(s) needed more than one model attempt — the server retried automatically. "
              f"This is expected sometimes; frequent retries are worth mentioning to the project owner.")
    print("RESULT: ALL CHECKS PASSED" if not failures else f"RESULT: {failures} problem(s) found")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
