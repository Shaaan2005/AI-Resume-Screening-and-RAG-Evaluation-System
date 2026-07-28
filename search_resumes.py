import chromadb
from sentence_transformers import SentenceTransformer

# Load AI model
model = SentenceTransformer("all-MiniLM-L6-v2")

# Connect to ChromaDB
client = chromadb.PersistentClient(
    path="chromadb_data"
)

collection = client.get_collection(
    name="resumes"
)

# Job Description
job_description = """
Looking for a Python Developer with Flask,
SQL, FastAPI, Machine Learning,
cloud deployment experience
"""

# Convert JD into embedding
query_embedding = model.encode(
    job_description
).tolist()

# Search ChromaDB
results = collection.query(
    query_embeddings=[query_embedding],
    n_results=5
)

print("\n===== TOP MATCHING CANDIDATES =====\n")

# Print complete raw result (important for understanding)
print("RAW CHROMADB RESULT:")
print(results)

print("\n===== RANKINGS =====\n")

for i in range(len(results["ids"][0])):

    print(f"Rank: {i+1}")

    print(
        f"Resume: {results['ids'][0][i]}"
    )

    # Distance may not exist in some configurationspy search_resumes.py
    if "distances" in results:
        print(
            f"Distance: {results['distances'][0][i]}"
        )

    print("-" * 40)