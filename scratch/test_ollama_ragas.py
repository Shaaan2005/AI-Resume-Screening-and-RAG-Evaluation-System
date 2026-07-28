import os
import pandas as pd
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import context_precision, context_recall
from langchain_ollama import ChatOllama
from langchain_community.embeddings import HuggingFaceEmbeddings
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.run_config import RunConfig

# Setup local models
print("Initializing Ollama & HuggingFace Embeddings...")
local_llm = ChatOllama(model="llama3", temperature=0.0)
local_embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

llm = LangchainLLMWrapper(local_llm)
embeddings = LangchainEmbeddingsWrapper(local_embeddings)

# Set ground_truth to represent the actual expected text instead of category label
data = {
    "question": ["Who is a C++ developer with multithreading experience?"],
    "contexts": [["Experienced in C++ and multithreading.", "Worked as a DevOps developer on Docker and Kubernetes."]],
    "ground_truth": ["We expect to retrieve a candidate with C++ development and multithreading experience."],
    "answer": ["We found candidates with C++ and multithreading experience."]
}
dataset = Dataset.from_dict(data)

print("Running test evaluation...")
run_config = RunConfig(max_workers=1, timeout=300)
result = evaluate(
    dataset,
    metrics=[context_precision, context_recall],
    llm=llm,
    embeddings=embeddings,
    run_config=run_config
)
print("\nSuccess! Raw DataFrame Results:")
print(result.to_pandas())
