"""
============================================================================
 MEDICINE AVAILABILITY — Smart Estimation Module
============================================================================
 Since real-time pharmacy stock data is not publicly available in India,
 this module estimates medicine availability using:

 Tier 1: Common/OTC medicines (likely at any pharmacy)
 Tier 2: Major chain pharmacy detection (stock 90%+ of brands)
 Tier 3: Category-based estimation
 Tier 4: Fallback — "Call to Confirm"
============================================================================
"""


# ── Tier 1: Common medicines every Indian pharmacy stocks ─────

ALWAYS_AVAILABLE = {
    # Analgesics / Fever
    "paracetamol", "dolo 650", "dolo", "crocin", "calpol", "combiflam",
    "ibuprofen", "diclofenac", "voveran", "brufen", "meftal",
    "sumo", "disprin", "saridon", "dart",

    # Antibiotics (common oral)
    "amoxicillin", "amoxyclav", "augmentin", "azithromycin", "azee",
    "ciprofloxacin", "ciplox", "ofloxacin", "levofloxacin",
    "cefixime", "zifi", "cephalexin", "metronidazole", "flagyl",
    "doxycycline", "norfloxacin",

    # Antacids / GI
    "omeprazole", "pantoprazole", "pan", "pantop", "ranitidine", "rantac",
    "esomeprazole", "rabeprazole", "digene", "gelusil", "eno",
    "ondansetron", "emeset", "domperidone", "domstal",
    "loperamide", "imodium", "ors",

    # Antihistamines / Allergy
    "cetirizine", "cetzine", "allegra", "fexofenadine", "avil",
    "levocetirizine", "montair", "montelukast",
    "chlorpheniramine",

    # Cough & Cold
    "benadryl", "grilinctus", "ascoril", "chericof", "dextromethorphan",
    "sinarest", "vicks", "otrivin", "nasivion", "strepsils",

    # Diabetes
    "metformin", "glycomet", "glimepiride", "amaryl",
    "gliclazide", "voglibose", "sitagliptin",

    # Cardiovascular
    "amlodipine", "atenolol", "losartan", "telmisartan", "ramipril",
    "aspirin", "ecosprin", "clopidogrel", "atorvastatin",
    "rosuvastatin", "metoprolol",

    # Vitamins & Supplements
    "becosules", "vitamin c", "limcee", "shelcal", "calcium",
    "iron", "folic acid", "b complex", "multivitamin", "revital",
    "zincovit", "supradyn",

    # Dermatology (OTC)
    "betadine", "soframycin", "neosporin", "clotrimazole", "candid",
    "clobetasol", "momate", "calamine", "lacto calamine",

    # Eye / Ear
    "ciprofloxacin eye drops", "moxifloxacin", "refresh tears",

    # Pain / Muscle
    "aceclofenac", "hifenac", "thiocolchicoside", "myospaz",
    "pregabalin", "gabapentin", "tramadol",

    # Others
    "betahistine", "vertin", "prochlorperazine", "stemetil",
    "hydroxyzine", "alprazolam", "clonazepam",
}

# Normalize all to lowercase
ALWAYS_AVAILABLE = {med.lower() for med in ALWAYS_AVAILABLE}


# ── Tier 2: Major pharmacy chains (stock 90%+ of brands) ─────

MAJOR_CHAINS = [
    "apollo pharmacy", "apollo", "medplus", "med plus",
    "netmeds", "pharmeasy", "1mg", "tata 1mg",
    "wellness forever", "frank ross",
    "guardian pharmacy", "guardian",
    "jan aushadhi", "janaushadhi",
    "davaindia", "noble plus",
    "healthkart", "health kart",
    "care pharmacy", "sanjivani",
    "new medical store",  # common generic chain name
]

# Categories that are widely available
COMMON_CATEGORIES = {
    "Analgesic", "Analgesics", "NSAID",
    "Antibiotic", "Antibiotics",
    "Antacid", "Antacids", "Proton Pump Inhibitor",
    "Antihistamine", "Antihistamines",
    "Vitamin", "Vitamins", "Supplement", "Supplements",
    "Antidiabetic", "Diabetes",
    "Antihypertensive", "Cardiovascular",
    "Antipyretic", "Fever",
    "Cough", "Cold", "Decongestant",
}


# ── Main Estimation Function ─────────────────────────────────

def estimate_availability(pharmacy_name, medicine_name, medicine_category=None):
    """
    Estimate whether a pharmacy is likely to have a medicine in stock.

    Returns:
        dict: {
            'available': bool or None,
            'confidence': 'high' | 'medium' | 'low',
            'label': str (display text),
            'icon': str (emoji/symbol for UI),
        }
    """
    med_lower = medicine_name.lower().strip()
    name_lower = pharmacy_name.lower().strip()

    # ── Tier 1: Common/Essential medicine ──
    # Check both exact match and partial (e.g., "Dolo 650" matches "dolo")
    is_common = med_lower in ALWAYS_AVAILABLE
    if not is_common:
        # Check if any word in the medicine name matches
        for known_med in ALWAYS_AVAILABLE:
            if known_med in med_lower or med_lower in known_med:
                is_common = True
                break

    if is_common:
        return {
            'available': True,
            'confidence': 'high',
            'label': 'Likely Available',
            'icon': '✅',
        }

    # ── Tier 2: Major chain pharmacy ──
    is_chain = any(chain in name_lower for chain in MAJOR_CHAINS)
    if is_chain:
        return {
            'available': True,
            'confidence': 'medium',
            'label': 'Probably Available',
            'icon': '🟡',
        }

    # ── Tier 3: Common category ──
    if medicine_category:
        cat_lower = medicine_category.strip()
        if cat_lower in COMMON_CATEGORIES:
            return {
                'available': True,
                'confidence': 'medium',
                'label': 'Probably Available',
                'icon': '🟡',
            }

    # ── Tier 4: Unknown → fallback ──
    return {
        'available': None,
        'confidence': 'low',
        'label': 'Call to Confirm',
        'icon': '📞',
    }
