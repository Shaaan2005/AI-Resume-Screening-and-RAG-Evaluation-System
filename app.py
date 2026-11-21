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
import uuid
import secrets
import logging
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps

# Setup structured application logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("ResumeScreening")

app = Flask(__name__)

# Security: Persistent secret key configuration
SECRET_KEY_FILE = ".secret_key"
def _get_or_create_secret_key():
    env_key = os.environ.get("FLASK_SECRET_KEY")
    if env_key:
        return env_key
    if os.path.exists(SECRET_KEY_FILE):
        try:
            with open(SECRET_KEY_FILE, "r", encoding="utf-8") as f:
                key = f.read().strip()
                if len(key) >= 32:
                    return key
        except Exception:
            pass
    # Generate and persist a cryptographic 32-byte key
    new_key = secrets.token_hex(32)
    try:
        with open(SECRET_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(new_key)
    except Exception as e:
        logger.warning(f"Could not persist secret key to {SECRET_KEY_FILE}: {e}")
    return new_key

app.secret_key = _get_or_create_secret_key()

# Security & Session Configuration
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024  # 16 MB max upload limit
)

UPLOAD_FOLDER = "uploads"
HISTORY_FILE = "recent_analyses.json"
DB_FILE = "users.db"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


def init_db():
    """Initializes user database and indexes."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, email TEXT, password TEXT)")
        try:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")
        conn.commit()


init_db()


# ── CSRF Protection Implementation ──────────────────────────────────────────

def get_or_create_csrf_token():
    """Retrieves or creates a session-bound CSRF token."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


@app.context_processor
def inject_csrf_and_user():
    user = None
    if "user_id" in session:
        try:
            with sqlite3.connect(DB_FILE) as conn:
                cur = conn.execute("SELECT id, username, email FROM users WHERE id = ?", (session["user_id"],))
                row = cur.fetchone()
                if row:
                    user = {"id": row[0], "username": row[1], "email": row[2]}
        except Exception as e:
            logger.error(f"Error querying current user: {e}")
    return {
        "user": user,
        "csrf_token": get_or_create_csrf_token
    }


@app.before_request
def csrf_protect():
    """Enforces CSRF token validation on all state-changing requests."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        # Allow disabling CSRF in test environments
        if app.config.get("TESTING") and not app.config.get("WTF_CSRF_ENABLED", True):
            return None

        sent_token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        session_token = session.get("csrf_token")

        if not session_token or not sent_token or not secrets.compare_digest(str(sent_token), str(session_token)):
            logger.warning(f"CSRF validation failed for {request.path} from IP {request.remote_addr}")
            abort(403, description="CSRF validation failed: Token missing or invalid")


# ── Custom Error Handlers ───────────────────────────────────────────────────

@app.errorhandler(400)
def bad_request_error(e):
    msg = getattr(e, "description", "The server could not understand the request.")
    return render_template("error.html", code=400, title="Bad Request", message=msg), 400


@app.errorhandler(403)
def forbidden_error(e):
    msg = getattr(e, "description", "You do not have permission to access this resource.")
    return render_template("error.html", code=403, title="Forbidden", message=msg), 403


@app.errorhandler(404)
def not_found_error(e):
    msg = getattr(e, "description", "The requested resource could not be found.")
    return render_template("error.html", code=404, title="Page Not Found", message=msg), 404


@app.errorhandler(413)
def request_entity_too_large(e):
    msg = "The uploaded file exceeds the 16MB limit. Please upload a smaller resume."
    return render_template("error.html", code=413, title="File Too Large", message=msg), 413


@app.errorhandler(500)
def internal_server_error(e):
    logger.error(f"Internal 500 error encountered: {e}")
    return render_template("error.html", code=500, title="Internal Server Error",
                           message="An unexpected error occurred. Please try again later."), 500


# ── Authentication Helper Decorator ─────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError, OSError):
            return []
    return []


def save_history(entry):
    try:
        history = load_history()
        history.insert(0, entry)
        history = history[:10]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not persist history: {e}")


# ── Two-Layer Category Detection ────────────────────────────────────────────

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
    if ce is None:
        return None

    try:
        cats = list(_CAT_DESCRIPTIONS.keys())
        pairs = [(query, _CAT_DESCRIPTIONS[cat]) for cat in cats]
        scores = ce.predict(pairs)

        best_idx = int(scores.argmax())
        best_score = float(scores[best_idx])
        best_cat = cats[best_idx]

        logger.info(f"[CROSS-ENCODER CATEGORY] Query: '{query}' -> {best_cat} (score: {best_score:.4f})")
        return best_cat if best_score > threshold else None
    except Exception as e:
        logger.warning(f"Category detection failed: {e}")
        return None


def detect_category(job_description):
    """Semantic category detection using Cross-Encoder model."""
    return cross_encoder_category_detect(job_description)


NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


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
        if w in {"c++", "c#", ".net", "go", "r", "js", "ts", "ui", "ux", "it", "hr", "pr", "bd", "ml", "ai", "db"} or len(w) >= 3:
            if w not in INTENT_NOISE and w not in SKIP_WORDS:
                clean.append(w)
    return " ".join(clean) if clean else None


def is_garbage(text):
    if not text or not text.strip():
        return True
    if re.search(r'\b(c\+\+|c#|\.net|go|r|it|hr|pr|bd|ml|ai|db)\b', text.lower()):
        return False
    words = extract_words(text)
    if not words:
        return not bool(re.search(r'[a-zA-Z0-9]', text))
    real = 0
    for w in words:
        if w in {"c++", "c#", ".net", "go", "r", "js", "ts", "ui", "ux", "it", "hr", "pr", "bd", "ml", "ai", "db"}:
            real += 1
            continue
        # Filter out unpronounceable keyboard mashing (5+ consecutive consonants) or keyboard walks
        if re.search(r'[bcdfghjklmnpqrstvwxyz]{5,}', w):
            continue
        if re.search(r'^(asdf|qwerty|zxcv|1234)', w):
            continue
        if len(w) >= 3 and any(v in w for v in "aeiouy") and w not in SKIP_WORDS:
            real += 1
    return real == 0


# ── Routes: Authentication ──────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("home"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            error = "Username and password are required"
        else:
            try:
                with sqlite3.connect(DB_FILE) as conn:
                    cur = conn.execute("SELECT id, username, password FROM users WHERE username = ?", (username,))
                    row = cur.fetchone()
                if row and check_password_hash(row[2], password):
                    session["user_id"] = row[0]
                    session["username"] = row[1]
                    session.permanent = True
                    logger.info(f"User '{username}' logged in successfully.")
                    return redirect(url_for("home"))
                error = "Invalid username or password"
            except Exception as e:
                logger.error(f"Login database error: {e}")
                error = "An error occurred during login. Please try again."

    return render_template("login.html", error=error)


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("home"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        # 1. Field presence validation
        if not username or not email or not password:
            error = "All fields are required"
        # 2. Username format validation (alphanumeric, underscores, hyphens, 3-30 chars)
        elif not re.match(r'^[a-zA-Z0-9_-]{3,30}$', username):
            error = "Username must be 3-30 characters and contain only letters, numbers, underscores, or hyphens."
        # 3. Robust Email RFC 5322 validation
        elif not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', email) or len(email) > 254:
            error = "Please enter a valid email address."
        # 4. Password strength enforcement (min 8 chars, at least 1 letter, at least 1 digit)
        elif len(password) < 8 or not re.search(r'[A-Za-z]', password) or not re.search(r'[0-9]', password):
            error = "Password must be at least 8 characters long and contain both letters and numbers."
        else:
            try:
                with sqlite3.connect(DB_FILE) as conn:
                    # Check duplicate username
                    cur = conn.execute("SELECT id FROM users WHERE username = ? COLLATE NOCASE", (username,))
                    if cur.fetchone():
                        error = "Username already taken"
                    else:
                        # Check duplicate email
                        cur = conn.execute("SELECT id FROM users WHERE email = ? COLLATE NOCASE", (email,))
                        if cur.fetchone():
                            error = "Email address is already registered"
                        else:
                            hashed_pw = generate_password_hash(password)
                            conn.execute(
                                "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                                (username, email, hashed_pw)
                            )
                            conn.commit()
                            cur = conn.execute("SELECT id FROM users WHERE username = ?", (username,))
                            session["user_id"] = cur.fetchone()[0]
                            session["username"] = username
                            session.permanent = True
                            logger.info(f"New user registered: {username} ({email})")
                            return redirect(url_for("home"))
            except sqlite3.IntegrityError:
                error = "Username or email is already registered"
            except Exception as e:
                logger.error(f"Registration error: {e}")
                error = "Registration failed due to a server error. Please try again."

    return render_template("register.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Routes: Search & Browse ─────────────────────────────────────────────────

@app.route("/search", methods=["POST"])
@login_required
def search():
    job_description = request.form.get("job_description", "").strip()
    if not job_description:
        return render_template("search_results.html",
            category=None, rankings=[], total_candidates=0,
            job_description="",
            msg="Please enter a search query.")

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
    logger.info(f"[SMART SEARCH] Query: '{job_description}' -> Intent: '{search_intent}'")

    all_dept = bool(re.search(r'\b(all|every)\s+departments?\b', job_description.lower()))

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
    total_candidates = collection.count() if collection else 0

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
    """Safely serves resume PDFs with strict path traversal protections."""
    # 1. Whitelist category against known categories
    if category not in SKILLS_BY_CATEGORY:
        abort(404, description="Invalid department category.")

    # 2. Strict filename sanitization
    safe_filename = secure_filename(filename)
    if not safe_filename or safe_filename != filename:
        abort(404, description="Invalid filename characters detected.")

    safe_dir = os.path.join(os.path.abspath("resumes"), category)
    if not os.path.isdir(safe_dir):
        abort(404, description="Department directory not found.")

    return send_from_directory(safe_dir, safe_filename)


@app.route("/")
@login_required
def home():
    history = load_history()
    return render_template("index.html", recent=history)


# ── Routes: Upload & Analysis ───────────────────────────────────────────────

@app.route("/upload", methods=["POST"])
@login_required
def upload():
    job_description = request.form.get("job_description", "").strip()
    if not job_description:
        return render_template("result.html", error="Job description is required.",
                               filename="", result={"score": 0, "skills": [], "recommendation": "REJECT"},
                               semantic_score=0, keyword_pct=0, combined_score=0, combined_rec="REJECT",
                               rankings=[], total_candidates=0, job_description="", category=None)

    file = request.files.get("resume")
    if not file or not file.filename:
        return render_template("result.html", error="Please upload a resume file.",
                               filename="", result={"score": 0, "skills": [], "recommendation": "REJECT"},
                               semantic_score=0, keyword_pct=0, combined_score=0, combined_rec="REJECT",
                               rankings=[], total_candidates=0, job_description=job_description, category=None)

    # 1. Extension validation
    allowed_extensions = {".pdf", ".docx"}
    _, ext = os.path.splitext(file.filename.lower())
    if ext not in allowed_extensions:
        return render_template("result.html", error="Only PDF and DOCX files are supported.",
                               filename=file.filename, result={"score": 0, "skills": [], "recommendation": "REJECT"},
                               semantic_score=0, keyword_pct=0, combined_score=0, combined_rec="REJECT",
                               rankings=[], total_candidates=0, job_description=job_description, category=None)

    # 2. MIME & Magic bytes signature validation
    try:
        header = file.read(16)
        file.seek(0)
        if ext == ".pdf" and not header.startswith(b"%PDF-"):
            return render_template("result.html", error="Invalid or corrupted PDF file signature.",
                                   filename=file.filename, result={"score": 0, "skills": [], "recommendation": "REJECT"},
                                   semantic_score=0, keyword_pct=0, combined_score=0, combined_rec="REJECT",
                                   rankings=[], total_candidates=0, job_description=job_description, category=None)
        if ext == ".docx" and not header.startswith(b"PK\x03\x04"):
            return render_template("result.html", error="Invalid or corrupted DOCX file signature.",
                                   filename=file.filename, result={"score": 0, "skills": [], "recommendation": "REJECT"},
                                   semantic_score=0, keyword_pct=0, combined_score=0, combined_rec="REJECT",
                                   rankings=[], total_candidates=0, job_description=job_description, category=None)
    except Exception as e:
        logger.warning(f"File signature read error: {e}")
        return render_template("result.html", error="Unable to read uploaded file format.",
                               filename=file.filename, result={"score": 0, "skills": [], "recommendation": "REJECT"},
                               semantic_score=0, keyword_pct=0, combined_score=0, combined_rec="REJECT",
                               rankings=[], total_candidates=0, job_description=job_description, category=None)

    # 3. Path traversal defense & unique filename generation
    clean_name = secure_filename(file.filename) or ("resume" + ext)
    unique_filename = f"{uuid.uuid4().hex[:8]}_{clean_name}"
    file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
    file.save(file_path)

    try:
        category = detect_category(job_description)
        result = analyze_resume(file_path, category=category)
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

        # Index chunks in vector store
        chunks = chunk_text(resume_text)
        chunk_ids = []
        chunk_embeddings = []
        chunk_docs = []
        chunk_metadatas = []

        for idx, chunk in enumerate(chunks):
            chunk_ids.append(f"{unique_filename}_chunk{idx}")
            chunk_embeddings.append(model.encode(chunk).tolist())
            chunk_docs.append(chunk)
            chunk_metadatas.append({
                "resume": unique_filename,
                "chunk": idx,
                "total_chunks": len(chunks),
                "recommendation": result["recommendation"],
                "skill_score": result["score"],
                "category": category or ""
            })

        if chunk_ids:
            collection = get_collection()
            if collection:
                collection.upsert(
                    ids=chunk_ids,
                    embeddings=chunk_embeddings,
                    documents=chunk_docs,
                    metadatas=chunk_metadatas
                )

        rankings = search_candidates(job_description, category=category)
        collection = get_collection()
        total_candidates = collection.count() if collection else 0

        save_history({
            "filename": clean_name,
            "score": float(semantic_score),
            "recommendation": result["recommendation"],
            "timestamp": datetime.now().strftime("%d %b %Y, %I:%M %p")
        })

        return render_template("result.html",
            filename=clean_name,
            error=None,
            result=result,
            semantic_score=semantic_score,
            keyword_pct=keyword_pct,
            combined_score=combined_score,
            combined_rec=combined_rec,
            rankings=rankings,
            total_candidates=total_candidates,
            job_description=job_description,
            category=category)
    except Exception as e:
        logger.error(f"Error processing resume upload: {e}")
        return render_template("result.html",
            filename=clean_name,
            error=f"Error analyzing resume: {str(e)}",
            result={"score": 0, "skills": [], "recommendation": "REJECT"},
            semantic_score=0, keyword_pct=0, combined_score=0, combined_rec="REJECT",
            rankings=[], total_candidates=0, job_description=job_description, category=None)


# ── Routes: Evaluation Dashboard ────────────────────────────────────────────

EVAL_CACHE_FILE = "evaluation_cache.json"

@app.route("/evaluate", methods=["GET", "POST"])
@login_required
def evaluate_dashboard():
    from evaluate_ragas import get_heuristic_scorecard, get_real_ragas_scorecard

    error_msg = None
    success_msg = None
    is_real_ragas = False

    force_recalc = (request.args.get("recalculate") == "true")

    h_results = None
    h_precision = 0.0
    h_recall = 0.0
    h_similarity = 0.0

    if not force_recalc and os.path.exists(EVAL_CACHE_FILE):
        try:
            with open(EVAL_CACHE_FILE, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
                h_results = cache_data.get("results")
                h_precision = cache_data.get("avg_precision", 0.0)
                h_recall = cache_data.get("avg_recall", 0.0)
                h_similarity = cache_data.get("avg_similarity", 0.0)
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            h_results = None

    if h_results is None:
        logger.info("Recalculating heuristic evaluation scorecard...")
        h_results, h_precision, h_recall, h_similarity = get_heuristic_scorecard()
        try:
            with open(EVAL_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "results": h_results,
                    "avg_precision": h_precision,
                    "avg_recall": h_recall,
                    "avg_similarity": h_similarity
                }, f, indent=4)
        except Exception as e:
            logger.warning(f"Failed to save evaluation cache: {e}")

    if force_recalc:
        success_msg = "Successfully recalculated baseline heuristic metrics across the benchmark suite!"

    results = h_results
    avg_precision = h_precision
    avg_recall = h_recall
    avg_similarity = h_similarity

    if request.method == "POST":
        eval_mode = request.form.get("eval_mode", "openai").strip()
        openai_key = request.form.get("openai_key", "").strip()

        if eval_mode == "openai" and not openai_key:
            error_msg = "Please enter a valid OpenAI API Key to run RAGAS."
        else:
            try:
                if eval_mode == "ollama":
                    logger.info("Running RAGAS evaluation using local Ollama (Llama 3)...")
                    r_results, r_precision, r_recall = get_real_ragas_scorecard(use_ollama=True)
                else:
                    logger.info("Running RAGAS evaluation using OpenAI API Key...")
                    r_results, r_precision, r_recall = get_real_ragas_scorecard(openai_key=openai_key)

                if not r_results:
                    error_msg = "RAGAS evaluation failed. Please verify that your selected judge model is running."
                elif eval_mode == "openai" and (math.isnan(r_precision) or math.isnan(r_recall)):
                    error_msg = "Ragas returned NaN scores. Please verify your OpenAI billing quota."
                else:
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
                           avg_similarity=round(avg_similarity * 100, 2) if avg_similarity is not None and not math.isnan(float(avg_similarity)) else None,
                           is_real_ragas=is_real_ragas,
                           error_msg=error_msg,
                           success_msg=success_msg)


if __name__ == "__main__":
    # Never enable the Werkzeug debugger on a network-facing interface: it allows
    # arbitrary code execution. Opt in locally with FLASK_DEBUG=1.
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    app.run(debug=debug, host=host, port=5000, use_reloader=False)
