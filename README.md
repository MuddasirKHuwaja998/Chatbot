# Bot

Bot is a virtual assistant for Otofarma Spa, built using Python and Flask. It provides automated responses to user queries about Otofarma’s services, products, appointments, and more. The bot supports natural language questions in Italian and uses a YAML-based Q&A corpus, fuzzy matching, and dynamic responses for time and date. It also includes a Telegram bot version.

## Features

- Responds to user questions about Otofarma (services, products, appointments, etc.)
- Supports natural, conversational queries in Italian
- Dynamic responses for current time and date (in Italian)
- Fallback responses for unknown or out-of-scope questions
- YAML corpus for easy editing and extension of Q&A pairs
- Telegram bot support (optional)
- Spellchecking for improved user experience

## Project Structure

```
/corpus/           # YAML Q&A files (knowledge base)
/templates/        # HTML templates for Flask frontend
/static/           # Static files (optional, e.g., CSS/images)
app.py             # Main Flask app
chatbot.py         # ChatterBot logic
bot.py             # Telegram bot logic (optional)
addons.py          # Utility and helper functions
requirements.txt   # Python dependencies
runtime.txt        # Python version for deployment (Render)
Procfile           # Gunicorn start command (for Render)
config.json        # (If used) Config data/tokens (do NOT commit secrets)
```

## Installation

1. **Clone the repository:**
   ```sh
   git clone https://github.com/youruser/otofarma-bot.git
   cd otofarma-bot
   ```

2. **Create a virtual environment (optional but recommended):**
   ```sh
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```sh
   pip install -r requirements.txt
   ```

4. **(Optional) Set up environment variables or config files:**
   - If your app uses `config.json` for secrets, fill in the required fields (never commit real tokens to GitHub!).

## Running Locally

```sh
python app.py
```
- The app will be accessible at `http://localhost:10000/` by default.

## Deployment (Render)

1. **Push your code to GitHub.**
2. **Connect your GitHub repo to [Render.com](https://render.com/).**
3. **Set up environment variables/tokens as needed in the Render dashboard.**
4. **Make sure your repo includes:**
   - `requirements.txt` (including `gunicorn`)
   - `Procfile` with: `web: gunicorn app:app`
   - `runtime.txt` with: `python-3.10.11`
5. **Deploy!**

## Customizing the Q&A

- Add/edit YAML files in `/corpus/` to teach the bot new answers.
- Use the existing structure for question/answer pairs.

## License

MIT License (or your preferred license)

## Author

- Muddasir khuwaja(engr.muddasir01@gmail.com)

---

**For any issues or questions, please open an issue on GitHub.**
