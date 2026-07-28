import os
import json
import shutil

# Remove existing database to ensure a clean slate and prevent SQLite locks
if os.path.exists("chromadb_data"):
    shutil.rmtree("chromadb_data")

from fpdf import FPDF
from model_loader import model
from resume_engine import extract_resume_text, chunk_text, analyze_resume
from chroma_search import get_collection
from evaluate_ragas import get_heuristic_scorecard

# 1. Clean build database
print("1. Rebuilding ChromaDB collection from resumes folder...")
collection = get_collection()

total_resumes = 0
for category in os.listdir("resumes"):
    category_path = os.path.join("resumes", category)
    if not os.path.isdir(category_path):
        continue

    for filename in os.listdir(category_path):
        if not filename.endswith(".pdf"):
            continue

        file_path = os.path.join(category_path, filename)
        text = extract_resume_text(file_path)
        result = analyze_resume(file_path)

        chunks = chunk_text(text)
        chunk_ids = []
        chunk_embeddings = []
        chunk_docs = []
        chunk_metadatas = []

        for idx, chunk in enumerate(chunks):
            chunk_ids.append(f"{filename}_chunk{idx}")
            chunk_embeddings.append(model.encode(chunk).tolist())
            chunk_docs.append(chunk)
            chunk_metadatas.append({
                "resume": filename,
                "chunk": idx,
                "total_chunks": len(chunks),
                "recommendation": result["recommendation"],
                "skill_score": result["score"],
                "category": category
            })

        if chunk_ids:
            collection.upsert(
                ids=chunk_ids,
                embeddings=chunk_embeddings,
                documents=chunk_docs,
                metadatas=chunk_metadatas
            )
            total_resumes += 1

print(f"Database build complete. Ingested {total_resumes} resumes, total chunks: {collection.count()}")

# 2. Run heuristic evaluation and write scorecard cache
print("2. Running heuristic evaluation...")
results, avg_precision, avg_recall, avg_similarity = get_heuristic_scorecard()

print(f"Evaluation complete. Avg Precision: {avg_precision:.4f}, Avg Recall: {avg_recall:.4f}")

with open("evaluation_cache.json", "w") as f:
    json.dump({
        "results": results,
        "avg_precision": avg_precision,
        "avg_recall": avg_recall,
        "avg_similarity": avg_similarity
    }, f, indent=4)

print("Saved updated metrics to evaluation_cache.json successfully!")
