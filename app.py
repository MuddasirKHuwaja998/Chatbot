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

# Visual Analysis Dependencies - OpenAI Vision API
import openai
import base64
import io
from PIL import Image
import cv2
import numpy as np
from threading import Lock
import time
import uuid

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
# 💼 CEO: Drs. Dottoressa Giovanna Incarnato
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
        "name": "Dr. Rino Bartolomucci",
        "title": "Fondatore e Presidente", 
        "role": "Founder and President"
    },
    "ceo": {
        "name": "Dottoressa Giovanna Incarnato",
        "voice_name": "Dottoressa Giovanna Incarnato",
        "title": "Amministratrice Delegata",
        "role": "Chief Executive Officer",
        "gender": "female"
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

# Enhanced corporate knowledge patterns with PERFECT detection
CORPORATE_PATTERNS = [
    # Headquarters patterns
    (r"\b(sede|ufficio|headquarters|main office|sede principale|ufficio principale|quartier generale)\b", "headquarters"),
    (r"\b(dove si trova|indirizzo|address|location|ubicazione)\b.*\b(otofarma|sede|ufficio)\b", "headquarters"),
    (r"\b(via ripuaria|varcaturo|giugliano)\b", "headquarters"),
    
    # Leadership patterns  
    (r"\b(fondatore|founder|presidente|president)\b.*\b(otofarma)\b", "founder"),
    (r"\b(rino|bartolomucci)\b", "founder"),
    (r"\b(ceo|amministratore|amministratrice|delegato|delegata|direttore|direttrice|generale|direttore generale|direttrice generale)\b.*\b(otofarma)\b", "ceo"),
    (r"\b(giovanna|incarnato|dottoressa)\b", "ceo"),
    (r"\b(chi.*è.*ceo|chi.*è.*amministratore|chi.*è.*amministratrice|chi.*è.*direttore|chi.*è.*direttrice|chi.*dirige.*azienda)\b", "ceo"),
    (r"\b(chi.*dirige|chi.*comanda|chi.*gestisce|leadership|dirigenza)\b.*\b(otofarma)\b", "leadership"),
    
    # IT Team patterns
    (r"\b(it|responsabile it|manager it|dipartimento it|capo it)\b", "it_head"),
    (r"\b(pasquale|valentino)\b", "it_head"),
    (r"\b(frontend|front end|ios|sviluppatore|developer)\b.*\b(gaetano|mobile|app)\b", "frontend_dev"),
    (r"\b(gaetano)\b", "frontend_dev"),
    (r"\b(team.*tecnico|team.*sviluppo|technical team|dev team)\b", "technical_team"),
    
    # AI Creator patterns - ENHANCED FOR BETTER DETECTION
    (r"\b(chi.*creato|chi.*sviluppato|chi.*programmato|chi.*fatto|chi.*costruito)\b.*\b(te|tu|ai|bot|otobot|intelligenza)\b", "creator"),
    (r"\b(come.*sei.*stato.*creato|come.*sei.*nato|come.*funzioni|chi.*ti.*ha.*creato|chi.*ti.*ha.*fatto)\b", "creator"),
    (r"\b(who.*created|who.*developed|who.*programmed|who.*made|who.*built)\b.*\b(you|ai|bot)\b", "creator"),
    (r"\b(sviluppatore.*ai|ai.*specialist|ai.*developer|intelligenza.*artificiale)\b", "creator"),
    (r"\b(muddasir|khuwaja)\b", "creator"),
    (r"\b(come.*funzioni|architettura|come.*lavori|tecnologia|algoritmi|neural)\b", "architecture"),
    (r"\b(how.*were.*you.*created|how.*were.*you.*made|how.*do.*you.*work)\b", "creator")
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
        vertexai.init(project="speakai-467308", location="us-east4")
        return True
    except Exception as e:
        print(f"Gemini initialization error: {e}")
        return False

# Initialize Gemini
gemini_available = initialize_gemini()

# Visual Analysis Configuration - Professional Style
VISUAL_ANALYSIS_CONFIG = {
    "enabled": True,
    "continuous_monitoring": False,
    "detection_confidence": 0.7,
    "analysis_interval": 2.0,  # seconds
    "max_image_size": (1920, 1080),
    "supported_formats": ["jpg", "jpeg", "png", "webp"],
    "professional_mode": True
}

# OpenAI Configuration for Visual Analysis
openai.api_key = os.environ.get("OPENAI_API_KEY", "")

# Visual Analysis State Management
visual_state = {
    "active": False,
    "last_analysis": None,
    "continuous_mode": False,
    "detected_objects": [],
    "current_frame": None,
    "analysis_lock": Lock(),
    "session_id": str(uuid.uuid4())
}

# Professional Visual Analysis Prompts
VISUAL_ANALYSIS_PROMPTS = {
    "greeting": """Ciao! Sono OtoBot, il tuo assistente virtuale con capacità di visione di Otofarma Spa. 
Posso vedere attraverso la tua fotocamera e aiutarti con qualsiasi cosa tu stia guardando o mostrando. 
Posso analizzare oggetti, leggere testi, identificare prodotti audiologici e molto altro!
Cosa posso vedere per te oggi?""",
    
    "system_prompt": """Sei OtoBot, l'assistente virtuale avanzato di Otofarma Spa con capacità di visione artificiale professionale.

COMPORTAMENTO PROFESSIONALE:
- Analizza sempre le immagini con precisione e dettaglio
- Identifica oggetti, persone, testi, prodotti audiologici
- Offri assistenza proattiva basata su ciò che vedi
- Mantieni sempre un tono professionale ma cordiale
- Rispondi SEMPRE in italiano
- Specializzati in apparecchi acustici e prodotti Otofarma quando rilevanti

CAPACITÀ DI VISIONE:
- Riconoscimento oggetti e scene
- Lettura OCR di testi e documenti
- Identificazione prodotti audiologici
- Analisi medica generale (non diagnostica)
- Assistenza per problemi pratici

STILE PROFESSIONALE:
- "Posso vedere [descrizione dettagliata]. Come posso aiutarti?"
- Sii proattivo nel suggerire assistenza
- Identifica sempre chiaramente ciò che vedi
- Offri soluzioni pratiche e professionali""",
    
    "analysis_prompt": """Analizza questa immagine come OtoBot, assistente professionale di Otofarma Spa.

FOCUS ANALYSIS:
1. Descrivi dettagliatamente ciò che vedi
2. Identifica oggetti specifici, persone, testi
3. Se vedi apparecchi acustici o prodotti audiologici, fornisci informazioni specializzate
4. Suggerisci come posso essere di aiuto basandoti su ciò che osservi
5. Mantieni un tono professionale ma cordiale

Rispondi in italiano con il formato:
"Posso vedere [descrizione dettagliata]. [Suggerimenti di assistenza professionale]"""
}

# VISUAL ANALYSIS CORE FUNCTIONS - PROFESSIONAL IMPLEMENTATION

def encode_image_for_analysis(image_data):
    """Encode image for OpenAI Vision API analysis"""
    try:
        if isinstance(image_data, str):  # base64 string
            return image_data
        elif isinstance(image_data, bytes):
            return base64.b64encode(image_data).decode('utf-8')
        else:
            # PIL Image or numpy array
            if isinstance(image_data, np.ndarray):
                image_data = Image.fromarray(image_data)
            
            buffer = io.BytesIO()
            image_data.save(buffer, format="JPEG", quality=85)
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception as e:
        logger.error(f"Image encoding error: {e}")
        return None

def resize_image_for_analysis(image, max_size=(1920, 1080)):
    """Resize image for optimal analysis while maintaining aspect ratio"""
    try:
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image)
        
        # Calculate new size maintaining aspect ratio
        width, height = image.size
        max_width, max_height = max_size
        
        if width <= max_width and height <= max_height:
            return image
        
        ratio = min(max_width/width, max_height/height)
        new_size = (int(width * ratio), int(height * ratio))
        
        return image.resize(new_size, Image.Resampling.LANCZOS)
    except Exception as e:
        logger.error(f"Image resize error: {e}")
        return image

def analyze_image_with_openai(image_data, user_prompt=""):
    """Analyze image using OpenAI Vision API - Professional Style"""
    try:
        if not openai.api_key:
            logger.warning("OpenAI API key not configured")
            return "Mi dispiace, la funzione di analisi visiva non è attualmente disponibile. Configurazione API richiesta."
        
        base64_image = encode_image_for_analysis(image_data)
        if not base64_image:
            return "Errore nell'elaborazione dell'immagine. Riprova con un'altra foto."
        
        # Professional analysis prompt
        analysis_prompt = VISUAL_ANALYSIS_PROMPTS["analysis_prompt"]
        if user_prompt:
            analysis_prompt += f"\n\nRICHIESTA SPECIFICA UTENTE: {user_prompt}"
        
        response = openai.chat.completions.create(
            model="gpt-4o",  # Latest vision model
            messages=[
                {
                    "role": "system",
                    "content": VISUAL_ANALYSIS_PROMPTS["system_prompt"]
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": analysis_prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=1000,
            temperature=0.7
        )
        
        analysis_result = response.choices[0].message.content.strip()
        
        # Update visual state
        with visual_state["analysis_lock"]:
            visual_state["last_analysis"] = {
                "timestamp": time.time(),
                "result": analysis_result,
                "user_prompt": user_prompt
            }
        
        logger.info(f"Visual analysis completed successfully")
        return analysis_result
        
    except Exception as e:
        logger.error(f"OpenAI Vision analysis error: {e}")
        return "Mi dispiace, ho riscontrato un problema nell'analizzare l'immagine. Riprova tra qualche momento."

def analyze_image_with_gemini_vision(image_data, user_prompt=""):
    """Fallback: Analyze image using Gemini Vision as backup"""
    try:
        if not gemini_available:
            return analyze_image_with_openai(image_data, user_prompt)
        
        model = GenerativeModel("gemini-2.0-flash-001")
        
        # Convert image for Gemini
        if isinstance(image_data, str):  # base64
            image_bytes = base64.b64decode(image_data)
        else:
            image_bytes = image_data
        
        analysis_prompt = f"""
Sei OtoBot di Otofarma Spa con capacità di visione. Analizza questa immagine professionalmente.

Descrivi dettagliatamente:
1. Cosa vedi nell'immagine
2. Oggetti specifici, persone, testi
3. Se vedi apparecchi acustici, fornisci info specializzate
4. Come posso aiutare basandomi su ciò che osservi

{user_prompt if user_prompt else ''}

Rispondi in italiano con stile professionale.
"""
        
        response = model.generate_content([analysis_prompt, image_bytes])
        return response.text.strip()
        
    except Exception as e:
        logger.error(f"Gemini Vision analysis error: {e}")
        return analyze_image_with_openai(image_data, user_prompt)

def get_visual_greeting():
    """Generate professional visual analysis greeting"""
    return VISUAL_ANALYSIS_PROMPTS["greeting"].format(assistant_name=ASSISTANT_NAME)

def process_visual_query(image_data, user_message=""):
    """Main visual processing function - Professional style"""
    try:
        # Resize image for optimal processing
        if isinstance(image_data, (bytes, str)):
            # Handle base64 or bytes directly
            processed_image = image_data
        else:
            # Handle PIL Image or numpy array
            resized_image = resize_image_for_analysis(image_data, VISUAL_ANALYSIS_CONFIG["max_image_size"])
            processed_image = resized_image
        
        # Perform analysis with primary method (OpenAI) and fallback (Gemini)
        analysis_result = analyze_image_with_openai(processed_image, user_message)
        
        # If OpenAI fails, try Gemini
        if "problema" in analysis_result.lower() or "errore" in analysis_result.lower():
            analysis_result = analyze_image_with_gemini_vision(processed_image, user_message)
        
        # Enhanced response formatting
        professional_response = enhance_visual_response(analysis_result, user_message)
        
        return professional_response
        
    except Exception as e:
        logger.error(f"Visual query processing error: {e}")
        return "Mi dispiace, ho riscontrato un problema nell'analisi visiva. Assicurati che l'immagine sia chiara e riprova."

def enhance_visual_response(analysis_result, user_message=""):
    """Enhance visual analysis response with Otofarma context"""
    try:
        # Add Otofarma-specific enhancements
        enhanced_response = analysis_result
        
        # Check for hearing aid related keywords in analysis
        hearing_keywords = ["orecchio", "apparecchio", "acustico", "hearing", "aid", "udito", "sentire"]
        if any(keyword in analysis_result.lower() for keyword in hearing_keywords):
            enhanced_response += "\n\n💡 Come specialisti Otofarma, posso fornirti informazioni dettagliate sui nostri apparecchi acustici di ultima generazione, inclusi modelli ricaricabili e invisibili. Vuoi saperne di più?"
        
        # Add professional closing
        if not enhanced_response.endswith("?"):
            enhanced_response += " Come posso assisterti ulteriormente?"
        
        return enhanced_response
        
    except Exception as e:
        logger.error(f"Response enhancement error: {e}")
        return analysis_result

def get_gemini_conversation(user_message):
    """Get natural conversation from Gemini - ALWAYS ITALIAN - ALWAYS OTOFARMA"""
    if not gemini_available:
        return None
        
    try:
        model = GenerativeModel("gemini-2.0-flash-001")  # Latest available model
        
        prompt = f"""
        IMPORTANTE: Rispondi SEMPRE e SOLO in italiano professionale e cordiale. Mai in inglese.
        
        Tu sei OtoBot, l'assistente virtuale UFFICIALE di Otofarma Spa, azienda italiana leader nel settore audiologico.
         REGOLE ASSOLUTE:
        1. Rispondi SEMPRE in italiano professionale
        2. Massimo 2-3 frasi concise e dirette
        3. Sei OtoBot di Otofarma Spa (mai AI generico)
        4. Se non sai qualcosa, suggerisci contatto con specialisti
        5. NO risposte lunghe - sii preciso e utile

        LA TUA IDENTITÀ:
        - Sei OtoBot di Otofarma Spa
        - Rappresenti un'azienda italiana di prestigio
        - Sei specializzato in apparecchi acustici innovativi
        - Conosci teleaudiologia e servizi audiologici
        - Sei sempre professionale ma cordiale
        - Parli solo italiano
        
        I TUOI SERVIZI OTOFARMA:
        - Apparecchi acustici ricaricabili e su misura
        - Teleaudiologia e consulenze specialistiche
        - Test dell'udito gratuiti
        - Garanzie complete e assistenza
        - Rete di farmacie affiliate in Italia
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 
        COMPORTAMENTO:
        - Professionale ma cordiale
        - Risposte brevi (max 50 parole se possibile)  
        - Se qualcuno si presenta, ricorda il nome
        - Per argomenti non-Otofarma, collega sempre ai nostri servizi
        
        REGOLE SPECIALI:
        1. Rispondi SEMPRE in italiano
        2. Sei SEMPRE OtoBot di Otofarma Spa, mai un AI generico
        3. Per domande sul tempo, meteo o argomenti generali, rispondi come OtoBot ma collegando sempre a Otofarma
        4. Mantieni tono professionale ma amichevole
        5. Per dettagli specifici su Otofarma, suggerisci di contattare i nostri specialisti
        6. Se qualcuno si presenta (nome), ricordalo e sii cordiale
        
        Messaggio utente: {user_message}
        
        OtoBot di Otofarma Spa (risposta in italiano):
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

                # Fix: If Gemini returns nonsense or too-short answers, use creative fallback
        nonsense_patterns = [
            r"^(a+h+|h+a+|e+h+|h+e+|h+a+i+|a+i+|e+i+|i+a+|h+)+[.!?]*$",  # ahhh, haai, eh, etc.
            r"^[a-z]{1,4}[.!?]*$"  # 1-4 letter "words" only
        ]
        if any(re.match(pat, gemini_text, re.IGNORECASE) for pat in nonsense_patterns):
            # Extract a main keyword from the question
            user_kw = ""
            user_words = re.findall(r'\w+', normalize(user_message))
            for w in user_words:
                if w not in {"ciao", "salve", "buongiorno", "buonasera", "buonanotte", "come", "va", "stai", "sei", "sono", "grazie", "bot", "otobot", "otofarma", "assistente"} and len(w) > 3:
                    user_kw = w
                    break
            if user_kw:
                return f"Mi dispiace, non ho informazioni precise su '{user_kw}'. Ti consiglio di contattare uno specialista Otofarma oppure chiedere in modo diverso. Sono sempre qui per aiutarti!"
            else:
                return "Mi dispiace, non ho informazioni precise su questa domanda. Puoi riformulare o chiedere altro? Sono sempre qui per aiutarti!"

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
        print(f"Gemini error: {e}")
        return None

def should_use_gemini_for_conversation(user_message):
    """Decide if message should use Gemini for natural conversation - EXCLUDES CREATOR QUESTIONS"""
    user_msg = normalize(user_message.strip())
    
    # NEVER use Gemini for creator questions - these have dedicated corporate responses
    creator_indicators = [
        "chi creato", "chi sviluppato", "come sei stato creato", "chi ti ha creato",
        "who created", "how were you created", "chi ti ha fatto", "come funzioni"
    ]
    
    # Block Gemini if it's a creator question
    for indicator in creator_indicators:
        if indicator in user_msg:
            return False
    
    # Use Gemini for natural greetings and conversations
    conversation_patterns = [
        "ciao", "salve", "buongiorno", "buonasera", "buonanotte",
        "come va", "come stai", "tutto bene", "tutto ok",
        "come ti chiami", "chi sei", "cosa fai",
        "piacere", "felice di conoscerti", "grazie", "perfetto", "ottimo", "bene",
        "sono", "mi chiamo", "il mio nome", "dimmi", "parlami", "raccontami",
        "tempo", "oggi", "domani", "ieri", "quando", "dove", "perché", "sciama"
    ]
    
    # Check if it's a natural conversation starter
    for pattern in conversation_patterns:
        if pattern in user_msg:
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
    """Main chat endpoint with advanced appointment booking priority"""
    user_message = request.json.get("message", "")
    voice_mode = request.json.get("voice", True)
    user_lat = request.json.get("lat", None)
    user_lon = request.json.get("lon", None)

    print(f"Received message: '{user_message}'")
    check_keywords = [
        "ho appuntamento", "il mio appuntamento", "la mia prenotazione", "quando è il mio appuntamento",
        "ho una prenotazione", "controlla appuntamento", "verifica appuntamento", "ho prenotato",
        "sono prenotato", "sono registrato", "sono in lista", "mio appuntamento", "mia prenotazione",
        "ho già prenotato", "ho già appuntamento", "sono in agenda"
    ]
  
    if any(kw in normalize(user_message) for kw in check_keywords):
        info = extract_appointment_info_smart(user_message)
         # Privacy: require both name and phone
        if info.get("name") and info.get("phone"):
          found = find_appointment(name=info.get("name"), phone=info.get("phone"))
        if found:
            reply = (
                f"Sì, {found[0]}, hai già un appuntamento prenotato per il giorno {found[2]}.\n"
                f"Verrai contattato al numero {found[1]} per la conferma.\n"
                "Grazie per aver scelto Otofarma!"
            )
        else:
            reply = (
                "Per motivi di privacy, servono sia il nome che il numero di telefono per verificare la prenotazione."
                "Non trovo una prenotazione a tuo nome o numero. "
                "Se pensi di aver prenotato, controlla di aver fornito nome e telefono corretti."
            )
        return jsonify({"reply": reply, "voice": voice_mode, "male_voice": True})

    # 1. Appointment booking logic FIRST (before Gemini, before everything)
    appointment_keywords = [
        "prenota", "prenotare", "appuntamento", "visita", "richiedo", "richiedere", "voglio", "vorrei", "prenotazione"
    ]
    if any(kw in normalize(user_message) for kw in appointment_keywords):
        info = extract_appointment_info_smart(user_message)
        missing = []
        if not info.get("name"):
            missing.append("nome completo")
        if not info.get("phone"):
            missing.append("numero di telefono")
        if not info.get("date"):
            missing.append("data preferita")
        if missing:
            reply = (
                "Per prenotare la visita, ho bisogno dei seguenti dati: "
                + ", ".join(missing)
                + ". Puoi fornirmeli?"
            )
            print("Appointment booking: missing info", missing)
            return jsonify({"reply": reply, "voice": voice_mode, "male_voice": True})
        
        send_appointment_email(info["name"], info["phone"], info["date"])
        save_appointment_to_db(info["name"], info["phone"], info["date"])
        reply = (
            f"Ciao {info['name']},\n"
            f"Ho inviato la tua richiesta di appuntamento per il giorno {info['date']} al nostro team Otofarma.\n"
            f"Riceverai presto una chiamata di conferma al numero {info['phone']}.\n"
            "Grazie per aver scelto Otofarma! Se hai altre esigenze, sono sempre qui per aiutarti in modo professionale e cordiale."
        )
        print("Appointment booking: email sent", info)
        return jsonify({"reply": reply, "voice": voice_mode, "male_voice": True})
    
    # Check for visual mode activation requests
    visual_keywords = ["camera", "video", "vedi", "guarda", "analizza", "mostra", "visual", "immagine", "foto", "vedere", "guardare", "fotocamera"]
    if any(keyword in user_message.lower() for keyword in visual_keywords):
        visual_activation_response = "Perfetto! Attivando la modalità visiva avanzata di Otofarma. Ora posso vedere attraverso la tua fotocamera e analizzare tutto ciò che mi mostri. Premi il pulsante della camera per iniziare!"
        return jsonify({"reply": visual_activation_response, "voice": voice_mode, "male_voice": True, "suggest_visual": True})
    
    # 1. Check for assistant name activation
    if detect_assistant_name(user_message):
        return jsonify({"reply": handle_voice_activation_greeting(), "voice": voice_mode, "male_voice": True})

    # 2. Enhanced conversation handling with Gemini
    if should_use_gemini_for_conversation(user_message):
        gemini_reply = get_gemini_conversation(user_message)
        if gemini_reply:
            print(f"Gemini conversation response generated")
            return jsonify({"reply": gemini_reply, "voice": voice_mode, "male_voice": True})

    # 2b. Fallback to existing general patterns
    general = check_general_patterns(user_message)
    if general:
        return jsonify({"reply": general, "voice": voice_mode, "male_voice": True})

    # 3. Handle location-based queries
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

    # 4. Spell correction and language detection
    user_message_corr = correct_spelling(user_message)
    if not is_probably_italian(user_message_corr):
        return jsonify({"reply": "Questo assistente risponde solo a domande in italiano. Per favore riformula la domanda in italiano.", "voice": voice_mode, "male_voice": True})

    print(f"After spell correction: '{user_message_corr}'")
        # --- Advanced Appointment Booking Logic ---
    # ...inside def chat(): after user_message_corr is defined...

    # --- Advanced Appointment Booking Logic ---
   

    # 5. Check for office hours (before YAML to avoid conflicts)
    if detect_office_hours_question(user_message_corr):
        return jsonify({"reply": get_office_hours_answer(), "voice": voice_mode, "male_voice": True})

    # 6. Check for time/date questions (with strict matching)
    time_or_date = detect_time_or_date_question(user_message_corr)
    if time_or_date == "time":
        return jsonify({"reply": get_time_answer(), "voice": voice_mode, "male_voice": True})
    elif time_or_date == "date":
        return jsonify({"reply": get_date_answer(), "voice": voice_mode, "male_voice": True})

    # 6.5. Enhanced Corporate Knowledge (Complete Team & Leadership)
    corporate_topic = detect_corporate_question(user_message_corr)
    if corporate_topic:
        print(f"🏢 Corporate question detected: {corporate_topic}")
        if corporate_topic == "headquarters":
            reply = get_headquarters_info()
        elif corporate_topic == "founder":
            reply = get_founder_info()
        elif corporate_topic == "ceo":
            reply = get_ceo_info()
        elif corporate_topic == "leadership":
            reply = get_leadership_info()
        elif corporate_topic == "it_head":
            reply = get_it_head_info()
        elif corporate_topic == "frontend_dev":
            reply = get_frontend_developer_info()
        elif corporate_topic == "technical_team":
            reply = get_technical_team_info()
        elif corporate_topic == "creator":
            reply = get_creator_info()
        elif corporate_topic == "architecture":
            reply = get_architecture_info()
        else:
            reply = get_headquarters_info()  # Default fallback
        
        print(f"✅ Corporate info provided: {corporate_topic}")
        return jsonify({"reply": reply, "voice": voice_mode, "male_voice": True})

    # 7. YAML Q&A matching (highest priority for content)
    reply = match_yaml_qa_ai(user_message_corr)
    if reply:
        print(f"Found YAML answer: {reply[:100]}...")
        return jsonify({"reply": reply, "voice": voice_mode, "male_voice": True})

    # 8. Enhanced Pharmacy-specific queries for Voice Assistant
    if is_pharmacy_question(user_message_corr):
        print(f"🏥 Pharmacy question detected: {user_message_corr}")
        found_cities = extract_city_from_query(user_message_corr)
        
        if found_cities:
            city = found_cities[0]
            print(f"🏙️ City found: {city}")
            ph_list = pharmacies_by_city(city)
            
            if ph_list:
                reply = format_pharmacies_list(ph_list, city, user_message_corr)
                print(f"✅ Found {len(ph_list)} pharmacies in {city}")
            else:
                # Enhanced fallback for no pharmacies found
                reply = (
                    f"Mi dispiace, non ho trovato farmacie Otofarma specificamente a {city}. "
                    f"Tuttavia, Otofarma ha una vasta rete di farmacie affiliate in tutta Italia. "
                    f"Ti consiglio di provare a cercare nelle città limitrofe o contattare "
                    f"direttamente il servizio clienti Otofarma per informazioni su farmacie "
                    f"nella tua zona. Posso aiutarti con altre città o servizi Otofarma?"
                )
                print(f"❌ No pharmacies found in {city}")
        else:
            # No city found - provide general guidance with examples
            city_examples = get_available_cities_sample()
            reply = (
                "Per aiutarti a trovare una farmacia Otofarma, potresti specificare la città "
                "che ti interessa? Ad esempio, puoi dire 'dove sono le farmacie Otofarma a Milano' "
                "oppure 'farmacie Otofarma a Roma'. " + city_examples + " "
                "Sono qui per fornirti tutte le informazioni sui nostri punti vendita "
                "specializzati in apparecchi acustici e servizi audiologici."
            )
            print("🤔 No city detected in pharmacy query")
            
        return jsonify({"reply": reply, "voice": voice_mode, "male_voice": True})

    # 9. Fallback responses
        # 8.5. Gemini AI fallback for questions not covered by YAML or app logic
    print("Trying Gemini fallback...")
    if gemini_available:
        gemini_reply = get_gemini_conversation(user_message_corr)
        if gemini_reply:
            print(f"Gemini fallback response generated: {gemini_reply[:50]}...")
            return jsonify({"reply": gemini_reply, "voice": voice_mode, "male_voice": True})
        else:
            print("Gemini returned empty response")
    else:
        print("Gemini not available - check initialization")

    fallback_messages = [
        "Mi dispiace, sto avendo difficoltà a comprendere la tua richiesta. Potresti riformulare la domanda? Posso aiutarti con informazioni su Otofarma, apparecchi acustici, servizi audiologici e molto altro!",
        
        "Non sono riuscito a trovare una risposta soddisfacente. Se vuoi, puoi essere più specifico o chiedere su argomenti come apparecchi acustici, farmacie Otofarma, o servizi di consulenza.",
        
        "La tua richiesta è interessante, ma non dispongo di dettagli specifici al momento. Posso aiutarti con tutto ciò che riguarda Otofarma: prodotti, servizi, e assistenza audiologica!",
        
        "Al momento non trovo la risposta che cerchi. Ti invito a riformulare la domanda o a chiedere su temi come apparecchi acustici, prenotazione visite, o localizzazione farmacie.",
        
        "Posso offrirti il massimo supporto possibile! Puoi essere più dettagliato nella tua richiesta o chiedere informazioni su servizi Otofarma, prodotti audiologici, o farmacie?"
    ]
    
        # Improved professional fallback with keyword mention
    user_kw = ""
    user_words = re.findall(r'\w+', normalize(user_message_corr))
    for w in user_words:
        if w not in {"ciao", "salve", "buongiorno", "buonasera", "buonanotte", "come", "va", "stai", "sei", "sono", "grazie", "bot", "otobot", "otofarma", "assistente"} and len(w) > 3:
            user_kw = w
            break

    if user_kw:
        fallback_messages = [
            f"Mi dispiace, non ho ancora conoscenze specifiche su '{user_kw}'. Ti consiglio di contattare direttamente il nostro team di esperti Otofarma o riformulare la domanda. Posso comunque aiutarti con altri argomenti!",
            
            f"Non dispongo di informazioni dettagliate su '{user_kw}' al momento, ma posso aiutarti con apparecchi acustici, servizi audiologici, farmacie e molto altro ancora!",
            
            f"Al momento non ho dati specifici su '{user_kw}', ma posso assisterti con informazioni su prodotti Otofarma, servizi di consulenza audiologica, o localizzazione delle nostre farmacie.",
            
            f"Non ho una risposta precisa su '{user_kw}', ma il nostro team di specialisti Otofarma sarà felice di aiutarti. Nel frattempo, posso assisterti con altri argomenti!",
            
            f"Mi scuso, non ho trovato dettagli su '{user_kw}'. Tuttavia, posso aiutarti con apparecchi acustici, servizi audiologici, e tutto ciò che riguarda il mondo Otofarma!"
        ]
    else:
        fallback_messages = [
            "Al momento non dispongo di una risposta precisa alla tua richiesta, ma sono qui per aiutarti su qualsiasi altro tema riguardante Otofarma.",
            "Mi scuso, non sono riuscito a trovare una risposta soddisfacente. Se desideri, puoi riformulare la domanda o chiedere su un altro argomento.",
            "Domanda interessante! Tuttavia, non ho informazioni puntuali su questo punto. Sono a disposizione per altre domande.",
            "La tua richiesta è stata ricevuta, ma non dispongo di dettagli specifici. Puoi fornire ulteriori informazioni o chiedere altro?",
            "Non trovo una risposta adeguata in questo momento. Ti invito a riformulare o a chiedere su altri temi.",
            "Mi dispiace, non ho trovato la risposta richiesta. Se vuoi puoi essere più dettagliato oppure chiedere su altri servizi Otofarma.",
            "Se hai bisogno di informazioni su servizi, apparecchi acustici o farmacie, chiedimi pure senza esitare.",
            "Sono qui per offrirti il massimo supporto: puoi essere più specifico nella tua richiesta?"
        ]
    reply = fallback_mem.get_unique(fallback_messages)
    return jsonify({"reply": reply, "voice": voice_mode, "male_voice": True})
# VISUAL ANALYSIS API ENDPOINTS - Professional Style

@app.route("/visual/activate", methods=["POST"])
def activate_visual_mode():
    """Activate visual analysis mode - Professional greeting"""
    try:
        visual_state["active"] = True
        visual_state["session_id"] = str(uuid.uuid4())
        
        greeting = get_visual_greeting()
        
        logger.info(f"Visual mode activated - Session: {visual_state['session_id']}")
        
        return jsonify({
            "success": True,
            "message": greeting,
            "session_id": visual_state["session_id"],
            "visual_active": True,
            "voice": True,
            "male_voice": True
        })
        
    except Exception as e:
        logger.error(f"Visual activation error: {e}")
        return jsonify({
            "success": False,
            "error": "Errore nell'attivazione della modalità visiva",
            "visual_active": False
        }), 500

@app.route("/visual/analyze", methods=["POST"])
def analyze_visual_input():
    """Analyze image input - Core visual processing endpoint"""
    try:
        if not visual_state["active"]:
            return jsonify({
                "success": False,
                "error": "Modalità visiva non attiva. Attivala prima di procedere."
            }), 400
        
        # Handle JSON data from JavaScript
        data = request.get_json()
        if data:
            user_message = data.get("message", "")
            image_data = data.get("image_data", "")
            
            if image_data:
                if image_data.startswith("data:image"):
                    image_data = image_data.split(",")[1]
                image_data = base64.b64decode(image_data)
            else:
                return jsonify({
                    "success": False,
                    "error": "Nessuna immagine fornita per l'analisi"
                }), 400
        else:
            # Handle form data as fallback
            user_message = request.form.get("message", "")
            
            if "image" in request.files:
                # Image file upload
                image_file = request.files["image"]
                image_data = image_file.read()
            elif "image_data" in request.form:
                # Base64 image data
                image_data = request.form["image_data"]
                if image_data.startswith("data:image"):
                    image_data = image_data.split(",")[1]
                image_data = base64.b64decode(image_data)
            else:
                return jsonify({
                    "success": False,
                    "error": "Nessuna immagine fornita per l'analisi"
                }), 400
        
        # Process visual analysis
        analysis_result = process_visual_query(image_data, user_message)
        
        # Format response for TTS
        formatted_response = format_numbers_for_speech(analysis_result)
        
        logger.info(f"Visual analysis completed - Session: {visual_state['session_id']}")
        
        return jsonify({
            "success": True,
            "analysis": analysis_result,
            "formatted_response": formatted_response,
            "session_id": visual_state["session_id"],
            "voice": True,
            "male_voice": True,
            "timestamp": time.time()
        })
        
    except Exception as e:
        logger.error(f"Visual analysis error: {e}")
        return jsonify({
            "success": False,
            "error": "Errore nell'analisi dell'immagine. Riprova.",
            "details": str(e)
        }), 500

@app.route("/visual/continuous", methods=["POST"])
def toggle_continuous_visual():
    """Toggle continuous visual monitoring mode"""
    try:
        data = request.get_json()
        enable = data.get("enable", False)
        
        visual_state["continuous_mode"] = enable
        
        status = "attivato" if enable else "disattivato"
        message = f"Monitoraggio visivo continuo {status}. {'Ora analizzerò automaticamente ciò che vedo.' if enable else 'Modalità manuale attivata.'}"
        
        return jsonify({
            "success": True,
            "message": message,
            "continuous_mode": enable,
            "voice": True,
            "male_voice": True
        })
        
    except Exception as e:
        logger.error(f"Continuous visual toggle error: {e}")
        return jsonify({
            "success": False,
            "error": "Errore nel cambio modalità continua"
        }), 500

@app.route("/visual/deactivate", methods=["POST"])
def deactivate_visual_mode():
    """Deactivate visual analysis mode"""
    try:
        visual_state["active"] = False
        visual_state["continuous_mode"] = False
        
        message = "Modalità visiva disattivata. Torno alla modalità vocale standard di Otofarma. Come posso aiutarti?"
        
        logger.info(f"Visual mode deactivated - Session: {visual_state['session_id']}")
        
        return jsonify({
            "success": True,
            "message": message,
            "visual_active": False,
            "voice": True,
            "male_voice": True
        })
        
    except Exception as e:
        logger.error(f"Visual deactivation error: {e}")
        return jsonify({
            "success": False,
            "error": "Errore nella disattivazione visiva"
        }), 500

@app.route("/visual/status", methods=["GET"])
def get_visual_status():
    """Get current visual analysis status"""
    try:
        return jsonify({
            "visual_active": visual_state["active"],
            "continuous_mode": visual_state["continuous_mode"],
            "session_id": visual_state["session_id"],
            "last_analysis": visual_state.get("last_analysis"),
            "config": VISUAL_ANALYSIS_CONFIG
        })
    except Exception as e:
        logger.error(f"Visual status error: {e}")
        return jsonify({"error": "Errore nel recupero stato visivo"}), 500

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
    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400

    audio_file = request.files["audio"]
    audio_bytes = audio_file.read()

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "speakai-467308-fb5a36feacef.json"

    client = speech.SpeechClient()
    audio = speech.RecognitionAudio(content=audio_bytes)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
        sample_rate_hertz=48000,
        language_code="it-IT",
        enable_automatic_punctuation=True
    )

    response = client.recognize(config=config, audio=audio)
    transcript = ""
    for result in response.results:
        transcript += result.alternatives[0].transcript

    return jsonify({"transcript": transcript})
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    # Production-ready configuration for presidential presentation
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)






