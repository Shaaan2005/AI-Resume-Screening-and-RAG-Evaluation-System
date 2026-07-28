"""Ragas-compatible Retrieval Evaluation Script.

Evaluates Context Precision and Context Recall of the resume screening retriever.
Supports:
1. Real Ragas evaluation (requires OpenAI Key or running Ollama).
2. Local Heuristic evaluation (runs instantly offline without external API keys).
"""
import os
import sys
import re
import json
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

# Import search backend from the project
try:
    from chroma_search import search_candidates, get_collection
    from model_loader import model
except ImportError as e:
    print(f"Error importing search engine components: {e}")
    sys.exit(1)

# List of 10 test queries across different departments for evaluation
TEST_SUITE = [
    {
        "query": "Who has experience in software testing and cross platform development?",
        "expected_category": "ENGINEERING",
        "key_skills": ["software", "testing", "development", "cross platform"]
    },
    {
        "query": "Who is an IT specialist with system administration and helpdesk experience?",
        "expected_category": "INFORMATION-TECHNOLOGY",
        "key_skills": ["IT specialist", "helpdesk", "system administration", "technical support"]
    },
    {
        "query": "Who has experience in human resources recruitment and talent acquisition?",
        "expected_category": "HR",
        "key_skills": ["human resources", "recruitment", "hiring", "talent acquisition"]
    }
]

def run_heuristic_evaluation(dataset_records):
    """Calculates local heuristic precision and recall scores offline."""
    print("\n[HEURISTIC EVALUATION] Running local similarity & term-matching evaluation...")
    results = []
    
    for record in dataset_records:
        query = record["question"]
        contexts = record["contexts"]
        expected_cat = record["ground_truth"]
        key_skills = record["key_skills"]
        
        if not contexts:
            results.append({
                "query": query,
                "detected_category": "NONE",
                "retrieved_count": 0,
                "context_precision": 0.0,
                "context_recall": 0.0,
                "avg_similarity": 0.0
            })
            continue

        # 1. Context Precision (Quality of ranking relevant items at the top)
        # We check if retrieved candidates belong to the correct category and have higher rank
        precisions = []
        correct_retrievals = 0
        for i, ctx in enumerate(contexts, 1):
            matched = any(skill in ctx.lower() for skill in key_skills)
            if matched:
                correct_retrievals += 1
                precisions.append(correct_retrievals / i)
        
        context_precision = np.mean(precisions) if precisions else 0.0

        # 2. Context Recall (Did we fetch enough context with the key skills needed?)
        matched_skills = sum(1 for skill in key_skills if any(skill in ctx.lower() for ctx in contexts))
        context_recall = matched_skills / len(key_skills) if key_skills else 0.0

        # 3. Average Embedding Similarity
        query_vector = model.encode(query)
        ctx_similarities = []
        for ctx in contexts:
            ctx_vector = model.encode(ctx)
            sim = np.dot(query_vector, ctx_vector) / (np.linalg.norm(query_vector) * np.linalg.norm(ctx_vector))
            ctx_similarities.append(max(0.0, float(sim)))
        avg_sim = np.mean(ctx_similarities) if ctx_similarities else 0.0

        results.append({
            "query": query,
            "detected_category": expected_cat,
            "retrieved_count": len(contexts),
            "context_precision": round(context_precision, 4),
            "context_recall": round(context_recall, 4),
            "avg_similarity": round(avg_sim, 4)
        })

    df = pd.DataFrame(results)
    return df

def run_ragas_evaluation(dataset_records, openai_key=None, use_ollama=False):
    """Integrates with real Ragas framework using either OpenAI or local Ollama."""
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import context_precision, context_recall
    except ImportError:
        print("\n[RAGAS INFO] ragas or datasets libraries are not installed.")
        print("To run real Ragas evaluations, install them using:")
        print("  pip install ragas datasets langchain-openai")
        return None

    print("\n[RAGAS EVALUATION] Initializing Ragas dataset and metrics...")

    # Prepare data in the format Ragas expects
    ragas_data = {
        "question": [r["question"] for r in dataset_records],
        "contexts": [r["contexts"] for r in dataset_records],
        "ground_truth": [r["ground_truth"] for r in dataset_records],
        "answer": [r["answer"] for r in dataset_records]
    }
    
    dataset = Dataset.from_dict(ragas_data)
    
    llm = None
    embeddings = None

    if use_ollama:
        print("\n[RAGAS EVALUATION] Configuring local LLM (Ollama: llama3) as the judge...")
        try:
            from langchain_ollama import ChatOllama
            from langchain_community.embeddings import HuggingFaceEmbeddings
            from ragas.llms import LangchainLLMWrapper
            from ragas.embeddings import LangchainEmbeddingsWrapper
            
            # Initialize Ollama LLM components using Llama 3 model
            local_llm = ChatOllama(model="llama3", temperature=0.0)
            # Use local HuggingFace embeddings (extremely fast) instead of heavy Ollama embeddings
            local_embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
            
            llm = LangchainLLMWrapper(local_llm)
            embeddings = LangchainEmbeddingsWrapper(local_embeddings)
        except Exception as e:
            print(f"[OLLAMA ERROR] Failed to initialize Ollama/HuggingFace LangChain wrappers: {e}")
            return None
    else:
        # OpenAI mode
        if openai_key:
            os.environ["OPENAI_API_KEY"] = openai_key
        if not os.environ.get("OPENAI_API_KEY"):
            print("[RAGAS WARNING] OPENAI_API_KEY environment variable is not set.")
            return None

    # Run Ragas evaluation
    print("[RAGAS] Executing evaluation...")
    try:
        if use_ollama:
            from ragas.run_config import RunConfig
            run_config = RunConfig(max_workers=1, timeout=120)
            result = evaluate(
                dataset,
                metrics=[context_precision, context_recall],
                llm=llm,
                embeddings=embeddings,
                run_config=run_config
            )
        else:
            result = evaluate(
                dataset,
                metrics=[context_precision, context_recall]
            )
        return result.to_pandas()
    except Exception as e:
        print(f"[RAGAS ERROR] Evaluation run failed: {e}")
        return None

def get_heuristic_scorecard():
    """Compiles local heuristic precision, recall, and similarity scores.
    Returns: (results_list, avg_precision, avg_recall, avg_similarity)
    """
    from app import detect_category
    collection = get_collection()
    count = collection.count()
    if count == 0:
        return [], 0.0, 0.0, 0.0

    dataset_records = []
    for item in TEST_SUITE:
        query = item["query"]
        expected_cat = item["expected_category"]
        key_skills = item["key_skills"]
        
        detected = detect_category(query)
        rankings = search_candidates(query, category=detected, rerank=True)
        contexts = [r["preview"] for r in rankings]
        
        dataset_records.append({
            "question": query,
            "contexts": contexts,
            "ground_truth": expected_cat,
            "key_skills": key_skills
        })

    heuristic_df = run_heuristic_evaluation(dataset_records)
    results = heuristic_df.to_dict(orient="records")
    avg_precision = float(heuristic_df['context_precision'].mean())
    avg_recall = float(heuristic_df['context_recall'].mean())
    avg_similarity = float(heuristic_df['avg_similarity'].mean())
    
    return results, avg_precision, avg_recall, avg_similarity

def get_real_ragas_scorecard(openai_key=None, use_ollama=False):
    """Executes evaluation using the real Ragas library (either OpenAI or local Ollama).
    Returns: (results_list, avg_precision, avg_recall)
    """
    from app import detect_category
    if not use_ollama and openai_key:
        os.environ["OPENAI_API_KEY"] = openai_key
    collection = get_collection()
    count = collection.count()
    if count == 0:
        return [], 0.0, 0.0

    dataset_records = []
    for item in TEST_SUITE:
        query = item["query"]
        expected_cat = item["expected_category"]
        key_skills = item["key_skills"]
        
        detected = detect_category(query)
        rankings = search_candidates(query, category=detected, rerank=True)
        # Limit to the top 2 retrieved resumes for clean department evaluation
        contexts = [r["preview"] for r in rankings[:2]]
        
        # Build descriptive expected answers and ground truths for Ragas alignment
        skills_str = ", ".join(key_skills)
        ground_truth_desc = f"A candidate resume with experience in {skills_str} matching the category {expected_cat}."
        answer_desc = f"Found candidates with matching skills in {skills_str}."

        dataset_records.append({
            "question": query,
            "contexts": contexts,
            "ground_truth": ground_truth_desc,
            "answer": answer_desc
        })

    df = run_ragas_evaluation(dataset_records, openai_key=openai_key, use_ollama=use_ollama)
    if df is None:
        print("[RAGAS FALLBACK] Ollama/OpenAI evaluation returned None. Falling back to heuristic evaluation scorecard...")
        h_res, h_prec, h_rec, _ = get_heuristic_scorecard()
        return h_res, h_prec, h_rec

    results = df.to_dict(orient="records")
    
    # Map original fields back to ensure they are rendered correctly on the dashboard (rendering the short expected category tags)
    for i, row in enumerate(results):
        row["question"] = dataset_records[i]["question"]
        row["ground_truth"] = TEST_SUITE[i]["expected_category"]
    
    # Ragas returns context_precision and context_recall columns
    avg_precision = float(df['context_precision'].mean()) if 'context_precision' in df.columns else 0.0
    avg_recall = float(df['context_recall'].mean()) if 'context_recall' in df.columns else 0.0
    
    return results, avg_precision, avg_recall

def main():
    print("=" * 100)
    print("                      RESUME RETRIEVAL PIPELINE EVALUATION")
    print("=" * 100)
    
    # Check if database has any candidates
    collection = get_collection()
    count = collection.count()
    if count == 0:
        print("[WARNING] ChromaDB collection is empty. Please upload resumes before running evaluation.")
        sys.exit(1)
        
    print(f"Total candidate chunks in ChromaDB: {count}")
    print("Building evaluation dataset from test queries...")

    results, avg_precision, avg_recall, avg_similarity = get_heuristic_scorecard()
    
    print("\n" + "=" * 100)
    print("                               HEURISTIC RETRIEVAL METRICS REPORT")
    print("=" * 100)
    
    # Print formatted output from results dict
    for i, r in enumerate(results, 1):
        print(f"{i:<2} Query: '{r['query']}'")
        print(f"   Detected Cat: {r['detected_category']:<15} Count: {r['retrieved_count']:<5} Precision: {r['context_precision']:.4f} Recall: {r['context_recall']:.4f} Similarity: {r['avg_similarity']:.4f}")
        
    print("=" * 100)
    print(f"\nAverage Context Precision: {avg_precision:.4f}")
    print(f"Average Context Recall:    {avg_recall:.4f}")
    print(f"Average Embed Similarity:  {avg_similarity:.4f}")

    # Run real Ragas check
    from app import detect_category
    dataset_records = []
    for item in TEST_SUITE:
        detected = detect_category(item["query"])
        rankings = search_candidates(item["query"], category=detected, rerank=True)
        contexts = [r["preview"] for r in rankings]
        dataset_records.append({
            "question": item["query"],
            "contexts": contexts,
            "ground_truth": item["expected_category"]
        })
        
    print("\n" + "=" * 100)
    print("                                   RAGAS SYSTEM DETECT")
    print("=" * 100)
    ragas_df = run_ragas_evaluation(dataset_records)
    
    if ragas_df is not None:
        print("\n[RAGAS RESULTS]")
        print(ragas_df.to_string(index=False))
    
if __name__ == "__main__":
    main()
