from chatterbot import ChatBot
from chatterbot.response_selection import get_first_response, get_most_frequent_response

taylorchatbot = ChatBot(
    "Taylor",
    storage_adapter="chatterbot.storage.SQLStorageAdapter",
    database="./db.sqlite3",
    input_adapter="chatterbot.input.VariableInputTypeAdapter",
    output_adapter="chatterbot.output.OutputAdapter",
    logic_adapters=[
        {
            'import_path': 'chatterbot.logic.BestMatch',
        }
    ],
    language='italian',  # This will set ChatterBot to use Italian logic/corpus if available
    response_selection_method=get_first_response
)
