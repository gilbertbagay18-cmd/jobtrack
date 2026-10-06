# JobTrack 📋

Land the job. Track every step.

A mobile-first job application tracker built with Flask and SQLite. Installable as a PWA and developed entirely on an Android phone with Termux.

## Features

- Accounts: sign up, log in and out, forgot and reset password (expiring, single-use tokens), change password, delete account
- Track applications: company, position, status (Applied, Interview, Offer, Rejected, Withdrawn), date applied, interview date and time, location or meeting link, job posting link, salary, employment type, work setup, notes
- Dashboard: totals, this week, this month, interview rate, upcoming interviews
- Search, status and date filters, and sorting
- Company and place finder (OpenStreetMap)
- Profile and Settings: light, dark, or system theme, default status, default sorting
- Toast notifications, confirmation dialogs, loading states, custom error pages
- Installable PWA

## Security

- Passwords hashed with Werkzeug
- CSRF protection on every form
- Sessions are invalidated on logout and password change
- Every query is scoped to the logged-in user
- Rate limiting on login and password reset
- Secrets live in environment variables, never in code

## Tech stack

Python, Flask, SQLite, Flask-WTF, Flask-Limiter, HTML, CSS, JavaScript

## Run locally

    git clone https://github.com/YOUR-USERNAME/jobtrack.git
    cd jobtrack
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env
    python app.py

Open http://127.0.0.1:5000. Set a long random SECRET_KEY in `.env` first.

## Environment variables

| Variable | Purpose |
| --- | --- |
| SECRET_KEY | Signs session cookies (required) |
| FLASK_DEBUG | 1 for development, 0 for production |
| DATABASE_PATH | SQLite file location |
| RESET_TOKEN_EXPIRATION | Reset link lifetime in seconds |
| BASE_URL | Public site URL used in reset emails |
| MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_DEFAULT_SENDER | SMTP settings. Without them, reset links print in the server console (dev mode) |

## Roadmap

- Automated tests
- Dashboard charts
- Production deployment with PostgreSQL
