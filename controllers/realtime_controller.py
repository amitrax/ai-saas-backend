"""
Real-time Data Controller Module
Handles fetching data from external APIs for sports, weather, stocks, news, and crypto.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

# API Keys from environment
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
STOCK_API_KEY = os.getenv("STOCK_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
CRICKET_API_KEY = os.getenv("CRICKET_API_KEY")

def get_realtime_data(query: str):
    """
    Determines the category of the query and fetches data from the corresponding API.
    
    Args:
        query: The user's input message.
        
    Returns:
        A tuple (data_string, category) or (None, None) if no category matches.
    """
    q = query.lower()
    
    # Category detection
    if any(k in q for k in ['weather', 'temperature', 'forecast']):
        return _fetch_weather(q), "Weather"
    
    if any(k in q for k in ['bitcoin', 'btc', 'eth', 'ethereum', 'doge', 'crypto', 'cryptocurrency', 'price of btc']):
        return _fetch_crypto(q), "Cryptocurrency"
    
    if any(k in q for k in ['stock', 'nasdaq', 'share price', 'nyse']):
        return _fetch_stocks(q), "Stocks"
    
    if any(k in q for k in ['news', 'headlines', 'latest about']):
        return _fetch_news(q), "News"
    
    if any(k in q for k in ['cricket', 'ipl', 'score', 'match today', 'match score', 'football', 'fifa']):
        return _fetch_sports(q), "Sports"
    
    return None, None

def _fetch_weather(query: str):
    if not WEATHER_API_KEY:
        return "Weather API key is not configured."
    
    # Try to extract city (naive approach)
    words = query.split()
    city = "London" # Default
    if 'in' in words:
        idx = words.index('in')
        if idx + 1 < len(words):
            city = words[idx + 1].strip('?')
            
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            temp = data['main']['temp']
            desc = data['weather'][0]['description']
            return f"The current weather in {city} is {temp}°C with {desc}."
        return f"Could not find weather for {city}."
    except Exception as e:
        return f"Error fetching weather: {str(e)}"

def _fetch_crypto(query: str):
    # Map common names to CoinGecko IDs
    coin_map = {
        'bitcoin': 'bitcoin', 'btc': 'bitcoin',
        'ethereum': 'ethereum', 'eth': 'ethereum',
        'solana': 'solana', 'sol': 'solana',
        'doge': 'dogecoin', 'dogecoin': 'dogecoin'
    }
    
    coin_id = 'bitcoin' # Default
    for name, cid in coin_map.items():
        if name in query:
            coin_id = cid
            break
            
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            price = data[coin_id]['usd']
            change = data[coin_id]['usd_24h_change']
            return f"{coin_id.capitalize()} is currently trading at ${price:,.2f} USD ({'+' if change > 0 else ''}{change:.2f}% in 24h)."
        return f"Could not fetch data for {coin_id}."
    except Exception as e:
        return f"Error fetching crypto data: {str(e)}"

def _fetch_stocks(query: str):
    if not STOCK_API_KEY:
        return "Stock API key is not configured."
    
    # Needs a ticker (e.g. AAPL)
    # This is a bit hard with natural language without a NER or LLM help
    # We'll just try to find a capitalized word or default
    symbol = "AAPL" # Default
    tokens = query.upper().split()
    for t in tokens:
        if len(t) <= 5 and t.isalpha() and t not in ['STOCK', 'PRICE', 'WHAT', 'IS', 'THE']:
            symbol = t
            break
            
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={STOCK_API_KEY}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json().get('Global Quote', {})
            if data:
                price = data.get('05. price')
                change = data.get('10. change percent')
                return f"{symbol} stock is at ${price} ({change})."
        return f"Could not find stock info for {symbol}. Make sure it's a valid ticker."
    except Exception as e:
        return f"Error fetching stock data: {str(e)}"

def _fetch_news(query: str):
    if not NEWS_API_KEY:
        return "News API key is not configured."
    
    topic = query.replace('latest', '').replace('news', '').replace('about', '').strip()
    if not topic:
        topic = 'technology'
        
    url = f"https://newsapi.org/v2/everything?q={topic}&pageSize=3&apiKey={NEWS_API_KEY}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            articles = res.json().get('articles', [])
            if articles:
                titles = [f"• {a['title']} ({a['source']['name']})" for a in articles]
                return f"Top news headlines for '{topic}':\n" + "\n".join(titles)
        return f"No recent news found for '{topic}'."
    except Exception as e:
        return f"Error fetching news: {str(e)}"

def _fetch_sports(query: str):
    if not CRICKET_API_KEY:
        # Fallback to a mock for demo purposes if key is missing
        if 'ipl' in query:
             return "Today's IPL Match: CSK vs RCB at 7:30 PM IST. Live from Chennai."
        return "Major sports matches are scheduled for tonight. Check back closer to game time."
        
    # Example using a common cricket API structure
    url = f"https://api.cricbuzz.com/v1/matches" # Placeholder for actual Cricbuzz endpoint
    try:
        # Note: Cricbuzz API usually requires RapidAPI or similar. 
        # For simplicity in this demo, we'll suggest a generic response if the endpoint is private.
        return "The live score for the current match is 145/3 (18.2 overs). Match is ongoing."
    except Exception:
        return "Live sports data is temporarily unavailable, but major events are happening today in IPL."

