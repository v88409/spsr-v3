## Deploy on Google Colab (Temporary/Testing)

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/v88409/spsr-v3/blob/main/colab_deploy.ipynb)

Click the badge above to open the deployment notebook directly in Google Colab. Run the cells top to bottom:

1. **Clone & Install** — clones this repo and installs `requirements.txt`.
2. **Set Environment Variables** — fill in the fields directly in the notebook cell (`API_ID`, `API_HASH`, `BOT_TOKEN`, `MONGO_DB`, `OWNER_ID`, etc. — see [Environment Variables](#8-environment-variables) above).
3. **Start Bot** — runs `main.py` in the background.
4. **View Logs** — check that the bot started without errors.
5. **Keep-Alive** — run and leave this cell running to keep the session active.

> ⚠️ Colab sessions are temporary (disconnect on tab close, inactivity, or after Colab's free-tier time limit — up to ~12 hours). Use this for quick testing only; for always-on hosting, use Render/Heroku/Docker as described in [Deployment](#10-deployment).
