import os
import re
import yaml
import glob
import random
import csv
import unicodedata
import math
from datetime import datetime
import pytz

from flask import Flask, render_template, request, jsonify

try:
    from flask_cors import CORS
except ImportError:
    raise ImportError("Install flask-cors: pip install flask-cors")
app = Flask(__name__)
CORS(app)

try:
    import nltk
    nltk.download('punkt', quiet=True)
    nltk.download('averaged_perceptron_tagger', quiet=True)
    nltk.download('stopwords', quiet=True)
    from nltk.tokenize import word_tokenize
    from nltk.corpus import stopwords
    from nltk import pos_tag
    nltk_it_stopwords = set(stopwords.words('italian'))
    nltk_available = True
except Exception:
    nltk_available = False

try:
    from spellchecker import SpellChecker
    spell = SpellChecker(language="it")
    spellchecker_available = True
except Exception:
    spellchecker_available = False
    spell = None

try:
    from rapidfuzz import process, fuzz, distance
    rapidfuzz_available = True
except ImportError:
    rapidfuzz_available = False

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    nlp_available = True
except ImportError:
    nlp_available = False

ASSISTANT_NAME = "OtoBot"

PRECISE_ASSISTANT_NAME_PATTERNS = [
    r"^otobot$",
    r"^oto\s+bot$",
    r"^oto\s*bot$",
    r"\botobot\b",
    r"\boto\s+bot\b",
    r"\boto\s*bot\b"
]

EXTENDED_ASSISTANT_NAME_PATTERNS = [
    r"\b(otofarm)\b",
    r"\b(otofarma)\b",
    r"\b(assistente\s+virtuale)\b",
    r"\b(assistente\s+otofarma)\b",
    r"\b(virtual\s+assistant)\b"
]

VOICE_ACTIVATION_KEYWORDS = {
    "otobot", "oto bot", "assistente virtuale", "assistente otofarma", 
    "virtual assistant", "hey otobot", "ciao otobot", "salve otobot"
}

ASSISTANT_RESPONSES = [
    f"Buongiorno, sono {ASSISTANT_NAME}, l'assistente virtuale di Otofarma Spa. Sono qui per aiutarla in tutto ciò che riguarda i nostri servizi e prodotti. Come posso esserle utile oggi?",
    f"Salve, sono {ASSISTANT_NAME}, il suo assistente virtuale di Otofarma. Sono a sua completa disposizione per rispondere alle sue domande sui nostri servizi. Cosa desidera sapere?",
    f"Buongiorno, sono {ASSISTANT_NAME} da Otofarma Spa. Sono qui per fornirle tutte le informazioni di cui ha bisogno sui nostri apparecchi acustici e servizi. Come posso aiutarla?",
    f"Salve, mi presento, sono {ASSISTANT_NAME}, l'assistente virtuale di Otofarma. Sono a sua disposizione per qualsiasi domanda sui nostri prodotti e servizi. Cosa posso fare per lei?",
    f"Buongiorno, sono {ASSISTANT_NAME}, il suo assistente personale di Otofarma Spa. Sono qui per supportarla e rispondere a tutte le sue domande. Come posso essere di aiuto?",
    f"Salve, sono {ASSISTANT_NAME} di Otofarma. Sono qui per offrirle assistenza completa sui nostri servizi audiologici e apparecchi acustici. Cosa desidera sapere?",
    f"Buongiorno, sono {ASSISTANT_NAME}, assistente virtuale di Otofarma Spa. Sono a sua completa disposizione per fornirle informazioni dettagliate sui nostri servizi. Come posso aiutarla oggi?",
    f"Salve, sono {ASSISTANT_NAME}, il suo consulente virtuale specializzato in soluzioni uditive Otofarma. Sono qui per supportarla in ogni sua esigenza. Come posso assisterla?",
    f"Buongiorno, sono {ASSISTANT_NAME} da Otofarma Spa, il suo partner digitale per tutte le informazioni sui nostri prodotti e servizi audiologici. Cosa posso fare per lei oggi?",
    f"Salve, mi chiamo {ASSISTANT_NAME} e sono l'assistente virtuale dedicato di Otofarma. Sono qui per guidarla e rispondere a tutte le sue domande sui nostri apparecchi acustici. Come posso aiutarla?"
]

CUSTOM_GREETINGS = [
    ("ciao", "Salve! Sono qui per aiutarti in tutto ciò che riguarda Otofarma."),
    ("salve", "Salve! Sono qui per aiutarti in tutto ciò che riguarda Otofarma."),
    ("buongiorno", "Buongiorno! Sono sempre disponibile per rispondere alle tue domande."),
    ("buonasera", "Buonasera! Sono sempre disponibile per rispondere alle tue domande."),
    ("buonanotte", "Buonanotte! Sono qui anche a quest'ora per aiutarti."),
    ("come va", "Sto bene, grazie! Sono sempre pronto a rispondere alle tue domande su Otofarma."),
    ("come stai", "Sto bene, grazie! Sono sempre pronto a rispondere alle tue domande su Otofarma."),
    ("ehi", "Ciao! Come posso aiutarti?"),
    ("hey", "Ciao! Come posso aiutarti?"),
    ("come va?", "Sto bene, grazie! Sono sempre pronto a rispondere alle tue domande su Otofarma."),
]

COMMON_MISSPELLINGS = {
    "caio": "ciao",
    "ciaociao": "ciao",
    "coia": "ciao",
    "coaio": "ciao",
    "comeva": "come va",
    "comeva?": "come va",
    "come ba": "come va",
    "chi e": "chi è",
    "giorni": "giorno",
    "giornata": "giorno",
    "otofarma": "otofarma",
    "aprito": "aperto",
    "chiuso": "chiuso",
    "orariufficio": "orari ufficio",
    "aprite": "aprite",
    "chiudete": "chiudete",
    "fns": "fine",
    "fn": "fine",
    "otobot": "otobot",
    "otobott": "otobot",
    "ottobot": "otobot",
    "otubot": "otobot",
    "apparecchi": "apparecchi",
    "acustici": "acustici",
    "ricaricabili": "ricaricabili",
    "garanzia": "garanzia",
    "teleaudiologia": "teleaudiologia",
    "fastidio": "fastidio",
    "orecchio": "orecchio",
    "caccia": "caccia",
    "collegano": "collegano",
    "perdere": "perdere",
    "acqua": "acqua"
}

def glue_split(text):
    for k in ["ciao", "salve", "buongiorno", "buonasera", "comeva", "comeva?", "come ba", "otobot"]:
        if k in text and text.count(k) > 1:
            text = text.replace(k, f"{k} ")
    return text

def correct_spelling(text):
    text = glue_split(text)
    for wrong, right in COMMON_MISSPELLINGS.items():
        text = re.sub(rf'\b{wrong}\b', right, text, flags=re.IGNORECASE)
    if not spellchecker_available or not text:
        return text
    words = re.findall(r'\w+', text)
    corrections = []
    for word in words:
        c = spell.correction(word)
        if c and rapidfuzz_available and fuzz.ratio(word, c) >= 65:
            corrections.append(c)
        else:
            corrections.append(word)
    fixed = text
    for w, c in zip(words, corrections):
        fixed = re.sub(r'\b{}\b'.format(re.escape(w)), c, fixed, count=1)
    return fixed

OFFICE_PATTERNS = [
    r"\b(orari\s*(d[ei]l)?\s*ufficio)\b", r"\b(orari\s*apertura)\b", r"\b(orari\s*chiusura)\b",
    r"\b(quando\s*apre)\b", r"\b(quando\s*chiude)\b", r"\b(quando\s*è\s*aperto)\b",
    r"\b(quando\s*è\s*chiuso)\b", r"\b(apertura\s*otofarma)\b", r"\b(chiusura\s*otofarma)\b",
    r"\b(orario\s*otofarma)\b", r"\b(aprite)\b", r"\b(chiudete)\b", r"\b(orari\s*servizio)\b",
    r"\b(orari\s*assistenz)\b", r"\b(office\s*hours)\b", r"\b(business\s*hours)\b",
    r"\b(aperti)\b", r"\b(chiusi)\b",
    r"\b(a\s*che\s*ora\s*apre)\b", r"\b(a\s*che\s*ora\s*otofarma\s*apre)\b", r"\b(quando\s*apre\s*otofarma)\b",
    r"\b(a\s*che\s*ora\s*otofarma\s*spa\s*apre)\b", r"\b(a\s*che\s*ora\s*apre\s*otofarma\s*spa)\b",
    r"\b(quando\s*apre\s*otofarma\s*spa)\b", r"\b(orari\s*otofarma\s*spa)\b"
]
OFFICE_TIMES = [
    "Gli uffici Otofarma sono aperti dal lunedì al venerdì dalle 9:00 alle 18:30 (ora italiana).",
    "L'orario di apertura degli uffici Otofarma è dalle 9:00 alle 18:30 dal lunedì al venerdì (CET).",
    "Puoi contattare Otofarma nei giorni feriali dalle 9:00 alle 18:30, ora locale italiana.",
    "Gli orari di servizio Otofarma sono dal lunedì al venerdì, dalle 9 alle 18:30 (ora italiana).",
    "Siamo disponibili dal lunedì al venerdì dalle 9:00 alle 18:30 (fuso orario italiano).",
    "I nostri uffici osservano il seguente orario: apertura alle 9:00 e chiusura alle 18:30 dal lunedì al venerdì.",
    "Orari Otofarma: dal lunedì al venerdì, apertura alle 9:00, chiusura alle 18:30 (ora europea).",
    "Otofarma è reperibile negli orari lavorativi: 9:00 - 18:30 dal lunedì al venerdì (CET)."
]
OFFICE_KEYWORDS = {"ufficio", "apertura", "chiusura", "orari", "office", "business", "servizio", "lavorativi", "aperti", "chiusi", "spa"}

FUZZY_TIME_PATTERNS = [
    r"(che\s*)?ora\s*(è|e|sono)?", r"mi\s*(puoi)?\s*dire\s*l'?ora", r"orario\s*(attuale|corrente)?", r"adesso\s*che\s*ore",
    r"adesso\s*ora", r"dimmi\s*ora", r"ora\s*adesso", r"ora\s*attuale", r"che\s*orario", r"quanto\s*è\s*l'?ora",
    r"tempi\s*adesso", r"ora\s*in\s*italia", r"orologio", r"orari\s*attuali"
]
FUZZY_DATE_PATTERNS = [
    r"(che\s*)?giorno\s*(è|e)?", r"che\s*giorno\s*è\s*oggi", r"data\s*di\s*oggi", r"giornata\s*di\s*oggi", r"oggi\s*che\s*giorno",
    r"mi\s*(puoi)?\s*dire\s*la\s*data", r"giorno\s*odierno", r"giorno\s*attuale", r"che\s*data", r"quale\s*data",
    r"oggi\s*che\s*data", r"data\s*odierna", r"giorno\s*della\s*settimana", r"quale\s*giorno"
]

# Use environment variable if available, else fallback to 'corpus' directory in current folder
CORPUS_PATH = os.environ.get("CORPUS_PATH", os.path.join(os.path.dirname(__file__), "corpus"))

# For deployment: prefer env variable, fallback to local 'farmacie.csv' in the same folder as app.py
PHARMACY_CSV_PATH = os.environ.get(
    "PHARMACY_CSV_PATH",
    os.path.join(os.path.dirname(__file__), "farmacie.csv")
)

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

qa_questions = [q for q, _ in all_qa_pairs]
qa_answers = [a for _, a in all_qa_pairs]

def normalize(text):
    text = text.strip().lower()
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text

def extract_keywords(text):
    if nltk_available:
        words = word_tokenize(normalize(text))
        filtered = [w for w in words if w not in nltk_it_stopwords and len(w) > 2]
        tagged = pos_tag(filtered)
        keywords = [w for w, t in tagged if t.startswith('NN') or t.startswith('JJ') or t == 'FW']
        main_words = keywords if keywords else filtered
        return set(main_words[:5])
    else:
        stopwords = set([
            "il","lo","la","i","gli","le","un","una","che","di","a","da","in","con","su","per","tra","fra",
            "mi","ti","si","ci","vi","lui","lei","noi","voi","loro","sono","sei","è","siamo","siete","ho","hai","ha",
            "abbiamo","avete","hanno","era","eri","fu","fui","eravamo","eravate","erano","ma","e","o","ed","anche",
            "come","quando","dove","chi","cosa","perche","perché","quali","qual","quale","questo","questa","quello",
            "quella","questi","quelle","quelli","al","agli","alle","del","della","dello","degli","delle","dei",
            "sul","sullo","sulla","sulle","sui","all","alla","allo","alle","queste","questo","questi","quella",
            "quello","quelle","quelli","tu","te","io","noi","voi","loro","piu","meno","molto","tanto","tutta","tutto",
            "tutti","tutte","ogni","alcuni","alcune"
        ])
        filtered = [w for w in normalize(text).split() if w not in stopwords and len(w) > 2]
        return set(filtered[:5])

def semantic_match(user_msg, questions, answers):
    if not nlp_available or not questions:
        return None, 0
    try:
        corpus = list(questions) + [user_msg]
        vectorizer = TfidfVectorizer().fit(corpus)
        tfidf_matrix = vectorizer.transform(corpus)
        sim_scores = cosine_similarity(tfidf_matrix[-1], tfidf_matrix[:-1]).flatten()
        best_idx = sim_scores.argmax()
        best_score = sim_scores[best_idx]
        return (answers[best_idx], best_score) if best_score > 0.28 else (None, 0)
    except Exception:
        return None, 0

def fuzzy_match(user_msg, questions, answers):
    if not rapidfuzz_available or not questions:
        return None, 0
    try:
        results = process.extractOne(
            user_msg, questions, scorer=fuzz.partial_ratio
        )
        if results and results[1] > 65:
            idx = questions.index(results[0])
            return answers[idx], results[1] / 100.0
    except Exception:
        pass
    return None, 0

def enhanced_keyword_match(user_msg, questions, answers):
    msg_keywords = extract_keywords(user_msg)
    if not msg_keywords:
        return None, 0
    
    best_match = None
    best_score = 0
    
    for idx, question in enumerate(questions):
        q_keywords = extract_keywords(question)
        if not q_keywords:
            continue
            
        common_keywords = msg_keywords & q_keywords
        if common_keywords:
            score = len(common_keywords) / len(msg_keywords | q_keywords)
            if score > best_score and score > 0.35:
                best_score = score
                best_match = answers[idx]
    
    return best_match, best_score

def exact_phrase_match(user_msg, questions, answers):
    user_norm = normalize(user_msg)
    for idx, question in enumerate(questions):
        question_norm = normalize(question)
        if user_norm == question_norm:
            return answers[idx], 1.0
        if len(user_norm) > 10 and user_norm in question_norm:
            return answers[idx], 0.95
        if len(question_norm) > 10 and question_norm in user_norm:
            return answers[idx], 0.90
    return None, 0

def advanced_substring_match(user_msg, questions, answers):
    user_norm = normalize(user_msg)
    user_words = set(user_norm.split())
    
    best_match = None
    best_score = 0
    
    for idx, question in enumerate(questions):
        question_norm = normalize(question)
        question_words = set(question_norm.split())
        
        if len(user_words) == 0 or len(question_words) == 0:
            continue
            
        common_words = user_words & question_words
        if common_words:
            word_score = len(common_words) / max(len(user_words), len(question_words))
            
            # Bonus for important keywords from otofarmaspa.yml
            important_keywords = {
                "prova", "gratis", "mese", "assistenza", "prezzo", "ricaricabili", "fastidio", 
                "orecchio", "caccia", "collegano", "pagare", "perdere", "garanzia", "acqua",
                "teleaudiologia", "apparecchi", "acustici", "costo", "meno", "online"
            }
            
            important_matches = common_words & important_keywords
            if important_matches:
                word_score += len(important_matches) * 0.15
            
            if word_score > best_score and word_score > 0.25:
                best_score = word_score
                best_match = answers[idx]
    
    return best_match, best_score

def match_yaml_qa_ai(user_msg):
    msg_corr = correct_spelling(user_msg)
    msg_norm = normalize(user_msg)
    corr_norm = normalize(msg_corr)
    questions_norm = [normalize(q) for q in qa_questions]
    keywords = extract_keywords(msg_corr)
    
    # First: Exact phrase matching
    answer, score = exact_phrase_match(msg_corr, questions_norm, qa_answers)
    if answer and score > 0.85:
        return answer
    
    # Second: Exact normalized matching
    for idx, qn in enumerate(questions_norm):
        if qn == msg_norm or qn == corr_norm:
            return qa_answers[idx]
    
    # Third: Advanced substring matching with keyword bonuses
    answer, score = advanced_substring_match(msg_corr, questions_norm, qa_answers)
    if answer and score > 0.4:
        return answer
    
    # Fourth: Enhanced keyword matching
    answer, score = enhanced_keyword_match(msg_corr, questions_norm, qa_answers)
    if answer and score > 0.4:
        return answer
    
    # Fifth: Semantic similarity matching
    answer, score = semantic_match(msg_corr, questions_norm, qa_answers)
    if answer and score > 0.3:
        return answer
        
    # Sixth: Fuzzy matching as last resort
    answer, score = fuzzy_match(msg_corr, questions_norm, qa_answers)
    if answer and score > 0.7:
        return answer
    
    return None

def is_probably_italian(text):
    text_corr = correct_spelling(text)
    italian_keywords = [
        "ciao", "come", "puoi", "aiutarmi", "grazie", "prenotare", "test", "udito", "orari", "info", "salve",
        "quanto", "dove", "chi", "cosa", "quale", "azienda", "giorno", "ora", "bot", "servizio", "prenotazione",
        "farmacia", "farmacie", "indirizzo", "telefono", "email", "cap", "provincia", "regione", "otobot",
        "assistente", "apparecchi", "acustici", "ricaricabili", "garanzia", "prezzo", "pagare", "prova",
        "fastidio", "orecchio", "caccia", "collegano", "perdere", "acqua", "teleaudiologia", "gratis",
        "mese", "assistenza", "costano", "online", "resistenti", "vedere", "danno", "voglio", "parlarne",
        "familiare", "succede", "metto", "sono"
    ]
    text_lc = text_corr.lower()
    matches = sum(kw in text_lc for kw in italian_keywords)
    if matches > 0:
        return True
    msg_keywords = extract_keywords(text_corr)
    italian_keywords_set = set(italian_keywords)
    if len(msg_keywords & italian_keywords_set) > 0:
        return True
    english_starters = [
        "what", "who", "how", "when", "where", "why", "can you", "could you", "please", "help", "hi", "hello",
        "good morning", "good evening"
    ]
    if any(text_lc.strip().startswith(st) for st in english_starters):
        return False
    english_words = set([
        "what","who","where","when","why","how","pharmacy","address","mail","email","number","phone","open","close",
        "near","region","province","city","find","show","list","info"
    ])
    words = set(re.findall(r'\w+', text_lc))
    if len(words & english_words) / (len(words)+1e-5) > 0.3:
        return False
    return True

def detect_precise_assistant_name(msg):
    msg_corr = correct_spelling(msg)
    msg_lc = normalize(msg_corr).strip()
    
    # Exact word matching for precise activation
    words = msg_lc.split()
    
    # Check for exact "otobot" at start or end of message
    if words and (words[0] == "otobot" or words[-1] == "otobot"):
        return True
    
    # Check for "oto bot" (two words)
    if len(words) >= 2:
        for i in range(len(words) - 1):
            if words[i] == "oto" and words[i + 1] == "bot":
                return True
    
    # Check for voice activation keywords
    for keyword in VOICE_ACTIVATION_KEYWORDS:
        if keyword in msg_lc:
            return True
    
    # Precise pattern matching
    for pattern in PRECISE_ASSISTANT_NAME_PATTERNS:
        if re.search(pattern, msg_lc):
            return True
    
    # Extended pattern matching (less sensitive)
    for pattern in EXTENDED_ASSISTANT_NAME_PATTERNS:
        if re.search(pattern, msg_lc):
            # Additional context check to avoid false positives
            context_words = {"assistente", "virtuale", "otofarma", "spa"}
            if any(word in msg_lc for word in context_words):
                return True
    
    return False

def detect_assistant_name(msg):
    return detect_precise_assistant_name(msg)

def get_assistant_introduction():
    return random.choice(ASSISTANT_RESPONSES)

def detect_time_or_date_question(msg):
    msg_corr = correct_spelling(msg)
    msg_lc = normalize(msg_corr)
    for pat in FUZZY_TIME_PATTERNS:
        if re.search(pat, msg_lc):
            return "time"
        if rapidfuzz_available:
            if fuzz.partial_ratio(msg_lc, pat.replace(r"\s*", " ")) > 75:
                return "time"
    for pat in FUZZY_DATE_PATTERNS:
        if re.search(pat, msg_lc):
            return "date"
        if rapidfuzz_available:
            if fuzz.partial_ratio(msg_lc, pat.replace(r"\s*", " ")) > 75:
                return "date"
    tokens = msg_lc.split()
    if tokens:
        if tokens[0] in ["ora", "orario", "orari"]:
            return "time"
        if tokens[0] in ["giorno", "data"]:
            return "date"
    return None

def detect_office_hours_question(msg):
    msg_corr = correct_spelling(msg)
    msg_lc = normalize(msg_corr)
    if check_general_patterns(msg_lc):
        return False
    if detect_assistant_name(msg_lc):
        return False
    for pat in OFFICE_PATTERNS:
        if re.search(pat, msg_lc):
            return True
        if rapidfuzz_available:
            if fuzz.partial_ratio(msg_lc, pat.replace(r"\s*", " ")) > 80:
                return True
    tokens = set(msg_lc.split())
    if tokens & OFFICE_KEYWORDS:
        return True
    return False

def get_office_hours_answer():
    return random.choice(OFFICE_TIMES)

def get_time_answer():
    tz = pytz.timezone("Europe/Rome")
    now = datetime.now(tz)
    polite_formats = [
        f"L'orario attuale in Italia è {now.strftime('%H:%M')}",
        f"Ora in Italia sono le {now.strftime('%H:%M')}",
        f"In questo momento in Italia sono le {now.strftime('%H:%M')}",
        f"Siamo alle {now.strftime('%H:%M')} ora italiana",
        f"Attualmente in Italia sono le {now.strftime('%H:%M')}",
        f"In questo momento sono le {now.strftime('%H:%M')} in Italia",
        f"L'orologio segna le {now.strftime('%H:%M')} ora italiana",
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
        f"Oggi in Italia è {weekday} {now.day} {month} {now.year}",
        f"La data odierna in Italia è {now.day} {month} {now.year}",
        f"Oggi è il {now.day} {month} {now.year} {weekday} in Italia",
        f"È {weekday} {now.day} {month} {now.year} secondo il calendario italiano",
        f"Attualmente in Italia è {weekday} {now.day} {month} {now.year}",
        f"Oggi la data è: {weekday} {now.day} {month} {now.year}",
        f"Secondo il calendario italiano oggi è {weekday} {now.day} {month} {now.year}"
    ]
    return random.choice(polite_dates)

def check_general_patterns(user_msg):
    msg = normalize(correct_spelling(user_msg))
    
    if detect_assistant_name(msg):
        return None
    
    for pattern, reply in CUSTOM_GREETINGS:
        if rapidfuzz_available and fuzz.partial_ratio(pattern, msg) > 80:
            return reply
        if pattern in msg:
            return reply
    tokens = msg.split()
    for k in ["ciao", "salve", "buongiorno", "buonasera", "buonanotte"]:
        if tokens and tokens[0] == k and len(tokens) == 1:
            return CUSTOM_GREETINGS[0][1]
    return None

pharmacies = []
if os.path.isfile(PHARMACY_CSV_PATH):
    with open(PHARMACY_CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=';' if PHARMACY_CSV_PATH.lower().endswith('.csv') else ',')
        for row in reader:
            pharmacies.append(row)
    print(f"Caricate {len(pharmacies)} farmacie dal CSV.")
else:
    print(f"File CSV farmacie non trovato: {PHARMACY_CSV_PATH}")

def is_pharmacy_question(msg):
    msg_lc = normalize(msg)
    pharmacy_keywords = [
        "farmacia", "farmacie", "indirizzo", "telefono", "numero", "email", "contatto", "dove", "trovare",
        "vicino", "cap", "regione", "provincia", "orari", "aperta", "chiusa", "apertura", "chiusura", "città",
        "zona", "quartiere", "dottore", "dr", "dottoressa", "info", "contatti", "farmacista"
    ]
    for kw in pharmacy_keywords:
        if kw in msg_lc:
            return True
    return False

def extract_city_from_query(user_msg):
    user_msg_norm = normalize(user_msg)
    city_keys = ['Città', 'città', 'city', 'City']
    cities_original = []
    for ph in pharmacies:
        for key in city_keys:
            city = ph.get(key, "")
            if city:
                cities_original.append(city)
    cities_map = {normalize(city): city for city in cities_original}
    found_cities = []
    for city_norm, city_orig in cities_map.items():
        if city_norm and city_norm in user_msg_norm:
            found_cities.append(city_orig)
    return found_cities

def extract_field_intent(user_msg):
    user_msg = user_msg.lower()
    intents = []
    if any(w in user_msg for w in ["mail", "email", "posta"]):
        intents.append("Email")
    if any(w in user_msg for w in ["telefono", "phone", "numero", "chiama", "contatto", "whatsapp", "cellulare"]):
        intents.append("Telefono")
    if any(w in user_msg for w in ["indirizzo", "address", "via", "dove", "location"]):
        intents.append("Indirizzo")
    if any(w in user_msg for w in ["cap", "postal"]):
        intents.append("CAP")
    if any(w in user_msg for w in ["provincia", "province"]):
        intents.append("Provincia")
    if any(w in user_msg for w in ["regione", "region"]):
        intents.append("Regione")
    if not intents:
        intents = ["Telefono", "Email", "Indirizzo"]
    return intents

def pharmacy_best_match(user_msg, city=None):
    user_msg_norm = normalize(user_msg)
    max_score = 0
    best_ph = None
    for ph in pharmacies:
        name = normalize(ph.get("Farmacia", ph.get("Nome", "")))
        city_ph = normalize(ph.get("Città", ph.get("città", "")))
        prov = normalize(ph.get("Provincia", ph.get("provincia", "")))
        cap = normalize(ph.get("CAP", ph.get("cap", "")))
        reg = normalize(ph.get("Regione", ph.get("regione", "")))
        if city and city_ph != normalize(city):
            continue
        score = 0
        if name and name in user_msg_norm:
            score += 4
        if city_ph and city_ph in user_msg_norm:
            score += 3
        if prov and prov in user_msg_norm:
            score += 2
        if cap and cap in user_msg_norm:
            score += 2
        if reg and reg in user_msg_norm:
            score += 1
        if score > max_score:
            max_score = score
            best_ph = ph
    return best_ph

def pharmacies_by_city(city_name):
    city_norm = normalize(city_name)
    return [
        ph for ph in pharmacies
        if normalize(ph.get("Città", ph.get("città", ""))) == city_norm
    ]

def format_pharmacies_list(ph_list, city_name, user_msg=None):
    city_formatted = city_name.strip() or "la città richiesta"
    total = len(ph_list)
    intros = [
        f"Ti elenco le farmacie Otofarma presenti a {city_formatted}",
        f"Ecco le farmacie Otofarma disponibili a {city_formatted}",
        f"Queste sono le farmacie Otofarma che puoi trovare a {city_formatted}",
        f"Qui trovi le farmacie Otofarma in zona {city_formatted}",
        f"Ti segnalo le principali farmacie Otofarma a {city_formatted}",
        f"Scopri le farmacie Otofarma nella zona di {city_formatted}",
        f"Queste farmacie Otofarma sono in zona {city_formatted}",
        f"In elenco troverai le farmacie Otofarma di {city_formatted}",
        f"A {city_formatted} sono presenti queste farmacie Otofarma",
        f"Ora ti mostro le farmacie Otofarma di {city_formatted}",
        f"Ecco la lista delle farmacie Otofarma a {city_formatted}"
    ]
    count_lines = [
        f"In questa città ci sono {total} farmacie Otofarma",
        f"A {city_formatted} risultano {total} farmacie Otofarma affiliate",
        f"Abbiamo {total} farmacie Otofarma registrate per {city_formatted}",
        f"Il sistema mostra {total} farmacie Otofarma a {city_formatted}",
        f"Sono state trovate {total} farmacie Otofarma a {city_formatted}",
        f"Risultano {total} farmacie Otofarma operative a {city_formatted}"
    ]
    next_steps = [
        "Ecco quella che potrebbe essere più comoda per te:",
        "Qui i dettagli di una delle principali farmacie della zona:",
        "Ti segnalo subito una farmacia particolarmente accessibile:",
        "Questa farmacia potrebbe essere facilmente raggiungibile per te:",
        "Questa farmacia è tra le scelte più consigliate:",
        "Qui sotto trovi una farmacia selezionata per te:",
        "Inizio suggerendoti questa farmacia:"
    ]
    reply_lines = [
        random.choice(intros),
        random.choice(count_lines),
        random.choice(next_steps),
        ""
    ]
    best_ph = ph_list[0]
    name = best_ph.get("Farmacia", best_ph.get("Nome", "Nome non disponibile"))
    address = best_ph.get("Indirizzo", best_ph.get("indirizzo", "Indirizzo non disponibile"))
    cap = best_ph.get("CAP", best_ph.get("cap", "N/A"))
    prov = best_ph.get("Provincia", best_ph.get("provincia", "N/A"))
    tel = best_ph.get("Telefono", best_ph.get("telefono", "N/A"))
    email = best_ph.get("Email", best_ph.get("email", "N/A"))
    reg = best_ph.get("Regione", best_ph.get("regione", "N/A"))
    block = [
        f"Nome farmacia: {name}",
        f"Indirizzo: {address}",
        f"CAP: {cap}",
        f"Provincia: {prov}",
        f"Telefono: {tel}",
        f"Email: {email}",
        f"Regione: {reg}"
    ]
    reply_lines.extend(block)
    if total > 1:
        reply_lines.append("")
        reply_lines.append(f"Se vuoi conoscere altre farmacie a {city_formatted} chiedimi pure oppure specifica la zona che preferisci")
    reply_lines.append("Puoi trovare tutte le farmacie Otofarma vicine a te anche tramite la mappa nella nostra app!")
    reply_lines.append("Per qualsiasi altra informazione sono a tua disposizione.")
    return "\n".join(reply_lines)

def format_pharmacy_answer(ph, field_intents):
    if not ph:
        return ("Mi dispiace, non sono riuscito a trovare una farmacia corrispondente. Specifica il nome e la città o provincia per una ricerca più precisa.")
    name = ph.get("Farmacia", ph.get("Nome", "Nome non disponibile"))
    city = ph.get("Città", ph.get("città", ""))
    prov = ph.get("Provincia", ph.get("provincia", ""))
    cap = ph.get("CAP", ph.get("cap", ""))
    reg = ph.get("Regione", ph.get("regione", ""))
    address = ph.get("Indirizzo", ph.get("indirizzo", ""))
    lines = [f"Dettagli della farmacia {name} situata in {address}, {city} (provincia di {prov}, CAP {cap}, regione {reg})"]
    mapped = {
        "Telefono": "Telefono",
        "Email": "Email",
        "Indirizzo": "Indirizzo",
        "CAP": "CAP",
        "Provincia": "Provincia",
        "Regione": "Regione"
    }
    for field in field_intents:
        val = ph.get(mapped[field], ph.get(mapped[field].lower(), None))
        if val and val.strip():
            lines.append(f"{field}: {val}")
    if not any(ph.get(mapped[f], ph.get(mapped[f].lower(),"")).strip() for f in field_intents):
        lines.append("Non dispongo di informazioni aggiornate per questi dati.")
    lines.append("Ricorda! Puoi trovare tutte le farmacie Otofarma vicine a te tramite la mappa della nostra app.")
    return "\n".join(lines)

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def nearest_pharmacy(user_lat, user_lon):
    min_dist = float('inf')
    best_ph = None
    for ph in pharmacies:
        lat = ph.get('lat') or ph.get('Latitudine')
        lon = ph.get('lon') or ph.get('Longitudine')
        if not lat or not lon:
            continue
        try:
            dist = haversine(user_lat, user_lon, float(lat), float(lon))
            if dist < min_dist:
                min_dist = dist
                best_ph = ph.copy()
                best_ph['distanza_km'] = round(dist, 2)
        except Exception:
            continue
    return best_ph

def format_nearest_pharmacy(ph):
    if not ph:
        return random.choice([
            "Non sono riuscito a localizzare una farmacia nelle immediate vicinanze. Riprova tra qualche minuto oppure controlla la connessione.",
            "Al momento non trovo una farmacia molto vicina alla tua posizione. Puoi riprovare più tardi!"
        ])
    nome = ph.get('Nome') or ph.get('Farmacia') or "Nome non disponibile"
    indirizzo = ph.get('indirizzo') or ph.get('Indirizzo') or "Indirizzo non disponibile"
    città = ph.get('città') or ph.get('Città') or ""
    provincia = ph.get('provincia') or ph.get('Provincia') or ""
    cap = ph.get('cap') or ph.get('CAP') or ""
    telefono = ph.get('telefono') or ph.get('Telefono') or ""
    email = ph.get('email') or ph.get('Email') or ""
    distanza = ph.get('distanza_km', '?')
    intro = random.choice([
        f"Ecco la farmacia Otofarma più vicina a te in questo momento:",
        f"Ho trovato questa farmacia nelle tue vicinanze:",
        f"La farmacia più prossima alla tua posizione attuale è:",
        f"Sulla base della tua posizione, questa è la farmacia più vicina:",
        f"Risultato aggiornato: la farmacia Otofarma più comoda per te ora è:",
        f"Consultando la tua posizione, questa è la farmacia più rapidamente raggiungibile:"
    ])
    dettagli = [
        f"Nome: {nome}",
        f"Indirizzo: {indirizzo}, {cap} {città} ({provincia})",
        f"Telefono: {telefono}",
        f"Email: {email}",
        f"Distanza stimata: {distanza} km"
    ]
    outro = random.choice([
        "Se ti serve altro chiedimi pure, sono qui per aiutarti!",
        "Per maggiori informazioni o altre farmacie in zona, chiedimi senza problemi.",
        "Se vuoi conoscere altre opzioni vicine o dettagli aggiuntivi, chiedi pure!",
        "Puoi richiedere info su altre farmacie vicine quando vuoi.",
        "Sono sempre a disposizione per qualsiasi altra necessità!"
    ])
    return "\n".join([intro] + dettagli + [outro])

def is_near_me_query(user_msg):
    msg = normalize(user_msg)
    near_patterns = [
        "pharmacy near me", "pharmacies near me", "nearest pharmacy",
        "farmacia più vicina", "farmacia vicina", "farmacia vicino a me", "farmacie vicino a me", "farmacia nelle vicinanze",
        "farmacia qui", "farmacie qui", "farmacia intorno a me", "vicino a me", "più vicina a me", "vicina a me"
    ]
    return any(pat in msg for pat in near_patterns)

class FallbackMemory:
    def __init__(self, maxlen=20):
        self.maxlen = maxlen
        self.last_fallbacks = []
    def get_unique(self, pool):
        unused = [m for m in pool if m not in self.last_fallbacks]
        if not unused:
            unused = pool
            self.last_fallbacks = []
        chosen = random.choice(unused)
        self.remember(chosen)
        return chosen
    def remember(self, fallback):
        self.last_fallbacks.append(fallback)
        while len(self.last_fallbacks) > self.maxlen:
            self.last_fallbacks.pop(0)

fallback_mem = FallbackMemory()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/voice_activation", methods=["POST"])
def voice_activation():
    """Endpoint specifically for voice activation detection"""
    user_message = request.json.get("message", "")
    
    if detect_precise_assistant_name(user_message):
        return jsonify({
            "activated": True,
            "reply": get_assistant_introduction(),
            "voice": True
        })
    
    return jsonify({"activated": False})

@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json.get("message", "")
    voice_mode = request.json.get("voice", True)
    user_lat = request.json.get("lat", None)
    user_lon = request.json.get("lon", None)

    if detect_assistant_name(user_message):
        return jsonify({"reply": get_assistant_introduction(), "voice": voice_mode, "male_voice": True})

    general = check_general_patterns(user_message)
    if general:
        return jsonify({"reply": general, "voice": voice_mode, "male_voice": True})

    if is_near_me_query(user_message):
        if user_lat is not None and user_lon is not None:
            try:
                best_ph = nearest_pharmacy(float(user_lat), float(user_lon))
                reply = format_nearest_pharmacy(best_ph)
            except Exception:
                reply = "Si è verificato un errore nel calcolo della farmacia più vicina. Riprova tra poco!"
        else:
            reply = "Per poterti suggerire la farmacia più vicina ho bisogno che il browser consenta l'accesso alla posizione: controlla le impostazioni e aggiorna la pagina."
        return jsonify({"reply": reply, "voice": voice_mode, "male_voice": True})

    user_message_corr = correct_spelling(user_message)
    if not is_probably_italian(user_message_corr):
        return jsonify({"reply": "Questo assistente risponde solo a domande in italiano. Per favore riformula la domanda in italiano.", "voice": voice_mode, "male_voice": True})

    if detect_office_hours_question(user_message_corr):
        return jsonify({"reply": get_office_hours_answer(), "voice": voice_mode, "male_voice": True})

    if is_pharmacy_question(user_message_corr):
        found_cities = extract_city_from_query(user_message_corr)
        if found_cities:
            city = found_cities[0]
            ph_list = pharmacies_by_city(city)
            if ph_list:
                reply = format_pharmacies_list(ph_list, city, user_message_corr)
            else:
                reply = "Non ho trovato farmacie Otofarma in questa città. Controlla la scrittura o chiedi per un'altra località."
        else:
            field_intents = extract_field_intent(user_message_corr)
            best_ph = pharmacy_best_match(user_message_corr)
            reply = format_pharmacy_answer(best_ph, field_intents)
        return jsonify({"reply": reply, "voice": voice_mode, "male_voice": True})

    time_or_date = detect_time_or_date_question(user_message_corr)
    if time_or_date == "time":
        return jsonify({"reply": get_time_answer(), "voice": voice_mode, "male_voice": True})
    elif time_or_date == "date":
        return jsonify({"reply": get_date_answer(), "voice": voice_mode, "male_voice": True})

    reply = match_yaml_qa_ai(user_message_corr)
    if reply:
        return jsonify({"reply": reply, "voice": voice_mode, "male_voice": True})

    fallback_messages = [
        "Al momento non dispongo di una risposta precisa alla tua richiesta, ma sono qui per aiutarti su qualsiasi altro tema riguardante Otofarma.",
        "Mi scuso, non sono riuscito a trovare una risposta soddisfacente. Se desideri, puoi riformulare la domanda o chiedere su un altro argomento.",
        "Domanda interessante! Tuttavia, non ho informazioni puntuali su questo punto. Sono a disposizione per altre domande.",
        "La tua richiesta è stata ricevuta, ma non dispongo di dettagli specifici. Puoi fornire ulteriori informazioni o chiedere altro?",
        "Non trovo una risposta adeguata in questo momento. Ti invito a riformulare o a chiedere su altri temi.",
        "Mi dispiace, non ho trovato la risposta richiesta. Se vuoi puoi essere più dettagliato oppure chiedere su altri servizi Otofarma.",
        "Al momento non ho dati su questo specifico argomento. Sono qui per aiutarti su tutto ciò che riguarda Otofarma.",
        "Non dispongo di una risposta esaustiva ora, ma resto a disposizione per tutte le tue domande su Otofarma.",
        "Sto ancora apprendendo: puoi riprovare a chiedere in modo diverso o chiedere su un altro servizio?",
        "Non riesco a trovare informazioni pertinenti. Sono sempre pronto ad aiutarti per qualsiasi esigenza su Otofarma.",
        "Domanda ricevuta. Se vuoi, posso aiutarti a cercare altre informazioni o servizi correlati.",
        "Non sono sicuro di aver compreso appieno la richiesta. Puoi riformulare o chiedere altro?",
        "Se vuoi ulteriori dettagli su Otofarma o sulle farmacie, chiedimi pure!",
        "Sono qui per aiutarti: puoi chiedere in modo diverso o esplorare altri servizi disponibili.",
        "Se ti occorrono informazioni su orari, servizi o farmacie, chiedimi pure senza esitare.",
        "Sono qui per offrirti il massimo supporto: puoi essere più specifico nella tua richiesta?",
        "Non dispongo di una risposta su questo, ma posso aiutarti a trovare informazioni su servizi, orari o farmacie Otofarma.",
        "Se hai bisogno di dettagli aggiuntivi, sono disponibile ad aiutarti."
    ]
    reply = fallback_mem.get_unique(fallback_messages)
    return jsonify({"reply": reply, "voice": voice_mode, "male_voice": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

    
