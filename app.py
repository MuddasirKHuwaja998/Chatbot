import os
import re
import yaml
import glob
import random
from datetime import datetime, timedelta
import pytz
from flask import Flask, render_template, request, jsonify

# --- Spellchecker for Italian ---
try:
    from spellchecker import SpellChecker
    spell = SpellChecker(language="it")
    spellchecker_available = True
except Exception:
    spellchecker_available = False
    spell = None

# --- Rapidfuzz for fuzzy matching ---
try:
    from rapidfuzz import process, fuzz
    rapidfuzz_available = True
except ImportError:
    rapidfuzz_available = False

app = Flask(__name__)
CORPUS_PATH = os.environ.get("CORPUS_PATH", os.path.join(os.path.dirname(__file__), "corpus"))

# -- Load all Q/A from corpus .yml files --
all_qa_pairs = []
for yml_file in glob.glob(os.path.join(CORPUS_PATH, "**", "*.yml"), recursive=True):
    with open(yml_file, encoding='utf-8') as f:
        try:
            data = yaml.safe_load(f)
            conversations = data.get('conversations', [])
            for conv in conversations:
                if isinstance(conv, list) and len(conv) >= 2:
                    q, *a = conv
                    if q is not None:
                        all_qa_pairs.append((q.strip(), " ".join([str(x) for x in a if x is not None])))
        except Exception as e:
            print(f"Failed to parse {yml_file}: {e}")

print(f"Loaded {len(all_qa_pairs)} total questions from corpus.")

def normalize(text):
    return re.sub(r'[^\w\s]', '', text.strip().lower())

def correct_spelling(text):
    if not spellchecker_available or not text:
        return text
    words = text.split()
    corrected = [spell.correction(w) or w for w in words]
    return ' '.join(corrected)

def extract_keywords(text):
    stopwords = set([
        "il","lo","la","i","gli","le","un","una","che","di","a","da","in","con","su","per","tra","fra",
        "mi","ti","si","ci","vi","lui","lei","noi","voi","loro","sono","sei","è","siamo","siete","ho","hai","ha",
        "abbiamo","avete","hanno","era","eri","fu","fui","eravamo","eravate","erano","ma","e","o","ed","anche",
        "come","quando","dove","chi","cosa","perche","perché","quali","qual","quale","questo","questa","quello",
        "quella","questi","quelle","quelli","al","agli","alle","agli","del","della","dello","degli","delle","dei",
        "sul","sullo","sulla","sulle","sui","agli","all","alla","allo","alle","queste","questo","questi","quella",
        "quello","quelle","quelli","tu","te","io","noi","voi","loro","piu","meno","molto","tanto","tutta","tutto",
        "tutti","tutte","ogni","alcuni","alcune"
    ])
    return set([w for w in normalize(text).split() if w not in stopwords and len(w) > 2])

# --- Improved Italian check: use spell correction, accept more queries as Italian ---
def is_probably_italian(text):
    text_corr = correct_spelling(text)
    italian_keywords = [
        "ciao", "come", "puoi", "aiutarmi", "grazie", "prenotare", "test", "udito", "orari", "info", "salve",
        "quanto", "dove", "chi", "cosa", "quale", "azienda", "giorno", "ora", "bot", "servizio", "prenotazione"
    ]
    text_lc = text_corr.lower()
    # Accept also near matches with Italian keywords
    matches = sum(kw in text_lc for kw in italian_keywords)
    if matches > 0:
        return True
    # Accept if at least 1 Italian keyword after correction
    msg_keywords = extract_keywords(text_corr)
    italian_keywords_set = set(italian_keywords)
    if len(msg_keywords & italian_keywords_set) > 0:
        return True
    # Accept if contains Italian letters and not clear English starter
    english_starters = [
        "what", "who", "how", "when", "where", "why", "can you", "could you", "please", "help", "hi", "hello",
        "good morning", "good evening"
    ]
    if any(text_lc.strip().startswith(st) for st in english_starters):
        return False
    # Accept if after correction, not mostly English (must have vowels, etc)
    return True

def detect_time_or_date_question(msg):
    msg = correct_spelling(msg)
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
        r"che\s*ore\s*sono", r"che\s*ora\s*(è|e)?", r"mi\s*(puoi)?\s*dire\s*l'?ora", r"orario\s*(attuale|corrente)",
        r"adesso\s*che\s*ore\s*sono", r"chi\s*ora\s*sono", r"ora\s*attuale", r"ora\s*e",
    ]
    date_patterns = [
        r"che\s*giorno\s*(è|e)?", r"che\s*giorno\s*è\s*oggi", r"data\s*di\s*oggi", r"oggi\s*che\s*giorno\s*è",
        r"mi\s*(puoi)?\s*dire\s*la\s*data\s*di\s*oggi", r"giorno\s*mercato\s*azionario", r"che\s*giorno",
        r"giorno\s*di\s*oggi", r"oggi\s*che\s*giorno", r"chi\s*giorno\s*oggi", r"giornato", r"oggi", r"giorno",
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

# --- Use pytz to get correct Italian time (Europe/Rome) ---
def get_time_answer():
    tz = pytz.timezone("Europe/Rome")
    now = datetime.now(tz)
    polite_formats = [
        f"L'orario attuale in Italia è {now.strftime('%H:%M')}.",
        f"Ora in Italia sono le {now.strftime('%H:%M')}.",
        f"In questo momento in Italia sono le {now.strftime('%H:%M')}.",
        f"Siamo alle {now.strftime('%H:%M')} ora italiana.",
        f"Attualmente in Italia sono le {now.strftime('%H:%M')}."
    ]
    return random.choice(polite_formats)

def get_date_answer():
    tz = pytz.timezone("Europe/Rome")
    now = datetime.now(tz)
    days_it = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
    months_it = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
    weekday = days_it[now.weekday()]
    month = months_it[now.month - 1]
    polite_dates = [
        f"Oggi in Italia è {weekday} {now.day} {month} {now.year}.",
        f"La data odierna in Italia è {now.day} {month} {now.year}.",
        f"Oggi è il {now.day} {month} {now.year} ({weekday}) in Italia.",
        f"È {weekday} {now.day} {month} {now.year}, secondo il calendario italiano.",
        f"Attualmente in Italia è {weekday}, {now.day} {month} {now.year}."
    ]
    return random.choice(polite_dates)

# --- General chat patterns (correct spelling, AI-style) ---
GENERAL_PATTERNS = [
    (["come va", "come stai", "come te la passi", "come ti senti"], [
        "Sto bene, grazie! E tu?",
        "Molto bene, grazie di avermelo chiesto.",
        "Alla grande oggi! Tu come stai?",
        "Tutto ok, grazie. Posso aiutarti con qualcosa di Otofarma?",
        "Benissimo! Spero anche tu.",
        "Sto lavorando sodo per aiutarti. E tu come va la giornata?",
        "Una giornata positiva! Raccontami, come posso aiutarti?",
        "Grazie per l’interesse, sono qui per aiutarti in qualsiasi momento."
    ]),
    (["ciao", "salve", "buongiorno", "buonasera", "buonanotte", "hey", "ehi"], [
        "Ciao! Come posso aiutarti oggi?",
        "Salve! Sono qui per rispondere alle tue domande.",
        "Buongiorno! Come posso esserti utile?",
        "Buonasera! Hai bisogno di informazioni su Otofarma?",
        "Buonanotte! Se hai domande, sono qui.",
        "Ehi! Pronto ad aiutarti.",
        "Ciao! Sono l'assistente virtuale Otofarma.",
        "Un caro saluto! Sono qui per aiutarti nel migliore dei modi."
    ]),
    (["grazie", "thank you", "thanks"], [
        "Grazie a te!",
        "Sempre a disposizione.",
        "È un piacere aiutarti.",
        "Di nulla!",
        "Se hai altre domande, sono qui.",
        "La tua soddisfazione è importante per me."
    ]),
    (["chi sei", "chi sei?", "presentati", "come ti chiami"], [
        "Sono l'assistente virtuale di Otofarma Spa.",
        "Mi chiamo Otofarma Bot, sono qui per aiutarti.",
        "Assistente Otofarma, a tua disposizione.",
        "Sono un assistente digitale, specializzato nel rispondere alle tue domande su Otofarma.",
        "Il mio compito è supportarti con informazioni e cordialità."
    ]),
    (["che fai", "cosa fai", "in che modo puoi aiutarmi"], [
        "Posso fornirti informazioni su Otofarma, i prodotti, i servizi e molto altro.",
        "Sono qui per rispondere alle tue domande e aiutarti a trovare ciò che cerchi.",
        "Ti aiuto per tutto ciò che riguarda Otofarma Spa.",
        "Resto a disposizione per qualsiasi tua esigenza informativa."
    ])
]

def check_general_patterns(user_msg):
    msg = normalize(correct_spelling(user_msg))
    for triggers, responses in GENERAL_PATTERNS:
        for pattern in triggers:
            if pattern in msg:
                return random.choice(responses)
    return None

def match_yaml_qa(user_msg):
    msg_corr = correct_spelling(user_msg)
    msg_norm = normalize(user_msg)
    corr_norm = normalize(msg_corr)
    questions_norm = [normalize(q) for q, _ in all_qa_pairs]

    # 1. Exact match (original and corrected)
    for idx, qn in enumerate(questions_norm):
        if qn == msg_norm or qn == corr_norm:
            return all_qa_pairs[idx][1]

    # 2. Fuzzy match (only if high score)
    if rapidfuzz_available:
        best = process.extractOne(corr_norm, questions_norm, scorer=fuzz.token_set_ratio)
        best2 = process.extractOne(msg_norm, questions_norm, scorer=fuzz.token_set_ratio)
        for candidate in [best, best2]:
            if candidate and candidate[1] >= 88:
                return all_qa_pairs[candidate[2]][1]
    else:
        import difflib
        best_match = difflib.get_close_matches(corr_norm, questions_norm, n=1, cutoff=0.87)
        if best_match:
            idx = questions_norm.index(best_match[0])
            return all_qa_pairs[idx][1]

    # 3. Keyword overlap (require more overlap for accuracy)
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
    return None

# -- Fallbacks: shuffle at startup and avoid repeats --
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
random.shuffle(FALLBACK_MESSAGES)
_fallback_index = 0

def get_fallback_msg():
    global _fallback_index
    msg = FALLBACK_MESSAGES[_fallback_index % len(FALLBACK_MESSAGES)]
    _fallback_index += 1
    return msg

ENGLISH_LANGUAGE_MESSAGES = [
    "Gentile utente, sono stato progettato e addestrato esclusivamente per rispondere a domande in italiano, poiché il mio database e la mia conoscenza sono focalizzati sulla lingua italiana. Per favore, riformula la tua richiesta in italiano, così potrò aiutarti in modo più accurato e professionale. Grazie per la comprensione.",
    "Il mio funzionamento e le informazioni che posso fornire sono ottimizzati solo per domande in lingua italiana. Ti invito cortesemente a scrivere la tua domanda in italiano.",
    "Rispondo esclusivamente a domande in italiano perché sono stato sviluppato per quel contesto. Per favore, riprova in italiano per ricevere assistenza."
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

    # Always correct spelling first!
    user_message_corr = correct_spelling(user_message)

    # Use corrected message for language detection and all matching
    if not is_probably_italian(user_message_corr):
        reply = random.choice(ENGLISH_LANGUAGE_MESSAGES)
        return jsonify({"reply": reply, "voice": voice_mode})

    time_or_date = detect_time_or_date_question(user_message_corr)
    if time_or_date == "time":
        return jsonify({"reply": get_time_answer(), "voice": voice_mode})
    elif time_or_date == "date":
        return jsonify({"reply": get_date_answer(), "voice": voice_mode})

    general = check_general_patterns(user_message_corr)
    if general:
        return jsonify({"reply": general, "voice": voice_mode})

    reply = match_yaml_qa(user_message_corr)
    if reply:
        return jsonify({"reply": reply, "voice": voice_mode})

    reply = get_fallback_msg()
    return jsonify({"reply": reply, "voice": voice_mode})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
