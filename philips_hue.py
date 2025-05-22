# -*- coding: utf-8 -*-
import logging
import json
import addons
import chatbot
import random

#################################################
#              basic global var                 #
#################################################
with open("config.json") as f:
    data = json.loads(f.read())
    user = data["user"]

##################################################
#                     logging                    #
##################################################
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

##################################################
#                support functions               #
##################################################
with open("config.json") as f:
    data = json.loads(f.read())
    USERID = data["userid"]

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
#                conversation (CLI example)      #
##################################################

def cli_loop():
    print("Taylor Bot CLI - Type 'exit' to quit.")
    while True:
        user_says = input("You: ")
        if user_says.lower() == "exit":
            print("Bye!")
            break
        if "meme" in user_says.lower():
            print("[meme logic goes here]")
        elif "gif" in user_says.lower():
            print("[gif logic goes here]")
        elif "cantami una canzone" in user_says.lower() or "mi canti una canzone?" in user_says.lower() or "cantarmi una canzone" in user_says.lower():
            print("[song logic goes here]")
        elif (
            "un altro film" in user_says.lower() or
            "consigliami un film" in user_says.lower() or
            "mi consigli un film" in user_says.lower() or
            "un film da guardare" in user_says.lower()
        ):
            print(addons.get_random_movie())
        else:
            response = chatbot.taylorchatbot.get_response(user_says)
            print("Taylor:", str(response).capitalize())

##################################################
#                   bot core                     #
##################################################
def train():
    from chatterbot.trainers import ChatterBotCorpusTrainer
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
    # trainer.train('chatterbot.corpus.italian')

def main():
    train()
    cli_loop()

if __name__ == '__main__':
    main()