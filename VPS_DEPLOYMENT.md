# VPS Deployment

This app is ready to run on an Ubuntu VPS with Gunicorn once the required environment variables and Chrome dependencies are in place.

## 1. System packages

Install Python 3.11, Git, Google Chrome, and a matching ChromeDriver.

Example package list:

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip git unzip
```

Install Chrome and ChromeDriver using your preferred package source, then verify:

```bash
google-chrome --version
chromedriver --version
```

## 2. Application setup

```bash
git clone https://github.com/InstaProgith/comp-intel.git
cd comp-intel
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Set production environment variables before starting the app:

- `APP_ENV=production`
- `FLASK_SECRET_KEY=<long random secret>`
- `APP_ACCESS_PASSWORD=<strong password>`
- `ONE_MIN_AI_API_KEY=<optional>`

Optional LADBS overrides:

- `LADBS_CHROME_BINARY`
- `LADBS_CHROMEDRIVER_PATH`
- `SE_CACHE_PATH`
- `LADBS_SELENIUM_PROFILE_DIR`
- `LADBS_DRIVER_START_RETRIES`
- `LADBS_PAGE_LOAD_TIMEOUT`

## 3. Verify before serving

Run the smoke suite:

```bash
python -m unittest discover -s tests -v
```

Run the live LADBS smoke before exposing the app:

```bash
python -m app.ladbs_smoke --redfin-url https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003 --json
```

Optional LADBS runtime env vars:

- `LADBS_CHROME_BINARY`
- `LADBS_CHROMEDRIVER_PATH`
- `LADBS_SELENIUM_PROFILE_DIR`
- `LADBS_BROWSER_ENV_DIR`
- `SE_CACHE_PATH`
- `LADBS_HEADLESS`

## 4. Start with Gunicorn

```bash
APP_ENV=production \
FLASK_SECRET_KEY=... \
APP_ACCESS_PASSWORD=... \
.venv/bin/gunicorn app.ui_server:app --bind 127.0.0.1:5000 --workers 2 --timeout 180
```

## 5. Optional systemd service

```ini
[Unit]
Description=BLDGBIT comp-intel
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/comp-intel
Environment=APP_ENV=production
Environment=FLASK_SECRET_KEY=replace-me
Environment=APP_ACCESS_PASSWORD=replace-me
ExecStart=/opt/comp-intel/.venv/bin/gunicorn app.ui_server:app --bind 127.0.0.1:5000 --workers 2 --timeout 180
Restart=always

[Install]
WantedBy=multi-user.target
```

## 6. Operational notes

- The app now fails closed in production-like environments if `FLASK_SECRET_KEY` or `APP_ACCESS_PASSWORD` is missing.
- LADBS browser bootstrap writes logs under `data/logs/ladbs/`.
- Selenium cache and browser profiles should point to writable directories on the VPS.
- `python -m app.ladbs_smoke` is the repeatable post-deploy check for browser startup + live LADBS search flow.
- `access_password.txt` is intentionally ignored by git and should only be used for local-only setups.
