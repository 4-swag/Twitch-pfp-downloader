# Twitch-pfp

Fast CLI downloader for Twitch profile pictures. Saves each avatar at the largest size Twitch's CDN serves (600x600, falling back to 300x300) and prints a short account summary: display name, user ID, creation date, and broadcaster type. Reads only public data exposed by the official Twitch Helix API.

## Setup

Python 3.11+. Requires a free Twitch application from https://dev.twitch.tv/console/apps (OAuth redirect `http://localhost`, client type *Confidential*).

```
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate      # Linux / macOS
pip install -r requirements.txt
cp .env.example .env
# edit .env: set TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET
```

On Windows you can skip all of that and just run `run.bat`: it creates the virtual environment on first launch and prompts for usernames if none are given.

## Usage

```
python main.py shroud
python main.py @pokimane
python main.py https://www.twitch.tv/xqc
python main.py user1 user2 user3
```

Accepts a login name, `@login`, or a full `twitch.tv` URL. Up to 100 names are looked up per API call.

## Output

Per account: display name, login, user ID, creation date and age, broadcaster type (partner / affiliate / regular), and the downloaded image size.

Images are written to `downloads/<login>_<size>.<ext>` (change the folder with `OUTPUT_DIR` in `.env`). The exit code is non-zero if any name was invalid, not found, or could not be downloaded.

## Credits

Made by **4swag**. Released under the [MIT License](LICENSE).
