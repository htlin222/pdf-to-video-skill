"""Validate a checked-in request before creating the runner matrix."""
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys


def valid_path(value, suffix):
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and path.suffix.lower() == suffix


def plan(path):
    data = json.loads(path.read_text())
    repo = data.get("input_repository", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("input_repository must be owner/repository")
    ref = data.get("input_ref", "")
    if not re.fullmatch(r"[a-f0-9]{40}", ref):
        raise ValueError("input_ref must be a full Git commit SHA")
    tag = data.get("release_tag", "")
    if tag and not re.fullmatch(r"pdf-video-[A-Za-z0-9._-]+", tag):
        raise ValueError("release_tag must start with pdf-video-")
    documents = data["documents"]
    if not isinstance(documents, list) or not 1 <= len(documents) <= 20:
        raise ValueError("Expected one to 20 documents")
    ids = set()
    for doc in documents:
        slug = doc["id"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", slug) or slug in ids:
            raise ValueError(f"Invalid or duplicate document id: {slug}")
        ids.add(slug)
        if not isinstance(doc["title"], str) or not doc["title"].strip():
            raise ValueError(f"{slug}: title is required")
        if not valid_path(doc["pdf"], ".pdf") or (doc.get("notes") and not valid_path(doc["notes"], ".json")):
            raise ValueError(f"{slug}: expected relative PDF and JSON paths")
    return {"matrix": json.dumps(list(range(len(documents)))), "repository": repo, "ref": ref, "tag": tag}


if __name__ == "__main__":
    values = plan(Path(sys.argv[1]))
    with open(os.environ["GITHUB_OUTPUT"], "a") as file:
        for key, value in values.items():
            file.write(f"{key}={value}\n")
