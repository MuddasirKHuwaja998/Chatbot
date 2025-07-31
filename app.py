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
    
    # Check enhanced patterns
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
    
    # Check greetings
    for pattern, reply in CUSTOM_GREETINGS:
        # Exact match for short greetings
        if len(msg.split()) <= 2 and pattern in msg:
            return reply
            
        # Fuzzy match for longer patterns
        if rapidfuzz_available and len(pattern) > 3:
            if fuzz.partial_ratio(pattern, msg) > 85:
                return reply
    
    # Check for standalone greetings
    tokens = msg.split()
    if len(tokens) == 1 and tokens[0] in ["ciao", "salve", "buongiorno", "buonasera", "buonanotte"]:
        return "Salve! Sono qui per aiutarti in tutto ciò che riguarda Otofarma."
    
    return None

# Pharmacy-related functions (unchanged but with better error handling)
pharmacies = []
if os.path.isfile(PHARMACY_CSV_PATH):
    try:
        with open(PHARMACY_CSV_PATH, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=';' if PHARMACY_CSV_PATH.lower().endswith('.csv') else ',')
            for row in reader:
                pharmacies.append(row)
        print(f"Caricate {len(pharmacies)} farmacie dal CSV.")
    except Exception as e:
        print(f"Errore nel caricamento del CSV farmacie: {e}")
else:
    print(f"File CSV farmacie non trovato: {PHARMACY_CSV_PATH}")

def is_pharmacy_question(msg):
    """Detect pharmacy-related questions"""
    if not msg:
        return False
        
    msg_lc = normalize(msg)
    pharmacy_keywords = [
        "farmacia", "farmacie", "indirizzo", "telefono", "numero", "email", "contatto", 
        "dove", "trovare", "vicino", "cap", "regione", "provincia", "orari", "aperta", 
        "chiusa", "apertura", "chiusura", "città", "zona", "quartiere", "dottore", 
        "dr", "dottoressa", "info", "contatti", "farmacista"
    ]
    
    return any(kw in msg_lc for kw in pharmacy_keywords)

def extract_city_from_query(user_msg):
    """Extract city names from user query"""
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
    """Format pharmacy list response"""
    city_formatted = city_name.strip() or "la città richiesta"
    total = len(ph_list)
    
    intros = [
        f"Ti elenco le farmacie Otofarma presenti a {city_formatted}",
        f"Ecco le farmacie Otofarma disponibili a {city_formatted}",
        f"Queste sono le farmacie Otofarma che puoi trovare a {city_formatted}",
        f"Qui trovi le farmacie Otofarma in zona {city_formatted}"
    ]
    
    count_lines = [
        f"In questa città ci sono {total} farmacie Otofarma",
        f"A {city_formatted} risultano {total} farmacie Otofarma affiliate",
        f"Abbiamo {total} farmacie Otofarma registrate per {city_formatted}"
    ]
    
    next_steps = [
        "Ecco quella che potrebbe essere più comoda per te:",
        "Qui i dettagli di una delle principali farmacie della zona:",
        "Ti segnalo subito una farmacia particolarmente accessibile:"
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
    """Main chat endpoint with enhanced intelligence"""
    user_message = request.json.get("message", "")
    voice_mode = request.json.get("voice", True)
    
    # Enhanced voice activation detection
    if detect_enhanced_voice_activation(user_message):
        print("🔥 Hey OtoBot detected in chat!")
        return jsonify({"reply": handle_voice_activation_greeting(), "voice": voice_mode, "male_voice": True})
    user_lat = request.json.get("lat", None)
    user_lon = request.json.get("lon", None)
    

    print(f"Received message: '{user_message}'")

    # 1. Check for assistant name activation
    if detect_assistant_name(user_message):
        return jsonify({"reply": handle_voice_activation_greeting(), "voice": voice_mode, "male_voice": True})

    # 2. Check for general greetings first
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

    # 5. Check for office hours (before YAML to avoid conflicts)
    if detect_office_hours_question(user_message_corr):
        return jsonify({"reply": get_office_hours_answer(), "voice": voice_mode, "male_voice": True})

    # 6. Check for time/date questions (with strict matching)
    time_or_date = detect_time_or_date_question(user_message_corr)
    if time_or_date == "time":
        return jsonify({"reply": get_time_answer(), "voice": voice_mode, "male_voice": True})
    elif time_or_date == "date":
        return jsonify({"reply": get_date_answer(), "voice": voice_mode, "male_voice": True})

    # 7. YAML Q&A matching (highest priority for content)
    reply = match_yaml_qa_ai(user_message_corr)
    if reply:
        print(f"Found YAML answer: {reply[:100]}...")
        return jsonify({"reply": reply, "voice": voice_mode, "male_voice": True})

    # 8. Pharmacy-specific queries
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

    # 9. Fallback responses
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
# Google Cloud TTS endpoint for Italian male voice
@app.route("/tts", methods=["POST"])
def tts():
    data = request.json
    text = data.get("text", "")
    voice_name = "it-IT-Wavenet-F"  # Your chosen male Italian voice

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "speakai-467308-fb5a36feacef.json"

    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=text)
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
    app.run(host="0.0.0.0", port=port, debug=True)
