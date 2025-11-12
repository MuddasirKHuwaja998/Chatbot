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
import json
from google.cloud import texttospeech
from google.cloud import speech
from flask import Flask, render_template, request, jsonify
import sendgrid
from sendgrid.helpers.mail import Mail
import sqlite3
import logging

# Configure professional logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('otofarma_ai_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('OtofarmaAI')

DB_PATH = "appointments.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()
def save_appointment_to_db(name, phone, date):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO appointments (name, phone, date) VALUES (?, ?, ?)",
        (name, phone, date)
    )
    conn.commit()
    conn.close()

def find_appointment(name=None, phone=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    query = "SELECT name, phone, date FROM appointments WHERE 1=1"
    params = []
    if name:
        query += " AND name LIKE ?"
        params.append(f"%{name}%")
    if phone:
        query += " AND phone LIKE ?"
        params.append(f"%{phone}%")
    c.execute(query, params)
    result = c.fetchone()
    conn.close()
    return result

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")  #

def send_appointment_email(patient_name, patient_phone, patient_date):
    subject = f"Nuova Prenotazione Visita - {patient_name}"
    body = (
        f"Gentile Team Otofarma,\n\n"
        f"È stata richiesta una nuova prenotazione da:\n"
        f"Nome paziente: {patient_name}\n"
        f"Telefono: {patient_phone}\n"
        f"Data preferita: {patient_date}\n\n"
        f"Si prega di contattare il paziente per confermare l'appuntamento e ricordare la visita.\n\n"
        f"Questa email è generata automaticamente dall'Assistente Virtuale Otofarma AI Bot.\n"
        f"Grazie per la collaborazione.\n\n"
        f"Cordiali saluti,\nOtofarma AI Bot"
    )
    message = Mail(
        from_email="otofarmaibot@gmail.com",
        to_emails="engr.muddasir01@gmail.com",
        subject=subject,
        plain_text_content=body
    )
    try:
        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"SendGrid email status: {response.status_code}")
        if response.status_code >= 400:
            print(f"SendGrid error body: {response.body}")
    except Exception as e:
        print(f"SendGrid email error: {e}")

def extract_appointment_info_smart(user_message):
    import re
    from datetime import datetime
    msg = user_message.strip()
    msg_lower = msg.lower()
    # Name extraction
    name_pattern = r"(mi chiamo|sono|il mio nome è|nome[:\s]*)\s*([A-Za-zÀ-ÿ' ]{3,})"
    name_match = re.search(name_pattern, msg_lower)
    name = None
    if name_match:
        name = name_match.group(2).strip().title()
    else:
        possible_names = re.findall(r"\b([A-Z][a-zàèéìòù']{2,})\b", msg)
        if possible_names:
            name = possible_names[0]
    # Phone extraction
    phone_match = re.search(r"((?:\d[\s\-]*){8,13})", msg)
    phone = None
    if phone_match:
        phone_candidate = re.sub(r"[\s\-]", "", phone_match.group(1))
        if 8 <= len(phone_candidate) <= 13:
            phone = phone_candidate
    # Date extraction
    date_pattern = r"(lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica|oggi|domani|dopodomani|[0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4}|[0-9]{1,2} [a-z]+|prossimo|settimana|mese|[0-9]{1,2} [a-z]+)"
    date_match = re.search(date_pattern, msg_lower)
    date = date_match.group(0).strip().title() if date_match else None
    # If date missing, use current year and month
    if not date:
        now = datetime.now()
        date = f"{now.day} {now.strftime('%B')} {now.year}"
    return {
        "name": name,
        "phone": phone,
        "date": date
    }
try:
    from flask_cors import CORS
except ImportError:
    raise ImportError("Install flask-cors: pip install flask-cors")
app = Flask(__name__)
CORS(app)
    
# Add these new imports for Gemini API
import vertexai
from vertexai.generative_models import GenerativeModel

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

# More precise patterns for assistant name detection
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

# Enhanced voice activation for continuous listening
ENHANCED_ACTIVATION_PATTERNS = [
    r"\bhey\s+otobot\b",
    r"\bciao\s+otobot\b", 
    r"\bsalve\s+otobot\b",
    r"\bbuongiorno\s+otobot\b",
    r"\bbuonasera\s+otobot\b",
    r"^otobot\b",
    r"\botobot$",
    r"\boto\s+bot\b",
    r"\bassistente\s+otofarma\b",
    r"\botofarma\s+assistente\b",
    r"\botobot\s+",
    r"\s+otobot\b",
    r"^otobot$"
]

def detect_enhanced_voice_activation(text):
    """Enhanced voice activation detection for Hey OtoBot"""
    if not text:
        return False
   
        
    text_clean = normalize(text.strip())
    
    # Check enhanced patterns0
    for pattern in ENHANCED_ACTIVATION_PATTERNS:
        if re.search(pattern, text_clean, re.IGNORECASE):
            return True
    
    # Check if message starts or ends with activation words
    words = text_clean.split()
    if words:
        first_two = " ".join(words[:2]).lower()
        last_two = " ".join(words[-2:]).lower()
        
        activation_phrases = ["hey otobot", "ciao otobot", "salve otobot", "otobot", "oto bot"]
        for phrase in activation_phrases:
            if phrase in first_two or phrase in last_two:
                return True
    
    return False

def handle_voice_activation_greeting():
    """Generate automatic greeting for Hey OtoBot - PROFESSIONAL RESPONSES"""
    professional_greetings = [
        f"Salve! Sono {ASSISTANT_NAME}, il suo assistente vocale professionale di Otofarma Spa. È un piacere sentirla! Come posso aiutarla oggi con i nostri apparecchi acustici di ultima generazione e servizi di teleaudiologia?",
        f"Buongiorno! Sono {ASSISTANT_NAME} di Otofarma Spa. Sono molto felice che mi abbia attivato! Sono qui per fornirle tutte le informazioni sui nostri prodotti audiologici innovativi e servizi specializzati. Cosa desidera sapere?",
        f"Salve e benvenuto! Sono {ASSISTANT_NAME}, il suo consulente virtuale specializzato di Otofarma. È un onore poterla servire oggi! Posso aiutarla con apparecchi acustici ricaricabili, garanzie, prezzi o qualsiasi altra informazione?",
        f"Ciao! Sono {ASSISTANT_NAME} da Otofarma Spa. Sono entusiasta di poterla assistere! Sono qui per rispondere a tutte le sue domande sui nostri apparecchi acustici su misura, la teleaudiologia e i nostri servizi premium. Come posso essere utile?",
        f"Buongiorno! È un piacere sentirla. Sono {ASSISTANT_NAME}, il suo assistente vocale di fiducia di Otofarma Spa. Sono completamente a sua disposizione per informazioni dettagliate sui nostri prodotti e servizi. Cosa posso fare per lei oggi?"
    ]
    return random.choice(professional_greetings)
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

# Enhanced spell correction with more Italian words
COMMON_MISSPELLINGS = {
    "caio": "ciao", "ciaociao": "ciao", "coia": "ciao", "coaio": "ciao",
    "comeva": "come va", "comeva?": "come va", "come ba": "come va",
    "chi e": "chi è", "cosa e": "cosa è", "dove e": "dove è",
    "quando e": "quando è", "quanto e": "quanto è", "quale e": "quale è",
    "giorni": "giorno", "giornata": "giorno", "otofarma": "otofarma",
    "aprito": "aperto", "chiuso": "chiuso", "orariufficio": "orari ufficio",
    "aprite": "aprite", "chiudete": "chiudete", "fns": "fine", "fn": "fine",
    "otobot": "otobot", "otobott": "otobot", "ottobot": "otobot", "otubot": "otobot",
    "apparecchi": "apparecchi", "acustici": "acustici", "ricaricabili": "ricaricabili",
    "garanzia": "garanzia", "teleaudiologia": "teleaudiologia", "fastidio": "fastidio",
    "orecchio": "orecchio", "caccia": "caccia", "collegano": "collegano",
    "perdere": "perdere", "acqua": "acqua", "assistenza": "assistenza",
    "inclusa": "inclusa", "tipo": "tipo", "tipi": "tipi", "prezzo": "prezzo",
    "costo": "costo", "costano": "costano", "prova": "prova", "gratis": "gratis",
    "gratuita": "gratuita", "mese": "mese", "mesi": "mesi", "online": "online",
    "resistenti": "resistenti", "vedere": "vedere", "danno": "danno",
    "voglio": "voglio", "parlarne": "parlarne", "familiare": "familiare",
    "succede": "succede", "metto": "metto", "sono": "sono", "che": "che",
    "chi": "chi", "cosa": "cosa", "dove": "dove", "quando": "quando",
    "quanto": "quanto", "quale": "quale", "come": "come", "perché": "perché",
    "perche": "perché", "servizio": "servizio", "servizi": "servizi"
}

def glue_split(text):
    """Fix common word concatenation issues"""
    for k in ["ciao", "salve", "buongiorno", "buonasera", "comeva", "comeva?", "come ba", "otobot"]:
        if k in text and text.count(k) > 1:
            text = text.replace(k, f"{k} ")
    return text

def advanced_spelling_correction(text):
    """Enhanced spell correction with context awareness"""
    text = glue_split(text)
    
    # First pass - common misspellings
    for wrong, right in COMMON_MISSPELLINGS.items():
        text = re.sub(rf'\b{wrong}\b', right, text, flags=re.IGNORECASE)
    
    # Second pass - intelligent spell checking
    if spellchecker_available and text:
        words = re.findall(r'\w+', text)
        corrections = []
        
        for word in words:
            word_lower = word.lower()
            
            # Skip if already a common Italian word
            if word_lower in COMMON_MISSPELLINGS.values():
                corrections.append(word)
                continue
                
            # Skip question words that are often correct
            if word_lower in ["chi", "cosa", "dove", "quando", "quanto", "quale", "come", "perché", "perche"]:
                corrections.append(word)
                continue
                
            correction = spell.correction(word)
            if correction and rapidfuzz_available:
                similarity = fuzz.ratio(word.lower(), correction.lower())
                if similarity >= 70:  # More lenient threshold
                    corrections.append(correction)
                else:
                    corrections.append(word)
            else:
                corrections.append(word)
        
        # Reconstruct text with corrections
        fixed = text
        for original, corrected in zip(words, corrections):
            if original != corrected:
                fixed = re.sub(r'\b{}\b'.format(re.escape(original)), corrected, fixed, count=1)
        
        return fixed
    
    return text

def correct_spelling(text):
    """Wrapper for backward compatibility"""
    return advanced_spelling_correction(text)

# More specific patterns for office hours detection
OFFICE_PATTERNS = [
    r"\b(orari\s*(d[ei]l)?\s*ufficio)\b", r"\b(orari\s*apertura)\b", r"\b(orari\s*chiusura)\b",
    r"\b(quando\s*apre)\b", r"\b(quando\s*chiude)\b", r"\b(quando\s*è\s*aperto)\b",
    r"\b(quando\s*è\s*chiuso)\b", r"\b(apertura\s*otofarma)\b", r"\b(chiusura\s*otofarma)\b",
    r"\b(orario\s*otofarma)\b", r"\b(aprite)\b", r"\b(chiudete)\b", r"\b(orari\s*servizio)\b",
    r"\b(orari\s*assistenz)\b", r"\b(office\s*hours)\b", r"\b(business\s*hours)\b",
    r"\b(aperti)\b", r"\b(chiusi)\b"
]

OFFICE_TIMES = [
    "Gli uffici Otofarma sono aperti dal lunedì al venerdì dalle 9:00 alle 18:30 (ora italiana).",
    "L'orario di apertura degli uffici Otofarma è dalle 9:00 alle 18:30 dal lunedì al venerdì (CET).",
    "Puoi contattare Otofarma nei giorni feriali dalle 9:00 alle 18:30, ora locale italiana.",
    "Gli orari di servizio Otofarma sono dal lunedì al venerdì, dalle 9 alle 18:30 (ora italiana).",
    "Siamo disponibili dal lunedì al venerdì dalle 9:00 alle 18:30 (fuso orario italiano)."
]

OFFICE_KEYWORDS = {"ufficio", "apertura", "chiusura", "orari", "office", "business", "servizio", "lavorativi", "aperti", "chiusi", "spa"}

# More specific time/date patterns to avoid false positives
FUZZY_TIME_PATTERNS = [
    r"^(che\s*)?ora\s*(è|e|sono)?$", 
    r"^mi\s*(puoi)?\s*dire\s*l'?ora$", 
    r"^orario\s*(attuale|corrente)?$", 
    r"^adesso\s*che\s*ore\s*(sono)?$",
    r"^adesso\s*ora$", 
    r"^dimmi\s*l'?ora$", 
    r"^ora\s*adesso$", 
    r"^ora\s*attuale$", 
    r"^che\s*orario\s*(è)?$", 
    r"^quanto\s*è\s*l'?ora$",
    r"^orologio$", 
    r"^orari\s*attuali$"
]

FUZZY_DATE_PATTERNS = [
    r"^(che\s*)?giorno\s*(è|e)?$", 
    r"^che\s*giorno\s*è\s*oggi$", 
    r"^data\s*di\s*oggi$", 
    r"^giornata\s*di\s*oggi$", 
    r"^oggi\s*che\s*giorno\s*(è)?$",
    r"^mi\s*(puoi)?\s*dire\s*la\s*data$", 
    r"^giorno\s*odierno$", 
    r"^giorno\s*attuale$", 
    r"^che\s*data\s*(è)?$", 
    r"^quale\s*data\s*(è)?$",
    r"^oggi\s*che\s*data\s*(è)?$", 
    r"^data\s*odierna$", 
    r"^giorno\s*della\s*settimana$", 
    r"^quale\s*giorno\s*(è)?$"
]

# Use environment variable if available, else fallback to 'corpus' directory in current folder
CORPUS_PATH = os.environ.get("CORPUS_PATH", os.path.join(os.path.dirname(__file__), "corpus"))

# For deployment: prefer env variable, fallback to local 'farmacie.csv' in the same folder as app.py
PHARMACY_CSV_PATH = os.environ.get(
    "PHARMACY_CSV_PATH",
    os.path.join(os.path.dirname(__file__), "farmacie.csv")
)

# ===== OTOFARMA SPA CORPORATE INFORMATION =====
# 🏢 HEADQUARTERS: Via Ripuaria, 50k, Varcaturo, 80014 Giugliano in Campania NA
# 👔 FOUNDER & PRESIDENT: Dr. Rino Bartolomucci  
# 💼 CEO: Drs. Giovanna Incarnato
# 💻 IT HEAD: Pasquale Valentino
# 📱 FRONTEND/iOS DEV: Gaetano  
# 🤖 AI SPECIALIST: Muddasir Khuwaja

OTOFARMA_HEADQUARTERS = {
    "address": "Via Ripuaria, 50k, Varcaturo",
    "postal_code": "80014", 
    "city": "Giugliano in Campania",
    "province": "NA",
    "full_address": "Via Ripuaria, 50k, Varcaturo, 80014 Giugliano in Campania NA"
}

OTOFARMA_LEADERSHIP = {
    "founder_president": {
        "name": "Dottor Rino Bartolomucci",
        "title": "Fondatore e Presidente", 
        "role": "Founder and President",
        "voice_name": "Dottor Rino Bartolomucci"
    },
    "ceo": {
        "name": "Dottoressa Giovanna Incarnato",
        "title": "Amministratore Delegato",
        "role": "Chief Executive Officer",
        "voice_name": "Dottoressa Giovanna Incarnato",
        "italian_titles": ["CEO", "amministratore delegato", "direttore generale", "direttrice generale", "amministratrice delegata"]
    },
    "it_head": {
        "name": "Pasquale Valentino",
        "title": "Responsabile IT / IT Manager",
        "role": "IT Head and Manager"
    },
    "frontend_developer": {
        "name": "Gaetano",
        "title": "Frontend Developer e iOS Developer",
        "role": "Frontend and iOS Developer"
    }
}

OTOFARMA_TEAM = {
    "technical_team": {
        "ai_specialist": {
            "name": "Muddasir Khuwaja",
            "role": "Responsabile dell'implementazione AI presso Otofarma Spa",
            "specialization": "Artificial Intelligence & Machine Learning"
        },
        "it_manager": {
            "name": "Pasquale Valentino", 
            "role": "IT Head e Manager del Dipartimento IT",
            "specialization": "IT Infrastructure & Systems Management"
        },
        "frontend_ios_dev": {
            "name": "Gaetano",
            "role": "Frontend Developer e iOS Developer",
            "specialization": "User Interface Development & Mobile Applications"
        }
    }
}

AI_CREATOR_INFO = {
    "developer": "Muddasir Khuwaja",
    "role": "Responsabile dell'implementazione AI presso Otofarma Spa",
    "technologies": ["Deep Neural Networks", "Vertex AI", "Gemini 2.0 Flash", "Advanced NLP", "Voice Recognition"],
    "description": "Sistema AI avanzato addestrato su migliaia di nodi neurali"
}

# REVOLUTIONARY ENHANCED CORPORATE PATTERNS - HUMAN-FRIENDLY & CONTEXT-AWARE
CORPORATE_PATTERNS = [
    # Headquarters patterns - MASSIVELY EXPANDED
    (r"\b(sede|ufficio|headquarters|main office|sede principale|ufficio principale|quartier generale|dove.*lavorate|dove.*siete|dove.*otofarma|ubicazione.*otofarma)\b", "headquarters"),
    (r"\b(dove si trova|indirizzo|address|location|ubicazione|situato|posizionato|si trova)\b.*\b(otofarma|sede|ufficio|azienda|ditta|società)\b", "headquarters"),
    (r"\b(via ripuaria|varcaturo|giugliano|campania|napoli)\b", "headquarters"),
    
    # Leadership patterns - REVOLUTIONARY CONTEXT UNDERSTANDING
    (r"\b(fondatore|founder|presidente|president|ha fondato|chi ha fondato|creatore.*azienda)\b.*\b(otofarma|azienda|ditta|società)\b", "founder"),
    (r"\b(rino|bartolomucci|dottor.*rino|doctor.*rino)\b", "founder"),
    
    # CEO PATTERNS - MASSIVELY ENHANCED FOR ITALIAN CONTEXT
    (r"\b(ceo|amministratore.*delegato|amministratrice.*delegata|direttore.*generale|direttrice.*generale|ad|a\.d\.|capo|boss|dirigente.*principale|vertice.*azienda)\b", "ceo"),
    (r"\b(chi.*dirige|chi.*comanda|chi.*gestisce|chi.*capo|chi.*responsabile.*principale|chi.*guida.*azienda|leadership|dirigenza|vertice)\b.*\b(otofarma|azienda|ditta|società)\b", "ceo"), 
    (r"\b(giovanna|incarnato|dottoressa.*giovanna|dott\.ssa.*giovanna)\b", "ceo"),
    (r"\b(donna.*capo|signora.*direttrice|responsabile.*donna|amministratrice)\b", "ceo"),
    
    # APPOINTMENT & BOOKING PATTERNS - SUPER INTELLIGENT
    (r"\b(prenotazione|prenotato|prenotare|appuntamento|visita|controllo|test.*udito|quando.*mio.*appuntamento|ho.*prenotato|sono.*prenotato|verificare.*prenotazione)\b", "appointment_check"),
    
    # IT Team patterns
    (r"\b(it|responsabile.*it|manager.*it|dipartimento.*it|capo.*it|tecnologia|sistemi.*informatici)\b", "it_head"),
    (r"\b(pasquale|valentino)\b", "it_head"),
    (r"\b(frontend|front.*end|ios|sviluppatore|developer|programmatore|app.*mobile|interfacce)\b.*\b(gaetano|mobile|app)\b", "frontend_dev"),
    (r"\b(gaetano)\b", "frontend_dev"),
    (r"\b(team.*tecnico|team.*sviluppo|technical.*team|dev.*team|squadra.*tecnica)\b", "technical_team"),
    
    # AI Creator patterns - SUPER ENHANCED CONTEXT UNDERSTANDING
    (r"\b(chi.*creato|chi.*sviluppato|chi.*programmato|chi.*fatto|chi.*costruito|chi.*inventato|chi.*progettato)\b.*\b(te|tu|ai|bot|otobot|intelligenza|assistente|sistema)\b", "creator"),
    (r"\b(come.*sei.*stato.*creato|come.*sei.*nato|come.*funzioni|chi.*ti.*ha.*creato|chi.*ti.*ha.*fatto|da.*dove.*vieni|origine|sviluppatore)\b", "creator"),
    (r"\b(who.*created|who.*developed|who.*programmed|who.*made|who.*built|your.*creator|your.*developer)\b.*\b(you|ai|bot)\b", "creator"),
    (r"\b(sviluppatore.*ai|ai.*specialist|ai.*developer|intelligenza.*artificiale|machine.*learning|neural.*network)\b", "creator"),
    (r"\b(muddasir|khuwaja|mudda)\b", "creator"),
    (r"\b(come.*funzioni|architettura|come.*lavori|tecnologia|algoritmi|neural|gemini|vertex)\b", "architecture"),
    (r"\b(how.*were.*you.*created|how.*were.*you.*made|how.*do.*you.*work|what.*technology)\b", "creator")
]

# Load YAML Q&A pairs with better error handling
all_qa_pairs = []
yaml_files_loaded = 0

for yml_file in glob.glob(os.path.join(CORPUS_PATH, "**", "*.yml"), recursive=True):
    with open(yml_file, encoding='utf-8') as f:
        try:
            data = yaml.safe_load(f)
            if not data:
                continue
                
            conversations = data.get('conversations', [])
            for conv in conversations:
                if isinstance(conv, list) and len(conv) >= 2:
                    question = conv[0]
                    answers = conv[1:]
                    
                    if question and question.strip():
                        # Join all answer parts
                        full_answer = " ".join([str(x) for x in answers if x is not None and str(x).strip()])
                        if full_answer:
                            all_qa_pairs.append((question.strip(), full_answer))
                            
            yaml_files_loaded += 1
            print(f"Loaded {len(conversations)} conversations from {os.path.basename(yml_file)}")
            
        except Exception as e:
            print(f"Failed to parse {yml_file}: {e}")

print(f"Total YAML files loaded: {yaml_files_loaded}")
print(f"Total Q&A pairs loaded: {len(all_qa_pairs)}")

qa_questions = [q for q, _ in all_qa_pairs]
qa_answers = [a for _, a in all_qa_pairs]

def normalize(text):
    """Enhanced text normalization"""
    if not text:
        return ""
    
    text = str(text).strip().lower()
    
    # Remove accents but preserve Italian characters
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    
    # Clean punctuation but preserve essential characters
    text = re.sub(r'[^\w\s\']', ' ', text)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def extract_keywords(text):
    """Enhanced keyword extraction with better Italian support"""
    if not text:
        return set()
        
    if nltk_available:
        try:
            words = word_tokenize(normalize(text))
            # Filter stopwords and short words
            filtered = [w for w in words if w not in nltk_it_stopwords and len(w) > 2]
            
            # Get POS tags
            tagged = pos_tag(filtered)
            
            # Extract important words (nouns, adjectives, foreign words)
            keywords = [w for w, t in tagged if t.startswith('NN') or t.startswith('JJ') or t == 'FW']
            
            # If no keywords found, use filtered words
            main_words = keywords if keywords else filtered[:8]
            
            return set(main_words)
            
        except Exception:
            pass
    
    # Fallback method with enhanced Italian stopwords
    italian_stopwords = {
        "il", "lo", "la", "i", "gli", "le", "un", "una", "uno", "dei", "delle", "del", "della", "dello",
        "che", "di", "a", "da", "in", "con", "su", "per", "tra", "fra", "sono", "sei", "è", "siamo", 
        "siete", "ho", "hai", "ha", "abbiamo", "avete", "hanno", "era", "eri", "fu", "fui", "eravamo", 
        "eravate", "erano", "ma", "e", "o", "ed", "anche", "come", "quando", "dove", "chi", "cosa", 
        "perche", "perché", "quali", "qual", "quale", "questo", "questa", "quello", "quella", "questi", 
        "quelle", "quelli", "al", "agli", "alle", "del", "della", "dello", "degli", "delle", "dei",
        "sul", "sullo", "sulla", "sulle", "sui", "all", "alla", "allo", "alle", "queste", "questo", 
        "questi", "quella", "quello", "quelle", "quelli", "tu", "te", "io", "noi", "voi", "loro", 
        "più", "piu", "meno", "molto", "tanto", "tutta", "tutto", "tutti", "tutte", "ogni", "alcuni", 
        "alcune", "mi", "ti", "si", "ci", "vi", "lui", "lei", "se", "già", "gia", "ancora", "sempre", 
        "mai", "qui", "qua", "lì", "li", "là", "la", "sopra", "sotto", "dentro", "fuori", "prima", 
        "dopo", "durante", "mentre", "poi", "quindi", "però", "pero", "invece", "infatti", "inoltre", 
        "comunque", "tuttavia", "pure", "solo", "soltanto", "appena", "subito", "presto", "tardi", 
        "oggi", "ieri", "domani", "ora", "adesso", "bene", "male", "meglio", "peggio", "così", "cosi"
    }
    
    words = normalize(text).split()
    filtered = [w for w in words if w not in italian_stopwords and len(w) > 2]
    
    return set(filtered[:8])

def intelligent_exact_match(user_msg, questions, answers):
    """Exact matching with intelligent preprocessing"""
    user_norm = normalize(user_msg)
    user_corr = normalize(correct_spelling(user_msg))
    
    for idx, question in enumerate(questions):
        question_norm = normalize(question)
        
        # Exact match
        if user_norm == question_norm or user_corr == question_norm:
            return answers[idx], 1.0
            
        # Substring match for longer texts
        if len(user_norm) > 15 and user_norm in question_norm:
            return answers[idx], 0.95
        if len(question_norm) > 15 and question_norm in user_norm:
            return answers[idx], 0.95
            
        # Check without common question words
        question_clean = re.sub(r'\b(che|tipo|di|è|sono|cosa|come|quando|dove|quale|quanto)\b', '', question_norm).strip()
        user_clean = re.sub(r'\b(che|tipo|di|è|sono|cosa|come|quando|dove|quale|quanto)\b', '', user_norm).strip()
        
        if question_clean and user_clean and len(question_clean) > 5:
            if user_clean in question_clean or question_clean in user_clean:
                return answers[idx], 0.9
    
    return None, 0

def enhanced_keyword_match(user_msg, questions, answers):
    """Enhanced keyword matching with better scoring"""
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
            # Calculate Jaccard similarity
            jaccard_score = len(common_keywords) / len(msg_keywords | q_keywords)
            
            # Boost score for important domain keywords
            important_keywords = {
                "assistenza", "inclusa", "tipo", "prova", "gratis", "mese", "prezzo", "ricaricabili", 
                "fastidio", "orecchio", "caccia", "collegano", "pagare", "perdere", "garanzia", 
                "acqua", "teleaudiologia", "apparecchi", "acustici", "costo", "costano", "online",
                "resistenti", "vedere", "danno", "voglio", "parlarne", "familiare", "succede", 
                "metto", "servizio", "servizi", "consulenza", "supporto", "aiuto"
            }
            
            important_matches = common_keywords & important_keywords
            if important_matches:
                jaccard_score += len(important_matches) * 0.2
            
            # Extra boost for exact keyword matches
            if len(common_keywords) >= 2:
                jaccard_score += 0.1
                
            if jaccard_score > best_score and jaccard_score > 0.3:
                best_score = jaccard_score
                best_match = answers[idx]
    
    return best_match, best_score

def semantic_match(user_msg, questions, answers):
    """Enhanced semantic matching"""
    if not nlp_available or not questions:
        return None, 0
        
    try:
        # Preprocess texts
        user_processed = normalize(correct_spelling(user_msg))
        questions_processed = [normalize(q) for q in questions]
        
        corpus = questions_processed + [user_processed]
        
        # Use TF-IDF with Italian-specific preprocessing
        vectorizer = TfidfVectorizer(
            min_df=1,
            max_df=0.9,
            ngram_range=(1, 2),
            stop_words=None  # We handle stopwords in preprocessing
        )
        
        tfidf_matrix = vectorizer.fit_transform(corpus)
        
        # Calculate cosine similarity
        sim_scores = cosine_similarity(tfidf_matrix[-1], tfidf_matrix[:-1]).flatten()
        
        best_idx = sim_scores.argmax()
        best_score = sim_scores[best_idx]
        
        # Higher threshold for semantic matching
        if best_score > 0.35:
            return answers[best_idx], best_score
            
    except Exception as e:
        print(f"Semantic matching error: {e}")
        
    return None, 0

def fuzzy_match(user_msg, questions, answers):
    """Enhanced fuzzy matching with better thresholds"""
    if not rapidfuzz_available or not questions:
        return None, 0
        
    try:
        user_processed = normalize(correct_spelling(user_msg))
        questions_processed = [normalize(q) for q in questions]
        
        # Try different fuzzy matching strategies
        results = process.extractOne(
            user_processed, 
            questions_processed, 
            scorer=fuzz.token_sort_ratio,
            score_cutoff=70
        )
        
        if results and results[1] > 70:
            idx = questions_processed.index(results[0])
            return answers[idx], results[1] / 100.0
            
        # Fallback to partial ratio
        results = process.extractOne(
            user_processed, 
            questions_processed, 
            scorer=fuzz.partial_ratio,
            score_cutoff=75
        )
        
        if results and results[1] > 75:
            idx = questions_processed.index(results[0])
            return answers[idx], results[1] / 100.0
            
    except Exception as e:
        print(f"Fuzzy matching error: {e}")
        
    return None, 0

def match_yaml_qa_ai(user_msg):
    """Enhanced YAML Q&A matching with multiple strategies"""
    if not user_msg or not qa_questions:
        return None
        
    # Preprocess user message
    msg_corr = correct_spelling(user_msg)
    
    print(f"Original: '{user_msg}' -> Corrected: '{msg_corr}'")
    
    # Strategy 1: Intelligent exact matching
    answer, score = intelligent_exact_match(msg_corr, qa_questions, qa_answers)
    if answer and score > 0.85:
        print(f"Exact match found with score: {score}")
        return answer
    
    # Strategy 2: Enhanced keyword matching
    answer, score = enhanced_keyword_match(msg_corr, qa_questions, qa_answers)
    if answer and score > 0.5:
        print(f"Keyword match found with score: {score}")
        return answer
    
    # Strategy 3: Semantic similarity matching
    answer, score = semantic_match(msg_corr, qa_questions, qa_answers)
    if answer and score > 0.4:
        print(f"Semantic match found with score: {score}")
        return answer
        
    # Strategy 4: Fuzzy matching as last resort
    answer, score = fuzzy_match(msg_corr, qa_questions, qa_answers)
    if answer and score > 0.75:
        print(f"Fuzzy match found with score: {score}")
        return answer
    
    print("No match found in YAML corpus")
    return None

def is_probably_italian(text):
    """Enhanced Italian language detection"""
    if not text:
        return False
        
    text_corr = correct_spelling(text)
    text_lc = text_corr.lower()
    
    # Italian keywords
    italian_keywords = [
        "ciao", "come", "puoi", "aiutarmi", "grazie", "prenotare", "test", "udito", "orari", "info", 
        "salve", "quanto", "dove", "chi", "cosa", "quale", "azienda", "giorno", "ora", "bot", 
        "servizio", "prenotazione", "farmacia", "farmacie", "indirizzo", "telefono", "email", 
        "cap", "provincia", "regione", "otobot", "assistente", "apparecchi", "acustici", 
        "ricaricabili", "garanzia", "prezzo", "pagare", "prova", "fastidio", "orecchio", 
        "caccia", "collegano", "perdere", "acqua", "teleaudiologia", "gratis", "mese", 
        "assistenza", "costano", "online", "resistenti", "vedere", "danno", "voglio", 
        "parlarne", "familiare", "succede", "metto", "sono", "che", "tipo", "tipi",
        "inclusa", "incluso", "servizi", "consulenza", "supporto", "aiuto", "quando",
        "perché", "perche", "qualità", "qualita", "migliore", "migliori", "buono",
        "buona", "buoni", "buone", "bene", "male", "meglio", "peggio", "prima", "dopo"
    ]
    
    # Count Italian keyword matches
    matches = sum(1 for kw in italian_keywords if kw in text_lc)
    
    # Enhanced detection
    if matches > 0:
        return True
    
    # Check for Italian word patterns
    msg_keywords = extract_keywords(text_corr)
    italian_keywords_set = set(italian_keywords)
    
    if len(msg_keywords & italian_keywords_set) > 0:
        return True
    
    # Check against English patterns
    english_starters = [
        "what", "who", "how", "when", "where", "why", "can you", "could you", 
        "please", "help", "hi", "hello", "good morning", "good evening"
    ]
    
    if any(text_lc.strip().startswith(st) for st in english_starters):
        return False
    
    # English word detection
    english_words = {
        "what", "who", "where", "when", "why", "how", "pharmacy", "address", 
        "mail", "email", "number", "phone", "open", "close", "near", "region", 
        "province", "city", "find", "show", "list", "info", "the", "and", "or", 
        "but", "for", "with", "from", "about", "this", "that", "your", "my"
    }
    
    words = set(re.findall(r'\w+', text_lc))
    english_ratio = len(words & english_words) / (len(words) + 1e-5)
    
    return english_ratio < 0.4

def detect_precise_assistant_name(msg):
    """Enhanced assistant name detection"""
    if not msg:
        return False
        
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
    
    # Extended pattern matching with context
    for pattern in EXTENDED_ASSISTANT_NAME_PATTERNS:
        if re.search(pattern, msg_lc):
            context_words = {"assistente", "virtuale", "otofarma", "spa"}
            if any(word in msg_lc for word in context_words):
                return True
    
    return False

def detect_assistant_name(msg):
    """Wrapper for assistant name detection"""
    return detect_precise_assistant_name(msg)

def get_assistant_introduction():
    """Get random assistant introduction"""
    return random.choice(ASSISTANT_RESPONSES)

def detect_time_or_date_question(msg):
    """Enhanced time/date detection with stricter patterns"""
    if not msg:
        return None
        
    msg_corr = correct_spelling(msg)
    msg_lc = normalize(msg_corr).strip()
    
    # Must be very specific to avoid false positives
    for pat in FUZZY_TIME_PATTERNS:
        if re.match(pat, msg_lc):
            return "time"
    
    for pat in FUZZY_DATE_PATTERNS:
        if re.match(pat, msg_lc):
            return "date"
    
    # Check for very short queries
    tokens = msg_lc.split()
    if len(tokens) <= 2:
        if tokens and tokens[0] in ["ora", "orario"]:
            return "time"
        if tokens and tokens[0] in ["giorno", "data"]:
            return "date"
    
    return None

def detect_office_hours_question(msg):
    """Enhanced office hours detection"""
    if not msg:
        return False
        
    msg_corr = correct_spelling(msg)
    msg_lc = normalize(msg_corr)
    
    # Skip if it's asking for assistant name or general patterns
    if detect_assistant_name(msg_lc):
        return False
        
    if check_general_patterns(msg_lc):
        return False
    
    # Check specific office hour patterns
    for pat in OFFICE_PATTERNS:
        if re.search(pat, msg_lc):
            return True
    
    # Check for office keywords
    tokens = set(msg_lc.split())
    office_matches = tokens & OFFICE_KEYWORDS
    
    # Need at least 2 relevant words for office hours
    if len(office_matches) >= 2:
        return True
    
    return False

def get_office_hours_answer():
    """Get random office hours answer"""
    return random.choice(OFFICE_TIMES)

def get_time_answer():
    """Get current time in Italian"""
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
    """Get current date in Italian"""
    tz = pytz.timezone("Europe/Rome")
    now = datetime.now(tz)
    
    days_it = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
    months_it = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", 
                 "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
    
    weekday = days_it[now.weekday()]
    month = months_it[now.month - 1]
    
    polite_dates = [
        f"Oggi in Italia è {weekday} {now.day} {month} {now.year}",
        f"La data odierna in Italia è {now.day} {month} {now.year}",
        f"Oggi è il {now.day} {month} {now.year} {weekday} in Italia",
        f"È {weekday} {now.day} {month} {now.year} secondo il calendario italiano"
    ]
    
    return random.choice(polite_dates)


def check_general_patterns(user_msg):
    """Enhanced general pattern checking"""
    if not user_msg:
        return None
        
    msg = normalize(correct_spelling(user_msg))
    
    # Skip if asking for assistant name
    if detect_assistant_name(msg):
        return None
    
    # Stricter greeting matching: only match exact short greetings or "come va"/"come stai" as whole phrase
    for pattern, reply in CUSTOM_GREETINGS:
        # Only match if the message is exactly the greeting or a very close fuzzy match
        if msg == pattern:
            return reply
        if rapidfuzz_available and len(pattern) > 3:
            if fuzz.ratio(pattern, msg) > 90:
                return reply

    # Check for standalone greetings
    tokens = msg.split()
    if len(tokens) == 1 and tokens[0] in ["ciao", "salve", "buongiorno", "buonasera", "buonanotte"]:
        return "Salve! Sono qui per aiutarti in tutto ciò che riguarda Otofarma."

    return None

# ===== OTOFARMA CORPORATE KNOWLEDGE FUNCTIONS =====

def detect_corporate_question(msg):
    """Detect questions about Otofarma corporate information"""
    if not msg:
        return None
        
    msg_lc = normalize(msg)
    
    for pattern, topic in CORPORATE_PATTERNS:
        if re.search(pattern, msg_lc, re.IGNORECASE):
            return topic
    
    return None

def get_headquarters_info():
    """Professional headquarters information"""
    responses = [
        f"La sede principale di Otofarma Spa si trova presso {OTOFARMA_HEADQUARTERS['full_address']}. "
        f"Questo è il nostro quartier generale dove vengono coordinate tutte le attività aziendali, "
        f"dalla ricerca e sviluppo di apparecchi acustici innovativi alla gestione della rete nazionale "
        f"di farmacie specializzate. La sede è strategicamente posizionata in Campania per servire "
        f"al meglio tutto il territorio italiano.",
        
        f"Il nostro ufficio principale è situato a {OTOFARMA_HEADQUARTERS['full_address']}. "
        f"Da questa sede centrale coordiniamo tutte le nostre attività di eccellenza nel settore "
        f"audiologico, inclusi i servizi di teleaudiologia e la distribuzione di apparecchi acustici "
        f"di ultima generazione su tutto il territorio nazionale.",
        
        f"Otofarma Spa ha la sua sede centrale presso {OTOFARMA_HEADQUARTERS['full_address']}. "
        f"È da qui che gestiamo la nostra missione di migliorare la qualità della vita delle persone "
        f"attraverso soluzioni auditive innovative e un servizio di eccellenza in tutta Italia."
    ]
    return random.choice(responses)

def get_founder_info():
    """Professional founder information"""
    founder = OTOFARMA_LEADERSHIP['founder_president']
    responses = [
        f"Il fondatore e presidente di Otofarma Spa è il rispettato {founder['name']}. "
        f"Sotto la sua guida visionaria, Otofarma è diventata un punto di riferimento nel settore "
        f"audiologico italiano, distinguendosi per l'innovazione tecnologica e l'eccellenza nel "
        f"servizio. Il {founder['name']} ha dedicato la sua carriera a migliorare la qualità "
        f"della vita delle persone con problemi uditivi.",
        
        f"Otofarma Spa è stata fondata e viene tuttora presieduta dal {founder['name']}, "
        f"una figura di grande prestigio nel settore audiologico. La sua esperienza e dedizione "
        f"hanno portato l'azienda a diventare leader nell'innovazione di apparecchi acustici e "
        f"servizi specializzati, con una rete capillare su tutto il territorio nazionale.",
        
        f"Il {founder['name']} è il fondatore e presidente di Otofarma Spa. "
        f"Grazie alla sua leadership illuminata e alla passione per l'innovazione, "
        f"Otofarma è oggi sinonimo di eccellenza nel campo dell'audiologia, offrendo "
        f"soluzioni all'avanguardia e un servizio personalizzato di altissimo livello."
    ]
    return random.choice(responses)

def get_ceo_info():
    """ENHANCED CEO Information - Perfect Italian with Voice-Friendly Pronunciation"""
    ceo = OTOFARMA_LEADERSHIP['ceo']
    voice_name = ceo['voice_name']  # "Dottoressa Giovanna Incarnato"
    
    responses = [
        f"La nostra Amministratrice Delegata è {voice_name}, "
        f"una professionista di eccezionale competenza che guida Otofarma Spa con grande "
        f"esperienza e visione strategica. Sotto la sua direzione, la nostra azienda continua "
        f"ad espandersi e innovare nel settore audiologico, mantenendo sempre al centro la soddisfazione "
        f"del cliente e l'eccellenza dei servizi offerti.",
        
        f"{voice_name} ricopre il ruolo di Amministratrice Delegata e CEO di Otofarma Spa. "
        f"Con la sua leadership dinamica e orientata all'innovazione, sta portando "
        f"l'azienda verso nuovi traguardi nel settore degli apparecchi acustici, implementando "
        f"tecnologie all'avanguardia come la teleaudiologia e sviluppando soluzioni "
        f"sempre più personalizzate per i nostri pazienti.",
        
        f"Il vertice operativo di Otofarma Spa è guidato dalla stimata {voice_name}, "
        f"che con la sua competenza medica e manageriale sta dirigendo la nostra azienda verso un futuro "
        f"di continue innovazioni. La sua visione strategica e l'attenzione ai dettagli clinici "
        f"garantiscono che ogni paziente riceva il miglior servizio audiologico possibile.",
        
        f"La direzione generale di Otofarma è affidata a {voice_name}, "
        f"una dottoressa con grande esperienza nel settore sanitario che combina competenze mediche "
        f"e manageriali. Sotto la sua guida, Otofarma Spa è diventata un punto di riferimento "
        f"nell'innovazione degli apparecchi acustici e nei servizi di teleaudiologia in Italia."
    ]
    return random.choice(responses)

def get_leadership_info():
    """Combined leadership information"""
    founder = OTOFARMA_LEADERSHIP['founder_president']
    ceo = OTOFARMA_LEADERSHIP['ceo']
    
    response = (
        f"Otofarma Spa è guidata da un team di leadership eccezionale. "
        f"Il fondatore e presidente è il rispettato {founder['name']}, "
        f"che ha creato e continua a ispirare la visione aziendale. "
        f"L'operatività quotidiana è gestita dalla nostra Amministratrice Delegata, "
        f"la {ceo['voice_name']}, che con la sua competenza sta portando "
        f"l'azienda verso nuovi traguardi di innovazione e eccellenza. "
        f"Insieme, formano una leadership che garantisce i più alti standard "
        f"di qualità e servizio nel settore audiologico."
    )
    return response

def get_creator_info():
    """AI creator and architecture information"""
    creator = AI_CREATOR_INFO
    responses = [
        f"Sono un sistema di intelligenza artificiale avanzato progettato e sviluppato da "
        f"{creator['developer']}, {creator['role']}. "
        f"La mia architettura si basa su migliaia di nodi neurali e utilizza tecnologie "
        f"all'avanguardia come {', '.join(creator['technologies'][:3])} e molte altre. "
        f"Per motivi di privacy aziendale, non posso condividere pubblicamente i dettagli "
        f"completi della mia architettura, ma posso assicurarti che dietro ogni mia risposta "
        f"lavorano milioni di connessioni neurali per offrirti il miglior servizio possibile.",
        
        f"Sono stato creato da {creator['developer']}, che è {creator['role']}. "
        f"Il mio sviluppo ha richiesto l'implementazione di tecnologie avanzate tra cui "
        f"{', '.join(creator['technologies'])} e sistemi di elaborazione del linguaggio "
        f"naturale di ultima generazione. Anche se non posso rivelare tutti i segreti "
        f"della mia architettura per questioni di riservatezza aziendale, posso dirti "
        f"che sono alimentato da una rete di milioni di nodi che lavorano incessantemente "
        f"per comprendere e rispondere alle tue esigenze nel migliore dei modi.",
        
        f"Il mio sviluppo è opera di {creator['developer']}, {creator['role']}. "
        f"Sono basato su un'architettura di deep learning che integra {', '.join(creator['technologies'][:2])} "
        f"e altre tecnologie proprietarie avanzate. Immagina milioni di nodi neurali che "
        f"collaborano per elaborare le tue richieste - questa è la complessità che si cela "
        f"dietro ogni mia interazione. Per proteggere il know-how aziendale, i dettagli "
        f"specifici della mia struttura rimangono riservati, ma posso garantirti che "
        f"rappresento il meglio dell'innovazione AI applicata al settore audiologico."
    ]
    return random.choice(responses)

def get_it_head_info():
    """IT Head information"""
    it_manager = OTOFARMA_LEADERSHIP['it_head']
    responses = [
        f"Il nostro {it_manager['title']} è {it_manager['name']}, "
        f"un professionista altamente qualificato che gestisce tutti i sistemi informatici "
        f"e l'infrastruttura tecnologica di Otofarma Spa. Sotto la sua supervisione esperta, "
        f"garantiamo che tutti i nostri sistemi digitali, dalla teleaudiologia alle piattaforme "
        f"di gestione clienti, funzionino sempre al massimo delle prestazioni.",
        
        f"{it_manager['name']} è il {it_manager['title']} di Otofarma Spa. "
        f"La sua competenza tecnica e leadership nel dipartimento IT assicurano che "
        f"tutte le nostre innovazioni tecnologiche siano implementate con eccellenza. "
        f"Gestisce l'intera infrastruttura digitale aziendale, garantendo sicurezza, "
        f"efficienza e continuità operativa in tutti i nostri servizi.",
        
        f"Il Dipartimento IT di Otofarma è diretto da {it_manager['name']}, "
        f"che ricopre il ruolo di {it_manager['title']}. La sua esperienza "
        f"e dedizione permettono a Otofarma di rimanere all'avanguardia nella "
        f"digitalizzazione dei servizi audiologici, mantenendo sempre i più alti "
        f"standard di sicurezza e affidabilità dei sistemi."
    ]
    return random.choice(responses)

def get_frontend_developer_info():
    """Frontend Developer information"""
    developer = OTOFARMA_LEADERSHIP['frontend_developer']
    responses = [
        f"Il nostro talentoso {developer['title']} è {developer['name']}, "
        f"che si occupa di creare e mantenere tutte le interfacce utente delle nostre "
        f"applicazioni web e mobile. La sua expertise nello sviluppo frontend e iOS "
        f"garantisce che i nostri clienti abbiano sempre un'esperienza digitale "
        f"fluida, intuitiva e di alta qualità su tutti i dispositivi.",
        
        f"{developer['name']} è il nostro {developer['title']} specializzato. "
        f"Grazie alle sue competenze avanzate nello sviluppo di interfacce utente "
        f"e applicazioni iOS, garantisce che tutti i nostri servizi digitali "
        f"siano accessibili, user-friendly e tecnologicamente all'avanguardia. "
        f"Il suo lavoro è fondamentale per l'esperienza cliente digitale di Otofarma.",
        
        f"Lo sviluppo delle nostre interfacce digitali è affidato a {developer['name']}, "
        f"il nostro {developer['title']}. La sua competenza nello sviluppo "
        f"frontend e nella creazione di app iOS ci permette di offrire soluzioni "
        f"digitali innovative e accessibili, sempre in linea con le più moderne "
        f"tendenze del design e dell'usabilità."
    ]
    return random.choice(responses)

def get_technical_team_info():
    """Complete technical team information"""
    ai_specialist = OTOFARMA_TEAM['technical_team']['ai_specialist']
    it_manager = OTOFARMA_TEAM['technical_team']['it_manager']
    frontend_dev = OTOFARMA_TEAM['technical_team']['frontend_ios_dev']
    
    response = (
        f"Il team tecnico di Otofarma Spa è composto da professionisti di eccellenza: "
        f"{ai_specialist['name']}, {ai_specialist['role']}, che si occupa dell'innovazione "
        f"nell'intelligenza artificiale e machine learning; {it_manager['name']}, "
        f"{it_manager['role']}, che gestisce tutta l'infrastruttura IT aziendale; "
        f"e {frontend_dev['name']}, {frontend_dev['role']}, che crea le interfacce "
        f"utente e le applicazioni mobile. Insieme, questo team garantisce che Otofarma "
        f"rimanga sempre all'avanguardia dell'innovazione tecnologica nel settore audiologico."
    )
    return response

def get_architecture_info():
    """Technical architecture information"""
    creator = AI_CREATOR_INFO
    response = (
        f"La mia architettura è il risultato di un lavoro innovativo guidato da "
        f"{creator['developer']}, {creator['role']}. "
        f"Utilizzo un sistema ibrido che combina {', '.join(creator['technologies'])} "
        f"con algoritmi proprietari sviluppati specificamente per il settore audiologico. "
        f"Dietro ogni mia risposta ci sono letteralmente milioni di parametri neurali "
        f"che elaborano informazioni in tempo reale. Tuttavia, per tutelare la proprietà "
        f"intellettuale di Otofarma, non posso condividere i dettagli tecnici completi "
        f"della mia struttura. Quello che posso dire è che rappresento l'eccellenza "
        f"dell'intelligenza artificiale applicata ai servizi audiologici."
    )
    return response

# Pharmacy-related functions (unchanged but with better error handling)
pharmacies = []
if os.path.isfile(PHARMACY_CSV_PATH):
    try:
        with open(PHARMACY_CSV_PATH, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=';' if PHARMACY_CSV_PATH.lower().endswith('.csv') else ',')
            for row in reader:
                pharmacies.append(row)
        print(f"Caricate {len(pharmacies)} farmacie dal CSV.")
        logger.info(f"🏥 Successfully loaded {len(pharmacies)} Otofarma pharmacy locations")
    except Exception as e:
        print(f"Errore nel caricamento del CSV farmacie: {e}")
        logger.error(f"❌ Error loading pharmacy CSV: {e}")
else:
    print(f"File CSV farmacie non trovato: {PHARMACY_CSV_PATH}")
    logger.warning(f"⚠️ Pharmacy CSV file not found: {PHARMACY_CSV_PATH}")

def is_pharmacy_question(msg):
    """Enhanced pharmacy question detection for voice assistant"""
    if not msg:
        return False
        
    msg_lc = normalize(msg)
    
    # Primary pharmacy keywords (high confidence)
    primary_keywords = ["farmacia", "farmacie", "otofarma", "pharmacy", "pharmacies"]
    
    # Location/search intent keywords - ENHANCED FOR "WHAT/WHICH" QUESTIONS
    location_keywords = [
        "dove", "trovare", "vicino", "cerca", "cerco", "mostra", "dimmi", "tell me",
        "trova", "locate", "position", "posizione", "locazione", "zona", "quartiere",
        "ci sono", "sono", "esistono", "availability", "disponibili", "presenti",
        "quali", "what", "which", "cosa", "che", "elenca", "list", "lista", "elenco",
        # ADDED MORE VARIATIONS
        "sono le", "sono i", "ci sono le", "sono presenti", "sono disponibili",
        "tutte le", "all the", "show me", "tell me about"
    ]
    
    # City/region keywords
    place_keywords = [
        "milano", "roma", "napoli", "torino", "firenze", "bologna", "venezia", "genova",
        "palermo", "bari", "catania", "brescia", "verona", "padova", "trieste", "taranto",
        "reggio", "modena", "prato", "parma", "città", "city", "regione", "provincia",
        "cap", "zona", "area", "località", "comune", "centro", "periferia"
    ]
    
    # Contact info keywords
    contact_keywords = [
        "indirizzo", "telefono", "numero", "email", "contatto", "info", "informazioni",
        "address", "phone", "mail", "contact", "details", "dettagli", "orari", "apertura",
        "chiusura", "aperta", "chiusa", "hours", "when", "quando", "schedule"
    ]
    
    # Check for primary keyword + intent
    has_pharmacy = any(kw in msg_lc for kw in primary_keywords)
    has_location_intent = any(kw in msg_lc for kw in location_keywords)
    has_place = any(kw in msg_lc for kw in place_keywords)
    has_contact_intent = any(kw in msg_lc for kw in contact_keywords)
    
    # Advanced pattern matching for voice queries - ENHANCED FOR "WHAT/WHICH" QUESTIONS
    voice_patterns = [
        r"\b(dove\s+(sono|si\s+trovano|posso\s+trovare).*(farmacie?|otofarma))\b",
        r"\b(farmacie?.*\s+(milano|roma|napoli|torino|firenze|bologna|venezia|genova|palermo|bari|catania|brescia|verona|padova|trieste|taranto|reggio|modena|prato|parma))\b",
        r"\b(cerco\s+(una\s+)?farmacie?)\b",
        r"\b(ci\s+sono.*farmacie?.*\s+(a|in|su|per|di))\b",
        r"\b(mostra.*farmacie?)\b",
        r"\b(dimmi.*farmacie?)\b",
        r"\b(qual.*farmacie?.*vicin)\b",
        r"\b(dove.*otofarma)\b",
        # ENHANCED PATTERNS FOR "WHAT/WHICH ARE PHARMACIES"
        r"\b(quali?\s+(sono|sono\s+le)\s+farmacie?)\b",
        r"\b(what\s+are\s+.*(pharmacy|pharmacies))\b",
        r"\b(which\s+are\s+.*(pharmacy|pharmacies))\b",
        r"\b(cosa\s+sono\s+.*farmacie?)\b",
        r"\b(che\s+farmacie?)\b",
        r"\b(elenco.*farmacie?)\b",
        r"\b(lista.*farmacie?)\b",
        r"\b(elenca.*farmacie?)\b",
        # NEW COMPREHENSIVE PATTERNS
        r"\b(quali?\s+farmacie?\s+(ci\s+sono|sono|esistono|sono\s+presenti))\b",
        r"\b(farmacie?\s+(a|in|di)\s+(milano|roma|napoli|torino|firenze|bologna|venezia|genova|palermo|bari|catania|brescia|verona|padova))\b",
        r"\b(which\s+farmacie?)\b",
        r"\b(what\s+farmacie?)\b"
    ]
    
    # Check voice patterns
    for pattern in voice_patterns:
        if re.search(pattern, msg_lc, re.IGNORECASE):
            return True
    
    # Scoring system for better detection
    score = 0
    if has_pharmacy:
        score += 3
    if has_location_intent:
        score += 2
    if has_place:
        score += 2
    if has_contact_intent:
        score += 1
        
    return score >= 3

def extract_city_from_query(user_msg):
    """Advanced city extraction from voice queries"""
    user_msg_norm = normalize(user_msg)
    
    # Get all possible cities from CSV
    city_keys = ['Città', 'città', 'city', 'City', 'CITTÀ']
    cities_original = set()
    
    for ph in pharmacies:
        for key in city_keys:
            city = ph.get(key, "")
            if city and city.strip():
                cities_original.add(city.strip())
    
    # Create normalized mapping
    cities_map = {normalize(city): city for city in cities_original}
    found_cities = []
    
    # Direct city matching
    for city_norm, city_orig in cities_map.items():
        if city_norm and city_norm in user_msg_norm:
            found_cities.append(city_orig)
    
    # If no cities found, try major Italian cities patterns
    major_cities_patterns = {
        r"\bmilan[oi]?\b": "Milano",
        r"\brom[ae]?\b": "Roma", 
        r"\bnapoli?\b": "Napoli",
        r"\btorin[oi]?\b": "Torino",
        r"\bfirenz[ei]?\b": "Firenze",
        r"\bbologn[ae]?\b": "Bologna",
        r"\bvenezi[ae]?\b": "Venezia",
        r"\bgenov[ae]?\b": "Genova",
        r"\bpalerm[oi]?\b": "Palermo",
        r"\bbari?\b": "Bari",
        r"\bcatani[ae]?\b": "Catania",
        r"\bbresci[ae]?\b": "Brescia",
        r"\bveron[ae]?\b": "Verona",
        r"\bpadov[ae]?\b": "Padova"
    }
    
    if not found_cities:
        for pattern, city in major_cities_patterns.items():
            if re.search(pattern, user_msg_norm, re.IGNORECASE):
                # Check if this city exists in our CSV
                if city in cities_original:
                    found_cities.append(city)
                    break
    
    return found_cities

def get_available_cities_sample():
    """Get a sample of available cities for user guidance"""
    city_keys = ['Città', 'città', 'city', 'City', 'CITTÀ']
    cities_set = set()
    
    for ph in pharmacies:
        for key in city_keys:
            city = ph.get(key, "")
            if city and city.strip():
                cities_set.add(city.strip())
    
    cities_list = sorted(list(cities_set))
    
    # Return first 10 cities as examples
    if len(cities_list) > 10:
        sample_cities = cities_list[:10]
        return f"Ecco alcune delle città dove abbiamo farmacie Otofarma: {', '.join(sample_cities[:8])}, e molte altre. Dimmi la città che ti interessa!"
    else:
        return f"Le città disponibili sono: {', '.join(cities_list)}"

def extract_field_intent(user_msg):
    """Extract what information user wants about pharmacy"""
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
    """Find best matching pharmacy"""
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
    """Get all pharmacies in a specific city"""
    city_norm = normalize(city_name)
    return [
        ph for ph in pharmacies
        if normalize(ph.get("Città", ph.get("città", ""))) == city_norm
    ]

def format_pharmacies_list(ph_list, city_name, user_msg=None):
    """Professional voice-optimized pharmacy list response with formal Italian"""
    if not ph_list:
        return f"Mi dispiace, non ho trovato farmacie Otofarma a {city_name}. Posso cercare in un'altra città se desideri."
    
    city_formatted = city_name.strip() or "la città richiesta"
    total = len(ph_list)
    
    # Professional voice-friendly introduction
    intro_templates = [
        f"Perfetto! Ho trovato {total} farmaci{'a' if total == 1 else 'e'} Otofarma a {city_formatted}.",
        f"Eccellente! A {city_formatted} sono presenti {total} farmaci{'a' if total == 1 else 'e'} Otofarma affiliate.",
        f"Ottimo! Risultano {total} farmaci{'a' if total == 1 else 'e'} Otofarma registrate per {city_formatted}."
    ]
    
    # Get the best/first pharmacy for detailed info
    best_ph = ph_list[0]
    name = best_ph.get("Farmacia", best_ph.get("Nome", "Farmacia Otofarma"))
    address = best_ph.get("Indirizzo", best_ph.get("indirizzo", ""))
    cap = best_ph.get("CAP", best_ph.get("cap", ""))
    prov = best_ph.get("Provincia", best_ph.get("provincia", ""))
    tel = best_ph.get("Telefono", best_ph.get("telefono", ""))
    email = best_ph.get("Email", best_ph.get("email", ""))
    
    # Professional voice response WITHOUT BULLET POINTS - using formal Italian
    response_parts = [
        random.choice(intro_templates),
        "",
        "Ecco i dettagli della farmacia principale della zona.",
        "",
        f"Nome: {name}",
        f"Indirizzo: {address}"
    ]
    
    if cap and prov:
        response_parts.append(f"Codice postale: {cap}, {city_formatted}, provincia di {prov}")
    elif cap:
        response_parts.append(f"Codice postale: {cap}")
    elif prov:
        response_parts.append(f"Provincia di {prov}")
    
    if tel and tel != "N/A" and tel.strip():
        response_parts.append(f"Telefono di contatto: {tel}")
    
    if email and email != "N/A" and email.strip() and "@" in email:
        response_parts.append(f"Indirizzo email: {email}")
    
    response_parts.extend([
        "",
        "Questa farmacia offre tutti i servizi specializzati Otofarma, inclusi apparecchi acustici su misura, consulenze audiologiche e teleaudiologia.",
        "",
        f"Se desideri informazioni su altre farmacie a {city_formatted} o hai bisogno di dettagli specifici, chiedimi pure!"
    ])
    
    # Add information about multiple pharmacies if applicable
    if total > 1:
        response_parts.extend([
            "",
            f"Sono disponibili altre {total-1} farmacie Otofarma a {city_formatted}. Se vuoi conoscere altre farmacie in questa città, chiedimi pure specificando la zona che preferisci."
        ])
    
    response_parts.extend([
        "",
        "Puoi trovare tutte le farmacie Otofarma vicine a te anche tramite la mappa nella nostra app!"
    ])
    
    return "\n".join(response_parts)

def format_pharmacy_answer(ph, field_intents):
    """Format single pharmacy response"""
    if not ph:
        return "Mi dispiace, non sono riuscito a trovare una farmacia corrispondente. Specifica il nome e la città o provincia per una ricerca più precisa."
    
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
    """Calculate distance between two points"""
    R = 6371.0
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def nearest_pharmacy(user_lat, user_lon):
    """Find nearest pharmacy"""
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
    """Format nearest pharmacy response"""
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
        f"La farmacia più prossima alla tua posizione attuale è:"
    ])
    
    dettagli = [
        f"Nome: {nome}",
        f"Indirizzo: {indirizzo}, {cap} {città} ({provincia})",
        f"Telefono: {telefono}",
        f"Email: {email}",
        f"Distanza stimata: {distanza} km"
    ]
    
    outro = "Se ti serve altro chiedimi pure, sono qui per aiutarti!"
    
    return "\n".join([intro] + dettagli + [outro])

def is_near_me_query(user_msg):
    """Detect 'near me' queries"""
    msg = normalize(user_msg)
    near_patterns = [
        "pharmacy near me", "pharmacies near me", "nearest pharmacy",
        "farmacia più vicina", "farmacia vicina", "farmacia vicino a me", 
        "farmacie vicino a me", "farmacia nelle vicinanze", "farmacia qui", 
        "farmacie qui", "farmacia intorno a me", "vicino a me", "più vicina a me", 
        "vicina a me"
    ]
    
    return any(pat in msg for pat in near_patterns)

class FallbackMemory:
    """Memory for fallback responses"""
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

def format_numbers_for_speech(text):
    """INTELLIGENT number formatting for TTS - contacts vs prices vs years"""
    import re
    
    # Enhanced patterns for different number types
    phone_pattern = r'\b(\d{8,12})\b'  # 8-12 digits = phone numbers
    price_pattern = r'€\s*(\d+)'  # Prices with € symbol
    year_pattern = r'\b(19|20)(\d{2})\b'  # Years 1900-2099
    
    def format_phone_digits(match):
        number = match.group(1)
        digit_map = {
            '0': 'zero', '1': 'uno', '2': 'due', '3': 'tre', '4': 'quattro',
            '5': 'cinque', '6': 'sei', '7': 'sette', '8': 'otto', '9': 'nove'
        }
        return ' '.join(digit_map[digit] for digit in number)
    
    # Context-aware number detection
    text_lower = text.lower()
    
    # If context suggests contact/phone number
    if any(word in text_lower for word in ['numero', 'telefono', 'cellulare', 'contatto', 'chiama', 'whatsapp']):
        # Format long numbers (8+ digits) as digit-by-digit
        text = re.sub(phone_pattern, format_phone_digits, text)
    
    # Keep prices and years as normal numbers (unchanged)
    return text

# Initialize Gemini AI for natural Italian conversations



def initialize_gemini():
    """Initialize Gemini AI"""
    try:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "speakai-467308-fb5a36feacef.json"
        vertexai.init(project="speakai-467308", location="us-east4") # Changed location
        return True
    except Exception as e:
        print(f"Gemini initialization error: {e}")
        return False

# Initialize Gemini
gemini_available = initialize_gemini()

def analyze_full_context_with_gemini(user_message):
    """REVOLUTIONARY CONTEXT ANALYZER - Understands complete sentence meaning"""
    if not gemini_available:
        return None
        
    try:
        model = GenerativeModel("gemini-2.0-flash-exp-1121")  # Latest experimental model
        
        analysis_prompt = f"""
        ANALISI CONTESTO ITALIANO - Sei un analizzatore di contesto per OtoBot di Otofarma Spa.
        
        Analizza questa frase italiana e determina ESATTAMENTE cosa vuole l'utente:
        "{user_message}"
        
        Rispondi con UNA SOLA parola che rappresenta l'INTENZIONE PRINCIPALE:
        - "prenotazione" = se chiede di verificare/controllare appuntamenti esistenti
        - "nuova_prenotazione" = se vuole prenotare nuovo appuntamento  
        - "ceo" = se chiede del CEO/direttore/capo/amministratore delegato
        - "fondatore" = se chiede del fondatore/presidente
        - "creatore" = se chiede chi ha creato l'AI/bot
        - "sede" = se chiede dove si trova Otofarma
        - "farmacia" = se cerca farmacie/punti vendita
        - "servizi" = se chiede dei servizi Otofarma
        - "conversazione" = per tutto il resto
        
        RISPOSTA (una sola parola):
        """
        
        response = model.generate_content(analysis_prompt)
        intent = response.text.strip().lower()
        
        return intent if intent in ["prenotazione", "nuova_prenotazione", "ceo", "fondatore", "creatore", "sede", "farmacia", "servizi", "conversazione"] else "conversazione"
        
    except Exception as e:
        print(f"Context analysis error: {e}")
        return "conversazione"

def get_gemini_conversation(user_message):
    """SUPER-ENHANCED Gemini - FULL SENTENCE UNDERSTANDING"""
    if not gemini_available:
        return None
        
    try:
        model = GenerativeModel("gemini-2.0-flash-exp-1121")  # Latest experimental model with better context
        
        prompt = f"""
        Sei l'assistente AI di Otofarma Spa. COMPRENDI TUTTO IL CONTESTO della frase, non solo le parole singole.
        
        REGOLE CRITICHE:
        1. NON presentarti mai ("Io sono...", "Sono OtoBot", ecc.)
        2. Vai DIRETTAMENTE alla risposta alla domanda
        3. Analizza TUTTA la frase, non solo parole chiave
        4. Comprendi l'INTENZIONE completa dell'utente
        5. Rispondi SEMPRE in italiano perfetto e naturale
        6. Mantieni tono professionale ma UMANO e amichevole
        7. Se non capisci, chiedi chiarimenti specifici SENZA autopresentarti
        
        CONTESTO AZIENDALE:
        - CEO: Dottoressa Giovanna Incarnato (amministratrice delegata)
        - Fondatore: Dottor Rino Bartolomucci 
        - Sede: Via Ripuaria, Varcaturo, Giugliano in Campania
        - Servizi: apparecchi acustici, teleaudiologia, farmacie
        
        COMPRENSIONE TOTALE - Analizza questa richiesta completa:
        "{user_message}"
        
        Rispondi considerando IL SIGNIFICATO COMPLETO, non solo le parole singole. 
        IMPORTANTE: Rispondi direttamente SENZA mai dire chi sei.
        
        Risposta diretta (massimo 3 frasi, italiano perfetto, NO autopresentazioni):
        """
        
        response = model.generate_content(prompt)
        gemini_text = response.text.strip()

        # Enhanced response validation
        if len(gemini_text) < 10 or not gemini_text:
            return f"Ho compreso la tua richiesta su '{user_message}', ma ho bisogno di maggiori dettagli per aiutarti al meglio. Puoi essere più specifico?"

        # Remove self-introductions if they slip through
        intro_patterns = [
            r'^(Ciao[,!]?\s*)?Sono\s+(il\s+)?OtoBot[.,!]?\s*',
            r'^(Salve[,!]?\s*)?Io\s+sono\s+(il\s+)?OtoBot[.,!]?\s*',
            r'^(Mi\s+chiamo|Sono)\s+(il\s+)?OtoBot[.,!]?\s*',
            r'^OtoBot\s+qui[.,!]?\s*',
            r'^Sono\s+l\'assistente\s+AI\s+(di\s+)?Otofarma[.,!]?\s*'
        ]
        
        for pattern in intro_patterns:
            gemini_text = re.sub(pattern, '', gemini_text, flags=re.IGNORECASE)
        
        gemini_text = gemini_text.strip()
        
        # If text was only an introduction, return fallback
        if len(gemini_text) < 10:
            return f"Ho compreso la tua richiesta, ma ho bisogno di maggiori dettagli per aiutarti al meglio. Puoi essere più specifico?"

        # Ensure professional Italian response
        if len(gemini_text) > 300:
            # Find best cut point
            sentences = gemini_text.split('. ')
            if len(sentences) > 1:
                gemini_text = '. '.join(sentences[:2]) + '.'
            else:
                gemini_text = gemini_text[:300] + '...'
                
        return gemini_text

    except Exception as e:
        print(f"Enhanced Gemini error: {e}")
        return None

def intelligent_appointment_detector(user_message):
    """REVOLUTIONARY Appointment Context Detector"""
    user_msg = normalize(user_message.strip())
    
    # CONTEXT ANALYSIS - Check if asking about EXISTING appointment
    check_patterns = [
        "mio appuntamento", "mia prenotazione", "ho prenotato", "sono prenotato",
        "quando ho", "che giorno ho", "verificare", "controllare", "confermare",
        "ho già prenotato", "già prenotato", "sono in lista", "sono registrato",
        "quando è il mio", "che ore ho", "a che ora ho", "controllo prenotazione"
    ]
    
    if any(pattern in user_msg for pattern in check_patterns):
        return "check_appointment"
    
    # NEW BOOKING patterns
    booking_patterns = [
        "voglio prenotare", "vorrei prenotare", "posso prenotare", "prenotazione",
        "nuovo appuntamento", "fissare appuntamento", "richiedere visita"
    ]
    
    if any(pattern in user_msg for pattern in booking_patterns):
        return "new_booking"
        
    return None

def should_use_gemini_for_conversation(user_message):
    """SUPER-INTELLIGENT Decision Engine - Context Aware"""
    user_msg = normalize(user_message.strip())
    
    # Get context analysis from Gemini
    context_intent = analyze_full_context_with_gemini(user_message)
    
    # NEVER use Gemini for specific corporate topics
    blocked_intents = ["prenotazione", "ceo", "fondatore", "creatore", "sede", "farmacia"]
    if context_intent in blocked_intents:
        return False
    
    # NEVER use Gemini for creator questions - these have dedicated corporate responses
    creator_indicators = [
        "chi creato", "chi sviluppato", "come sei stato creato", "chi ti ha creato",
        "who created", "how were you created", "chi ti ha fatto", "come funzioni",
        "muddasir", "khuwaja"
    ]
    
    # Block Gemini if it's a creator question
    for indicator in creator_indicators:
        if indicator in user_msg:
            return False
    
    # INTELLIGENT conversation detection
    conversation_patterns = [
        "ciao", "salve", "buongiorno", "buonasera", "buonanotte",
        "come va", "come stai", "tutto bene", "tutto ok", "che fai",
        "come ti chiami", "chi sei", "cosa fai", "dimmi di te",
        "piacere", "felice di conoscerti", "grazie", "perfetto", "ottimo", "bene",
        "sono", "mi chiamo", "il mio nome", "dimmi", "parlami", "raccontami",
        "tempo", "oggi", "domani", "ieri", "quando", "dove", "perché", "sciama",
        "ti piace", "cosa pensi", "opinione", "consiglio"
    ]
    
    # Use enhanced Gemini for natural conversations
    if context_intent == "conversazione" or any(pattern in user_msg for pattern in conversation_patterns):
        return True
    
    # Use Gemini for personal introductions and general questions
    if any(word in user_msg for word in ["sono", "mi chiamo", "il mio nome è", "parlami", "dimmi", "raccontami", "tempo"]):
        return True
        
    return False


def process_voice_through_existing_chat(transcribed_text):
    """Process voice input through existing chat logic"""
    # Use all your existing chat processing logic
    user_message_corr = correct_spelling(transcribed_text)
    
    # Assistant name detection
    if detect_assistant_name(user_message_corr):
        return get_assistant_introduction()
    
    # General patterns
    general = check_general_patterns(user_message_corr)
    if general:
        return general
    
    # Language detection
    if not is_probably_italian(user_message_corr):
        return "Questo assistente risponde solo a domande in italiano."
    
    # Office hours
    if detect_office_hours_question(user_message_corr):
        return get_office_hours_answer()
    
    # Time/date
    time_or_date = detect_time_or_date_question(user_message_corr)
    if time_or_date == "time":
        return get_time_answer()
    elif time_or_date == "date":
        return get_date_answer()
    
    # YAML matching
    reply = match_yaml_qa_ai(user_message_corr)
    if reply:
        return reply
    
    # Pharmacy queries
    if is_pharmacy_question(user_message_corr):
        found_cities = extract_city_from_query(user_message_corr)
        if found_cities:
            city = found_cities[0]
            ph_list = pharmacies_by_city(city)
            if ph_list:
                return format_pharmacies_list(ph_list, city, user_message_corr)
            else:
                return "Non ho trovato farmacie Otofarma in questa città."
        else:
            field_intents = extract_field_intent(user_message_corr)
            best_ph = pharmacy_best_match(user_message_corr)
            return format_pharmacy_answer(best_ph, field_intents)
    
    # Fallback
    fallback_messages = [
        "Mi dispiace, non ho capito bene. Puoi ripetere?",
        "Non sono riuscito a trovare una risposta. Puoi essere più specifico?",
        "Domanda interessante! Puoi riformulare la richiesta?"
    ]
    return fallback_mem.get_unique(fallback_messages)
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
    """REVOLUTIONARY CHAT ENGINE - Full Context Understanding with Gemini 2.0 Flash Exp"""
    user_message = request.json.get("message", "")
    voice_mode = request.json.get("voice", True)
    user_lat = request.json.get("lat", None)
    user_lon = request.json.get("lon", None)

    print(f"🎯 RECEIVED MESSAGE: '{user_message}'")
    
    # STEP 0: INTELLIGENT CONTEXT ANALYSIS with Gemini
    context_intent = analyze_full_context_with_gemini(user_message)
    print(f"🧠 CONTEXT ANALYSIS: {context_intent}")
    
    # STEP 1: INTELLIGENT APPOINTMENT DETECTION
    appointment_intent = intelligent_appointment_detector(user_message)
    
    if appointment_intent == "check_appointment":
        info = extract_appointment_info_smart(user_message)
        # Privacy: require both name and phone
        if info.get("name") and info.get("phone"):
            found = find_appointment(name=info.get("name"), phone=info.get("phone"))
            if found:
                reply = (
                    f"Perfetto! Ho trovato il tuo appuntamento, {found[0]}. "
                    f"Sei prenotato per il giorno {found[2]} e verrai contattato "
                    f"al numero {found[1]} per la conferma dell'orario esatto. "
                    f"Ti aspettiamo presso Otofarma per il tuo test dell'udito!"
                )
            else:
                reply = (
                    "Ho cercato nel nostro sistema ma non ho trovato una prenotazione "
                    "con i dati forniti. Per motivi di privacy, ho bisogno sia del nome completo "
                    "che del numero di telefono per verificare l'appuntamento. "
                    "Puoi riprovare fornendo entrambi i dati?"
                )
        else:
            missing_data = []
            if not info.get("name"): missing_data.append("nome completo")
            if not info.get("phone"): missing_data.append("numero di telefono")
            
            reply = (
                f"Per verificare la tua prenotazione ho bisogno di alcuni dati: {' e '.join(missing_data)}. "
                f"Puoi fornirmeli per favore? È per garantire la privacy dei nostri pazienti."
            )
        
        print(f"✅ APPOINTMENT CHECK RESPONSE")
        return jsonify({"reply": reply, "voice": voice_mode, "male_voice": True})

    # STEP 2: NEW APPOINTMENT BOOKING (Enhanced Intelligence)
    if appointment_intent == "new_booking" or context_intent == "nuova_prenotazione":
        info = extract_appointment_info_smart(user_message)
        missing = []
        if not info.get("name"): missing.append("nome completo")
        if not info.get("phone"): missing.append("numero di telefono")
        if not info.get("date"): missing.append("data preferita")
        
        if missing:
            reply = (
                f"Perfetto! Sarò felice di aiutarti a prenotare una visita audiologica presso Otofarma. "
                f"Per completare la prenotazione ho bisogno di: {', '.join(missing)}. "
                f"Puoi fornirmeli? Garantiamo la massima privacy dei tuoi dati."
            )
            print(f"📋 NEW BOOKING: missing {missing}")
            return jsonify({"reply": reply, "voice": voice_mode, "male_voice": True})
        
        # Complete booking
        send_appointment_email(info["name"], info["phone"], info["date"])
        save_appointment_to_db(info["name"], info["phone"], info["date"])
        reply = (
            f"Eccellente, {info['name']}! Ho inviato la tua richiesta di appuntamento "
            f"per il {info['date']} al nostro team specializzato di Otofarma. "
            f"Riceverai presto una chiamata di conferma al {info['phone']} per concordare "
            f"l'orario esatto. Ti aspettiamo per offrirti il miglior servizio audiologico!"
        )
        print(f"✅ NEW BOOKING COMPLETED: {info}")
        return jsonify({"reply": reply, "voice": voice_mode, "male_voice": True})
    # STEP 3: ASSISTANT NAME ACTIVATION - ONLY for direct activation
    if detect_assistant_name(user_message):
        print(f"🎯 ASSISTANT ACTIVATION DETECTED")
        return jsonify({"reply": get_assistant_introduction(), "voice": voice_mode, "male_voice": True})

    # STEP 4: LANGUAGE & CORRECTION - Enhanced Italian-only detection
    user_message_corr = correct_spelling(user_message)
    if not is_probably_italian(user_message_corr):
        technical_responses = [
            "Mi dispiace, sono un assistente AI specializzato esclusivamente per la lingua italiana. "
            "Il mio modello di elaborazione del linguaggio naturale è stato ottimizzato solo per l'italiano. "
            "Potresti per favore riformulare la tua domanda in italiano?",
            
            "Sono spiacente, la mia architettura di intelligenza artificiale è configurata esclusivamente "
            "per comprendere e rispondere in lingua italiana. Non posso elaborare richieste in altre lingue. "
            "Ti prego di comunicare con me in italiano.",
            
            "Mi scuso, ma il mio sistema di comprensione del linguaggio è stato addestrato solo per l'italiano. "
            "Per motivi tecnici, non sono in grado di processare testi in lingue diverse dall'italiano. "
            "Potresti gentilmente ripetere la domanda in italiano?"
        ]
        return jsonify({"reply": random.choice(technical_responses), "voice": voice_mode, "male_voice": True})

    print(f"📝 AFTER CORRECTION: '{user_message_corr}'")

    # STEP 5: LOCATION-BASED QUERIES
    if is_near_me_query(user_message):
        if user_lat is not None and user_lon is not None:
            try:
                best_ph = nearest_pharmacy(float(user_lat), float(user_lon))
                reply = format_nearest_pharmacy(best_ph)
            except Exception:
                reply = "Si è verificato un errore nel calcolo della farmacia più vicina. Riprova tra poco!"
        else:
            reply = "Per suggerirti la farmacia Otofarma più vicina ho bisogno che il browser acceda alla tua posizione. Puoi attivare la geolocalizzazione nelle impostazioni?"
        return jsonify({"reply": reply, "voice": voice_mode, "male_voice": True})

    # STEP 6: OFFICE HOURS 
    if detect_office_hours_question(user_message_corr):
        print(f"🕐 OFFICE HOURS QUESTION")
        return jsonify({"reply": get_office_hours_answer(), "voice": voice_mode, "male_voice": True})

    # STEP 7: TIME/DATE QUESTIONS
    time_or_date = detect_time_or_date_question(user_message_corr)
    if time_or_date == "time":
        print(f"⏰ TIME QUESTION")
        return jsonify({"reply": get_time_answer(), "voice": voice_mode, "male_voice": True})
    elif time_or_date == "date":
        print(f"📅 DATE QUESTION")
        return jsonify({"reply": get_date_answer(), "voice": voice_mode, "male_voice": True})

    # STEP 8: CORPORATE KNOWLEDGE (PRIORITY #1 - Before YAML)
    corporate_topic = detect_corporate_question(user_message_corr)
    if corporate_topic or context_intent in ["ceo", "fondatore", "creatore", "sede"]:
        
        # Use context analysis to determine the right response
        final_topic = corporate_topic or context_intent
        
        print(f"🏢 CORPORATE QUESTION: {final_topic}")
        
        if final_topic in ["ceo"]:
            reply = get_ceo_info()
        elif final_topic in ["founder", "fondatore"]:
            reply = get_founder_info()
        elif final_topic in ["creator", "creatore"]:
            reply = get_creator_info()
        elif final_topic in ["headquarters", "sede"]:
            reply = get_headquarters_info()
        elif corporate_topic == "leadership":
            reply = get_leadership_info()
        elif corporate_topic == "it_head":
            reply = get_it_head_info()
        elif corporate_topic == "frontend_dev":
            reply = get_frontend_developer_info()
        elif corporate_topic == "technical_team":
            reply = get_technical_team_info()
        elif corporate_topic == "architecture":
            reply = get_architecture_info()
        else:
            reply = get_headquarters_info()  # Default fallback
        
        print(f"✅ CORPORATE RESPONSE PROVIDED")
        return jsonify({"reply": reply, "voice": voice_mode, "male_voice": True})

    # STEP 9: YAML KNOWLEDGE BASE (Priority #2)
    if context_intent != "farmacia":  # Only if not a pharmacy question
        reply = match_yaml_qa_ai(user_message_corr)
        if reply:
            print(f"📚 YAML ANSWER FOUND: {reply[:100]}...")
            return jsonify({"reply": reply, "voice": voice_mode, "male_voice": True})

    # STEP 10: PHARMACY QUERIES (Enhanced with Context)
    if is_pharmacy_question(user_message_corr) or context_intent == "farmacia":
        print(f"🏥 PHARMACY QUESTION: {user_message_corr}")
        found_cities = extract_city_from_query(user_message_corr)
        
        if found_cities:
            city = found_cities[0]
            print(f"🏙️ CITY DETECTED: {city}")
            ph_list = pharmacies_by_city(city)
            
            if ph_list:
                reply = format_pharmacies_list(ph_list, city, user_message_corr)
                print(f"✅ FOUND {len(ph_list)} PHARMACIES in {city}")
            else:
                reply = (
                    f"Mi dispiace, non ho trovato farmacie Otofarma specificamente a {city}. "
                    f"Tuttavia, Otofarma ha una vasta rete di farmacie affiliate in tutta Italia. "
                    f"Posso aiutarti a cercare in una città limitrofa o fornirti informazioni "
                    f"su come contattare il nostro servizio clienti per trovare il punto vendita "
                    f"più vicino a te. Quale preferisci?"
                )
                print(f"❌ NO PHARMACIES in {city}")
        else:
            city_examples = get_available_cities_sample()
            reply = (
                f"Perfetto! Posso aiutarti a trovare le farmacie Otofarma. "
                f"Dimmi in quale città stai cercando? Ad esempio: 'Farmacie a Milano' "
                f"oppure 'Dove sono le Otofarma a Roma'. {city_examples}"
            )
            print("🤔 NO CITY DETECTED in pharmacy query")
            
        return jsonify({"reply": reply, "voice": voice_mode, "male_voice": True})

    # 9. Fallback responses
        # 8.5. Gemini AI fallback for questions not covered by YAML or app logic
    # STEP 11: GEMINI AI CONVERSATION (Final Intelligence)
    print("🧠 USING GEMINI AI FOR INTELLIGENT CONVERSATION...")
    if gemini_available:
        gemini_reply = get_gemini_conversation(user_message_corr)
        if gemini_reply:
            print(f"🎯 GEMINI RESPONSE: {gemini_reply[:100]}...")
            return jsonify({"reply": gemini_reply, "voice": voice_mode, "male_voice": True})
        else:
            print("⚠️ GEMINI RETURNED EMPTY RESPONSE")
    else:
        print("⚠️ GEMINI NOT AVAILABLE - CHECK INITIALIZATION")

    # STEP 12: ULTIMATE INTELLIGENT FALLBACK
    print("🔧 ENGAGING ULTIMATE INTELLIGENT FALLBACK...")
    
    # Extract key user words for context-aware response
    user_kw = ""
    user_words = re.findall(r'\w+', normalize(user_message_corr))
    for w in user_words:
        if w not in {"ciao", "salve", "buongiorno", "buonasera", "buonanotte", "come", "va", "stai", "sei", "sono", "grazie", "bot", "otobot", "otofarma", "assistente"} and len(w) > 3:
            user_kw = w
            break

    if user_kw:
        fallback_messages = [
            f"Mi dispiace, non ho ancora conoscenze specifiche su '{user_kw}'. "
            f"Ti consiglio di contattare direttamente il nostro team di esperti Otofarma "
            f"o riformulare la domanda. Sono comunque qui per aiutarti con altri argomenti!",
            
            f"Non dispongo di informazioni dettagliate su '{user_kw}' al momento, "
            f"ma sono qui per aiutarti con apparecchi acustici, servizi audiologici, "
            f"farmacie e molto altro ancora!",
            
            f"Al momento non ho dati specifici su '{user_kw}', ma posso aiutarti "
            f"con informazioni su prodotti Otofarma, servizi di consulenza "
            f"audiologica, o localizzazione delle nostre farmacie.",
            
            f"Non ho una risposta precisa su '{user_kw}', ma il nostro team "
            f"di specialisti Otofarma sarà felice di aiutarti. Nel frattempo, "
            f"posso assisterti con altri argomenti!",
            
            f"Mi scuso, non ho trovato dettagli su '{user_kw}'. Tuttavia, "
            f"sono esperto in apparecchi acustici, servizi audiologici, "
            f"e tutto ciò che riguarda il mondo Otofarma!"
        ]
    else:
        fallback_messages = [
            "Mi dispiace, sto avendo difficoltà a comprendere la tua richiesta. "
            "Potresti riformulare la domanda? Sono qui per aiutarti con informazioni "
            "su Otofarma, apparecchi acustici, servizi audiologici e molto altro!",
            
            "Non sono riuscito a trovare una risposta soddisfacente. "
            "Se vuoi, puoi essere più specifico o chiedere su argomenti come "
            "apparecchi acustici, farmacie Otofarma, o servizi di consulenza.",
            
            "La tua richiesta è interessante, ma non dispongo di dettagli "
            "specifici al momento. Sono specializzato in tutto ciò che riguarda "
            "Otofarma: prodotti, servizi, e assistenza audiologica!",
            
            "Al momento non trovo la risposta che cerchi. Ti invito a "
            "riformulare la domanda o a chiedere su temi come apparecchi "
            "acustici, prenotazione visite, o localizzazione farmacie.",
            
            "Sono qui per offrirti il massimo supporto possibile! "
            "Puoi essere più dettagliato nella tua richiesta o chiedere "
            "informazioni su servizi Otofarma, prodotti audiologici, o farmacie?"
        ]
    
    reply = fallback_mem.get_unique(fallback_messages)
    print(f"⚠️ INTELLIGENT FALLBACK ENGAGED: {reply[:50]}...")
    return jsonify({"reply": reply, "voice": voice_mode, "male_voice": True})
# Google Cloud TTS endpoint for Italian male voice
@app.route("/tts", methods=["POST"])
def tts():
    data = request.json
    text = data.get("text", "")
    
    # Format numbers for speech BEFORE TTS
    formatted_text = format_numbers_for_speech(text)
    
    voice_name = "it-IT-Chirp3-HD-Enceladus"  # Premium Chirp3 - Warm & Natural Male Italian Voice

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "speakai-467308-fb5a36feacef.json"

    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=formatted_text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="it-IT",
        name=voice_name
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )

    return (
        response.audio_content,
        200,
        {
            "Content-Type": "audio/mpeg",
            "Content-Disposition": "inline; filename=output.mp3"
        }
    )
from google.cloud import speech


@app.route("/transcribe", methods=["POST"])
def transcribe():
    """Professional cross-platform audio transcription with iOS/Android support"""
    if "audio" not in request.files:
        logger.error("No audio file provided in transcription request")
        return jsonify({"error": "No audio file provided"}), 400

    audio_file = request.files["audio"]
    if not audio_file or not audio_file.filename:
        logger.error("Invalid audio file in transcription request")
        return jsonify({"error": "Invalid audio file"}), 400
        
    audio_bytes = audio_file.read()
    if len(audio_bytes) == 0:
        logger.error("Empty audio file received")
        return jsonify({"error": "Empty audio file"}), 400

    logger.info(f"Transcription request - File: {audio_file.filename}, Size: {len(audio_bytes)} bytes")

    try:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "speakai-467308-fb5a36feacef.json"
        client = speech.SpeechClient()
        audio = speech.RecognitionAudio(content=audio_bytes)
        
        # Professional format detection and configuration
        filename = audio_file.filename.lower()
        
        if filename.endswith('.mp4') or filename.endswith('.m4a'):
            # iOS/Safari often uses MP4 format
            encoding = speech.RecognitionConfig.AudioEncoding.MP3  # Google accepts MP3 for MP4 audio
            sample_rate = 48000
            logger.info("Using MP4/M4A configuration for iOS device")
            
        elif filename.endswith('.wav'):
            # Some Android devices use WAV
            encoding = speech.RecognitionConfig.AudioEncoding.LINEAR16
            sample_rate = 48000
            logger.info("Using WAV configuration for Android device")
            
        else:
            # Default WEBM_OPUS for desktop/Chrome
            encoding = speech.RecognitionConfig.AudioEncoding.WEBM_OPUS
            sample_rate = 48000
            logger.info("Using WEBM_OPUS configuration for desktop/Chrome")

        config = speech.RecognitionConfig(
            encoding=encoding,
            sample_rate_hertz=sample_rate,
            language_code="it-IT",
            enable_automatic_punctuation=True,
            model="latest_long",  # Better for conversational audio
            use_enhanced=True    # Enhanced model for better accuracy
        )

        logger.info(f"Starting Google Speech recognition with encoding: {encoding.name}")
        response = client.recognize(config=config, audio=audio)
        
        transcript = ""
        confidence_total = 0
        result_count = 0
        
        for result in response.results:
            if result.alternatives:
                transcript += result.alternatives[0].transcript + " "
                confidence_total += result.alternatives[0].confidence
                result_count += 1
                
        transcript = transcript.strip()
        avg_confidence = confidence_total / result_count if result_count > 0 else 0
        
        logger.info(f"Transcription completed - Length: {len(transcript)}, Confidence: {avg_confidence:.2f}")
        logger.info(f"Transcript: '{transcript}'")
        
        if not transcript:
            logger.warning("Empty transcript received from Google Speech")
            return jsonify({"error": "No speech detected", "transcript": ""})

        return jsonify({
            "transcript": transcript,
            "confidence": avg_confidence,
            "audio_format": encoding.name
        })
        
    except Exception as e:
        logger.error(f"Transcription error: {str(e)}")
        return jsonify({"error": f"Transcription failed: {str(e)}"}), 500
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    # Production-ready configuration for presidential presentation
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
