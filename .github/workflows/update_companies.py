import json
import requests

YF_URL = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}?modules=financialData"

def fetch_revenue(ticker):
    try:
        url = YF_URL.format(ticker=ticker)
        r = requests.get(url, timeout=10)
        data = r.json()
        fin = data["quoteSummary"]["result"][0]["financialData"]
        revenue = fin.get("totalRevenue", {}).get("raw")
        return revenue
    except Exception:
        return None

def main():
    with open("tickers.json", "r") as f:
        tickers = json.load(f)

    companies = []

    for t in tickers:
        revenue = fetch_revenue(t)
        if revenue:
            companies.append({
                "ticker": t,
                "annual_revenue_usd": revenue
            })

    with open("companies.json", "w") as f:
        json.dump(companies, f, indent=2)

    print("Updated companies.json with", len(companies), "companies.")

if __name__ == "__main__":
    main()
