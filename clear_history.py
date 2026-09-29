#!/usr/bin/env python3
"""
Deletes every document in the Firestore "runs" collection — Checking Agent's saved
run history. Nothing else (checklists, code, settings) is touched.

Lists what it found first, asks you to type 'yes' before deleting anything.

Usage:
  pip3 install --user google-cloud-firestore
  python3 clear_history.py

If it fails to authenticate, run this once first, then try again:
  gcloud auth application-default login
"""
from google.cloud import firestore

PROJECT = "checking-agent-507207"


def main():
    db = firestore.Client(project=PROJECT)
    docs = list(db.collection("runs").stream())

    if not docs:
        print("No saved runs found in Firestore. Nothing to delete.")
        return

    print(f"Found {len(docs)} run(s) in Firestore:\n")
    for d in docs:
        data = d.to_dict()
        owner = data.get("ownerEmail") or data.get("runOwner") or "?"
        print(f"  {d.id}  —  account: {data.get('account','?')}  "
              f"date: {data.get('date','?')}  owner: {owner}")

    print()
    confirm = input(f"Delete all {len(docs)} run(s) above? This cannot be undone. Type 'yes' to proceed: ")
    if confirm.strip().lower() != "yes":
        print("Cancelled — nothing deleted.")
        return

    for d in docs:
        d.reference.delete()
        print(f"deleted: {d.id}")

    print(f"\nDone. Firestore run history is now empty ({len(docs)} run(s) removed).")


if __name__ == "__main__":
    main()
