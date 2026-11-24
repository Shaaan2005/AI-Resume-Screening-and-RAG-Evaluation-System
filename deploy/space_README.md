---
title: AI Resume Screening
emoji: 🎯
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
short_description: Semantic resume search with a retrieval benchmark
---

# AI Resume Screening

Search 242 sample resumes across 24 job categories by describing the role you need, or upload a resume to score it against a job description.

- **Search:** dense semantic retrieval (`all-mpnet-base-v2` + ChromaDB) with automatic department detection.
- **Evaluation page:** a reproducible benchmark of 8 ranking setups on 48 labeled queries.

**Demo notes**
- Register any username to try it. Accounts are reset when the Space restarts.
- Uploaded resumes are scored and then deleted. They are never added to the shared search index.
- The free Space sleeps after a period without visitors; the first visit after that takes a minute or two to wake it.

Source code, benchmark details, and setup instructions: [GitHub repository](https://github.com/Shaaan2005/AI-Resume-Screening-and-RAG-Evaluation-System).

Sample resumes: [Resume Dataset](https://www.kaggle.com/datasets/snehaanbhawal/resume-dataset) by Snehaan Bhawal (CC0).
