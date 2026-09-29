"""
Checking Agent — backend.
Real document comparison using Gemini via Vertex AI. No mock data.
"""

import os
import secrets
import json
import re
import difflib
import time
import uuid
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from google.cloud import firestore
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_auth_requests

from flask import Flask, request, jsonify, send_from_directory, session
import pdfplumber
from id_validation import validate_id, mask_id
from google import genai
from google.genai import types

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "checking-agent-507207")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.7-flash")

# Max characters of extracted text sent to the model per document.
# Text beyond this is cut off, so fields that only appear later in a long
# policy can come back "missing". Raise it via env var, but check the model's
# input limit and any long-prompt pricing tier first.
MAX_DOC_CHARS = int(os.environ.get("MAX_DOC_CHARS", "15000"))

# Output budget per model call. On models that think, this includes thinking
# tokens, and the answer grows with the number of fields checked (roughly one
# JSON object per field), so it needs headroom for the larger checklists.
MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "8192"))

# How close two characters must be to count as one word when reading a PDF. The library default (3)
# ran the words of some PDFs together (a 950-word binder came out as 231 words: "NamedInsured: SmithR.wilson").
# 1.5 keeps words apart on those files and leaves other documents unchanged.
PDF_X_TOLERANCE = float(os.environ.get("PDF_X_TOLERANCE", "1.5"))

# "extract" (default): the model only reports what each document says and on which
# page, and this code decides match / mismatch / missing by fixed rules, so the same
# extraction always gives the same verdict. "judge": the earlier behaviour, where the
# model also decides the verdict. Switch back without a redeploy:
#   gcloud run services update checking-agent --region us-central1 --update-env-vars COMPARE_MODE=judge
COMPARE_MODE = "judge" if os.environ.get("COMPARE_MODE", "extract").strip().lower() == "judge" else "extract"

# Optional: limit how long the model thinks ("low", "medium" or "high"). Unset = model default.
# Lower levels are faster and cheaper, but re-run selftest.py before relying on them.
THINKING_LEVEL = os.environ.get("THINKING_LEVEL", "").strip().lower()

# selftest.py found the model occasionally reports nothing found anywhere, for every field,
# including a name and policy number that are in plain text on page 1 of both documents
# (about 1 run in 3 on a 74-page policy). Retried, the very same request came back correct.
# ANCHOR_KINDS name the field kinds (Named Insured, Policy Number) almost always present in a
# real insurance document, used below to tell this failure apart from a checklist that
# legitimately does not apply (e.g. Property fields on a GL policy), which looks similar but
# is not a failure. Set to 1 to try this request only once, no matter what comes back.
MAX_EXTRACT_ATTEMPTS = 1 if os.environ.get("DISABLE_BLACKOUT_RETRY") else \
    max(1, int(os.environ.get("MAX_EXTRACT_ATTEMPTS", "3")))
ANCHOR_KINDS = {"name", "id"}

# Firestore (optional): when set up, runs survive a redeploy instead of living only in
# this process' memory. If Firestore is not enabled, not yet created, or a call
# to it fails for any reason, every function below falls back to the old in-memory
# behaviour — the app never gets WORSE because of this, only better when it works.
# One-time setup (not code): enable the API, create the database, grant the service
# account access. See the project README for the exact commands.
FIRESTORE_ENABLED = os.environ.get("DISABLE_FIRESTORE", "").strip() != "1"
RUNS_COLLECTION = os.environ.get("FIRESTORE_RUNS_COLLECTION", "runs")
MAX_HISTORY = int(os.environ.get("MAX_HISTORY", "500"))

# Document diff (Documents tab). A line-level diff of the two documents' extracted
# text. Bounded on purpose: a 4-page binder against a 150-page policy would show as
# "almost everything is different", which is not a useful view and would be expensive
# to store — so a diff that differs by more than MAX_DIFF_DIFFERING_CHARS, or where
# either document has more than MAX_DIFF_LINES lines, is skipped entirely (None) and
# the frontend explains why instead of showing a wall of highlighted text.
MAX_DIFF_LINES = int(os.environ.get("MAX_DIFF_LINES", "4000"))
MAX_DIFF_DIFFERING_CHARS = int(os.environ.get("MAX_DIFF_DIFFERING_CHARS", "60000"))


def compute_doc_diff(text_left, text_right):
    """Line-level diff for the Documents tab, or None when not meaningful/too large."""
    def strip_markers(t):
        return re.sub(r"^\[Page \d+\]\n?", "", t, flags=re.M)
    left_lines = strip_markers(text_left).splitlines()
    right_lines = strip_markers(text_right).splitlines()
    if len(left_lines) > MAX_DIFF_LINES or len(right_lines) > MAX_DIFF_LINES:
        return None

    sm = difflib.SequenceMatcher(None, left_lines, right_lines, autojunk=False)
    chunks, differing_chars = [], 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            n = i2 - i1
            if n <= 4:
                chunks.append({"type": "equal", "left": left_lines[i1:i2]})
            else:
                chunks.append({"type": "equal_collapsed", "count": n})
            continue
        if tag == "replace":
            l, r = left_lines[i1:i2], right_lines[j1:j2]
            differing_chars += sum(len(x) for x in l) + sum(len(x) for x in r)
            chunks.append({"type": "replace", "left": l, "right": r})
        elif tag == "delete":
            l = left_lines[i1:i2]
            differing_chars += sum(len(x) for x in l)
            chunks.append({"type": "left_only", "left": l})
        elif tag == "insert":
            r = right_lines[j1:j2]
            differing_chars += sum(len(x) for x in r)
            chunks.append({"type": "right_only", "right": r})
        if differing_chars > MAX_DIFF_DIFFERING_CHARS:
            return None  # the documents are too different for a useful line-by-line view
    return chunks

# ---------------------------------------------------------------------------
# Identity and authorization (Cloud IAP)
#
# IMPORTANT: this code alone does not restrict who can reach the app. The actual
# gate is Cloud Run's invoker policy — only requests IAP has approved should ever
# reach this container. Until that is configured (see the project README), the
# Cloud Run URL is exactly as public as it always was; nothing below changes that.
# What this code does is find out WHO is calling, once IAP is in front of the app,
# and decide what they may see.
#
# Two ways an identity can arrive, in order of trust:
#  1. A signed IAP JWT (X-Goog-IAP-JWT-Assertion), verified against Google's public
#     signing keys. This cannot be forged even if a request somehow reaches the app
#     without going through IAP's own enforcement. Enabled by setting IAP_AUDIENCE
#     to the exact value IAP's settings page shows for this service.
#  2. The plain X-Goog-Authenticated-User-Email header IAP also sends. This is NOT
#     cryptographically verified — it is only trustworthy if Cloud Run's invoker is
#     locked down so nothing but IAP can ever reach the app. Used only as a fallback
#     while IAP_AUDIENCE is not yet set, so the feature is testable mid-setup.
# If IAP_AUDIENCE IS set and the JWT is missing or fails verification, identity is
# None — it never falls back to trusting the plain header in that case, since doing
# so would defeat the point of verifying at all.
IAP_AUDIENCE = os.environ.get("IAP_AUDIENCE", "").strip()
ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}

_iap_verify_request = None


def _iap_request():
    global _iap_verify_request
    if _iap_verify_request is None:
        _iap_verify_request = google_auth_requests.Request()
    return _iap_verify_request


def get_current_user():
    """The caller's email, or None if there is no trustworthy identity for this request.
    None must be treated as 'identity unknown' everywhere it is used — never as a
    specific person, and never given access an authenticated person would get."""
    jwt = request.headers.get("X-Goog-IAP-JWT-Assertion")
    if IAP_AUDIENCE:
        if not jwt:
            return None
        try:
            claims = google_id_token.verify_token(
                jwt, _iap_request(), audience=IAP_AUDIENCE,
                certs_url="https://www.gstatic.com/iap/verify/public_key")
            return claims.get("email")
        except Exception as e:
            _fs_warn("iap_jwt_verify_failed", error=str(e))
            return None  # fail closed: do not fall back to the unsigned header here
    raw = request.headers.get("X-Goog-Authenticated-User-Email", "")
    if raw.startswith("accounts.google.com:"):
        return raw.split(":", 1)[1]
    # No IAP identity at all (IAP not configured). This is the ONLY path that ever
    # consults a test-login session — it never runs once IAP_AUDIENCE is set above,
    # so turning on real IAP retires test users automatically.
    u = session.get("user")
    return u if u in TEST_USERS else None


def is_admin(email):
    return bool(email) and email.lower() in ADMIN_EMAILS


def require_admin():
    """(email, None) if the caller is an admin; otherwise (email, error_response)."""
    email = get_current_user()
    if not is_admin(email):
        return email, (jsonify({"error": "Admin access required."}), 403)
    return email, None


_firestore_client = None


def _db():
    """The Firestore client, created on first real use (not at import time)."""
    global _firestore_client
    if _firestore_client is None:
        _firestore_client = firestore.Client(project=PROJECT_ID)
    return _firestore_client


def _fs_warn(event, **extra):
    print(json.dumps({"severity": "WARNING", "message": event, **extra}), flush=True)


def save_run_to_firestore(run):
    """Best-effort. Never raises; a failure here must not affect the response to the user."""
    if not FIRESTORE_ENABLED:
        return False
    try:
        doc = dict(run)
        doc["ts"] = firestore.SERVER_TIMESTAMP
        _db().collection(RUNS_COLLECTION).document(run["id"]).set(doc)
        return True
    except Exception as e:
        _fs_warn("firestore_save_failed", run_id=run.get("id"), error=str(e))
        return False


def list_runs_from_firestore(limit=200):
    """None means "could not reach Firestore, use the in-memory fallback"; [] means
    "reached it, there is nothing there yet" (e.g. before the very first run)."""
    if not FIRESTORE_ENABLED:
        return None
    try:
        docs = (_db().collection(RUNS_COLLECTION)
                .order_by("ts", direction=firestore.Query.DESCENDING)
                .limit(limit).stream())
        out = []
        for d in docs:
            row = d.to_dict()
            row.pop("ts", None)
            out.append(row)
        return out
    except Exception as e:
        _fs_warn("firestore_list_failed", error=str(e))
        return None


def get_run_from_firestore(run_id):
    if not FIRESTORE_ENABLED:
        return None
    try:
        doc = _db().collection(RUNS_COLLECTION).document(run_id).get()
        if not doc.exists:
            return None
        row = doc.to_dict()
        row.pop("ts", None)
        return row
    except Exception as e:
        _fs_warn("firestore_get_failed", run_id=run_id, error=str(e))
        return None


def firestore_health():
    if not FIRESTORE_ENABLED:
        return "disabled"
    try:
        list(_db().collection(RUNS_COLLECTION).limit(1).stream())
        return "connected"
    except Exception as e:
        return "error: " + str(e)[:200]


def _rate(name):
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return None


# USD per 1M tokens. Deliberately not hardcoded: set them from the current
# Vertex AI pricing page for the model in MODEL_NAME, e.g.
#   gcloud run services update checking-agent --region us-central1 \
#     --update-env-vars PRICE_INPUT_PER_M=<rate>,PRICE_OUTPUT_PER_M=<rate>
# If either is unset, cost shows as "Rate not configured" in the UI.
PRICE_INPUT_PER_M = _rate("PRICE_INPUT_PER_M")
PRICE_OUTPUT_PER_M = _rate("PRICE_OUTPUT_PER_M")

client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)


def _thinking_config():
    if THINKING_LEVEL not in ("low", "medium", "high"):
        return None
    try:
        return types.ThinkingConfig(thinking_level=getattr(types.ThinkingLevel, THINKING_LEVEL.upper()))
    except Exception as e:  # older SDK without thinking levels: run with the model default
        print(json.dumps({"severity": "WARNING", "message": "THINKING_LEVEL ignored: " + str(e)}), flush=True)
        return None


THINKING_CONFIG = _thinking_config()

app = Flask(__name__, static_folder="static", static_url_path="")

# ---------------------------------------------------------------------------
# Test login — a stand-in for real SSO while IAP is being set up.
#
# NOT for real client data: it authenticates whoever knows a username/password
# pair, with no MFA, no password rotation, no lockout after repeated attempts.
# It gives REAL per-person identity for the people who use it — run ownership,
# admin gating, and "can this person open someone else's run" all work exactly
# as they do under IAP — but unlike IAP it does not stop someone from calling
# the API directly without ever logging in (they just get the same "no identity"
# view anyone gets today). It is automatically disabled the moment IAP_AUDIENCE
# is set, with no separate step to remember.
#
# Configure with, e.g.:
#   TEST_USERS="user1:pick-a-password,user2:pick-a-password,user3:pick-a-password,admin:pick-a-password"
#   ADMIN_EMAILS="admin"   (reuses the same allowlist real IAP uses — no separate admin list)
#   SESSION_SECRET_KEY="some-long-random-string"   (sessions survive redeploys only if this is set)
TEST_USERS = {}
for _pair in os.environ.get("TEST_USERS", "").split(","):
    if ":" in _pair:
        _u, _p = _pair.split(":", 1)
        _u = _u.strip()
        if _u:
            TEST_USERS[_u] = _p.strip()

app.secret_key = os.environ.get("SESSION_SECRET_KEY", "").strip() or None
if TEST_USERS and not app.secret_key:
    print(json.dumps({"severity": "WARNING", "message": "test_login_missing_secret_key",
                      "note": "Set SESSION_SECRET_KEY, or everyone is signed out on every redeploy"}), flush=True)
    app.secret_key = secrets.token_hex(32)  # works within this one running instance

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,     # Cloud Run is HTTPS-only
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)

# In-memory run history — resets on redeploy.
# Fine for MVP/demo; swap for Firestore before any real production use.
# Per-run usage is also written to Cloud Logging (see the run_usage log line).
RUN_HISTORY = []

MAX_FILE_SIZE_MB = 25
VALID_STATUSES = {"match", "mismatch", "missing"}

# ---------------------------------------------------------------------------
# Checklists
#
# The checklists a reviewer ticks in the UI are defined here, on the server.
# A run compares exactly the fields of the selected checklists (duplicates
# removed). `guidance` is optional text passed to the model once per selected
# checklist, for cases where a field is easy to misread.
# ---------------------------------------------------------------------------
CHECKLISTS = [
    {
        "id": "gl-declarations",
        "line": "general-liability",
        "lineLabel": "General liability",
        "name": "GL Declarations",
        "type": "Declarations",
        "desc": "Named insured, policy number, policy period and total premium",
        "guidance": (
            "Total Premium is the total for the whole policy including taxes and fees, "
            "as labelled 'Total'. Do not use the advance premium of a single coverage part "
            "or an endorsement premium."
        ),
        "fields": [
            {"section": "Declarations", "field": "Named Insured", "kind": "name"},
            {"section": "Declarations", "field": "Policy Number", "kind": "id"},
            {"section": "Declarations", "field": "Policy Effective Date", "kind": "date"},
            {"section": "Declarations", "field": "Policy Expiration Date", "kind": "date"},
            {"section": "Declarations", "field": "Total Premium", "kind": "money"},
        ],
    },
    {
        "id": "gl-limits",
        "line": "general-liability",
        "lineLabel": "General liability",
        "name": "GL Limits of Insurance",
        "type": "Limits",
        "desc": "The six limits on the Commercial General Liability coverage part declarations",
        "guidance": (
            "Read each limit from the Limits of Insurance schedule on the coverage part "
            "declarations, not from descriptive text in the coverage form. An amount may be "
            "printed inside underlined blanks with underscores between the digits "
            "(for example $_2_1_5_4_); report the digits without the underscores."
        ),
        "fields": [
            {"section": "Liability Limits", "field": "General Aggregate Limit (Other Than Products-Completed Operations)", "kind": "money"},
            {"section": "Liability Limits", "field": "Products-Completed Operations Aggregate Limit", "kind": "money"},
            {"section": "Liability Limits", "field": "Personal and Advertising Injury Limit", "kind": "money"},
            {"section": "Liability Limits", "field": "Each Occurrence Limit", "kind": "money"},
            {"section": "Liability Limits", "field": "Damage to Premises Rented to You Limit", "kind": "money"},
            {"section": "Liability Limits", "field": "Medical Expense Limit", "kind": "money"},
        ],
    },
    {
        "id": "property-coverage",
        "line": "commercial-property",
        "lineLabel": "Commercial property",
        "name": "Property Coverage",
        "type": "Coverage",
        "desc": "Building limit, deductible, coinsurance and valuation. For commercial property documents; not applicable to general liability",
        "guidance": "",
        "fields": [
            {"section": "Property Coverage", "field": "Building Limit", "kind": "money"},
            {"section": "Property Coverage", "field": "Deductible", "kind": "money"},
            {"section": "Property Coverage", "field": "Coinsurance %", "kind": "percent"},
            {"section": "Property Coverage", "field": "Valuation Method", "kind": "text"},
        ],
    },
    {
        "id": "policy-language",
        "line": "any",
        "lineLabel": "Any policy",
        "name": "Policy Language",
        "type": "Language",
        "desc": "Whether a waiver of subrogation clause or endorsement is present",
        "guidance": (
            "Report whether a waiver of subrogation (a waiver of transfer of rights of recovery "
            "against others to us) endorsement or clause is present, and its form name if given. "
            "The standard 'Transfer Of Rights Of Recovery Against Others To Us' condition in the "
            "coverage form is not a waiver."
        ),
        "fields": [
            {"section": "Policy Language", "field": "Waiver of Subrogation", "kind": "presence"},
        ],
    },
]
CHECKLISTS_BY_ID = {c["id"]: c for c in CHECKLISTS}


def public_checklist(c):
    return {
        "id": c["id"],
        "name": c["name"],
        "type": c["type"],
        "line": c.get("line", "any"),
        "lineLabel": c.get("lineLabel", "Any policy"),
        "desc": c["desc"],
        "guidance": c.get("guidance", ""),
        "status": "Active",
        "fieldCount": len(c["fields"]),
        "fields": c["fields"],
    }


def parse_selected(raw):
    """Turn the submitted checklist ids into checklist dicts, in catalog order."""
    try:
        ids = json.loads(raw or "[]")
    except json.JSONDecodeError:
        raise ValueError("The checklist selection was not valid.")
    if not isinstance(ids, list) or not ids:
        raise ValueError("Select at least one checklist.")
    if not all(isinstance(i, str) for i in ids):
        raise ValueError("The checklist selection was not valid.")
    unknown = [i for i in ids if i not in CHECKLISTS_BY_ID]
    if unknown:
        raise ValueError("Unknown checklist: " + ", ".join(unknown))
    wanted = set(ids)
    return [c for c in CHECKLISTS if c["id"] in wanted]


def resolve_fields(checklists):
    """Union of the checklists' fields, in order, without duplicates."""
    fields, seen = [], set()
    for c in checklists:
        for f in c["fields"]:
            key = (f["section"], f["field"])
            if key in seen:
                continue
            seen.add(key)
            fields.append(f)
    return fields


def extract_text(file_storage):
    """Extract text from an uploaded PDF. Raises ValueError on bad input."""
    filename = file_storage.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise ValueError(f"Unsupported file type for '{filename}'. Only PDF is supported in this MVP.")

    file_storage.stream.seek(0, os.SEEK_END)
    size_mb = file_storage.stream.tell() / (1024 * 1024)
    file_storage.stream.seek(0)
    if size_mb > MAX_FILE_SIZE_MB:
        raise ValueError(f"'{filename}' is {size_mb:.1f}MB — exceeds the {MAX_FILE_SIZE_MB}MB MVP limit.")

    try:
        with pdfplumber.open(file_storage.stream) as pdf:
            pages = [p.extract_text(x_tolerance=PDF_X_TOLERANCE) or "" for p in pdf.pages]
            text = "\n".join(pages).strip()
    except Exception as e:
        raise ValueError(f"Could not read '{filename}' as a PDF: {e}")

    if not text:
        raise ValueError(f"'{filename}' appears to have no extractable text (possibly a scanned image PDF — not supported in this MVP).")

    # Page markers let the model say where a value appears, and let it notice a
    # document that states the same field differently on different pages.
    marked = "\n".join(f"[Page {i}]\n{t}" for i, t in enumerate(pages, 1)).strip()
    return marked, len(pages)


def extract_usage(response):
    """Pull token counts from a google-genai response."""
    u = getattr(response, "usage_metadata", None)
    return {
        "input_tokens": getattr(u, "prompt_token_count", 0) or 0,
        "output_tokens": getattr(u, "candidates_token_count", 0) or 0,
        "thinking_tokens": getattr(u, "thoughts_token_count", 0) or 0,
    }


def estimate_cost(usage):
    """Estimated USD cost for one run, or None if rates are not configured."""
    if PRICE_INPUT_PER_M is None or PRICE_OUTPUT_PER_M is None:
        return None
    billed_out = usage["output_tokens"] + usage["thinking_tokens"]  # thinking bills as output
    return round(
        (usage["input_tokens"] * PRICE_INPUT_PER_M + billed_out * PRICE_OUTPUT_PER_M) / 1_000_000,
        6,
    )


DOC_TYPES = {"Binder", "Quote", "Policy", "Endorsement", "Renewal"}


def doc_refs(type_left, type_right):
    """How notes should name the two documents. Only known types are used, never free text from the form."""
    left = type_left if type_left in DOC_TYPES else None
    right = type_right if type_right in DOC_TYPES else None
    if left and right:
        if left == right:
            return f"the left {left}", f"the right {right}"
        return f"the {left}", f"the {right}"
    return "Document A", "Document B"


def build_prompt(text_left, text_right, checklists, fields, ref_left="Document A", ref_right="Document B"):
    field_list = "\n".join(f"- [{f['section']}] {f['field']}" for f in fields)
    guidance = "\n".join(f"- {c['name']}: {c['guidance']}" for c in checklists if c.get("guidance"))
    guidance_block = f"\nGuidance for specific fields:\n{guidance}\n" if guidance else ""
    return f"""You are comparing two insurance documents field by field.

DOCUMENT A (left / source):
---
{text_left[:MAX_DOC_CHARS]}
---

DOCUMENT B (right / target):
---
{text_right[:MAX_DOC_CHARS]}
---

For each field below, extract its value from BOTH documents and determine the comparison status.

Fields to check:
{field_list}
{guidance_block}
Respond with ONLY a JSON array, no other text, no markdown fences. Include exactly one element per field listed above. Each element:
{{
  "section": "<section name exactly as given>",
  "field": "<field name exactly as given>",
  "value_a": "<value found in Document A, or null if not found>",
  "value_b": "<value found in Document B, or null if not found>",
  "status": "match" | "mismatch" | "missing",
  "note": "<one short sentence explaining the result, especially for mismatch/missing>",
  "conflict": "<null, or one short sentence when this field has a different value elsewhere in the same document: name the pages and the other value>"
}}

Rules:
- "match": values are the same in substance (minor formatting differences like "$1,000" vs "$1,000.00" still count as match)
- "mismatch": both documents have a value for this field, but they differ
- "missing": the field could not be found in one or both documents
- Copy values as they are printed. Do not add currency symbols or separators that are not in the document.
- Be precise. Do not guess values that aren't actually present in the text.
- Pages in each document are marked [Page N]. If one document shows different values for the same field in different places, report the value from the earliest page and describe the other value in "conflict". Otherwise set "conflict" to null.
- A conflict is one thing stated two different ways, not two different things. For example, a premium before taxes and a total after taxes are different things.
- In "note" and "conflict", refer to Document A as "{ref_left}" and Document B as "{ref_right}".
"""


def _generate_json(prompt):
    """Send the prompt, return (parsed JSON array, usage_dict)."""
    cfg = {"temperature": 0.0, "max_output_tokens": MAX_OUTPUT_TOKENS}
    if THINKING_CONFIG is not None:
        cfg["thinking_config"] = THINKING_CONFIG
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(**cfg),
    )
    usage = extract_usage(response)
    raw = (response.text or "").strip()  # text can be None if the response was cut off
    # Strip markdown fences if the model added them despite instructions
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Model did not return valid JSON: {e}. Raw response: {raw[:500]}")
    if not isinstance(parsed, list):
        raise ValueError(f"Model returned JSON but not an array. Raw response: {raw[:500]}")
    return parsed, usage


def call_gemini_compare(text_left, text_right, checklists, fields, type_left=None, type_right=None):
    """Judge mode. Returns (parsed_results_list, usage_dict)."""
    ref_left, ref_right = doc_refs(type_left, type_right)
    return _generate_json(build_prompt(text_left, text_right, checklists, fields, ref_left, ref_right))


def _row_for(field, raw_results):
    """The model's raw row for one requested field, matched loosely like compare_extracted does."""
    for r in raw_results:
        if isinstance(r, dict) and str(r.get("field", "")).strip().lower() == field["field"].strip().lower():
            return r
    return None


def _is_blackout(fields, raw_results):
    """True when the fields nearly every real document states (a name, a policy number) all
    came back with nothing found in either document. A checklist that legitimately does not
    apply (Property fields on a GL policy) never trips this, because it has no anchor fields.
    """
    anchors = [f for f in fields if f.get("kind") in ANCHOR_KINDS]
    if not anchors:
        return False
    for f in anchors:
        row = _row_for(f, raw_results)
        if row is None:
            continue  # no value either way; still counts toward a blackout below (the model gave
                      # us nothing for this field, same as if it had returned an empty result)
        if _clean_side(row.get("a", row.get("values_a"))) or _clean_side(row.get("b", row.get("values_b"))):
            return False  # at least one anchor field has a value: a normal result
    return True


def call_gemini_extract(text_left, text_right, checklists, fields):
    """Extract mode. Returns (parsed_results_list, usage_dict)."""
    combined = {"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0}
    attempts = 0
    for attempts in range(1, MAX_EXTRACT_ATTEMPTS + 1):
        parsed, usage = _generate_json(build_extraction_prompt(text_left, text_right, checklists, fields))
        for k in combined:
            combined[k] += usage[k]
        if attempts >= MAX_EXTRACT_ATTEMPTS or not _is_blackout(fields, parsed):
            break
        print(json.dumps({"severity": "WARNING", "message": "blackout_retry",
                          "attempt": attempts, "max_attempts": MAX_EXTRACT_ATTEMPTS}), flush=True)
    combined["attempts"] = attempts
    return parsed, combined


def _val(x):
    """Display value for a field; em dash when absent."""
    if x is None or (isinstance(x, str) and not x.strip()):
        return "—"
    return str(x)


def _conflict(x):
    """Conflict note from the model, or None when there is none."""
    if x is None:
        return None
    s = str(x).strip()
    if not s or s.lower() in ("null", "none", "n/a", "no conflict", "no conflicts"):
        return None
    return s


def align_results(fields, raw_results):
    """One result row per requested field, in the requested order.

    Rows the model returned for fields that were not requested are dropped.
    A requested field the model skipped is reported as missing with an
    explicit note, so a short answer can never hide a field.
    Returns (results, count_of_fields_the_model_did_not_return).
    """
    by_full, by_field = {}, {}
    for r in raw_results:
        if not isinstance(r, dict):
            continue
        sec = str(r.get("section", "")).strip().lower()
        name = str(r.get("field", "")).strip().lower()
        by_full.setdefault((sec, name), r)
        by_field.setdefault(name, r)

    results, unreturned = [], 0
    for f in fields:
        r = by_full.get((f["section"].lower(), f["field"].lower())) or by_field.get(f["field"].lower())
        if r is None:
            unreturned += 1
            results.append({
                "sec": f["section"],
                "field": f["field"],
                "binder": "—",
                "policy": "—",
                "status": "missing",
                "absent": False,
                "note": "The model returned no result for this field. Check the source documents.",
                "conflict": None,
            })
            continue
        status = str(r.get("status", "missing")).strip().lower()
        if status not in VALID_STATUSES:
            status = "missing"
        binder, policy = _val(r.get("value_a")), _val(r.get("value_b"))
        # Nothing found in either document: there is nothing to compare, so it is
        # reported as absent from both and not counted as a discrepancy.
        absent = binder == "—" and policy == "—"
        if absent:
            status = "missing"
        results.append({
            "sec": f["section"],
            "field": f["field"],
            "binder": binder,
            "policy": policy,
            "status": status,
            "absent": absent,
            "note": r.get("note", ""),
            "conflict": _conflict(r.get("conflict")),
        })
    return results, unreturned


# ---------------------------------------------------------------------------
# Extract mode: the model reports what each document says (with page numbers);
# the comparison below is plain code, so it is repeatable and can be tested.
# ---------------------------------------------------------------------------
def build_extraction_prompt(text_left, text_right, checklists, fields):
    field_list = "\n".join(f"- [{f['section']}] {f['field']}" for f in fields)
    guidance = "\n".join(f"- {c['name']}: {c['guidance']}" for c in checklists if c.get("guidance"))
    guidance_block = f"\nGuidance for specific fields:\n{guidance}\n" if guidance else ""
    return f"""You are extracting field values from two insurance documents. Do not compare the documents; only report what each one says.

DOCUMENT A (left / source):
---
{text_left[:MAX_DOC_CHARS]}
---

DOCUMENT B (right / target):
---
{text_right[:MAX_DOC_CHARS]}
---

For each field below, list the values each document states for it, with the page number where each value appears.

Fields to extract:
{field_list}
{guidance_block}
Respond with ONLY a JSON array, no other text, no markdown fences. Include exactly one element per field listed above. Each element:
{{
  "section": "<section name exactly as given>",
  "field": "<field name exactly as given>",
  "a": [{{"value": "<value as printed>", "page": <page number>}}],
  "b": [{{"value": "<value as printed>", "page": <page number>}}]
}}

Rules:
- "a" is for Document A and "b" is for Document B. Use an empty list when a document does not state the field.
- Pages are marked [Page N] in the text. Give the page number as a whole number.
- Copy each value exactly as it is printed, without the field label. Do not add currency symbols or separators that are not in the document.
- Report the value for this field only. A premium before taxes and a total after taxes are different things.
- If the same value appears several times, list it once, with the earliest page. If a document states different values for the same field in different places, list each different value with its page. Give at most 5 values per document.
- Do not guess. Only report values that are actually present in the text.
"""


NEGATIVE_VALUES = {"none", "no", "n/a", "na", "nil", "null", "not applicable", "not present",
                   "not found", "not stated", "not specified", "not provided"}
TEXT_SYNONYMS = {"rc": "replacement cost", "rcv": "replacement cost", "replacement cost value": "replacement cost",
                 "acv": "actual cash value"}
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _alnum(text):
    return re.sub(r"[^0-9a-z]", "", text.lower())


def _number(text):
    """First number in the text as a canonical string ('3205' for '$ 3,205.00'), or None."""
    m = re.search(r"\d[\d,]*(?:\.\d+)?", text.replace("_", ""))
    if not m:
        return None
    try:
        return format(Decimal(m.group(0).replace(",", "")).normalize(), "f")
    except InvalidOperation:
        return None


def _date(text):
    """First date in the text as YYYY-MM-DD, or None. Numeric dates are read US style (month/day/year)."""
    t = text.replace("_", "")
    y = mo = d = None
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if m:
        y, mo, d = (int(g) for g in m.groups())
    else:
        m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", t)
        if m:
            mo, d, y = (int(g) for g in m.groups())
            y += 2000 if y < 100 else 0
        else:
            m = re.search(r"\b([A-Za-z]{3,9})\.? (\d{1,2})(?:st|nd|rd|th)?,? (\d{4})\b", t)
            if m and m.group(1).lower()[:3] in MONTHS:
                mo, d, y = MONTHS[m.group(1).lower()[:3]], int(m.group(2)), int(m.group(3))
            else:
                m = re.search(r"\b(\d{1,2}) ([A-Za-z]{3,9})\.?,? (\d{4})\b", t)
                if m and m.group(2).lower()[:3] in MONTHS:
                    d, mo, y = int(m.group(1)), MONTHS[m.group(2).lower()[:3]], int(m.group(3))
    if y is None:
        return None
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def normalize_value(kind, text):
    """Canonical form used to decide whether two values are the same, or None for an empty value."""
    s = str(text).strip()
    if not s or s.lower() in NEGATIVE_VALUES:
        return None
    if kind in ("money", "percent"):
        n = _number(s)
        if n is not None:
            return "num:" + n
    elif kind == "date":
        d = _date(s)
        if d:
            return "date:" + d
    elif kind == "presence":
        return "present"
    elif kind == "id":
        a = _alnum(s)
        if a:
            return "id:" + a.upper()
    elif kind == "name":
        a = _alnum(s)
        if a:
            return "name:" + a
    # text, or a value whose number/date could not be read
    t = re.sub(r"\s+", " ", re.sub(r"[^0-9a-z ]", " ", s.lower())).strip()
    t = TEXT_SYNONYMS.get(t, t)
    return "text:" + t if t else None


def _clean_side(items):
    """[(value, page)] from whatever the model returned for one document."""
    if isinstance(items, (str, int, float, dict)):
        items = [items]
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        v, p = (it.get("value"), it.get("page")) if isinstance(it, dict) else (it, None)
        if v is None or not str(v).strip() or str(v).strip().lower() in NEGATIVE_VALUES:
            continue
        try:
            p = int(float(p)) if p is not None and str(p).strip() != "" else None
        except (TypeError, ValueError):
            p = None
        out.append((str(v).strip(), p))
    return out


def _groups(kind, items):
    """Distinct values, earliest page first: [(key, value, page)]. Same value on several pages counts once."""
    found = {}
    for idx, (v, p) in enumerate(items):
        key = normalize_value(kind, v)
        if key is None:
            continue
        g = found.get(key)
        if g is None:
            found[key] = [v, p, idx]
        elif p is not None and (g[1] is None or p < g[1]):
            g[0], g[1] = v, p
    ordered = sorted(found.items(), key=lambda kv: (kv[1][1] is None, kv[1][1] or 0, kv[1][2]))
    return [(k, g[0], g[1]) for k, g in ordered]


def _cap(text):
    return text[:1].upper() + text[1:]


def _page(p):
    return f" (page {p})" if p is not None else ""


def _display_clean(kind, text):
    """A readable form of a raw extracted value. The model sometimes copies an
    underlined form blank verbatim ('$__________3_,2_0_5__.0_0__') instead of just the
    digits, even though comparisons already strip this for matching (normalize_value).
    This applies the same cleanup to what gets SHOWN — the cell, the mismatch note, the
    conflict note — so a correct 'Match' never displays looking like a broken value.
    Only touches money/percent fields; other kinds are shown exactly as extracted.
    """
    if kind in ("money", "percent") and "_" in text:
        cleaned = re.sub(r"\s+", " ", text.replace("_", "")).strip()
        return cleaned or text  # never show a blank if stripping somehow ate everything
    return text


# ---------------------------------------------------------------------------
# Identity check (v1, deliberately small): compares the ALREADY-DECIDED Named Insured
# value against an ID document's name, when one is provided. The ID is one more
# independent reference, not an authority — it never overrides the Binder/Policy
# comparison, it only adds one more fact for the reviewer. No OCR/extraction: the ID's
# data is supplied as JSON (a stand-in for whatever extraction step comes later).
# ID numbers are format-checked (id_validation.py) and Aadhaar is stored masked.
# ---------------------------------------------------------------------------
def parse_id_data(raw):
    """Best-effort JSON parse of the optional ID data. Never raises — a malformed or
    absent blob just means no identity check runs, it does not block the comparison."""
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    name = str(data.get("fullName") or data.get("name") or "").strip()
    if not name:
        return None
    id_type = str(data.get("idType") or "").strip()[:60] or None
    raw_number = str(data.get("idNumber") or "").strip()[:60] or None
    id_number, id_error = None, None
    if raw_number:
        # Format check only (never authenticity). The raw number is not kept past this
        # point: a valid Aadhaar is stored masked to its last 4 digits (UIDAI rule), and
        # an invalid number is dropped entirely rather than persisted.
        ok, _, err = validate_id(id_type or "", raw_number)
        if ok:
            id_number = mask_id(id_type or "", raw_number)
        else:
            id_error = err
    return {
        "name": name[:200],
        "idType": id_type,
        "idNumber": id_number,
        "idNumberError": id_error,
    }


def check_identity(results, id_data):
    """Compares the resolved Named Insured field against id_data['name'], if both
    exist. Returns a small dict describing the check, or None if not applicable —
    purely additive, never changes the Named Insured row itself."""
    if not id_data:
        return None
    named = next((r for r in results if r.get("field") == "Named Insured"), None)
    if named is None:
        return None
    if id_data.get("idNumberError"):
        # Invalid ID number: report it, but give no Matches/Does-not-match verdict —
        # a name check against an ID we can't trust would be false confidence.
        return {
            "idName": id_data["name"],
            "idType": id_data.get("idType"),
            "idNumber": None,
            "idNumberError": id_data["idNumberError"],
            "binderValue": named.get("binder"),
            "policyValue": named.get("policy"),
            "binderMatches": None,
            "policyMatches": None,
        }
    id_key = normalize_value("name", id_data["name"])
    if id_key is None:
        return None

    def side_matches(value):
        if value in (None, "—"):
            return None  # nothing on this side to compare
        return normalize_value("name", value) == id_key

    return {
        "idName": id_data["name"],
        "idType": id_data.get("idType"),
        "idNumber": id_data.get("idNumber"),
        "binderValue": named.get("binder"),
        "policyValue": named.get("policy"),
        "binderMatches": side_matches(named.get("binder")),
        "policyMatches": side_matches(named.get("policy")),
    }


def compare_field(kind, items_a, items_b, ref_a, ref_b):
    """Verdict for one field from what each document says. Pure function, no model involved."""
    ga, gb = _groups(kind, _clean_side(items_a)), _groups(kind, _clean_side(items_b))
    va, vb = (ga[0] if ga else None), (gb[0] if gb else None)
    # Clean the display text once here so the cell, every note below, and the conflict
    # listing all show the same readable value — not just the comparison logic.
    if va: va = (va[0], _display_clean(kind, va[1]), va[2])
    if vb: vb = (vb[0], _display_clean(kind, vb[1]), vb[2])
    row = {
        "binder": va[1] if va else "—", "policy": vb[1] if vb else "—",
        "pageA": va[2] if va else None, "pageB": vb[2] if vb else None,
        "absent": False, "note": "", "conflict": None,
    }
    if not va and not vb:
        row.update(status="missing", absent=True, note="Not found in either document.")
        return row
    if not va or not vb:
        ref_have, ref_lack = (ref_b, ref_a) if not va else (ref_a, ref_b)
        key, value, page = vb if not va else va
        row.update(status="missing", note=f"Found in {ref_have} only: {value}{_page(page)}. Not found in {ref_lack}.")
    elif kind == "presence" or va[0] == vb[0]:
        row["status"] = "match"
    else:
        row.update(status="mismatch",
                   note=f"{_cap(ref_a)} shows {va[1]}{_page(va[2])}; {ref_b} shows {vb[1]}{_page(vb[2])}.")
    # one document stating the same field two different ways
    parts = []
    for ref, groups in ((ref_a, ga), (ref_b, gb)):
        if len(groups) > 1 and kind != "presence":
            others = "; ".join(_display_clean(kind, v) + (f" on page {p}" if p is not None else "") for _, v, p in groups[1:])
            parts.append(f"{_cap(ref)} also shows {others}.")
    row["conflict"] = " ".join(parts) or None
    return row


def compare_extracted(fields, raw_results, ref_left, ref_right):
    """One result row per requested field. Returns (results, count_of_fields_the_model_did_not_return)."""
    by_full, by_field = {}, {}
    for r in raw_results:
        if not isinstance(r, dict):
            continue
        sec = str(r.get("section", "")).strip().lower()
        name = str(r.get("field", "")).strip().lower()
        by_full.setdefault((sec, name), r)
        by_field.setdefault(name, r)

    results, unreturned = [], 0
    for f in fields:
        r = by_full.get((f["section"].lower(), f["field"].lower())) or by_field.get(f["field"].lower())
        if r is None:
            unreturned += 1
            results.append({
                "sec": f["section"], "field": f["field"], "binder": "—", "policy": "—",
                "pageA": None, "pageB": None, "status": "missing", "absent": False,
                "note": "The model returned no result for this field. Check the source documents.",
                "conflict": None,
            })
            continue
        row = compare_field(f.get("kind", "text"),
                            r.get("a", r.get("values_a")), r.get("b", r.get("values_b")),
                            ref_left, ref_right)
        row.update(sec=f["section"], field=f["field"])
        results.append(row)
    return results, unreturned


@app.route("/api/compare", methods=["POST"])
def compare():
    try:
        t0 = time.time()

        if "fileLeft" not in request.files or "fileRight" not in request.files:
            return jsonify({"error": "Both fileLeft and fileRight are required."}), 400

        # Validate the selection before doing any expensive work.
        selected = parse_selected(request.form.get("checklists"))
        fields = resolve_fields(selected)

        file_left = request.files["fileLeft"]
        file_right = request.files["fileRight"]
        account = (request.form.get("account") or "").strip() or "Unnamed Account"
        type_left = request.form.get("typeLeft", "Document A")
        type_right = request.form.get("typeRight", "Document B")
        run_owner = (request.form.get("runOwner") or "").strip() or None
        owner_email = get_current_user()  # None if no verified identity yet — never blocks the run
        policy_effective = (request.form.get("policyEffective") or "").strip() or None
        id_data = parse_id_data(request.form.get("idData"))

        text_left, pages_left = extract_text(file_left)
        text_right, pages_right = extract_text(file_right)
        t_read = time.time()

        ref_left, ref_right = doc_refs(type_left, type_right)
        if COMPARE_MODE == "judge":
            raw_results, usage_raw = call_gemini_compare(text_left, text_right, selected, fields, type_left, type_right)
            results, unreturned = align_results(fields, raw_results)
        else:
            raw_results, usage_raw = call_gemini_extract(text_left, text_right, selected, fields)
            results, unreturned = compare_extracted(fields, raw_results, ref_left, ref_right)

        t_model = time.time()

        usage = {
            **usage_raw,
            # Sum only the three token fields by name — never sum(usage_raw.values())
            # blindly, since usage_raw can carry non-token metadata (e.g. "attempts" from
            # the retry logic) that must not be counted as tokens.
            "total_tokens": usage_raw["input_tokens"] + usage_raw["output_tokens"] + usage_raw["thinking_tokens"],
            "model": MODEL_NAME,
            "est_cost_usd": estimate_cost(usage_raw),
            "latency_s": round(time.time() - t0, 2),  # end to end
            "parse_s": round(t_read - t0, 2),          # reading the two PDFs
            "model_s": round(t_model - t_read, 2),     # the model call
            "field_count": len(fields),
            "mode": COMPARE_MODE,
            "attempts": usage_raw.get("attempts", 1),
            "unreturned": unreturned,
            "conflicts": sum(1 for r in results if r["conflict"]),
            "truncated": {
                "left": len(text_left) > MAX_DOC_CHARS,
                "right": len(text_right) > MAX_DOC_CHARS,
            },
        }

        absent = sum(1 for r in results if r["absent"])
        matched = sum(1 for r in results if r["status"] == "match")
        mismatched = sum(1 for r in results if r["status"] == "mismatch")
        # "missing" = present in one document only (or not returned by the model)
        missing = sum(1 for r in results if r["status"] == "missing" and not r["absent"])

        run_id = "r-" + uuid.uuid4().hex[:8]
        run = {
            "id": run_id,
            "account": account,
            "runOwner": run_owner,
            "ownerEmail": owner_email,
            "policyEffective": policy_effective,
            "docLeft": {"name": file_left.filename, "pages": pages_left, "type": type_left},
            "docRight": {"name": file_right.filename, "pages": pages_right, "type": type_right},
            "date": datetime.now(timezone.utc).strftime("%m/%d/%Y %I:%M %p UTC"),
            "checklists": [{"id": c["id"], "name": c["name"]} for c in selected],
            "fieldCount": len(fields),
            "docDiff": compute_doc_diff(text_left, text_right),
            "identityCheck": check_identity(results, id_data),
            "remarkVersions": [],  # appended to by POST .../remarks, never overwritten
            "approval": None,      # set once by POST .../approve
            "rejection": None,     # CURRENT rejection; cleared automatically the next time
                                    # remarks are saved (that IS "review has resumed")
            "rejectionHistory": [],  # every rejection ever issued, never cleared — the
                                      # permanent audit trail (Workflow History tab)
            "matched": matched,
            "mismatched": mismatched,
            "missing": missing,
            "absent": absent,
            "status": "Completed",
            "usage": usage,
            "results": results,
        }
        RUN_HISTORY.insert(0, run)
        del RUN_HISTORY[MAX_HISTORY:]  # bound memory use; Firestore (if set up) keeps the rest
        save_run_to_firestore(run)     # best-effort; the response to the user does not wait on this

        # One structured line per run. Cloud Run parses JSON on stdout into
        # jsonPayload, so this survives redeploys (RUN_HISTORY does not).
        # Filenames and account names are left out on purpose.
        print(json.dumps({
            "severity": "INFO",
            "message": "run_usage",
            "event": "run_usage",
            "run_id": run_id,
            "checklist_ids": [c["id"] for c in selected],
            "type_left": type_left,
            "type_right": type_right,
            "pages_left": pages_left,
            "pages_right": pages_right,
            "chars_left": len(text_left),
            "chars_right": len(text_right),
            **usage,
        }), flush=True)

        return jsonify(_with_status(run))

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Comparison failed: {e}"}), 500


@app.route("/api/checklists", methods=["GET"])
def checklists():
    return jsonify([public_checklist(c) for c in CHECKLISTS])


@app.route("/api/me", methods=["GET"])
def me():
    email = get_current_user()
    return jsonify({
        "email": email,
        "isAdmin": is_admin(email),
        "iapVerified": bool(IAP_AUDIENCE),
        "testLoginAvailable": bool(TEST_USERS) and not IAP_AUDIENCE,
    })


@app.route("/api/login", methods=["POST"])
def login():
    if not TEST_USERS or IAP_AUDIENCE:
        return jsonify({"error": "Test login is not enabled."}), 404
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    # constant-time comparison: do not let response timing hint at a correct username
    correct = TEST_USERS.get(username)
    if correct is not None and secrets.compare_digest(correct, password):
        session.clear()
        session.permanent = True
        session["user"] = username
        return jsonify({"email": username, "isAdmin": is_admin(username),
                        "iapVerified": False, "testLoginAvailable": True})
    return jsonify({"error": "Incorrect username or password."}), 401


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/admin/stats", methods=["GET"])
def admin_stats():
    _, err = require_admin()
    if err:
        return err
    rows = list_runs_from_firestore()
    if rows is None:
        rows = RUN_HISTORY
    else:
        known_ids = {r.get("id") for r in rows}
        rows = [r for r in RUN_HISTORY if r["id"] not in known_ids] + rows

    by_user, total_tokens, total_cost, costed_runs = {}, 0, 0.0, 0
    by_status = {"new": 0, "in_review": 0, "rejected": 0, "approved": 0}
    for r in rows:
        by_status[compute_workflow_status(r)] += 1
        u = r.get("usage") or {}
        owner = r.get("ownerEmail") or r.get("runOwner") or "Unknown"
        b = by_user.setdefault(owner, {"email": owner, "runs": 0, "tokens": 0, "cost": 0.0, "costedRuns": 0, "latencies": []})
        b["runs"] += 1
        tok = u.get("total_tokens") or 0
        b["tokens"] += tok
        total_tokens += tok
        cost = u.get("est_cost_usd")
        if cost is not None:
            b["cost"] += cost; b["costedRuns"] += 1
            total_cost += cost; costed_runs += 1
        lat = u.get("latency_s")
        if lat is not None:
            b["latencies"].append(lat)

    by_user_list = []
    for b in by_user.values():
        lat = b.pop("latencies")
        b["avgLatencyS"] = round(sum(lat) / len(lat), 1) if lat else None
        b["cost"] = round(b["cost"], 4) if b["costedRuns"] else None
        b.pop("costedRuns")
        by_user_list.append(b)
    by_user_list.sort(key=lambda x: x["runs"], reverse=True)

    return jsonify({
        "totalRuns": len(rows),
        "byStatus": by_status,
        "totalTokens": total_tokens,
        "totalCost": round(total_cost, 4) if costed_runs else None,
        "byUser": by_user_list,
    })


@app.route("/api/history", methods=["GET"])
def history():
    email = get_current_user()
    team_view = is_admin(email) and request.args.get("scope") == "team"
    rows = list_runs_from_firestore()
    if rows is None:  # Firestore not set up, or unreachable right now
        rows = RUN_HISTORY
    else:
        # A run whose save to Firestore failed exists only in this instance's memory.
        # Without this, it would be missing here even though the comparison succeeded
        # and was shown to the person who ran it.
        known_ids = {r.get("id") for r in rows}
        rows = [r for r in RUN_HISTORY if r["id"] not in known_ids] + rows
    if email and not team_view:
        rows = [r for r in rows if r.get("ownerEmail") == email]
    # email is None: no verified identity yet (IAP not configured), so there is nothing
    # to scope by — everyone sees everything, same as before this feature existed.
    # results/docDiff/remarkVersions can each be sizeable; the list view only needs
    # enough to render a row and the status badge, not the full run detail. Status is
    # computed from the FULL run (it depends on remarkVersions) before stripping it.
    summary = []
    for run in rows:
        row = {k: v for k, v in run.items() if k not in ("results", "docDiff", "remarkVersions", "rejectionHistory")}
        row["reviewStatus"] = compute_workflow_status(run)
        summary.append(row)
    return jsonify(summary)


def _find_run(run_id):
    """The full run dict from wherever it can be found (Firestore, then the in-memory
    fallback), or None. Shared by every endpoint that needs one run's full record."""
    run = get_run_from_firestore(run_id)
    if run is not None:
        return run
    for r in RUN_HISTORY:  # Firestore unavailable, or this run predates it being set up
        if r["id"] == run_id:
            return r
    return None


def _run_visible_to(run, email):
    """Whether the caller may see this run at all — same rule everywhere it matters."""
    owner = run.get("ownerEmail")
    return not (email and owner not in (None, email) and not is_admin(email))


def _apply_run_update(run_id, patch):
    """Best-effort partial update to a run — Firestore if reachable, and the in-memory
    fallback either way, so a save is never silently lost if Firestore is down."""
    try:
        _db().collection(RUNS_COLLECTION).document(run_id).update(patch)
    except Exception as e:
        _fs_warn("firestore_run_update_failed", run_id=run_id, error=str(e))
    for r in RUN_HISTORY:
        if r["id"] == run_id:
            r.update(patch)
            break


def compute_workflow_status(run):
    """The visible review stage — derived, never stored, so it can never drift out of
    sync with the approval/rejection/remarks data it is computed from.
      new        — created, nobody has started reviewing it yet
      in_review  — at least one remarks version has been saved
      rejected   — an admin rejected it, and no remarks have been saved since
      approved   — an admin approved it (terminal)
    """
    if run.get("approval"):
        return "approved"
    if run.get("rejection"):
        return "rejected"
    if run.get("remarkVersions"):
        return "in_review"
    return "new"


def _with_status(run):
    """A shallow copy with reviewStatus added — use this, not jsonify(run) directly,
    everywhere a full run goes back to the client."""
    return {**run, "reviewStatus": compute_workflow_status(run)}


def _discrepancy_keys(results):
    """Field keys ('section-field') that need review before a run can be approved:
    mismatches, and 'missing' fields genuinely present on only one side — not the
    'absent from both' bucket, which was never a real discrepancy to begin with."""
    return [f"{r['sec']}-{r['field']}" for r in results
            if r.get("status") == "mismatch" or (r.get("status") == "missing" and not r.get("absent"))]


@app.route("/api/history/<run_id>", methods=["GET"])
def history_detail(run_id):
    run = _find_run(run_id)
    if run is None:
        return jsonify({"error": "Run not found"}), 404
    # 404, not 403: do not confirm to a non-owner that this run id exists at all.
    if not _run_visible_to(run, get_current_user()):
        return jsonify({"error": "Run not found"}), 404
    return jsonify(_with_status(run))


@app.route("/api/history/<run_id>/remarks", methods=["POST"])
def save_remarks(run_id):
    email = get_current_user()
    run = _find_run(run_id)
    if run is None or not _run_visible_to(run, email):
        return jsonify({"error": "Run not found"}), 404
    if run.get("approval"):
        return jsonify({"error": "This run is already approved; remarks are locked."}), 409

    data = request.get_json(silent=True) or {}
    remarks = data.get("remarks")
    if not isinstance(remarks, dict):
        return jsonify({"error": "remarks must be an object"}), 400

    # Only accept known field keys, and cap text length — this is free-text a person
    # types, not something to trust blindly into storage.
    valid_keys = {f"{r['sec']}-{r['field']}" for r in run.get("results", [])}
    cleaned = {}
    for k, v in remarks.items():
        if k not in valid_keys or not isinstance(v, dict):
            continue
        cleaned[k] = {"text": str(v.get("text", ""))[:500], "resolved": bool(v.get("resolved"))}

    versions = run.get("remarkVersions") or []
    now = datetime.now(timezone.utc)
    entry = {
        "version": len(versions) + 1,
        "remarks": cleaned,
        "savedBy": email or "Unknown",
        "savedAt": now.strftime("%m/%d/%Y %I:%M %p UTC"),
        "savedAtIso": now.isoformat(),
    }
    versions = versions + [entry]
    patch = {"remarkVersions": versions}
    # Saving new remarks after a rejection IS "review has resumed" — clear it so the
    # run moves back to in_review automatically, no separate action needed.
    if run.get("rejection"):
        patch["rejection"] = None
    _apply_run_update(run_id, patch)
    updated = {**run, **patch}
    return jsonify({"remarkVersions": versions, "rejection": patch.get("rejection", run.get("rejection")),
                    "reviewStatus": compute_workflow_status(updated)})


@app.route("/api/history/<run_id>/approve", methods=["POST"])
def approve_run(run_id):
    _, err = require_admin()
    if err:
        return err
    run = _find_run(run_id)
    if run is None:
        return jsonify({"error": "Run not found"}), 404
    if run.get("approval"):
        return jsonify({"error": "Already approved."}), 409

    versions = run.get("remarkVersions") or []
    latest = versions[-1]["remarks"] if versions else {}
    needed = _discrepancy_keys(run.get("results", []))
    unresolved = [k for k in needed if not latest.get(k, {}).get("resolved")]
    if unresolved:
        return jsonify({
            "error": f"{len(unresolved)} flagged field(s) are not yet marked resolved.",
            "unresolvedFields": unresolved,
        }), 409

    _now = datetime.now(timezone.utc)
    approval = {
        "approvedBy": get_current_user() or "Unknown",
        "approvedAt": _now.strftime("%m/%d/%Y %I:%M %p UTC"),
        "approvedAtIso": _now.isoformat(),
    }
    _apply_run_update(run_id, {"approval": approval})
    return jsonify({"approval": approval, "reviewStatus": "approved"})


@app.route("/api/history/<run_id>/reject", methods=["POST"])
def reject_run(run_id):
    """Admin-only. No resolved-fields precondition — rejecting IS the "not ready yet"
    signal, unlike approve. Cleared automatically the next time remarks are saved.
    Can be reissued (a run can be rejected more than once across review cycles), but
    not once a run is already approved — that stays terminal.
    """
    _, err = require_admin()
    if err:
        return err
    run = _find_run(run_id)
    if run is None:
        return jsonify({"error": "Run not found"}), 404
    if run.get("approval"):
        return jsonify({"error": "This run is already approved and cannot be rejected."}), 409

    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason", "")).strip()[:500]
    _now = datetime.now(timezone.utc)
    rejection = {
        "rejectedBy": get_current_user() or "Unknown",
        "rejectedAt": _now.strftime("%m/%d/%Y %I:%M %p UTC"),
        "rejectedAtIso": _now.isoformat(),
        "reason": reason,
    }
    history = (run.get("rejectionHistory") or []) + [rejection]
    _apply_run_update(run_id, {"rejection": rejection, "rejectionHistory": history})
    return jsonify({"rejection": rejection, "rejectionHistory": history, "reviewStatus": "rejected"})


@app.route("/api/checklist-fields", methods=["GET"])
def checklist_fields():
    # Kept for older cached pages: every field of every checklist, flat.
    return jsonify(resolve_fields(CHECKLISTS))


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "model": MODEL_NAME,
        "project": PROJECT_ID,
        "max_doc_chars": MAX_DOC_CHARS,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "pdf_x_tolerance": PDF_X_TOLERANCE,
        "compare_mode": COMPARE_MODE,
        "max_extract_attempts": MAX_EXTRACT_ATTEMPTS,
        "firestore": firestore_health(),
        "iap_verification": "jwt" if IAP_AUDIENCE else "header-only (not cryptographically verified — see README)",
        "admin_emails_configured": len(ADMIN_EMAILS),
        "test_login_enabled": bool(TEST_USERS) and not IAP_AUDIENCE,
        "test_login_accounts": len(TEST_USERS),
        "thinking_level": THINKING_LEVEL if THINKING_CONFIG is not None else None,
        "checklists": len(CHECKLISTS),
        "pricing_configured": PRICE_INPUT_PER_M is not None and PRICE_OUTPUT_PER_M is not None,
    })


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)