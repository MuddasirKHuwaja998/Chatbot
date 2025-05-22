import os
import re
import difflib
import yaml
import glob
import random
from datetime import datetime
from flask import Flask, render_template, request, jsonify

# If chatbot.py is not in the same directory, you may need to adjust your import path!
import chatbot

app = Flask(__name__)

# --- CONFIGURATION ---
# Use environment variable for corpus path, fallback to local "corpus" for cloud deployment (Render etc)
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

# --- NLP Normalization + Spelling Correction ---
# On Render, spellchecker might not be available or slow; wrap with try/except
try:
    from spellchecker import SpellChecker
    spellchecker_available = True
except ImportError:
    spellchecker_available = False

def normalize(text):
    return re.sub(r'[^\w\s]', '', text.strip().lower())

def correct_spelling(text):
    if not spellchecker_available:
        return text
    try:
        spell = SpellChecker(language='it')
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
    """Heuristic: Check if most words are Italian stopwords or have Italian structure."""
    italian_keywords = [
        "ciao", "come", "puoi", "aiutarmi", "grazie", "prenotare", "test", "udito", "orari", "info", "salve", "quanto", "dove", "chi", "cosa", "quale", "azienda"
    ]
    text_lc = text.lower()
    matches = sum(kw in text_lc for kw in italian_keywords)
    # If less than 2 matches and not many Italian stopwords, probably not Italian
    if matches == 0 and len(extract_keywords(text)) >= 2:
        # Check for non-latin script as a stronger signal
        if re.search(r"[а-яёΑ-ωЀ-ӿ]", text):  # Cyrillic or Greek
            return False
        # If mostly English question words and no Italian keywords
        english_starters = ["what", "who", "how", "when", "where", "why", "can you", "could you", "please", "help"]
        if any(text_lc.strip().startswith(st) for st in english_starters):
            return False
    return True

# --- TIME/DATE DETECTION & ANSWER (ONLY IN ITALIAN) ---
def detect_time_or_date_question(msg):
    msg_lc = msg.strip().lower()
    # Time-related Italian phrases
    time_phrases = [
        "che ore sono", "che ora è", "mi dici l'ora", "mi puoi dire l'ora", "orario attuale", "orario corrente", "mi dici l’orario", "puoi dirmi che ore sono"
    ]
    # Date-related Italian phrases
    date_phrases = [
        "che giorno è", "che giorno è oggi", "data di oggi", "qual è la data", "qual è la data di oggi", "oggi che giorno è", "mi dici la data di oggi"
    ]
    # Use substring matching for flexibility
    for p in time_phrases:
        if p in msg_lc:
            return "time"
    for p in date_phrases:
        if p in msg_lc:
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
    month = months_it[now.month-1]
    date_formats = [
        f"Oggi è {weekday} {now.day} {month} {now.year}.",
        f"La data di oggi è {now.day} {month} {now.year}.",
        f"Oggi è il {now.day} {month} {now.year}.",
        f"È {weekday} {now.day} {month} {now.year}.",
        f"Attualmente è {weekday}, {now.day} {month} {now.year}."
    ]
    return random.choice(date_formats)

# --- YAML QA ADVANCED MATCHING ---
def match_yaml_qa(user_msg):
    msg_norm = normalize(user_msg)

    # 1. Direct full-string match (normalized, highest priority)
    for q, a in all_qa_pairs:
        if normalize(q) == msg_norm:
            return a

    # 2. Fuzzy full-string match (very strict threshold)
    questions = [normalize(q) for q, _ in all_qa_pairs]
    best_match = difflib.get_close_matches(msg_norm, questions, n=1, cutoff=0.95)
    if best_match:
        idx = questions.index(best_match[0])
        return all_qa_pairs[idx][1]

    # 3. Keyword overlap (at least 2 keywords, >70% overlap)
    msg_keywords = extract_keywords(user_msg)
    if not msg_keywords:
        return None
    best_score = 0
    best_answer = None
    for q, a in all_qa_pairs:
        q_keywords = extract_keywords(q)
        overlap = len(msg_keywords & q_keywords)
        score = overlap / (len(msg_keywords) + 1e-5)
        if overlap >= 2 and score > best_score and score >= 0.7:
            best_score = score
            best_answer = a
    if best_answer:
        return best_answer

    # 4. No single-keyword fallback (prevents confusion from generic answers)
    return None

# --- FALLBACK ANSWERS ---
FALLBACK_MESSAGES = [
    "Mi dispiace, non ho una risposta precisa a questa domanda. Puoi riformulare la domanda oppure contattare il nostro servizio clienti al +39 081 1234567 o via email info@otofarmaspa.com.",
    "Al momento non dispongo di informazioni sufficienti per rispondere. Ti consiglio di consultare il nostro sito ufficiale www.otofarmaspa.com o chiamare il servizio clienti.",
    "Non sono sicura di poter aiutare con questa richiesta specifica. Puoi provare a chiedere in modo diverso o scrivere a info@otofarmaspa.com.",
    "Questa domanda è molto interessante! Tuttavia, per una risposta dettagliata ti suggerisco di contattare direttamente Otofarma Spa.",
    "Non ho la risposta pronta, ma puoi trovare molte informazioni utili sul nostro sito web o chiamando il nostro servizio clienti.",
]

FALLBACK_LANGUAGE_MESSAGES = [
    "Gentile utente, il servizio è attualmente ottimizzato per domande in italiano. Ti invitiamo gentilmente a scrivere la tua richiesta in italiano per ricevere assistenza accurata. Se hai bisogno di supporto, puoi anche contattarci via email a info@otofarmaspa.com o telefonicamente al +39 081 1234567. Grazie per la comprensione.",
    "Il nostro assistente virtuale funziona principalmente in italiano. Per favore, ripeti la domanda in italiano oppure scrivici a info@otofarmaspa.com per ricevere supporto nella tua lingua.",
    "Questo servizio risponde principalmente a richieste in lingua italiana. Ti invitiamo a riformulare la domanda in italiano per ricevere risposte complete e dettagliate. Grazie!",
]

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

    # --- Fallback: Language detection before ChatterBot or generic default
    if not is_probably_italian(user_message):
        reply = random.choice(FALLBACK_LANGUAGE_MESSAGES)
        return jsonify({"reply": reply, "voice": voice_mode})

    # Default fallback: ChatterBot or generic default
    try:
        bot_response = chatbot.taylorchatbot.get_response(user_message)
        reply = str(bot_response).strip()
        # If ChatterBot doesn't know or gives a blank/irrelevant answer, use a professional fallback
        if not reply or reply.lower() in ["non lo so", "non posso rispondere", "non capisco", ""]:
            reply = random.choice(FALLBACK_MESSAGES)
    except Exception as e:
        print("Error in /chat:", e)
        reply = random.choice(FALLBACK_MESSAGES)

    return jsonify({"reply": reply, "voice": voice_mode})

# For Render: use PORT env variable, default to 10000 for local
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)