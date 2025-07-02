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
    from spellchecker import SpellChecker
    spell = SpellChecker(language="it")
    spellchecker_available = True
except Exception:
    spellchecker_available = False
    spell = None

try:
    from rapidfuzz import process, fuzz
    rapidfuzz_available = True
except ImportError:
    rapidfuzz_available = False

app = Flask(__name__)

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

def normalize(text):
    text = text.strip().lower()
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text

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

def is_probably_italian(text):
    text_corr = correct_spelling(text)
    italian_keywords = [
        "ciao", "come", "puoi", "aiutarmi", "grazie", "prenotare", "test", "udito", "orari", "info", "salve",
        "quanto", "dove", "chi", "cosa", "quale", "azienda", "giorno", "ora", "bot", "servizio", "prenotazione",
        "farmacia", "farmacie", "indirizzo", "telefono", "email", "cap", "provincia", "regione"
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

def get_time_answer():
    tz = pytz.timezone("Europe/Rome")
    now = datetime.now(tz)
    polite_formats = [
        f"L'orario attuale in Italia è {now.strftime('%H:%M')}",
        f"Ora in Italia sono le {now.strftime('%H:%M')}",
        f"In questo momento in Italia sono le {now.strftime('%H:%M')}",
        f"Siamo alle {now.strftime('%H:%M')} ora italiana",
        f"Attualmente in Italia sono le {now.strftime('%H:%M')}"
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
        f"Attualmente in Italia è {weekday} {now.day} {month} {now.year}"
    ]
    return random.choice(polite_dates)

def check_general_patterns(user_msg):
    greetings = [
        "ciao", "salve", "buongiorno", "buonasera", "buonanotte", "hey", "ehi"
    ]
    msg = normalize(correct_spelling(user_msg))
    for g in greetings:
        if g in msg:
            return "Salve! Sono qui per rispondere alle tue domande."
    return None

def match_yaml_qa(user_msg):
    msg_corr = correct_spelling(user_msg)
    msg_norm = normalize(user_msg)
    corr_norm = normalize(msg_corr)
    questions_norm = [normalize(q) for q, _ in all_qa_pairs]
    for idx, qn in enumerate(questions_norm):
        if qn == msg_norm or qn == corr_norm:
            return all_qa_pairs[idx][1]
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
    # AI-style, Italian, random intros
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

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json.get("message", "")
    voice_mode = request.json.get("voice", False)
    user_lat = request.json.get("lat", None)
    user_lon = request.json.get("lon", None)

    # 1. Risposta localizzata farmacia più vicina — solo se lat/lon disponibili
    if is_near_me_query(user_message):
        if user_lat is not None and user_lon is not None:
            try:
                best_ph = nearest_pharmacy(float(user_lat), float(user_lon))
                reply = format_nearest_pharmacy(best_ph)
            except Exception:
                reply = "Si è verificato un errore nel calcolo della farmacia più vicina. Riprova tra poco!"
        else:
            # Non chiedere città, non rispondere in inglese, solo messaggio tecnico
            reply = "Per poterti suggerire la farmacia più vicina ho bisogno che il browser consenta l'accesso alla posizione: controlla le impostazioni e aggiorna la pagina."
        return jsonify({"reply": reply, "voice": voice_mode})

    # 2. Q&A standard
    user_message_corr = correct_spelling(user_message)
    if not is_probably_italian(user_message_corr):
        return jsonify({"reply": "Questo assistente risponde solo a domande in italiano. Per favore riformula la domanda in italiano.", "voice": voice_mode})

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

    fallback_messages = [
        "Mi dispiace, non ho trovato una risposta alla tua domanda. Puoi riformulare o chiedere altro?",
        "Non sono sicuro di aver capito. Puoi riprovare con una domanda diversa?",
        "Al momento non dispongo di informazioni su questo argomento. Vuoi chiedere qualcos'altro?",
        "Non ho trovato una risposta precisa. Se vuoi, puoi essere più specifico nella tua richiesta.",
        "Mi dispiace, non ho capito bene la domanda. Puoi chiarire o chiedere in altro modo?"
    ]
    reply = random.choice(fallback_messages)
    return jsonify({"reply": reply, "voice": voice_mode})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
