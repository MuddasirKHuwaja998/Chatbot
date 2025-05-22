# -*- coding: utf-8 -*-
import logging
import json
import random
import glob
import os
import yaml
import difflib
from spellchecker import SpellChecker
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

#################################################
#              basic global var                 #
#################################################
with open("config.json") as f:
    data = json.loads(f.read())
    token = data["token"]
    user = data["user"]
with open("config.json") as f:
    data = json.loads(f.read())
    USERID = data["userid"]

##################################################
#                     logging                    #
##################################################
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

##################################################
#                NLP + Corpus Loading            #
##################################################
CORPUS_PATH = "./corpus"
JSON_PATH = "./responses_it.json"

# Load all YAML Q/A
all_qa_pairs = []
for yml_file in glob.glob(os.path.join(CORPUS_PATH, "*.yml")):
    with open(yml_file, encoding='utf-8') as f:
        data = yaml.safe_load(f)
        for conv in data.get('conversations', []):
            if isinstance(conv, list) and len(conv) >= 2:
                q, *a = conv
                all_qa_pairs.append((q.strip().lower(), " ".join([str(x) for x in a])))

# Load JSON
if os.path.exists(JSON_PATH):
    with open(JSON_PATH, encoding='utf-8') as f:
        otofarma_data = json.load(f)
else:
    otofarma_data = {}

spell = SpellChecker(language='it')
def normalize(text):
    import re
    return re.sub(r'[^\w\s]', '', text.strip().lower())

def correct_spelling(text):
    words = text.split()
    corrected_words = [spell.correction(w) or w for w in words]
    return ' '.join(corrected_words)

def match_greeting(msg_norm):
    greetings = otofarma_data.get("greetings", [])
    common_words = otofarma_data.get("common_words", [])
    if msg_norm in [normalize(word) for word in common_words]:
        if isinstance(greetings, list):
            return random.choice(greetings)
        return greetings
    return None

def match_general_query(msg_norm):
    general_queries = otofarma_data.get("general_queries", [])
    norm_map = {
        normalize(item.get("query", "")): item.get("response", "")
        for item in general_queries if "query" in item and "response" in item
    }
    if msg_norm in norm_map:
        return norm_map[msg_norm]
    best_match = difflib.get_close_matches(msg_norm, norm_map.keys(), n=1, cutoff=0.7)
    if best_match:
        return norm_map[best_match[0]]
    return None

def match_direct_keys(msg_norm):
    keywords_map = {
        "prodotto": "products",
        "prodotti": "products",
        "location": "locations",
        "sede": "locations",
        "dipendenti": "employees",
        "impiegati": "employees",
        "team": "employees",
        "appuntamento": "appointment",
        "prenotazione": "appointment",
        "telemedicina": "telemedicine",
        "farmacie": "pharmacies",
        "farmacia": "pharmacies",
    }
    for k, v in keywords_map.items():
        if k in msg_norm and v in otofarma_data:
            return otofarma_data[v]
    return None

def match_yaml_qa(msg_norm):
    for q, a in all_qa_pairs:
        if msg_norm == normalize(q):
            return a
    msg_corr = correct_spelling(msg_norm)
    questions = [normalize(q) for q, _ in all_qa_pairs]
    best_match = difflib.get_close_matches(msg_corr, questions, n=1, cutoff=0.7)
    if best_match:
        idx = questions.index(best_match[0])
        return all_qa_pairs[idx][1]
    best_match = difflib.get_close_matches(msg_norm, questions, n=1, cutoff=0.7)
    if best_match:
        idx = questions.index(best_match[0])
        return all_qa_pairs[idx][1]
    return None

##################################################
#                support functions               #
##################################################
def enabled(user_id, admin_ids=USERID):
    return user_id in admin_ids

def error_message():
    answeres = [
        "Non sei il mio padrone vai via!",
        "Non sei il mio creatore sparisci!",
        "Puoi anche scrivermi non ti risponderò mai con alcuna frase di senso compiuto",
        "Get out, ti mangio gnam!",
        "Non sono il tuo bot, perciò ti sto per inviare un virus per il tuo smartphone",
        "Non sono il tuo bot, come mi hai trovato? Per punizione la tua curiosità verrà salvata per sempre sui miei log e chi sei segnalato al mio sviluppatore"
    ]
    return random.choice(answeres)

##################################################
#                conversation                    #
##################################################
async def start(update, context):
    user_id = update.effective_user.id
    if not enabled(user_id):
        with open("./gif/error.gif", 'rb') as gif:
            await update.message.reply_video(gif)
        return
    response_start = (
        "Ehilà! Sono un bot e mi chiamo Taylor, perché il mio creatore ha un feticcio per Taylor Swift, "
        "posso fare un sacco di cose, anche chiacchierare un po', se vuoi sapere cosa altro io sia in grado di fare "
        "invia pure il comando /help in chat :)."
    )
    await update.message.reply_text(response_start)

async def help(update, context):
    user_id = update.effective_user.id
    if not enabled(user_id):
        with open("./gif/error.gif", 'rb') as gif:
            await update.message.reply_video(gif)
        return
    response_help = (
        "Ehi, sono Taylor e so fare un sacco di cose, posso avere una semplice conversazione con te però, perdonami "
        "anticipatamente in caso ti dia risposte un po' 'così', sto ancora imparando! Però posso comunque dirti quando "
        "passi il prossimo autobus a Bologna utilizzando il comando /bus NUMEROFERMATA (NUMEROLINEA), puoi anche omettere "
        "il nome della linea!"
    )
    await update.message.reply_text(response_help)

async def bus(update, context):
    user_id = update.effective_user.id
    if not enabled(user_id):
        await update.message.reply_text(error_message())
        return
    user_says = " ".join(context.args)
    if not context.args:
        await update.message.reply_text("Devi specificare almeno il numero della fermata.")
        return
    fermata = context.args[0]
    try:
        bus_num = context.args[1]
    except IndexError:
        bus_num = 0
    try:
        import addons
        query_result = addons.query_hellobus(fermata, bus_num)
    except Exception:
        query_result = (
            "Oh oh oh! Hai inserito dei parametri non validi o, molto probabilmente, la linea che cerchi non è servita dal servizio di geolocalizzazione "
            "oppure hai inserito dei parametri a caso.\nRicorda che il comando corretto è:\n/bus NUMEROFERMATA [NUMEROAUTOBUS]"
        )
    await update.message.reply_text(query_result)

async def answer(update, context):
    user_id = update.effective_user.id
    if not enabled(user_id):
        with open("./gif/error.gif", 'rb') as gif:
            await update.message.reply_video(gif)
        await update.message.reply_text(error_message())
        return

    user_says = str(update.message.text).strip()
    msg_norm = normalize(user_says)

    # 1. Try JSON greeting
    reply = match_greeting(msg_norm)
    if reply:
        await update.message.reply_text(reply)
        return

    # 2. Try JSON general queries
    reply = match_general_query(msg_norm)
    if reply:
        await update.message.reply_text(reply)
        return

    # 3. Try JSON direct keys
    reply = match_direct_keys(msg_norm)
    if reply:
        await update.message.reply_text(reply)
        return

    # 4. Try YAML corpus Q&A with fuzzy NLP
    reply = match_yaml_qa(msg_norm)
    if reply:
        await update.message.reply_text(reply)
        return

    # 5. Default fallback: ChatterBot or generic default
    try:
        import chatbot
        bot_response = chatbot.taylorchatbot.get_response(user_says)
        reply = str(bot_response).strip()
        if not reply:
            reply = otofarma_data.get("default", "Mi dispiace, non ho capito. Puoi ripetere?")
    except Exception as e:
        print("Error in bot answer:", e)
        reply = f"Errore: {e}"

    await update.message.reply_text(reply)

##################################################
#                   bot core                     #
##################################################
def error(update, context):

    logger.warning('Update "%s" caused error "%s"', update, context.error)
def train():
    from chatterbot.trainers import ChatterBotCorpusTrainer
    import chatbot
    instance = chatbot.taylorchatbot
    trainer = ChatterBotCorpusTrainer(instance)
    trainer.train(
        "./corpus/ai.yml",
        "./corpus/botprofile.yml",
        "./corpus/computers.yml",
        "./corpus/conversations.yml",
        "./corpus/emotion.yml",
        "./corpus/food.yml",
        "./corpus/gossip.yml",
        "./corpus/greetings.yml",
        "./corpus/health.yml",
        "./corpus/history.yml",
        "./corpus/humor.yml",
        "./corpus/literature.yml",
        "./corpus/money.yml",
        "./corpus/politics.yml",
        "./corpus/psychology.yml",
        "./corpus/science.yml",
        "./corpus/sports.yml",
        "./corpus/trivia.yml",
        "./corpus/otofarma.yml",
        "./corpus/movies.yml",
        "./corpus/qna.yml",
        "./corpus/OTONEW.yml"
    )


def main():
    train()
    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("bus", bus))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(MessageHandler(filters.TEXT, answer))
    application.run_polling()

if __name__ == '__main__':
    main()
    