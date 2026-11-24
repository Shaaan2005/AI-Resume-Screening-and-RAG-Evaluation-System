"""Rebuilds the ChromaDB resume index from the resumes/<CATEGORY>/*.pdf folders.

Usage:  python vector_store.py                 # rebuild the app's index (chromadb_data/)
        python vector_store.py chromadb_public # build a separate clean index, e.g. for a
                                               # public demo started with CHROMA_PATH=chromadb_public

This deletes and recreates the "resumes" collection, so any resumes added
through the web upload form will need to be uploaded again afterwards.
"""
import os

import chromadb

from model_loader import model
from resume_engine import extract_resume_text, chunk_text, analyze_resume

DB_PATH = "chromadb_data"
RESUMES_DIR = "resumes"


def build_index(db_path=DB_PATH, resumes_dir=RESUMES_DIR):
    """Chunks, embeds, and stores every resume PDF. Returns the collection."""
    client = chromadb.PersistentClient(path=db_path)

    try:
        client.delete_collection(name="resumes")
    except Exception:
        pass  # Collection didn't exist yet

    collection = client.create_collection(
        name="resumes",
        metadata={"hnsw:space": "cosine"}
    )

    for category in sorted(os.listdir(resumes_dir)):
        category_path = os.path.join(resumes_dir, category)
        if not os.path.isdir(category_path):
            continue

        for filename in sorted(os.listdir(category_path)):
            if not filename.endswith(".pdf"):
                continue

            file_path = os.path.join(category_path, filename)
            text = extract_resume_text(file_path)
            result = analyze_resume(file_path, category=category, text=text)

            chunks = chunk_text(text)
            if not chunks:
                continue

            collection.upsert(
                ids=[f"{filename}_chunk{idx}" for idx in range(len(chunks))],
                embeddings=model.encode(chunks).tolist(),  # one batch per resume
                documents=chunks,
                metadatas=[{
                    "resume": filename,
                    "chunk": idx,
                    "total_chunks": len(chunks),
                    "recommendation": result["recommendation"],
                    "skill_score": result["score"],
                    "category": category,
                    "source": "dataset",
                } for idx in range(len(chunks))]
            )

    return collection


if __name__ == "__main__":
    import sys
    collection = build_index(db_path=sys.argv[1] if len(sys.argv) > 1 else DB_PATH)
    print("All resumes chunked and stored in ChromaDB (cosine distance)")
    print("Total chunks:", collection.count())
