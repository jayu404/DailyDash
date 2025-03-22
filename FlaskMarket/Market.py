import os
import datetime
import requests
import json
from flask import Flask, redirect, url_for, request, session, render_template, jsonify
from flask_cors import CORS
from google_auth_oauthlib.flow import Flow
import google.auth
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import uuid

# Flask Setup
app = Flask(__name__)
CORS(app)  # Enable CORS
app.secret_key = os.urandom(24)  # Session secret key

# Google OAuth Config
CLIENT_SECRETS_FILE = 'credentials.json'
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly', 'https://www.googleapis.com/auth/gmail.readonly']
API_NAME = 'calendar'
API_VERSION = 'v3'
API_KEY = "ed70a48eee5eec1d9baa14b214228cf0"
CITY = 'Fremont'
NEWS_API_KEY = "9cec027b5eee4bc9906b803e382b5c84"

@app.route('/')
def index():
    if 'credentials' not in session:
        return redirect(url_for('login'))

    # Load credentials from session
    credentials = google.oauth2.credentials.Credentials(**session['credentials'])
    service_calendar = build(API_NAME, API_VERSION, credentials=credentials)
    service_gmail = build('gmail', 'v1', credentials=credentials)

    # Fetch Gmail data (email snippets)
    email_data = get_gmail_data(service_gmail)

    # Fetch weather data
    weather_data = get_weather_data()

    # Fetch calendar events (existing functionality)
    events_result = service_calendar.events().list(
        calendarId='primary',
        maxResults=5,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])

    # Fetch top headlines (news)
    news_data = get_top_headlines()

    return render_template('dashboard.html',
                           weather=weather_data,
                           email_data=email_data,
                           events=events,
                           news=news_data)

def get_weather_data():
    url = f"http://api.openweathermap.org/data/2.5/weather?q={CITY}&appid={API_KEY}&units=metric"
    response = requests.get(url)
    data = response.json()

    if data.get("cod") != 200:
        return None

    weather = {
        'temperature': data['main']['temp'],
        'description': data['weather'][0]['description'],
        'city': CITY
    }
    return weather

def get_gmail_data(service):
    try:
        # Get the list of messages from Gmail
        results = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=5).execute()
        messages = results.get('messages', [])

        email_data = []
        if messages:
            for message in messages:
                msg = service.users().messages().get(userId='me', id=message['id']).execute()
                snippet = msg['snippet']

                # Extract email details
                headers = msg['payload']['headers']
                subject = ""
                sender = ""
                date = ""
                for header in headers:
                    if header['name'] == 'Subject':
                        subject = header['value']
                    if header['name'] == 'From':
                        sender = header['value']
                    if header['name'] == 'Date':
                        date = header['value']

                email_data.append({
                    'subject': subject,
                    'sender': sender,
                    'snippet': snippet,
                    'date': date
                })

        return email_data
    except Exception as error:
        return f"An error occurred: {error}"

@app.route('/get_top_headlines')
def get_top_headlines():
    url = f'https://newsapi.org/v2/top-headlines?country=us&apiKey={NEWS_API_KEY}'
    response = requests.get(url)
    data = response.json()

    # Fetch the top two headlines with images
    headlines = []
    for article in data['articles'][:2]:
        headline = {
            'title': article['title'],
            'url': article['url'],
            'image': article['urlToImage'],
            'description': article['description']
        }
        headlines.append(headline)

    return headlines

@app.route('/login')
def login():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for('oauth2callback', _external=True)
    )
    authorization_url, state = flow.authorization_url(prompt='consent')
    session['state'] = state
    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for('oauth2callback', _external=True)
    )
    flow.fetch_token(authorization_response=request.url)

    credentials = flow.credentials
    session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

    return redirect(url_for('index'))

@app.route('/get_events')
def get_events():
    if 'credentials' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    credentials = google.oauth2.credentials.Credentials(**session['credentials'])
    service = build(API_NAME, API_VERSION, credentials=credentials)

    # Fetch the next 10 events
    events_result = service.events().list(
        calendarId='primary',
        maxResults=10,
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])

    # Format events for FullCalendar
    formatted_events = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))
        formatted_events.append({
            'title': event['summary'],
            'start': start,
            'end': end
        })

    return jsonify(formatted_events)

@app.route('/quote')
def get_quote():
    try:
        response = requests.get("https://zenquotes.io/api/random")
        if response.status_code == 200:
            data = response.json()
            quote = data[0]["q"]  # Quote text
            author = data[0]["a"]  # Author
            return jsonify({"quote": quote, "author": author})
        else:
            return jsonify({"error": "Failed to fetch quote"}), 500
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500


@app.route('/this-day-in-history')
def this_day_in_history():
    today = datetime.datetime.today().strftime('%m/%d')  # Get today's date in MM/DD format
    url = f"https://history.muffinlabs.com/date"

    try:
        response = requests.get(url)
        data = response.json()

        # Pick a random historical event
        event = data["data"]["Events"][0]  # Get the first event of the day
        history_info = {
            'year': event['year'],
            'text': event['text'],
            'link': event['links'][0]['link'] if event['links'] else None
        }

        return jsonify(history_info)
    except Exception as e:
        return jsonify({'error': str(e)})
events = []  # This is temporary and will reset on server restart

@app.route('/api/calendar-events', methods=['GET'])
def get_calendar_events():
    return jsonify(events)

@app.route('/api/calendar-events', methods=['POST'])
def save_event():
    data = request.json
    data['id'] = str(uuid.uuid4())  # Assign a unique ID
    events.append(data)
    return jsonify(data)
@app.route('/about')
def about():
    return render_template('home.html')



if __name__ == '__main__':

    app.run(debug=True, ssl_context=('mycertificate.crt', 'myprivatekey.pem'))


