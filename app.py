from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os
import json
import re
import uuid
import hashlib
from db import db  

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', '.env'))

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL') 
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False               
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app) 

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'bmp', 'pdf'}

# API key from environment (fallback to legacy hardcoded for backward compat)
GROQ_API_KEY = os.getenv('GROQ_API_KEY', 'PUT YOUR API HERE')

# Multi-model fallback chain (primary → fallback)
GROQ_MODELS = [
    "meta-llama/llama-4-scout-17b-16e-instruct",    # Primary
    "meta-llama/llama-4-maverick-17b-128e-instruct", # Fallback
]
GROQ_MODEL = GROQ_MODELS[0]  # backward compat


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

from model import Medicine, Feedback, Prescription, Pharmacy, PharmacyInventory

brand_names = []
brand_names_lower = []
brand_to_generic = {}
brand_to_category = {}

with app.app_context():
    all_medicines = Medicine.query.all()
    for med in all_medicines:
        brand_names.append(med.brand)
        brand_to_generic[med.brand.lower()] = med.generic
        brand_to_category[med.brand.lower()] = med.category
    brand_names_lower = [b.lower() for b in brand_names]
    db.create_all()
    # print(f"Loaded {len(brand_names)} medicines from PostgreSQL")

# CRNN VALIDATOR (local CPU inference)

try:
    from crnn_engine import CRNNValidator
    crnn_validator = CRNNValidator()
    CRNN_READY = crnn_validator.ready
    print(f"[CRNN] CRNN_READY = {CRNN_READY}")
except Exception as e:
    import traceback
    print(f"[CRNN] Import/init failed: {e}")
    traceback.print_exc()
    crnn_validator = None
    CRNN_READY = False


# MATCHING ENGINE (rapidfuzz + jellyfish)

try:
    from rapidfuzz import fuzz as rf_fuzz, process as rf_process
    RAPIDFUZZ_OK = True
except ImportError:
    RAPIDFUZZ_OK = False
    print("[WARN] Install rapidfuzz: pip install rapidfuzz")

try:
    import jellyfish
    JELLYFISH_OK = True
except ImportError:
    JELLYFISH_OK = False
    print("[WARN] Install jellyfish: pip install jellyfish")


def edit_distance(s1, s2):
    """Levenshtein edit distance."""
    if len(s1) < len(s2):
        return edit_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[-1]


def match_medicine(name):

    name_lower = name.lower().strip()

    # Exact match
    if name_lower in brand_to_generic:
        idx = brand_names_lower.index(name_lower) if name_lower in brand_names_lower else -1
        match_name = brand_names[idx] if idx >= 0 else name
        generic = brand_to_generic.get(name_lower, '')
        category = brand_to_category.get(name_lower, '')
        return {
            'matched': True, 'match': match_name,
            'generic': generic,
            'category': category,
            'similarity': 1.0, 'status': 'exact',
            'status_text': 'Exact Match ✓',
            'status_class': 'verified',
            'db_status_text': 'DB_VERIFIED ✓ (sim: 100%)',
        }

    best = {'match': None, 'score': 0, 'generic': '', 'category': ''}

    if RAPIDFUZZ_OK and brand_names_lower:
        results = rf_process.extract(name_lower, brand_names_lower, scorer=rf_fuzz.ratio, limit=5)
        for match_lower, score, idx in results:
            fuzzy = score / 100.0
            partial = rf_fuzz.partial_ratio(name_lower, match_lower) / 100.0

            phon = 0.0
            if JELLYFISH_OK:
                try:
                    phon = jellyfish.jaro_winkler_similarity(
                        jellyfish.metaphone(name_lower), jellyfish.metaphone(match_lower))
                except:
                    pass

            if JELLYFISH_OK:
                ed = jellyfish.levenshtein_distance(name_lower, match_lower)
            else:
                ed = edit_distance(name_lower, match_lower)
            max_len = max(len(name_lower), len(match_lower), 1)
            edit_sc = max(0, 1.0 - (ed / max_len))

            combined = 0.35 * fuzzy + 0.25 * partial + 0.20 * phon + 0.20 * edit_sc

            if combined > best['score']:
                best = {
                    'match': brand_names[idx], 'score': combined,
                    'generic': brand_to_generic.get(match_lower, ''),
                    'category': brand_to_category.get(match_lower, ''),
                }
    else:
        for i, db_lower in enumerate(brand_names_lower):
            ed = edit_distance(name_lower, db_lower)
            sc = max(0, 1.0 - (ed / max(len(name_lower), len(db_lower), 1)))
            if sc > best['score']:
                best = {
                    'match': brand_names[i], 'score': sc,
                    'generic': brand_to_generic.get(db_lower, ''),
                    'category': brand_to_category.get(db_lower, ''),
                }

    sim_pct = round(best['score'] * 100)

    if best['score'] >= 0.85:
        status, cls = 'Verified', 'verified'
        db_st = f"DB_VERIFIED (sim: {sim_pct}%)"
    elif best['score'] >= 0.70:
        status, cls = 'Likely Match', 'likely'
        db_st = f"DB_LIKELY → {best['match']} (sim: {sim_pct}%)"
    elif best['score'] >= 0.50:
        status, cls = 'Possible Match', 'possible'
        db_st = f"DB_POSSIBLE → {best['match']} (sim: {sim_pct}%)"
    else:
        status, cls = 'Unverified', 'unverified'
        db_st = f"DB_UNVERIFIED (sim: {sim_pct}%)"

    return {
        'matched': best['score'] >= 0.50,
        'match': best['match'] or '',
        'generic': best['generic'], 'category': best['category'],
        'similarity': best['score'],
        'status_text': status, 'status_class': cls,
        'db_status_text': db_st,
    }

# HALLUCINATION FILTER (Multi-Signal Scoring)

COMMON_WORDS = {
    'the', 'and', 'for', 'with', 'that', 'this', 'from', 'have',
    'day', 'days', 'daily', 'morning', 'evening', 'night',
    'take', 'use', 'apply', 'water', 'food', 'milk', 'oil',
    'before', 'after', 'meal', 'meals', 'times', 'once', 'twice',
    'doctor', 'patient', 'hospital', 'clinic', 'date', 'name',
    'address', 'age', 'sex', 'male', 'female', 'reg', 'dressing',
    'tablet', 'capsule', 'syrup', 'injection', 'cream', 'ointment',
    'drops', 'solution', 'suspension', 'powder', 'gel', 'lotion',
    'diagnosis', 'advice', 'follow', 'rest', 'diet', 'exercise',
}


def compute_hallucination_score(name, db_result, api_conf, crnn_result=None):
    """
    Multi-signal hallucination scoring.
    Returns 0.0 (definitely real) to 1.0 (definitely fake).
    """
    name_lower = name.lower().strip()

    # Instant rejects
    if len(name) < 3:
        return 1.0
    if name_lower in COMMON_WORDS:
        return 1.0
    if name.isdigit():
        return 1.0

    signals = []

    # Signal 1: DB similarity (strongest signal, weight=0.35)
    db_sim = db_result.get('similarity', 0)
    if db_sim >= 0.85:
        signals.append(('db_strong', 0.0, 0.35))
    elif db_sim >= 0.70:
        signals.append(('db_likely', 0.15, 0.30))
    elif db_sim >= 0.50:
        signals.append(('db_weak', 0.40, 0.25))
    else:
        signals.append(('db_miss', 0.80, 0.30))

    # Signal 2: API confidence (weight=0.25)
    conf_map = {'high': 0.1, 'medium': 0.4, 'low': 0.7}
    api_score = conf_map.get(api_conf, 0.5)
    signals.append(('api_conf', api_score, 0.25))

    # Signal 3: CRNN agreement (weight=0.20, if available)
    if crnn_result and crnn_result.get('crnn_confidence', 0) > 0:
        crnn_match = crnn_result.get('match_score', 0)
        crnn_score = max(0, 1.0 - crnn_match)
        signals.append(('crnn', crnn_score, 0.20))

    # Signal 4: Name pattern heuristics (weight=0.15)
    pattern_score = 0.0
    if not re.match(r'^[A-Za-z][A-Za-z0-9 +\-\.]{1,24}$', name):
        pattern_score = 0.6
    if len(name) > 25:
        pattern_score = 0.7
    signals.append(('pattern', pattern_score, 0.15))

    # Weighted combination
    total_weight = sum(w for _, _, w in signals)
    weighted_sum = sum(s * w for _, s, w in signals)
    return round(weighted_sum / total_weight, 3) if total_weight > 0 else 0.5


def is_hallucination(name, db_result, api_conf, crnn_result=None, threshold=0.55):
    """Returns True if the hallucination score exceeds threshold."""
    score = compute_hallucination_score(name, db_result, api_conf, crnn_result)
    return score >= threshold

def convert_pdf_to_image(pdf_path):
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("[PDF] PyMuPDF not installed. Run: pip install PyMuPDF")
        return None

    try:
        doc = fitz.open(pdf_path)
        if len(doc) == 0:
            return None

        page = doc[0]
        # Render at 2x zoom for better OCR quality
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)

        img_path = pdf_path.rsplit('.', 1)[0] + '_page1.jpg'
        pix.save(img_path)
        doc.close()

        print(f"[PDF] Converted page 1 → {img_path}")
        return img_path
    except Exception as e:
        print(f"[PDF] Conversion error: {e}")
        return None

def clean_medicine_name(name):
    """Remove prefixes like Tab., Cap., Syr. and clean up."""
    if not name:
        return ''
    name = re.sub(r'^(Tab\.?|Cap\.?|Syr\.?|Inj\.?|Susp\.?|Cr\.?|Oint\.?)\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def preprocess_prescription_image(image_path):
    """
    Enhance prescription image for better OCR:
    1. Enhance contrast
    2. Sharpen blurry handwriting
    3. Upscale if too small
    Returns path to preprocessed image.
    """
    from PIL import Image as PILImage, ImageFilter, ImageEnhance

    try:
        img = PILImage.open(image_path).convert('RGB')

        # Step 1: Enhance contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)

        # Step 2: Sharpen
        img = img.filter(ImageFilter.SHARPEN)

        # Step 3: Upscale small images
        w, h = img.size
        min_dim = 800
        if max(w, h) < min_dim:
            scale = min_dim / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), PILImage.LANCZOS)

        preprocessed_path = image_path.rsplit('.', 1)[0] + '_preprocessed.jpg'
        img.save(preprocessed_path, quality=95)
        return preprocessed_path
    except Exception as e:
        print(f"[PREPROCESS] Error: {e}, using original image")
        return image_path


def build_enhanced_prompt(brand_names_sample):
    """
    Build a DB-grounded prompt that includes a representative medicine list.
    This dramatically reduces hallucinations by giving the LLM real names to match against.
    """
    med_list = sorted(set(brand_names_sample[:200]))
    med_str = ", ".join(med_list)

    return (
        "You are an expert pharmacist carefully reading a handwritten medical prescription image.\n\n"
        "STRICT RULES (follow exactly):\n"
        "1. Extract ONLY medicine/drug names that you can CLEARLY READ in the handwriting\n"
        "2. If you CANNOT read a word clearly, skip it — do NOT guess or make up names\n"
        "3. Remove prefixes: Tab/Tab./Cap/Cap./Syr/Syr./Inj/Inj.\n"
        "4. A medicine name should be a real pharmaceutical drug — not random words\n"
        "5. PREFER matching to known Indian medicine brands when handwriting is ambiguous\n"
        "6. For each medicine, rate your reading confidence HONESTLY:\n"
        "   - 'high': every letter is clearly readable\n"
        "   - 'medium': some letters are ambiguous but the word is likely correct\n"
        "   - 'low': significant guessing involved — include anyway but mark low\n\n"
        f"REFERENCE — Common Indian medicine brands (use to resolve ambiguous handwriting):\n"
        f"{med_str}\n\n"
        "ALSO extract these prescription details (if visible):\n"
        "- doctor_name: the prescribing doctor's name (from header/stamp)\n"
        "- clinic_address: hospital/clinic address (from header/stamp)\n"
        "- pincode: 6-digit Indian postal code (from the address, if visible)\n\n"
        "For EACH medicine you can clearly read, provide:\n"
        '- "medicine_name": the drug name (just the name, no Tab/Cap prefix)\n'
        '- "dosage": like 500mg, 250mg, 10mg. Use "" if not visible\n'
        '- "frequency": like 1-0-1, 2+0+2, BD, TDS, OD. Use "" if not visible\n'
        '- "confidence": "high", "medium", or "low"\n\n'
        'If NO medicines can be clearly read, return: {"medicines": [], "doctor_name": "", "clinic_address": "", "pincode": ""}\n\n'
        "Return ONLY valid JSON, no other text:\n"
        '{"medicines": [{"medicine_name": "...", "dosage": "...", "frequency": "...", "confidence": "..."}],'
        ' "doctor_name": "...", "clinic_address": "...", "pincode": "..."}'
    )


def _parse_api_response(raw):
    """Parse JSON from Groq API response. Returns dict or None."""
    if '```' in raw:
        raw = re.sub(r'```(?:json)?\s*', '', raw).replace('```', '')
    raw = raw.strip()
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())

            medicines = []
            if 'medicines' in data:
                for m in data['medicines']:
                    name = clean_medicine_name(m.get('medicine_name', '') or m.get('name', ''))
                    if name and len(name) >= 2:
                        medicines.append({
                            'name': name,
                            'dosage': str(m.get('dosage', '') or '').strip(),
                            'frequency': str(m.get('frequency', '') or '').strip(),
                            'api_confidence': m.get('confidence', 'medium'),
                        })

            doctor_name = str(data.get('doctor_name', '') or '').strip()
            clinic_address = str(data.get('clinic_address', '') or '').strip()
            pincode = str(data.get('pincode', '') or '').strip()

            if pincode and not re.match(r'^\d{6}$', pincode):
                pincode = ''

            return {
                'medicines': medicines,
                'doctor_name': doctor_name,
                'clinic_address': clinic_address,
                'pincode': pincode,
            }
        except (json.JSONDecodeError, KeyError):
            return None
    return None


def call_groq_api(image_path):
    """
    Enhanced Groq API call with:
    1. DB-grounded prompt (includes medicine reference list)
    2. Image preprocessing (contrast + sharpen)
    3. Multi-model fallback chain
    4. Exponential backoff on rate limits
    Returns (result_dict, error_string).
    """
    import time as _time

    try:
        from groq import Groq
        import base64
        import io
        from PIL import Image as PILImage
    except ImportError:
        return None, "Install dependencies: pip install groq Pillow"

    # Preprocess image for better extraction
    processed_path = preprocess_prescription_image(image_path)

    # Build DB-grounded prompt
    prompt = build_enhanced_prompt(brand_names)

    # Prepare image
    try:
        img = PILImage.open(processed_path).convert('RGB')
        w, h = img.size
        max_px = 1024
        if max(w, h) > max_px:
            scale = max_px / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), PILImage.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=95)
        b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    except Exception as e:
        return None, f"Image processing error: {e}"

    gc = Groq(api_key=GROQ_API_KEY)

    # Try each model in fallback chain
    for model_idx, model in enumerate(GROQ_MODELS):
        for attempt in range(3):
            try:
                resp = gc.chat.completions.create(
                    model=model,
                    messages=[{'role': 'user', 'content': [
                        {'type': 'text', 'text': prompt},
                        {'type': 'image_url', 'image_url': {
                            'url': f'data:image/jpeg;base64,{b64}'
                        }}
                    ]}],
                    max_tokens=1024,
                    temperature=0.0,
                )

                raw = resp.choices[0].message.content.strip()
                parsed = _parse_api_response(raw)
                if parsed is not None:
                    parsed['_model_used'] = model
                    parsed['_attempt'] = attempt + 1
                    return parsed, None

                # If parsing failed, still return empty rather than retrying
                return {'medicines': [], 'doctor_name': '', 'clinic_address': '', 'pincode': ''}, None

            except Exception as e:
                err_str = str(e)
                if '429' in err_str:
                    wait = min(15 * (2 ** attempt), 120)
                    print(f"[API] Rate limited, waiting {wait}s (attempt {attempt+1})...")
                    _time.sleep(wait)
                elif '503' in err_str or '500' in err_str:
                    _time.sleep(5 * (attempt + 1))
                else:
                    _time.sleep(3)

        if model_idx < len(GROQ_MODELS) - 1:
            print(f"[API] Model {model} failed, trying fallback...")

    return None, "All Groq models failed after retries"


def compute_combined_score(db_similarity, crnn_confidence, api_confidence_str, hallucination_score):
    """
    Compute a final confidence score (0-100) combining all signals.
    """
    db_pct = db_similarity * 100
    crnn_pct = crnn_confidence * 100 if crnn_confidence > 0 else None

    api_map = {'high': 90, 'medium': 60, 'low': 30}
    api_pct = api_map.get(api_confidence_str, 50)

    hall_penalty = hallucination_score * 40

    if crnn_pct is not None and crnn_pct > 0:
        raw = (db_pct * 0.40 + crnn_pct * 0.25 + api_pct * 0.20 +
               (100 - hall_penalty) * 0.15)
    else:
        raw = (db_pct * 0.50 + api_pct * 0.30 +
               (100 - hall_penalty) * 0.20)

    return max(0, min(100, round(raw)))

# FULL ANALYSIS PIPELINE

def analyze_prescription(image_path):
    """
    Full pipeline: Groq API → CRNN Validation → Medicine Matching → Hallucination Filter
    Returns dict with results matching Colab pipeline output format.
    Now also includes: doctor_name, clinic_address, pincode.
    """
    # Stage 1: Groq API (enhanced)
    api_result, error = call_groq_api(image_path)

    if error:
        return {'error': error, 'medicines': [], 'rejected': [], 'stats': {},
                'doctor_name': '', 'clinic_address': '', 'pincode': ''}

    if api_result is None:
        return {'error': 'API call failed', 'medicines': [], 'rejected': [], 'stats': {},
                'doctor_name': '', 'clinic_address': '', 'pincode': ''}

    medicines_raw = api_result.get('medicines', [])
    doctor_name = api_result.get('doctor_name', '')
    clinic_address = api_result.get('clinic_address', '')
    pincode = api_result.get('pincode', '')

    if not medicines_raw:
        return {'error': None, 'medicines': [], 'rejected': [],
                'stats': {'total': 0, 'accepted': 0, 'rejected': 0, 'verified': 0},
                'doctor_name': doctor_name, 'clinic_address': clinic_address, 'pincode': pincode}

    # Stage 2 & 3: CRNN Validation + DB Match + Multi-Signal Hallucination Filter
    accepted = []
    rejected = []

    for med in medicines_raw:
        db_result = match_medicine(med['name'])
        api_conf = med.get('api_confidence', 'medium')

        # Similarity percentage
        sim_pct = round(db_result['similarity'] * 100)

        # Generic display: "GenericName [Category]" matching Colab format
        generic = db_result.get('generic', '')
        category = db_result.get('category', '')
        generic_display = ''
        if generic:
            generic_display = f"{generic} [{category}]" if category else generic

        # CRNN Validation (local CPU inference)
        crnn_conf_pct = 0
        crnn_result = None
        if CRNN_READY:
            crnn_result = crnn_validator.validate(med['name'])
            crnn_status = crnn_result['status']
            crnn_conf_pct = round(crnn_result['crnn_confidence'] * 100)
            crnn_status = f"{crnn_status} (conf: {crnn_conf_pct}%)"
        else:
            crnn_status = 'N/A (model not loaded)'

        # Multi-signal hallucination scoring
        hall_score = compute_hallucination_score(med['name'], db_result, api_conf, crnn_result)
        hallucinated = hall_score >= 0.55

        # DB status text — matching Colab format
        db_status = db_result.get('db_status_text', f'sim: {sim_pct}%')

        # Improved combined scoring with all signals
        crnn_conf_raw = crnn_result['crnn_confidence'] if crnn_result else 0
        combined = compute_combined_score(
            db_result['similarity'], crnn_conf_raw, api_conf, hall_score
        )

        # Final status — matching Colab verdict format
        if hallucinated:
            final_status = '✗ REJECTED (hallucination)'
            final_status_class = 'rejected'
        elif db_result['similarity'] >= 0.85:
            final_status = f'✓ DB VERIFIED (score: {combined}%)'
            final_status_class = 'fully-verified'
        elif db_result['similarity'] >= 0.70:
            final_status = f'◐ LIKELY MATCH (score: {combined}%)'
            final_status_class = 'likely-verified'
        elif db_result['similarity'] >= 0.50:
            final_status = f'◐ PARTIALLY VERIFIED (score: {combined}%)'
            final_status_class = 'partial-verified'
        else:
            final_status = f'△ NEEDS REVIEW (score: {combined}%)'
            final_status_class = 'needs-review'

        entry = {
            'name': med['name'],
            'dosage': med.get('dosage', ''),
            'frequency': med.get('frequency', ''),
            'api_confidence': api_conf,
            'db_match': db_result.get('match', ''),
            'generic': generic,
            'category': category,
            'generic_display': generic_display,
            'similarity': sim_pct,
            'status_text': db_result.get('status_text', ''),
            'status_class': db_result.get('status_class', 'unverified'),
            'crnn_status': crnn_status,
            'db_status': db_status,
            'final_status': final_status,
            'final_status_class': final_status_class,
            'combined_score': combined,
            'hallucination_score': round(hall_score, 3),
            'is_hallucination': hallucinated,
        }

        if hallucinated:
            rejected.append(entry)
        else:
            accepted.append(entry)

    accepted.sort(key=lambda x: x['combined_score'], reverse=True)

    verified_count = sum(1 for m in accepted if m['final_status_class'] in ('fully-verified',))

    return {
        'error': None,
        'medicines': accepted,
        'rejected': rejected,
        'stats': {
            'total': len(medicines_raw),
            'accepted': len(accepted),
            'rejected': len(rejected),
            'verified': verified_count,
        },
        'doctor_name': doctor_name,
        'clinic_address': clinic_address,
        'pincode': pincode,
    }

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    if 'prescription' not in request.files:
        return render_template('index.html', error='No file uploaded')

    file = request.files['prescription']
    if file.filename == '':
        return render_template('index.html', error='No file selected')

    if not allowed_file(file.filename):
        return render_template('index.html', error='Invalid file type. Use JPG, PNG, WEBP, BMP, or PDF.')

    # Read file bytes and compute SHA-256 hash for duplicate detection
    file_bytes = file.read()
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    ext = file.filename.rsplit('.', 1)[1].lower()

    # ── Check prescription cache (DB) ──
    cached_rx = Prescription.query.filter_by(image_hash=file_hash).first()
    if cached_rx and cached_rx.raw_result:
        print(f"[CACHE] Reusing stored prescription {cached_rx.id[:8]}…")
        result = cached_rx.raw_result

        # Still need the image file for display
        hash_index_path = os.path.join(app.config['UPLOAD_FOLDER'], '.hash_index.json')
        hash_index = {}
        if os.path.exists(hash_index_path):
            try:
                with open(hash_index_path, 'r') as f:
                    hash_index = json.load(f)
            except (json.JSONDecodeError, IOError):
                hash_index = {}
        filename = hash_index.get(file_hash, f"{file_hash[:12]}.{ext}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(filepath):
            with open(filepath, 'wb') as f:
                f.write(file_bytes)
            hash_index[file_hash] = filename
            with open(hash_index_path, 'w') as f:
                json.dump(hash_index, f)

        return render_template('results.html',
                               result=result,
                               image_file=filename,
                               original_name=file.filename,
                               prescription_id=cached_rx.id)

    # ── Save file (deduplicate by hash) ──
    hash_index_path = os.path.join(app.config['UPLOAD_FOLDER'], '.hash_index.json')
    hash_index = {}
    if os.path.exists(hash_index_path):
        try:
            with open(hash_index_path, 'r') as f:
                hash_index = json.load(f)
        except (json.JSONDecodeError, IOError):
            hash_index = {}

    if file_hash in hash_index:
        filename = hash_index[file_hash]
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(filepath):
            filename = f"{file_hash[:12]}.{ext}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            with open(filepath, 'wb') as f:
                f.write(file_bytes)
            hash_index[file_hash] = filename
    else:
        filename = f"{file_hash[:12]}.{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(filepath, 'wb') as f:
            f.write(file_bytes)
        hash_index[file_hash] = filename

    with open(hash_index_path, 'w') as f:
        json.dump(hash_index, f)

    # ── PDF → Image conversion ──
    analyze_path = filepath
    if ext == 'pdf':
        img_path = convert_pdf_to_image(filepath)
        if img_path:
            analyze_path = img_path
        else:
            return render_template('index.html', error='Could not process PDF. Please upload an image instead.')

    # ── Analyze ──
    result = analyze_prescription(analyze_path)

    # ── Store prescription in DB for caching ──
    prescription_id = str(uuid.uuid4())
    try:
        rx = Prescription(
            id=prescription_id,
            image_hash=file_hash,
            medicines=[{
                'name': m['name'],
                'dosage': m.get('dosage', ''),
                'frequency': m.get('frequency', ''),
            } for m in result.get('medicines', [])],
            doctor_name=result.get('doctor_name', ''),
            clinic_address=result.get('clinic_address', ''),
            pincode=result.get('pincode', ''),
            raw_result=result,
        )
        db.session.add(rx)
        db.session.commit()
        print(f"[DB] Stored prescription {prescription_id[:8]}…")
    except Exception as e:
        print(f"[DB] Failed to store prescription: {e}")
        db.session.rollback()

    return render_template('results.html',
                           result=result,
                           image_file=filename,
                           original_name=file.filename,
                           prescription_id=prescription_id)


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    from flask import send_from_directory
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.ico') if os.path.exists(
        os.path.join(app.static_folder, 'favicon.ico')
    ) else ('', 204)


# ── PHARMACY FINDER ROUTES ───────────────────────────────────

@app.route('/pharmacies/<prescription_id>')
def pharmacies_page(prescription_id):
    """Render pharmacy results page for a given prescription."""
    rx = db.session.get(Prescription, prescription_id)
    if not rx:
        return render_template('index.html', error='Prescription not found. Please upload again.')

    return render_template('pharmacies.html',
                           prescription=rx,
                           prescription_id=prescription_id)

@app.route('/api/find-pharmacies', methods=['POST'])
def api_find_pharmacies():
    """
    API endpoint: find pharmacies with medicine availability.
    Accepts: { prescription_id, pincode, lat, lng, medicines[] }
    Prefers lat/lng for geo search, falls back to pincode.
    """
    from pharmacy_finder import find_pharmacies_with_medicines

    data = request.get_json(silent=True) or {}

    prescription_id = data.get('prescription_id')
    pincode = data.get('pincode', '').strip()
    medicine_names = data.get('medicines', [])
    user_lat = data.get('lat')    
    user_lng = data.get('lng')   

    # If prescription_id provided, load medicines from DB
    if prescription_id and not medicine_names:
        rx = db.session.get(Prescription, prescription_id)
        if rx:
            medicine_names = [m['name'] for m in (rx.medicines or [])]
            if not pincode:
                pincode = rx.pincode or ''

    if not medicine_names:
        return jsonify({'error': 'No medicines provided', 'pharmacies': []}), 400

    if not pincode and user_lat is None:
        return jsonify({'error': 'No location provided. Please enter a pincode or enable location.', 'pharmacies': []}), 400

    # Convert lat/lng to float if provided
    try:
        if user_lat is not None:
            user_lat = float(user_lat)
        if user_lng is not None:
            user_lng = float(user_lng)
    except (ValueError, TypeError):
        user_lat, user_lng = None, None

    results = find_pharmacies_with_medicines(
        medicines=medicine_names,
        lat=user_lat,
        lng=user_lng,
        pincode=pincode,
        db_session=db.session,
    )

    return jsonify({
        'error': None,
        'pincode': pincode,
        'lat': user_lat,
        'lng': user_lng,
        'medicines_searched': medicine_names,
        'pharmacies': results,
        'total': len(results),
    })


@app.route('/api/prescription/<prescription_id>')
def api_get_prescription(prescription_id):
    """Return stored prescription data (for cache reuse)."""
    rx = db.session.get(Prescription, prescription_id)
    if not rx:
        return jsonify({'error': 'Not found'}), 404

    return jsonify({
        'id': rx.id,
        'medicines': rx.medicines or [],
        'doctor_name': rx.doctor_name or '',
        'clinic_address': rx.clinic_address or '',
        'pincode': rx.pincode or '',
        'created_at': rx.created_at.isoformat() if rx.created_at else None,
    })


@app.route('/api/location', methods=['POST'])
def api_location():
    """
    Reverse geocode: { lat, lng } → pincode.
    Uses Google Geocoding API if key available, else mock fallback.
    """
    from pharmacy_finder import reverse_geocode_to_pincode

    data = request.get_json(silent=True) or {}
    lat = data.get('lat')
    lng = data.get('lng')

    if lat is None or lng is None:
        return jsonify({'error': 'lat and lng required'}), 400

    lat_f = float(lat)
    lng_f = float(lng)
    pincode = reverse_geocode_to_pincode(lat_f, lng_f)

    return jsonify({
        'pincode': pincode or '',
        'lat': lat_f,
        'lng': lng_f,
        'source': 'geolocation',
    })


# ── FEEDBACK ROUTES (unchanged) ──────────────────────────────

@app.route('/api/feedback', methods=['POST'])
def submit_feedback():
    """Store user feedback in PostgreSQL with enhanced tracking."""
    data = request.get_json(silent=True)
    if not data or 'medicine_name' not in data:
        return jsonify({'error': 'Missing medicine_name'}), 400

    corrected = data.get('corrected_name', '')
    is_correct = data.get('is_correct', corrected == '' or corrected == data.get('medicine_name', ''))

    entry = Feedback(
        image_hash=data.get('image_hash', ''),
        original_text=data.get('medicine_name', ''),
        corrected_text=corrected,
        feedback_type='confirmation' if is_correct else 'correction',
        api_confidence=data.get('api_confidence', ''),
        db_similarity=data.get('db_similarity'),
        used_in_training=False,
    )
    db.session.add(entry)
    db.session.commit()

    total = Feedback.query.count()
    return jsonify({'status': 'ok', 'total_feedbacks': total})


@app.route('/api/feedback', methods=['GET'])
def get_feedback():
    """Return all stored feedback from PostgreSQL."""
    rows = Feedback.query.order_by(Feedback.created_at.desc()).all()
    return jsonify([
        {
            'id': r.id,
            'original_text': r.original_text,
            'corrected_text': r.corrected_text,
            'image_hash': r.image_hash,
            'created_at': r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ])



# ── CRNN HOT-RELOAD ──────────────────────────────────────────

def check_model_reload():
    """Check if a new CRNN model is available and reload it."""
    global crnn_validator, CRNN_READY

    reload_flag = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'models', 'checkpoints', '.reload_requested'
    )

    if os.path.exists(reload_flag):
        try:
            from crnn_engine import CRNNValidator
            new_validator = CRNNValidator()
            if new_validator.ready:
                crnn_validator = new_validator
                CRNN_READY = True
                os.remove(reload_flag)
                print("[CRNN] ✓ Hot-reloaded new model")
            else:
                print("[CRNN] ✗ New model failed to load, keeping previous")
        except Exception as e:
            print(f"[CRNN] Hot-reload error: {e}")


@app.before_request
def _before_request_hooks():
    """Lightweight per-request checks."""
    # Check for CRNN model hot-reload (only checks file existence, very fast)
    check_model_reload()


# ── SCHEDULER INITIALIZATION ─────────────────────────────────

retraining_scheduler = None

if __name__ == '__main__':
    # Start retraining scheduler (only in main process, not reloader)
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        try:
            from scheduler import init_scheduler
            retraining_scheduler = init_scheduler(app)
        except Exception as e:
            print(f"[SCHEDULER] Init failed: {e}")

    print("\n" + "=" * 60)
    print("  PRESCRIPTION RECOGNITION — WEB DEMO")
    print("  Open: http://localhost:5000")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)
