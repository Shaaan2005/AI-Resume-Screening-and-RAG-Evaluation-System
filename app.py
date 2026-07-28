from flask import Flask, request, render_template, send_from_directory, abort, redirect, url_for, session
from resume_engine import analyze_resume, extract_resume_text, chunk_text
from semantic_match import get_similarity
from chroma_search import search_candidates, get_collection, get_cross_encoder
from model_loader import model
from skills_config import SKILLS_BY_CATEGORY

import os
import re
import json
import sqlite3
import math

from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()

UPLOAD_FOLDER = "uploads"
HISTORY_FILE = "recent_analyses.json"
DB_FILE = "users.db"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

LOGIN_BUILD = os.path.join(os.path.dirname(__file__), "login-app", "dist")


@app.route("/assets/<path:filename>")
def login_assets(filename):
    return send_from_directory(os.path.join(LOGIN_BUILD, "assets"), filename)


def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, email TEXT, password TEXT)")
    conn.commit()
    conn.close()


init_db()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.context_processor
def inject_user():
    user = None
    if "user_id" in session:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.execute("SELECT id, username, email FROM users WHERE id = ?", (session["user_id"],))
        row = cur.fetchone()
        conn.close()
        if row:
            user = {"id": row[0], "username": row[1], "email": row[2]}
    return {"user": user}


def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def save_history(entry):
    history = load_history()
    history.insert(0, entry)
    history = history[:10]
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


# --- Two-Layer Category Detection ---
# Semantic category detection — evaluated against 24 department descriptions using Cross-Encoder model


# Cross-encoder descriptions for semantic fallback
_CAT_DESCRIPTIONS = {
    "ACCOUNTANT": "The category for this query is ACCOUNTANT. Includes accounting, bookkeeper, auditor, tax consultant, CA, CPA, bookkeeping, payroll, audit.",
    "ADVOCATE": "The category for this query is ADVOCATE. Includes lawyer, attorney, legal counsel, solicitor, legal advisor, corporate lawyer, litigation, legal research, contract drafting.",
    "AGRICULTURE": "The category for this query is AGRICULTURE. Includes farmer, agronomist, agricultural scientist, horticulturist, farm manager, crop management, farming, agronomy.",
    "APPAREL": "The category for this query is APPAREL. Includes fashion, garment, textile, fashion designer, merchandiser, clothing, apparel designer, fashion design, garment construction.",
    "ARTS": "The category for this query is ARTS. Includes artist, painter, sculptor, illustrator, creative, fine arts, visual arts, digital art, graphic design, animation.",
    "AUTOMOBILE": "The category for this query is AUTOMOBILE. Includes automotive, mechanic, auto engineer, vehicle, car, motor, auto mechanics, engine repair, electric vehicles.",
    "AVIATION": "The category for this query is AVIATION. Includes pilot, flight, airline, aircraft, cabin crew, air traffic controller, flight attendant, aerospace, flight operations.",
    "BANKING": "The category for this query is BANKING. Includes banker, bank officer, loan officer, credit analyst, financial services, bank, investment banker, credit analysis, risk management.",
    "BPO": "The category for this query is BPO. Includes business process outsourcing, call center, customer support, customer service representative, telecaller, helpdesk, technical support.",
    "BUSINESS-DEVELOPMENT": "The category for this query is BUSINESS-DEVELOPMENT. Includes sales development, biz dev, partnerships, growth manager, business strategist, lead generation.",
    "CHEF": "The category for this query is CHEF. Includes cook, culinary, kitchen, baker, pastry chef, sous chef, head chef, food, culinary arts, cooking, menu planning.",
    "CONSTRUCTION": "The category for this query is CONSTRUCTION. Includes builder, site engineer, civil contractor, project manager construction, mason, civil engineering, structural engineering, blueprint.",
    "CONSULTANT": "The category for this query is CONSULTANT. Includes consulting, management consultant, strategy consultant, business analyst, advisor, strategic planning, management consulting.",
    "DESIGNER": "The category for this query is DESIGNER. Includes ui designer, ux designer, graphic designer, web designer, product designer, visual designer, figma, prototyping, wireframing.",
    "DIGITAL-MEDIA": "The category for this query is DIGITAL-MEDIA. Includes digital marketing, social media manager, content creator, seo specialist, online marketing, google ads, content strategy, copywriter.",
    "ENGINEERING": "The category for this query is ENGINEERING. Includes engineer, software engineer, software developer, programmer, coder, developer, devops engineer, data engineer, backend engineer, frontend engineer, full stack developer, software engineering, tech.",
    "FINANCE": "The category for this query is FINANCE. Includes financial analyst, investment analyst, portfolio manager, treasury, CFO, financial planner, wealth manager, financial modeling, valuation.",
    "FITNESS": "The category for this query is FITNESS. Includes personal trainer, gym instructor, fitness coach, yoga instructor, sports trainer, wellness coach, personal training, strength training.",
    "HEALTHCARE": "The category for this query is HEALTHCARE. Includes doctor, nurse, physician, medical, hospital, health, clinical, pharmacist, surgeon, therapist, patient care, nursing, surgery.",
    "HR": "The category for this query is HR. Includes human resources, recruiter, talent acquisition, hr manager, hr executive, people operations, hiring manager, recruitment, onboarding.",
    "INFORMATION-TECHNOLOGY": "The category for this query is INFORMATION-TECHNOLOGY. Includes IT support, system administrator, network administrator, sysadmin, cybersecurity, cloud computing, aws, linux, infrastructure.",
    "PUBLIC-RELATIONS": "The category for this query is PUBLIC-RELATIONS. Includes pr, communications, media relations, press, corporate communications, pr manager, spokesperson, press release.",
    "SALES": "The category for this query is SALES. Includes salesperson, sales executive, account executive, sales manager, business sales, lead generation, account management, closing.",
    "TEACHER": "The category for this query is TEACHER. Includes educator, professor, instructor, tutor, lecturer, teaching, academic, faculty, university professor, lecturing, classroom management.",
}


def cross_encoder_category_detect(query, threshold=0.3):
    """Semantic category detection using cross-encoder."""
    if not query or len(query.strip()) < 3:
        return None

    ce = get_cross_encoder()
    cats = list(_CAT_DESCRIPTIONS.keys())
    pairs = [(query, _CAT_DESCRIPTIONS[cat]) for cat in cats]
    scores = ce.predict(pairs)

    best_idx = int(scores.argmax())
    best_score = float(scores[best_idx])
    best_cat = cats[best_idx]

    print(f"[CROSS-ENCODER CATEGORY] Query: '{query}' -> {best_cat} (score: {best_score:.4f})")

    return best_cat if best_score > threshold else None


def detect_category(job_description):
    """Semantic category detection using Cross-Encoder model."""
    return cross_encoder_category_detect(job_description)


NUM_WORDS = {"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9,"ten":10}

def parse_requested_count(text):
    t = text.lower()
    match = re.search(r'\b(top|best|to|select|choose|pick|find|show|give|get|need|want)\s+(\d+)\b', t)
    if match:
        return int(match.group(2))
    match = re.search(r'\b(top|best|to|select|choose|pick|find|show|give|get|need|want)\s+(' + '|'.join(NUM_WORDS) + r')\b', t)
    if match:
        return NUM_WORDS[match.group(2)]
    match = re.search(r'(\d+)\s*(resume|result|candidate)s?\b', t)
    if match:
        return int(match.group(1))
    match = re.search(r'(' + '|'.join(NUM_WORDS) + r')\s+(resume|result|candidate)s?\b', t)
    if match:
        return NUM_WORDS[match.group(1)]
    return None


ALL_SKILLS_FLAT = set()
for skills in SKILLS_BY_CATEGORY.values():
    for s in skills:
        ALL_SKILLS_FLAT.add(s.lower())
        for part in s.split():
            ALL_SKILLS_FLAT.add(part)

SKIP_WORDS = {"the","a","an","in","on","at","to","for","with","from","by","and",
    "top","best","resume","resumes","candidate","candidates","list","show","give",
    "find","search","need","want","get","all","any","not","but","have","most",
    "matching","skills","experience","work","job","description","background",
    "team","role","skill","of","is","are","it","this","that",
    "looking","using","including","based","able","will","can","also",
    "well","per","year","years","new","like","make","made","one","each",
    "every","both","either","neither","some","few","several","many"}

INTENT_NOISE = {"show","list","find","search","need","want","get","give","me",
    "top","best","one","two","three","four","five","six","seven","eight",
    "nine","ten","each","every","per","all","both","neither","either",
    "any","some","few","several","many"}

def extract_words(text):
    """Utility to extract all query terms including short/special tech words."""
    words = re.findall(r'[a-zA-Z0-9+#.-]+', text.lower())
    cleaned = []
    for w in words:
        w = w.strip(".,;:!?()")
        if w:
            cleaned.append(w)
    return cleaned


def extract_search_intent(query):
    t = query.lower()
    for cat in SKILLS_BY_CATEGORY:
        name = cat.lower().replace("-", " ")
        t = re.sub(rf'\b{re.escape(name)}\b', '', t)
    words = extract_words(t)
    clean = []
    for w in words:
        # Require length >= 3 or valid short tech terms
        if w in {"c++", "c#", ".net", "go", "r", "js", "ts", "ui", "ux", "it", "hr", "pr", "bd", "ml", "ai", "db"} or len(w) >= 3:
            if w not in INTENT_NOISE and w not in SKIP_WORDS:
                clean.append(w)
    return " ".join(clean) if clean else None


def is_garbage(text):
    if not text or not text.strip():
        return True
    # Allow common short tech terms
    if re.search(r'\b(c\+\+|c#|\.net|go|r|it|hr|pr|bd|ml|ai|db)\b', text.lower()):
        return False
    words = extract_words(text)
    if not words:
        if re.search(r'[a-zA-Z0-9]', text):
            return False
        return True
    real = 0
    for w in words:
        # If it's a short valid tech term, it's real
        if w in {"c++", "c#", ".net", "go", "r", "js", "ts", "ui", "ux", "it", "hr", "pr", "bd", "ml", "ai", "db"}:
            real += 1
            continue
        if len(w) >= 3 and any(v in w for v in "aeiou") and w not in SKIP_WORDS:
            real += 1
    return real == 0





@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("home"))
    error = None
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        conn = sqlite3.connect(DB_FILE)
        cur = conn.execute("SELECT id, username, password FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        conn.close()
        if row and check_password_hash(row[2], password):
            session["user_id"] = row[0]
            session["username"] = row[1]
            return redirect(url_for("home"))
        error = "Invalid username or password"
    index_path = os.path.join(LOGIN_BUILD, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(LOGIN_BUILD, "index.html")
    return render_template("login.html", error=error)


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("home"))
    error = None
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]
        if not username or not email or not password:
            error = "All fields are required"
        elif len(username) < 3:
            error = "Username must be at least 3 characters"
        elif len(password) < 4:
            error = "Password must be at least 4 characters"
        else:
            conn = sqlite3.connect(DB_FILE)
            try:
                conn.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                             (username, email, generate_password_hash(password)))
                conn.commit()
                cur = conn.execute("SELECT id FROM users WHERE username = ?", (username,))
                session["user_id"] = cur.fetchone()[0]
                session["username"] = username
                conn.close()
                return redirect(url_for("home"))
            except sqlite3.IntegrityError:
                error = "Username already taken"
                conn.close()
    return render_template("register.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/search", methods=["POST"])
@login_required
def search():
    job_description = request.form["job_description"]

    if is_garbage(job_description):
        return render_template("search_results.html",
            category=None, rankings=[], total_candidates=0,
            job_description=job_description,
            msg="That doesn't look like a valid search — try something like 'top 5 from engineering'")

    words = extract_words(job_description)
    meaningful = []
    for w in words:
        if w in {"c++", "c#", ".net", "go", "r", "js", "ts", "ui", "ux", "it", "hr", "pr", "bd", "ml", "ai", "db"} or len(w) >= 3:
            if w not in SKIP_WORDS:
                meaningful.append(w)
    if len(meaningful) < 1:
        return render_template("search_results.html",
            category=None, rankings=[], total_candidates=0,
            job_description=job_description,
            msg="Please be more specific — try adding skills or a department name")

    search_intent = extract_search_intent(job_description) or job_description
    print(f"[SMART SEARCH] Query: '{job_description}' -> Intent: '{search_intent}'")

    all_dept = bool(re.search(r'\b(all|every)\s+departments?\b', job_description.lower()))

    # Two-layer category detection: keyword first, cross-encoder fallback
    if all_dept:
        categories = list(SKILLS_BY_CATEGORY.keys())
    else:
        detected = detect_category(job_description)
        categories = [detected] if detected else []

    is_multi = all_dept or len(categories) > 1
    category = categories[0] if categories else None
    multi_msg = None
    if all_dept:
        multi_msg = f"Showing results across {len(categories)} departments"
    elif len(categories) > 1:
        multi_msg = f"Multiple departments detected: {', '.join(categories)}"

    if is_multi:
        all_rankings = []
        seen = set()
        for cat in categories:
            for r in search_candidates(search_intent, category=cat):
                if r["resume"] not in seen:
                    seen.add(r["resume"])
                    all_rankings.append(r)
        all_rankings.sort(key=lambda x: x["similarity"], reverse=True)
        for i, r in enumerate(all_rankings, 1):
            r["rank"] = i
        rankings = all_rankings
    else:
        rankings = search_candidates(search_intent, category=category)

    if not rankings:
        return render_template("search_results.html",
            category=category, rankings=[], total_candidates=0,
            job_description=job_description,
            msg=f"No candidates found in {category or 'database'}")

    requested = parse_requested_count(job_description)
    msg = None

    # "each" / "every" distribution across categories
    if requested is None and is_multi and "each" in job_description.lower():
        requested = 1
    if requested is None:
        if re.search(r'\b(best|top)\b', job_description.lower()):
            requested = 1

    if requested and is_multi:
        per_cat = requested
        limited = []
        seen_cat = {}
        for r in rankings:
            rcat = r.get("category", "")
            if rcat not in seen_cat:
                seen_cat[rcat] = 0
            if seen_cat[rcat] < per_cat:
                limited.append(r)
                seen_cat[rcat] += 1
        rankings = limited
    elif requested:
        if requested > len(rankings):
            msg = f"Only {len(rankings)} candidates found in {category or 'database'} (requested {requested})"
        rankings = rankings[:requested]

    collection = get_collection()
    total_candidates = collection.count()

    return render_template("search_results.html",
        category=category,
        rankings=rankings,
        total_candidates=total_candidates,
        job_description=job_description,
        msg=msg,
        multi_msg=multi_msg)


@app.route("/resume/<category>/<filename>")
@login_required
def download_resume(category, filename):
    safe_dir = os.path.join("resumes", category)
    if not os.path.isdir(safe_dir):
        abort(404)
    return send_from_directory(safe_dir, filename)


@app.route("/")
@login_required
def home():
    history = load_history()
    return render_template("index.html", recent=history)


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    job_description = request.form["job_description"]
    file = request.files["resume"]
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)

    category = detect_category(job_description)

    result = analyze_resume(file_path)
    resume_text = extract_resume_text(file_path)
    semantic_score = get_similarity(job_description, resume_text)

    keyword_pct = result['score']
    combined_score = round(keyword_pct * 0.4 + semantic_score * 0.6, 1)
    if combined_score >= 60:
        combined_rec = "SHORTLIST"
    elif combined_score >= 35:
        combined_rec = "CONSIDER"
    else:
        combined_rec = "REJECT"

    chunks = chunk_text(resume_text)
    chunk_ids = []
    chunk_embeddings = []
    chunk_docs = []
    chunk_metadatas = []

    for idx, chunk in enumerate(chunks):
        chunk_ids.append(f"{file.filename}_chunk{idx}")
        chunk_embeddings.append(model.encode(chunk).tolist())
        chunk_docs.append(chunk)
        chunk_metadatas.append({
            "resume": file.filename,
            "chunk": idx,
            "total_chunks": len(chunks),
            "recommendation": result["recommendation"],
            "skill_score": result["score"],
            "category": category or ""
        })

    if chunk_ids:
        collection = get_collection()
        collection.upsert(
            ids=chunk_ids,
            embeddings=chunk_embeddings,
            documents=chunk_docs,
            metadatas=chunk_metadatas
        )

    rankings = search_candidates(job_description, category=category)

    collection = get_collection()
    total_candidates = collection.count()

    save_history({
        "filename": file.filename,
        "score": float(semantic_score),
        "recommendation": result["recommendation"],
        "timestamp": datetime.now().strftime("%d %b %Y, %I:%M %p")
    })

    return render_template("result.html",
        filename=file.filename,
        result=result,
        semantic_score=semantic_score,
        keyword_pct=keyword_pct,
        combined_score=combined_score,
        combined_rec=combined_rec,
        rankings=rankings,
        total_candidates=total_candidates,
        job_description=job_description,
        category=category)


EVAL_CACHE_FILE = "evaluation_cache.json"

@app.route("/evaluate", methods=["GET", "POST"])
@login_required
def evaluate_dashboard():
    from evaluate_ragas import get_heuristic_scorecard, get_real_ragas_scorecard
    
    error_msg = None
    success_msg = None
    is_real_ragas = False
    
    # Check if we should force recalculation of the heuristic baseline
    force_recalc = (request.args.get("recalculate") == "true")
    
    # Load heuristic scorecard from cache or calculate on-demand
    h_results = None
    if not force_recalc and os.path.exists(EVAL_CACHE_FILE):
        try:
            print("[EVAL DEBUG] Cache file exists. Reading...")
            with open(EVAL_CACHE_FILE, "r") as f:
                cache_data = json.load(f)
                h_results = cache_data["results"]
                h_precision = cache_data["avg_precision"]
                h_recall = cache_data["avg_recall"]
                h_similarity = cache_data["avg_similarity"]
            print("[EVAL DEBUG] Successfully loaded all metrics from cache!")
        except Exception as e:
            print(f"[EVAL DEBUG] Failed to load cache: {str(e)}")
            h_results = None

    if h_results is None:
        print("[EVAL DEBUG] Cache missing or recalculation forced. Running full 10-query benchmark (Takes 15-30s)...")
        # Calculate fresh scores and update cache
        h_results, h_precision, h_recall, h_similarity = get_heuristic_scorecard()
        try:
            print("[EVAL DEBUG] Benchmarking complete. Saving to cache file...")
            with open(EVAL_CACHE_FILE, "w") as f:
                json.dump({
                    "results": h_results,
                    "avg_precision": h_precision,
                    "avg_recall": h_recall,
                    "avg_similarity": h_similarity
                }, f, indent=4)
            print("[EVAL DEBUG] Cache saved successfully!")
        except Exception as e:
            print(f"[CACHE ERROR] Failed to save cache: {str(e)}")
            
    if force_recalc:
        success_msg = "Successfully recalculated baseline heuristic metrics across the test suite!"

    results = h_results
    avg_precision = h_precision
    avg_recall = h_recall
    avg_similarity = h_similarity
    
    if request.method == "POST":
        print(f"[DEBUG POST] Form keys: {list(request.form.keys())}")
        print(f"[DEBUG POST] Received eval_mode: {request.form.get('eval_mode')}")
        print(f"[DEBUG POST] Received openai_key (truncated): {request.form.get('openai_key')[:10] if request.form.get('openai_key') else None}")
        eval_mode = request.form.get("eval_mode", "openai").strip()
        openai_key = request.form.get("openai_key", "").strip()
        
        if eval_mode == "openai" and not openai_key:
            error_msg = "Please enter a valid OpenAI API Key to run RAGAS."
        else:
            try:
                if eval_mode == "ollama":
                    print(f"[RAGAS WEB RUN] Running actual Ragas evaluation using local Ollama (Llama 3)...")
                    r_results, r_precision, r_recall = get_real_ragas_scorecard(use_ollama=True)
                else:
                    print(f"[RAGAS WEB RUN] Running actual Ragas evaluation using OpenAI API Key...")
                    r_results, r_precision, r_recall = get_real_ragas_scorecard(openai_key=openai_key)
                
                # Check if Ragas returned NaN scores (indicates OpenAI credit/billing/local service issue)
                if not r_results:
                    error_msg = "RAGAS evaluation failed. Please verify that your selected judge model is running."
                elif eval_mode == "openai" and (math.isnan(r_precision) or math.isnan(r_recall)):
                    error_msg = "Ragas returned NaN scores. This happens when your OpenAI API Key has expired, has no credit balance, or hit a billing rate limit. Please verify your billing quota at https://platform.openai.com/usage"
                else:
                    # Clean up any individual NaN values in row scores for safe rendering
                    cleaned_results = []
                    for row in r_results:
                        cleaned_row = dict(row)
                        if 'context_precision' in cleaned_row and (cleaned_row['context_precision'] is None or math.isnan(cleaned_row['context_precision'])):
                            cleaned_row['context_precision'] = 0.0
                        if 'context_recall' in cleaned_row and (cleaned_row['context_recall'] is None or math.isnan(cleaned_row['context_recall'])):
                            cleaned_row['context_recall'] = 0.0
                        cleaned_results.append(cleaned_row)
                        
                    results = cleaned_results
                    avg_precision = r_precision
                    avg_recall = r_recall
                    is_real_ragas = True
                    if eval_mode == "ollama":
                        success_msg = "Successfully computed actual RAGAS metrics using local Ollama (Llama 3) Judge!"
                    else:
                        success_msg = "Successfully computed actual RAGAS metrics using OpenAI LLM Judge!"
            except Exception as e:
                error_msg = f"Error during Ragas evaluation: {str(e)}"
                
    return render_template("evaluate.html",
                           results=results,
                           avg_precision=round(avg_precision * 100, 2) if not math.isnan(avg_precision) else 0.0,
                           avg_recall=round(avg_recall * 100, 2) if not math.isnan(avg_recall) else 0.0,
                           avg_similarity=round(avg_similarity * 100, 2) if avg_similarity and not math.isnan(avg_similarity) else None,
                           is_real_ragas=is_real_ragas,
                           error_msg=error_msg,
                           success_msg=success_msg)



if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)