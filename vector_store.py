from model_loader import model
import chromadb
import os
from resume_engine import extract_resume_text, chunk_text, analyze_resume

client = chromadb.PersistentClient(path="chromadb_data")

try:
    client.delete_collection(name="resumes")
except:
    pass

collection = client.create_collection(
    name="resumes",
    metadata={"hnsw:space": "cosine"}
)

for category in os.listdir("resumes"):
    category_path = os.path.join("resumes", category)
    if not os.path.isdir(category_path):
        continue

    for filename in os.listdir(category_path):
        if not filename.endswith(".pdf"):
            continue

        file_path = os.path.join(category_path, filename)
        text = extract_resume_text(file_path)
        result = analyze_resume(file_path, category=category)

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

print("All resumes chunked and stored in ChromaDB (cosine distance)")
print("Total chunks:", collection.count())