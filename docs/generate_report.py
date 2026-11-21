import os
import sys

# Ensure python-docx is installed
try:
    import docx
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-docx"])
    import docx
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT

def create_report_docx():
    doc = docx.Document()

    # Set page margins
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    # Styling helper
    def add_title(text):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(text)
        run.bold = True
        run.font.size = Pt(22)
        run.font.name = 'Calibri'
        run.font.color.rgb = RGBColor(0, 51, 102)

    def add_subtitle(text):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(text)
        run.bold = True
        run.font.size = Pt(14)
        run.font.name = 'Calibri'
        run.font.color.rgb = RGBColor(0, 147, 147)

    def add_heading_1(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after = Pt(6)
        run = p.add_run(text)
        run.bold = True
        run.font.size = Pt(16)
        run.font.name = 'Calibri'
        run.font.color.rgb = RGBColor(0, 51, 102)

    def add_heading_2(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(text)
        run.bold = True
        run.font.size = Pt(13)
        run.font.name = 'Calibri'
        run.font.color.rgb = RGBColor(0, 102, 153)

    def add_body(text, bold_prefix=""):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.15
        if bold_prefix:
            run_b = p.add_run(bold_prefix)
            run_b.bold = True
            run_b.font.size = Pt(11)
            run_b.font.name = 'Calibri'
        run_t = p.add_run(text)
        run_t.font.size = Pt(11)
        run_t.font.name = 'Calibri'
        return p

    def add_bullet(text, bold_prefix=""):
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.15
        if bold_prefix:
            run_b = p.add_run(bold_prefix)
            run_b.bold = True
            run_b.font.size = Pt(11)
            run_b.font.name = 'Calibri'
        run_t = p.add_run(text)
        run_t.font.size = Pt(11)
        run_t.font.name = 'Calibri'

    # Title & Metadata
    add_title("INTERNSHIP PROJECT REPORT")
    add_subtitle("AI-POWERED RESUME SCREENING AND RAG EVALUATION SYSTEM")
    doc.add_paragraph()

    # Cover Meta Box
    add_body("Utkarsh Rai", "Student Name: ")
    add_body("B.Tech in Electronics & Communication Engineering (ECE), 7th Semester (4th Year)", "Degree & Branch: ")
    add_body("International Institute of Information Technology, Naya Raipur (IIIT-NR)", "University / Institution: ")
    add_body("Info Origin", "Company / Organization: ")
    add_body("Data Science & Artificial Intelligence Division", "Department: ")
    add_body("Mr. Anurag Tripathi (Director of Data Science)", "Working Under: ")
    add_body("Sir Mahendra Kumar Gurve", "Project Mentor: ")
    add_body("2 Months (June 1, 2026 – July 31, 2026)", "Internship Duration: ")
    add_body("https://github.com/Shaaan2005/AI-Resume-Screening-and-RAG-Evaluation-System", "GitHub Repository: ")

    doc.add_paragraph()

    # Table of Contents
    add_heading_1("TABLE OF CONTENTS")
    add_bullet("Executive Summary & Abstract", "1. ")
    add_bullet("Internship Overview & Work Culture at Info Origin", "2. ")
    add_bullet("Industry Problem Statement & Project Objectives", "3. ")
    add_bullet("Chronological Progress & Milestone Timeline (Daily Standups & Weekday Cadence)", "4. ")
    add_bullet("Core System Architecture & Subsystems", "5. ")
    add_bullet("Technical Implementation Details", "6. ")
    add_bullet("Performance Evaluation & Experimental Results", "7. ")
    add_bullet("Key Learnings & Technical Competencies Acquired", "8. ")
    add_bullet("Conclusion & Acknowledgments", "9. ")

    # Section 1
    add_heading_1("1. EXECUTIVE SUMMARY & ABSTRACT")
    add_body("During my 2-month summer internship at Info Origin (June 1, 2026 – July 31, 2026), working under the guidance of Mr. Anurag Tripathi (Director of Data Science) and my project mentor Sir Mahendra Kumar Gurve, I designed, developed, and evaluated an enterprise-grade, privacy-first AI Resume Screening and RAG Evaluation System.")
    add_body("Traditional Applicant Tracking Systems (ATS) rely heavily on exact keyword matching, which frequently fails when candidates use domain synonyms, non-standard phrasing, or abbreviations. To overcome this limitation, I built a hybrid search architecture combining ChromaDB vector search (all-mpnet-base-v2 dense embeddings) with a Cross-Encoder re-ranker (stsb-distilroberta-base). Furthermore, to fulfill enterprise requirements for data privacy and zero cloud operating costs, I integrated local Ollama (Llama 3) into the RAGAS evaluation framework, enabling offline metric scoring (Context Precision and Context Recall).")
    add_body("The system achieved a 93.33% Context Recall score on benchmark evaluation suites, operating 100% locally with zero cloud API dependencies.")

    # Section 2
    add_heading_1("2. INTERNSHIP OVERVIEW & WORK CULTURE AT INFO ORIGIN")
    add_body("My internship at Info Origin provided an enriching hands-on experience in production-grade Data Science and Applied AI engineering.")
    add_heading_2("2.1 Guidance & Mentorship Structure")
    add_bullet("I had the privilege of working directly under Mr. Anurag Tripathi, Director of Data Science at Info Origin, who provided strategic direction, technical standards, and team oversight.", "Leadership: ")
    add_bullet("Sir Mahendra Kumar Gurve served as my primary project mentor, providing daily guidance, code reviews, and architectural feedback.", "Project Mentorship: ")

    add_heading_2("2.2 Weekday Daily Standup Cadence (12:00 PM Meetings)")
    add_body("Throughout the 2-month internship, our team conducted daily standup meetings every weekday at 12:00 PM (noon). These daily meetings played a crucial role in my professional development:")
    add_bullet("Presenting daily technical accomplishments, code changes, and bug fixes.", "1. Daily Progress Reporting: ")
    add_bullet("Receiving direct, actionable feedback on system performance, resource efficiency, and algorithm choice.", "2. Iterative Feedback Loops: ")
    add_bullet("Identifying bottlenecks early—such as transitioning away from hardcoded alias dictionaries toward cross-encoder semantic classification, and switching from paid cloud APIs to local Ollama inference.", "3. Agile Problem Solving: ")

    # Section 3
    add_heading_1("3. INDUSTRY PROBLEM STATEMENT & PROJECT OBJECTIVES")
    add_heading_2("3.1 Industry Problem")
    add_body("Recruiters manually screen hundreds of resumes per job posting, spending ~23 hours per hiring decision. Legacy ATS filters rely on exact keyword strings, resulting in two major failures:")
    add_bullet("Rejecting qualified candidates who express skills differently (e.g., 'Container Orchestration' vs. 'Kubernetes').", "1. False Negatives: ")
    add_bullet("Cloud-based LLM screening services expose sensitive candidate PII (Personally Identifiable Information) to external servers and incur high recurring API charges.", "2. Privacy & Cost Risks: ")

    add_heading_2("3.2 Key Project Objectives")
    add_bullet("Build a natural language candidate search engine covering 24 specialized industry categories (Engineering, IT, HR, Healthcare, Finance, Agriculture, etc.).", "Objective 1: ")
    add_bullet("Implement a 2-stage search pipeline combining fast vector retrieval with Cross-Encoder re-ranking for top-candidate precision.", "Objective 2: ")
    add_bullet("Develop a 100% offline RAGAS evaluation dashboard powered by local Ollama (llama3) and local HuggingFace embeddings (all-MiniLM-L6-v2) to achieve $0 API costs and complete data privacy.", "Objective 3: ")

    # Section 4
    add_heading_1("4. CHRONOLOGICAL PROGRESS & MILESTONE TIMELINE")
    add_bullet("Implemented PDF/DOCX text extraction using pdfplumber and python-docx. Created 200-word sliding text chunking strategy for candidate resumes.", "Milestone 1 (Weeks 1-2): ")
    add_bullet("Embedded candidate text using SentenceTransformers (all-mpnet-base-v2). Created persistent ChromaDB collection with HNSW cosine distance indexing.", "Milestone 2 (Weeks 3-4): ")
    add_bullet("Identified flaw in old CAT_ALIASES dictionary. Replaced hardcoded lists with unified Cross-Encoder semantic category classifier. Implemented STSB-DistilRoBERTa cross-encoder re-ranking for top candidate search.", "Milestone 3 (Weeks 5-6): ")
    add_bullet("Integrated RAGAS evaluation framework (Context Precision & Context Recall). Connected local ChatOllama (llama3) as local LLM judge to eliminate API costs. Built hybrid speed setup with HuggingFace embeddings for fast evaluation.", "Milestone 4 (Weeks 7-8): ")

    # Section 5
    add_heading_1("5. CORE SYSTEM ARCHITECTURE & SUBSYSTEMS")
    add_bullet("PDF/DOCX Extraction -> 200-Word Chunks -> Dense Embeddings (all-mpnet-base-v2) -> ChromaDB Store", "1. Ingestion Subsystem: ")
    add_bullet("Search Query -> Category Classifier -> Vector Retrieval -> Cross-Encoder Re-Ranker -> Candidate Rankings", "2. Search & Re-Ranking: ")
    add_bullet("Benchmark Suite -> HuggingFace Embeddings + Local Ollama (Llama 3) -> RAGAS Metrics (Context Precision & Recall)", "3. Offline Evaluation Engine: ")

    # Section 6
    add_heading_1("6. TECHNICAL IMPLEMENTATION DETAILS")
    add_heading_2("6.1 Resume Parsing & Chunking (resume_engine.py)")
    add_body("Resumes are ingested from .pdf and .docx formats using pdfplumber and python-docx. The text is split into sliding chunks of 200 words to ensure semantic coherence while staying within optimal context bounds.")

    add_heading_2("6.2 Dense Vector Storage (vector_store.py & chroma_search.py)")
    add_body("Candidate chunks are encoded into 768-dimensional dense vectors using SentenceTransformer('all-mpnet-base-v2') and stored inside a persistent ChromaDB instance with HNSW cosine distance indexing.")

    add_heading_2("6.3 Semantic Intent Classification (detect_category in app.py)")
    add_body("I replaced the hardcoded alias dictionary (CAT_ALIASES) with a unified Cross-Encoder classifier (cross-encoder/stsb-distilroberta-base). It jointly evaluates user queries against 24 department descriptions, picking the category with highest semantic alignment.")

    add_heading_2("6.4 Hybrid Search & Re-Ranking (chroma_search.py)")
    add_body("Dense vector search retrieves top candidate chunks from ChromaDB. Top candidates pass through stsb-distilroberta-base to compute joint-attention scores. Final Score = 0.30 * Keyword Score + 0.70 * Cross-Encoder Score.")

    add_heading_2("6.5 Offline RAGAS Evaluation Engine (evaluate_ragas.py)")
    add_body("Integrated ChatOllama(model='llama3') wrapped in Ragas' LangchainLLMWrapper. Paired with HuggingFaceEmbeddings(model_name='all-MiniLM-L6-v2') for fast local vector calculation, configured with RunConfig(max_workers=1) for reliable local execution.")

    # Section 7
    add_heading_1("7. PERFORMANCE EVALUATION & EXPERIMENTAL RESULTS")
    table = doc.add_table(rows=5, cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = 'Table Grid'
    
    headers = ["Metric", "Score", "Analytical Interpretation"]
    for i, h in enumerate(headers):
        cell = table.cell(0, i)
        cell.paragraphs[0].text = h
        cell.paragraphs[0].runs[0].bold = True
        
    data = [
        ["Context Recall", "93.33%", "Near-Perfect Coverage: 93.33% of required skills retrieved into context (100% recall on IT & HR)."],
        ["Context Precision", "50.00%", "Healthy RAG Tradeoff: High recall ensures zero candidate skills missed; Cross-Encoder handles ranking."],
        ["Cloud API Cost", "$0.00", "100% Free: Runs entirely locally via Ollama with zero third-party cloud fees."],
        ["Data Privacy", "100% On-Premise", "Candidate resumes and queries never leave the host system."]
    ]
    for row_idx, row_data in enumerate(data, start=1):
        for col_idx, cell_value in enumerate(row_data):
            table.cell(row_idx, col_idx).paragraphs[0].text = cell_value

    doc.add_paragraph()

    # Section 8
    add_heading_1("8. KEY LEARNINGS & TECHNICAL COMPETENCIES ACQUIRED")
    add_bullet("Designing end-to-end vector search pipelines using dense embeddings, vector stores, and chunking strategies.", "1. Retrieval-Augmented Generation (RAG): ")
    add_bullet("Understanding the distinction between fast dual-encoder retrieval and accurate joint-attention re-ranking.", "2. Bi-Encoders vs. Cross-Encoders: ")
    add_bullet("Running, pre-warming, and integrating open-source models like llama3 into production Python applications.", "3. Local LLM Operationalization (Ollama): ")
    add_bullet("Applying standard RAG metrics (Context Precision & Context Recall) to measure system quality objectively.", "4. Quantitative AI Benchmarking (RAGAS): ")
    add_bullet("Participating in 12:00 PM daily standup meetings, presenting progress updates, incorporating mentor feedback, and maintaining clean code on GitHub.", "5. Agile Engineering & Professional Growth: ")

    # Section 9
    add_heading_1("9. CONCLUSION & ACKNOWLEDGMENTS")
    add_heading_2("9.1 Conclusion")
    add_body("The AI-Powered Resume Screening and RAG Evaluation System successfully demonstrates how enterprise AI solutions can deliver high search quality (93.33% Recall), $0 cloud API costs, and 100% data privacy. The project successfully met all goals set by Info Origin leadership.")

    add_heading_2("9.2 Deliverables & Links")
    add_bullet("https://github.com/Shaaan2005/AI-Resume-Screening-and-RAG-Evaluation-System", "GitHub Repository: ")

    add_heading_2("9.3 Acknowledgments")
    add_body("I express my sincere gratitude to:")
    add_bullet("Mr. Anurag Tripathi (Director of Data Science) for providing the opportunity to intern at Info Origin, his leadership, and architectural direction.")
    add_bullet("Sir Mahendra Kumar Gurve (Project Mentor) for his continuous guidance, constructive feedback during our 12:00 PM daily standups, and mentorship throughout the project.")
    add_bullet("International Institute of Information Technology, Naya Raipur (IIIT-NR) for providing academic support during my 7th semester.")

    output_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "Internship_Project_Report_Utkarsh_Rai_Final.docx")
    doc.save(output_filename)
    print(f"Successfully generated Word document: {os.path.abspath(output_filename)}")

if __name__ == "__main__":
    create_report_docx()
