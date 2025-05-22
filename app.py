import os
import re
import yaml
import glob
import random
from datetime import datetime
from flask import Flask, render_template, request, jsonify

# Optional: pip install rapidfuzz sentence-transformers
try:
    from rapidfuzz import process, fuzz
    rapidfuzz_available = True
except ImportError:
    rapidfuzz_available = False

try:
    from sentence_transformers import SentenceTransformer, util as st_util
    sentencetr_available = True
    # You can use a small Italian-capable model, e.g., 'paraphrase-multilingual-MiniLM-L12-v2'
    st_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
except Exception:
    sentencetr_available = False
    st_model = None

# --- Spellchecker: Italian dictionary from root ---
try:
    from spellchecker import SpellChecker
    spell = SpellChecker(language=None, local_dictionary="it.json.gz")
    spellchecker_available = True
except Exception:
    spell = None
    spellchecker_available = False

app = Flask(__name__)

CORPUS_PATH = os.environ.get("CORPUS_PATH", os.path.join(os.path.dirname(__file__), "corpus"))

# --- LOAD ALL YAML FILES (Q/A PAIRS) ---
all_qa_pairs = []
for yml_file in glob.glob(os.path.join(CORPUS_PATH, "*.yml")):
    with open(yml_file, encoding='utf-8') as f:
        data = yaml.safe_load(f)
        conversations = data.get('conversations', [])
        for conv in conversations:
            if isinstance(conv, list) and len(conv) >= 2:
                q, *a = conv
                if q is not None:
                    all_qa_pairs.append((
                        q.strip(),
                        " ".join([str(x) for x in a if x is not None])
                    ))

# --- Text normalization ---
def normalize(text):
    return re.sub(r'[^\w\s]', '', text.strip().lower())

def correct_spelling(text):
    if not spellchecker_available or not text:
        return text
    try:
        words = text.split()
        corrected_words = [spell.correction(w) or w for w in words]
        return ' '.join(corrected_words)
    except Exception:
        return text

def extract_keywords(text):
    stopwords = set([
        "il", "lo", "la", "i", "gli", "le", "un", "una", "che", "di", "a", "da", "in", "con", "su", "per", "tra", "fra",
        "mi", "ti", "si", "ci", "vi", "lui", "lei", "noi", "voi", "loro", "sono", "sei", "è", "siamo", "siete",
        "ho", "hai", "ha", "abbiamo", "avete", "hanno", "era", "eri", "fu", "fui", "eravamo", "eravate", "erano",
        "ma", "e", "o", "ed", "anche", "come", "quando", "dove", "chi", "cosa", "perche", "perché",
        "quali", "qual", "quale", "questo", "questa", "quello", "quella", "questi", "quelle", "quelli", "al", "agli", "alle", "agli",
        "del", "della", "dello", "degli", "delle", "dei", "sul", "sullo", "sulla", "sulle", "sui", "agli", "all", "alla", "allo", "alle",
        "queste", "questo", "questi", "quella", "quello", "quelle", "quelli", "tu", "te", "io", "noi", "voi", "loro",
        "piu", "meno", "molto", "tanto", "tutta", "tutto", "tutti", "tutte", "ogni", "alcuni", "alcune"
    ])
    words = [w for w in normalize(text).split() if w not in stopwords and len(w) > 2]
    return set(words)

def is_probably_italian(text):
    italian_keywords = [
        "ciao", "come", "puoi", "aiutarmi", "grazie", "prenotare", "test", "udito", "orari", "info", "salve", "quanto", "dove", "chi", "cosa", "quale", "azienda"
    ]
    text_lc = text.lower()
    matches = sum(kw in text_lc for kw in italian_keywords)
    if matches == 0 and len(extract_keywords(text)) >= 2:
        if re.search(r"[а-яёΑ-ωЀ-ӿ]", text):
            return False
        english_starters = ["what", "who", "how", "when", "where", "why", "can you", "could you", "please", "help"]
        if any(text_lc.strip().startswith(st) for st in english_starters):
            return False
    return True

# --- TIME/DATE DETECTION & ANSWER ---
def detect_time_or_date_question(msg):
    msg_lc = msg.strip().lower()
    msg_simple = (
        msg_lc.replace("é", "e")
        .replace("è", "e")
        .replace("à", "a")
        .replace("ò", "o")
        .replace("ù", "u")
        .replace("ì", "i")
    )
    time_patterns = [
        r"che\s*ore\s*sono",
        r"che\s*ora\s*(è|e)?",
        r"mi\s*(puoi)?\s*dire\s*l'?ora",
        r"orario\s*(attuale|corrente)",
        r"adesso\s*che\s*ore\s*sono",
        r"chi\s*ora\s*sono",
        r"ora\s*attuale",
        r"ora\s*e",
    ]
    date_patterns = [
        r"che\s*giorno\s*(è|e)?",
        r"che\s*giorno\s*è\s*oggi",
        r"data\s*di\s*oggi",
        r"oggi\s*che\s*giorno\s*è",
        r"mi\s*(puoi)?\s*dire\s*la\s*data\s*di\s*oggi",
        r"giorno\s*mercato\s*azionario",
        r"che\s*giorno",
        r"giorno\s*di\s*oggi",
        r"oggi\s*che\s*giorno",
        r"chi\s*giorno\s*oggi",
        r"giornato",
        r"oggi",
        r"giorno",
    ]
    for pat in time_patterns:
        if re.search(pat, msg_simple):
            return "time"
    for pat in date_patterns:
        if re.search(pat, msg_simple):
            return "date"
    if msg_simple.strip() in ["oggi", "giorno"]:
        return "date"
    return None

def get_time_answer():
    now = datetime.now()
    time_formats = [
        f"L'orario attuale è {now.strftime('%H:%M')}.",
        f"Sono le {now.strftime('%H:%M')}.",
        f"In questo momento sono le {now.strftime('%H:%M')}.",
        f"Adesso sono le {now.strftime('%H:%M')}.",
        f"Ora sono le {now.strftime('%H:%M')}."
    ]
    return random.choice(time_formats)

def get_date_answer():
    now = datetime.now()
    days_it = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
    months_it = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
    weekday = days_it[now.weekday()]
    month = months_it[now.month - 1]
    date_formats = [
        f"Oggi è {weekday} {now.day} {month} {now.year}.",
        f"La data di oggi è {now.day} {month} {now.year}.",
        f"Oggi è il {now.day} {month} {now.year} ({weekday}).",
        f"È {weekday} {now.day} {month} {now.year}.",
        f"Attualmente è {weekday}, {now.day} {month} {now.year}."
    ]
    return random.choice(date_formats)

# --- ADVANCED YAML QA MATCHING ---
def match_yaml_qa(user_msg):
    msg_norm = normalize(user_msg)
    corr_msg = correct_spelling(msg_norm)
    questions = [normalize(q) for q, _ in all_qa_pairs]

    # 1. Exact match (corrected and raw)
    for q, a in all_qa_pairs:
        if normalize(q) == msg_norm or normalize(q) == corr_msg:
            return a

    # 2. Semantic similarity (if available)
    if sentencetr_available and st_model:
        corpus_questions = [q for q, _ in all_qa_pairs]
        embeddings_corpus = st_model.encode(corpus_questions, convert_to_tensor=True)
        embedding_input = st_model.encode(user_msg, convert_to_tensor=True)
        cos_scores = st_util.pytorch_cos_sim(embedding_input, embeddings_corpus)[0]
        best_idx = int(cos_scores.argmax())
        if cos_scores[best_idx] > 0.70:
            return all_qa_pairs[best_idx][1]

    # 3. Fuzzy full-string match (RapidFuzz preferred, falls back to difflib)
    if rapidfuzz_available:
        best = process.extractOne(msg_norm, questions, scorer=fuzz.token_set_ratio)
        if best and best[1] >= 80:
            return all_qa_pairs[best[2]][1]
        # Try spelling-corrected
        if corr_msg != msg_norm:
            best = process.extractOne(corr_msg, questions, scorer=fuzz.token_set_ratio)
            if best and best[1] >= 80:
                return all_qa_pairs[best[2]][1]
    else:
        import difflib
        best_match = difflib.get_close_matches(msg_norm, questions, n=1, cutoff=0.80)
        if not best_match and corr_msg != msg_norm:
            best_match = difflib.get_close_matches(corr_msg, questions, n=1, cutoff=0.80)
        if best_match:
            idx = questions.index(best_match[0])
            return all_qa_pairs[idx][1]

    # 4. Keyword overlap (at least 1 keyword, >60% overlap)
    msg_keywords = extract_keywords(user_msg)
    if not msg_keywords:
        return None
    best_score = 0
    best_answer = None
    for q, a in all_qa_pairs:
        q_keywords = extract_keywords(q)
        overlap = len(msg_keywords & q_keywords)
        score = overlap / (len(msg_keywords) + 1e-5)
        if overlap >= 1 and score > best_score and score >= 0.6:
            best_score = score
            best_answer = a
    if best_answer:
        return best_answer
    return None

# --- FALLBACK RESPONSES, ROTATED (NO REPETITION) ---
FALLBACK_MESSAGES = [
    "Mi dispiace, non ho ancora una risposta precisa a questa domanda. Vuoi chiedermi qualcos'altro?",
    "Non sono sicura di aver capito. Puoi riformulare la domanda o chiedermene un'altra?",
    "Ottima domanda! Al momento non ho una risposta specifica, ma posso aiutarti in altro?",
    "Sto ancora imparando. Vuoi provare con una domanda diversa?",
    "Non so rispondere a questo, ma possiamo parlare di qualcos'altro che ti interessa?",
    "Scusami, non ho trovato una risposta. Prova a chiedere in modo diverso, oppure consulta il nostro sito ufficiale.",
    "Posso aiutarti con informazioni su servizi, prenotazioni o orari. Chiedimi pure!",
    "Mi piacerebbe aiutarti di più! Riprova con un'altra domanda o cerca nel nostro sito."
]
FALLBACK_LANGUAGE_MESSAGES = [
    "Gentile utente, il servizio è ottimizzato per domande in italiano. Scrivi la tua richiesta in italiano per ricevere assistenza accurata. Grazie!",
    "Il nostro assistente virtuale funziona principalmente in italiano. Ripeti la domanda in italiano per ricevere supporto.",
    "Questo servizio risponde solo a richieste in lingua italiana. Prova di nuovo, grazie!"
]
used_fallbacks = set()

def get_fallback_msg():
    global used_fallbacks
    available = [m for m in FALLBACK_MESSAGES if m not in used_fallbacks]
    if not available:
        used_fallbacks = set()
        available = FALLBACK_MESSAGES
    msg = random.choice(available)
    used_fallbacks.add(msg)
    return msg

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json.get("message", "")
    voice_mode = request.json.get("voice", False)
    if not user_message:
        return jsonify({"reply": "Per favore, scrivi qualcosa.", "voice": False})

    # --- Time/Date dynamic answers (only if question is in Italian) ---
    if is_probably_italian(user_message):
        time_or_date = detect_time_or_date_question(user_message)
        if time_or_date == "time":
            return jsonify({"reply": get_time_answer(), "voice": voice_mode})
        elif time_or_date == "date":
            return jsonify({"reply": get_date_answer(), "voice": voice_mode})

    # Try YAML corpus Q&A with advanced NLP
    reply = match_yaml_qa(user_message)
    if reply:
        return jsonify({"reply": reply, "voice": voice_mode})

    # --- Fallback: Language detection before generic default
    if not is_probably_italian(user_message):
        reply = random.choice(FALLBACK_LANGUAGE_MESSAGES)
        return jsonify({"reply": reply, "voice": voice_mode})

    # AI-like, friendly fallback answer for unknown queries (rotated, no repeat)
    reply = get_fallback_msg()
    return jsonify({"reply": reply, "voice": voice_mode})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
