"""Deploys the app to a Hugging Face Space (Docker SDK).

One-time setup:
    1. Create a free account at https://huggingface.co
    2. Create a token with "write" access: https://huggingface.co/settings/tokens
    3. Log in on this machine:  hf auth login

Deploy (creates the Space on first run, updates it afterwards):
    python deploy/deploy_hf_space.py                      # -> <your-username>/ai-resume-screening
    python deploy/deploy_hf_space.py --space you/my-space

The Space builds the Dockerfile itself; the first build takes ~10-15 minutes.
"""
import os
import sys
import secrets
import argparse
import subprocess

from huggingface_hub import HfApi, CommitOperationAdd
from huggingface_hub.utils import filter_repo_objects

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPACE_README = os.path.join(ROOT, "deploy", "space_README.md")
DEFAULT_SPACE_NAME = "ai-resume-screening"

# Mirrors .dockerignore: local data, secrets, and files the app doesn't need.
IGNORE = [
    ".git/*", ".github/*", "*__pycache__*", ".pytest_cache/*", ".venv/*", "venv/*",
    "chromadb_data/*", "chroma_db/*", "benchmark/.index/*", "uploads/*",
    "users.db", ".secret_key", "recent_analyses.json", "test_cache.json", "*.log",
    "assets/*", "docs/*", "tests/*", "scripts/*", "scratch/*", "conversations/*",
    "deploy/*", "*.pptx", "presentation_preview.html", "scratch_chat_summary.txt", "~$*",
    "README.md",  # replaced by deploy/space_README.md (Spaces need a config header)
]


def tracked_files():
    """Files in the last commit: never uploads untracked or uncommitted local changes."""
    out = subprocess.run(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


def committed_bytes(path):
    """File content exactly as committed (keeps Unix line endings on Windows)."""
    return subprocess.run(["git", "show", f"HEAD:{path}"], cwd=ROOT,
                          capture_output=True, check=True).stdout


def main():
    parser = argparse.ArgumentParser(description="Deploy to a Hugging Face Space")
    parser.add_argument("--space", help="Space id, e.g. username/ai-resume-screening")
    parser.add_argument("--dry-run", action="store_true", help="list the files that would be uploaded and exit")
    args = parser.parse_args()

    files = list(filter_repo_objects(tracked_files(), ignore_patterns=IGNORE))
    if args.dry_run:
        for path in files:
            print(path)
        print("README.md  (from deploy/space_README.md)")
        print(f"{len(files) + 1} files")
        return

    api = HfApi()
    try:
        username = api.whoami()["name"]
    except Exception:
        sys.exit("Not logged in to Hugging Face. Run `hf auth login` with a write token first.")
    space_id = args.space or f"{username}/{DEFAULT_SPACE_NAME}"

    operations = [CommitOperationAdd(path_in_repo=p, path_or_fileobj=committed_bytes(p)) for p in files]
    operations.append(CommitOperationAdd(path_in_repo="README.md", path_or_fileobj=SPACE_README))
    if subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                      capture_output=True, text=True).stdout.strip():
        print("Note: you have uncommitted changes; only the last commit is deployed.")
    print(f"Uploading {len(operations)} files to Space {space_id} ...")

    created = not api.repo_exists(space_id, repo_type="space")
    api.create_repo(space_id, repo_type="space", space_sdk="docker", exist_ok=True)
    if created:
        # A stable session secret so logins survive container restarts
        api.add_space_secret(space_id, "FLASK_SECRET_KEY", secrets.token_hex(32))

    api.create_commit(
        repo_id=space_id, repo_type="space", operations=operations,
        commit_message="Deploy from GitHub repository",
    )

    owner, name = space_id.split("/")
    print("Done. The Space is now building (first build ~10-15 minutes).")
    print(f"  Space page: https://huggingface.co/spaces/{space_id}")
    print(f"  Direct app: https://{owner.lower()}-{name.lower().replace('_', '-')}.hf.space")


if __name__ == "__main__":
    main()
