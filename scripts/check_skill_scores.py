import os, sys
# Run from anywhere: resolve imports and relative paths against the repo root.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from resume_engine import analyze_resume, chunk_text, extract_resume_text

for category in sorted(os.listdir("resumes")):
    category_path = os.path.join("resumes", category)
    if not os.path.isdir(category_path):
        continue
    for f in sorted(os.listdir(category_path)):
        if not f.endswith(".pdf"):
            continue
        file_path = os.path.join(category_path, f)
        r = analyze_resume(file_path, category=category)
        text = extract_resume_text(file_path)
        chunks = chunk_text(text)
        print(f'{r["score"]:3.1f}%  {r["recommendation"]:10s}  {len(chunks):2d} chunks  [{category}] {f}')