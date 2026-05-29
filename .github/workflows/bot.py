import requests
import json
from datetime import datetime, timedelta
import os
import smtplib
from email.mime.text import MIMEText

USA_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
YF_LOOKUP = "https://query1.finance.yahoo.com/v1/finance/search?q={query}"

AI_KEYWORDS = [
    "artificial intelligence", " ai ", "machine learning", " ml ",
    "llm", "large language model", "neural", "computer vision",
    "autonomy", "autonomous", "predictive maintenance"
]

def is_ai_related(text):
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in AI_KEYWORDS)

def is_multi_year(award):
    start = award.get("period_of_performance_start_date")
    end = award.get("period_of_performance_current_end_date")
    if not start or not end:
        return False
    try:
        s = datetime.fromisoformat(start[:10])
        e = datetime.fromisoformat(end[:10])
        return (e - s).days >= 365
    except:
        return False

def fetch_awards(start_date, end_date):
    payload = {
        "fields": [
            "Award ID", "Recipient Name", "Award Amount",
            "Description", "period_of_performance_start_date",
            "period_of_performance_current_end_date"
        ],
        "filters": {
            "time_period": [{"start_date": start_date, "end_date": end_date}],
            "award_type_codes": ["A", "B", "C", "D"]
        },
        "page": 1,
        "limit": 200
    }
    r = requests.post(USA_URL, json=payload)
    r.raise_for_status()
    return r.json().get("results", [])

def load_companies():
    with open("companies.json", "r") as f:
        return json.load(f)

def load_tickers():
    with open("tickers.json", "r") as f:
        return json.load(f)

def save_tickers(tickers):
    with open("tickers.json", "w") as f:
        json.dump(sorted(list(set(tickers))), f, indent=2)

def lookup_ticker(company_name):
    try:
        url = YF_LOOKUP.format(query=company_name.replace(" ", "%20"))
        r = requests.get(url, timeout=10)
        data = r.json()

        for item in data.get("quotes", []):
            if item.get("quoteType") == "EQUITY":
                return item.get("symbol")
    except:
        return None

def send_slack(text):
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if webhook:
        requests.post(webhook, json={"text": text})

def send_email(subject, body):
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    pwd = os.environ.get("SMTP_PASS")
    to = os.environ.get("ALERT_EMAIL")

    if not all([host, user, pwd, to]):
        print("Email not configured.")
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, pwd)
        server.send_message(msg)

def main():
    companies = load_companies()
    tickers = load_tickers()

    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)

    awards = fetch_awards(str(yesterday), str(today))

    alerts = []
    new_tickers = []

    for a in awards:
        desc = a.get("Description") or ""
        if not is_ai_related(desc):
            continue
        if not is_multi_year(a):
            continue

        recipient = a.get("Recipient Name", "")
        if not recipient:
            continue

        matched = None
        for c in companies:
            if c["ticker"] in tickers and c["ticker"].lower() in recipient.lower():
                matched = c
                break

        if not matched:
            ticker = lookup_ticker(recipient)
            if ticker and ticker not in tickers:
                new_tickers.append(ticker)
                tickers.append(ticker)

        companies = load_companies()

        for c in companies:
            if c["ticker"] in tickers:
                matched = c

        if not matched:
            continue

        amount = a.get("Award Amount") or 0
        if amount >= matched["annual_revenue_usd"]:
            alerts.append((matched, a))

    if new_tickers:
        save_tickers(tickers)
        send_slack(f"🆕 Added new tickers: {', '.join(new_tickers)}")

    if alerts:
        for company, award in alerts:
            msg = (
                f"🚨 AI Contract >= Annual Revenue\n\n"
                f"Company: {company['ticker']}\n"
                f"Award Amount: ${award.get('Award Amount', 0):,.0f}\n"
                f"Annual Revenue: ${company['annual_revenue_usd']:,.0f}\n"
                f"Recipient: {award.get('Recipient Name','')}\n"
                f"Description: {award.get('Description','')}\n"
                f"Start: {award.get('period_of_performance_start_date')}\n"
                f"End: {award.get('period_of_performance_current_end_date')}\n"
                f"Award ID: {award.get('Award ID')}"
            )
            send_slack(msg)
            send_email("AI Contract Alert", msg)

    print("Done.")

if __name__ == "__main__":
    main()
