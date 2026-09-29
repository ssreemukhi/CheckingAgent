"""
Checking Agent — Model Benchmark
Compares Gemini 3.1 Pro vs Gemini 3.1 Flash-Lite across the 20 planted-error
test cases, scoring accuracy against real ground truth and tracking cost/latency.
"""

import json
import time
import glob
import os

import vertexai
from vertexai.generative_models import GenerativeModel

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "checking-agent-507207")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")

vertexai.init(project=PROJECT_ID, location=LOCATION)

# Pricing: USD per 1M tokens (input / output), context <=200K.
# Verify against current Vertex AI pricing before citing these numbers formally —
# rates change, and these are the values known at build time.
MODEL_PRICING = {
    "gemini-3.1-pro-preview": {"input": 2.00, "output": 12.00},
    "gemini-3.1-flash-lite": {"input": 0.30, "output": 2.50},
}

MODELS_TO_TEST = list(MODEL_PRICING.keys())


def build_prompt(source_text, target_text, fields):
    field_list = "\n".join(f"- {f}" for f in fields)
    return f"""You are comparing two insurance documents field by field.

DOCUMENT A (source):
---
{source_text}
---

DOCUMENT B (target):
---
{target_text}
---

For each field below, determine whether the value matches between the two documents.

Fields to check:
{field_list}

Respond with ONLY a JSON array, no other text, no markdown fences. Each element:
{{"field": "<field name exactly as given>", "status": "matched" | "flagged"}}

"matched" = the value is the same in substance in both documents.
"flagged" = the value differs, or is missing/absent in one document but present in the other.
"""


def call_model(model_name, prompt):
    model = GenerativeModel(model_name)
    start = time.time()
    response = model.generate_content(
        prompt,
        generation_config={"temperature": 0.0, "max_output_tokens": 2048},
    )
    latency = time.time() - start

    raw = response.text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    usage = response.usage_metadata
    input_tokens = usage.prompt_token_count
    output_tokens = usage.candidates_token_count

    return raw, latency, input_tokens, output_tokens


def score_case(predicted, ground_truth):
    """Returns (correct_count, total_count, mismatches) for one case."""
    truth_map = {g["field"]: g["status"] for g in ground_truth}
    try:
        pred_list = json.loads(predicted)
        pred_map = {p["field"]: p["status"] for p in pred_list}
    except (json.JSONDecodeError, TypeError, KeyError):
        return 0, len(truth_map), [f"PARSE FAILURE — raw output: {predicted[:200]}"]

    correct = 0
    mismatches = []
    for field, true_status in truth_map.items():
        pred_status = pred_map.get(field, "MISSING FROM RESPONSE")
        if pred_status == true_status:
            correct += 1
        else:
            mismatches.append(f"{field}: expected '{true_status}', got '{pred_status}'")
    return correct, len(truth_map), mismatches


def run_benchmark():
    case_files = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "test_cases", "case_*.json")))
    if not case_files:
        case_files = sorted(glob.glob("test_cases/case_*.json"))

    if not case_files:
        print("No test case files found — check the test_cases/ folder path. Exiting.")
        return

    print(f"Found {len(case_files)} test cases.\n")

    results = {m: {"total_correct": 0, "total_fields": 0, "total_cost": 0.0,
                    "total_latency": 0.0, "case_results": [], "parse_failures": 0}
               for m in MODELS_TO_TEST}

    for case_path in case_files:
        with open(case_path) as f:
            case = json.load(f)

        prompt = build_prompt(case["source_text"], case["target_text"], case["fields"])

        for model_name in MODELS_TO_TEST:
            try:
                raw, latency, in_tok, out_tok = call_model(model_name, prompt)
            except Exception as e:
                print(f"  [{model_name}] case {case['case_id']}: API ERROR — {e}")
                results[model_name]["parse_failures"] += 1
                continue

            correct, total, mismatches = score_case(raw, case["ground_truth"])
            pricing = MODEL_PRICING[model_name]
            cost = (in_tok / 1_000_000 * pricing["input"]) + (out_tok / 1_000_000 * pricing["output"])

            r = results[model_name]
            r["total_correct"] += correct
            r["total_fields"] += total
            r["total_cost"] += cost
            r["total_latency"] += latency
            r["case_results"].append({
                "case_id": case["case_id"], "correct": correct, "total": total,
                "mismatches": mismatches, "latency_sec": round(latency, 2), "cost_usd": round(cost, 6),
            })
            if mismatches and "PARSE FAILURE" in str(mismatches):
                r["parse_failures"] += 1

            print(f"  [{model_name}] case {case['case_id']}: {correct}/{total} correct, "
                  f"{latency:.1f}s, ${cost:.6f}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for model_name in MODELS_TO_TEST:
        r = results[model_name]
        accuracy = (r["total_correct"] / r["total_fields"] * 100) if r["total_fields"] else 0
        avg_latency = r["total_latency"] / len(case_files)
        print(f"\n{model_name}")
        print(f"  Accuracy:       {r['total_correct']}/{r['total_fields']} fields ({accuracy:.1f}%)")
        print(f"  Total cost:     ${r['total_cost']:.6f}  (for all {len(case_files)} cases)")
        print(f"  Avg latency:    {avg_latency:.2f}s per comparison")
        print(f"  Parse failures: {r['parse_failures']}")

    with open("benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nFull results written to benchmark_results.json")


if __name__ == "__main__":
    run_benchmark()
