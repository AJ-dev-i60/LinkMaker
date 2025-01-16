from flask import Flask, request, jsonify, render_template, redirect
import firebase_admin
from firebase_admin import credentials, firestore
import os
from dotenv import load_dotenv
import string
import random
import pyshorteners
from datetime import datetime

# Load environment variables
load_dotenv()

# Set environment-specific base URL
FLASK_ENV = os.getenv('FLASK_ENV', 'development')
if FLASK_ENV == 'development':
    base_url = 'http://localhost:5000'
else:
    base_url = 'https://s.i60.co.za'

# Remove trailing slash if present
if base_url.endswith('/'):
    base_url = base_url.rstrip('/')

app = Flask(__name__)

# Initialize Firebase
cred = credentials.Certificate({
    "type": os.getenv('FIREBASE_TYPE'),
    "project_id": os.getenv('FIREBASE_PROJECT_ID'),
    "private_key_id": os.getenv('FIREBASE_PRIVATE_KEY_ID'),
    "private_key": os.getenv('FIREBASE_PRIVATE_KEY').replace('\\n', '\n') if os.getenv('FIREBASE_PRIVATE_KEY') else None,
    "client_email": os.getenv('FIREBASE_CLIENT_EMAIL'),
    "client_id": os.getenv('FIREBASE_CLIENT_ID'),
    "auth_uri": os.getenv('FIREBASE_AUTH_URI'),
    "token_uri": os.getenv('FIREBASE_TOKEN_URI'),
    "auth_provider_x509_cert_url": os.getenv('FIREBASE_AUTH_PROVIDER_CERT_URL'),
    "client_x509_cert_url": os.getenv('FIREBASE_CLIENT_CERT_URL')
})

firebase_admin.initialize_app(cred, {
    'projectId': os.getenv('FIREBASE_PROJECT_ID'),
    'storageBucket': f"{os.getenv('FIREBASE_PROJECT_ID')}.firebasestorage.app"
})
db = firestore.client()

def generate_short_code(length=6):
    """Generate a random short code for URLs"""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def use_external_shortener(url, service='tinyurl'):
    """Use external URL shortening service"""
    try:
        if service == 'tinyurl':
            s = pyshorteners.Shortener(api_key=os.getenv('TINYURL_API_TOKEN'))
            return s.tinyurl.short(url)
        elif service == 'isgd':
            s = pyshorteners.Shortener()
            return s.isgd.short(url)
        elif service == 'bitly':
            # Requires API key, will be implemented later
            raise NotImplementedError("Bitly support coming soon")
        else:
            raise ValueError(f"Unsupported service: {service}")
    except Exception as e:
        app.logger.error(f"Error shortening URL with {service}: {str(e)}")
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/shorten', methods=['POST'])
def shorten_url():
    data = request.get_json()
    long_url = data.get('url')
    service = data.get('service', 'custom')
    
    if not long_url:
        return jsonify({'error': 'URL is required'}), 400

    if service != 'custom':
        shortened_url = use_external_shortener(long_url, service)
        if shortened_url is None:
            return jsonify({'error': f'Failed to shorten URL using {service}'}), 500
        return jsonify({'shortened_url': shortened_url})

    # Generate a unique short code
    while True:
        short_code = generate_short_code()
        doc_ref = db.collection('urls').document(short_code)
        if not doc_ref.get().exists:
            break

    # Store in Firebase
    doc_ref.set({
        'long_url': long_url,
        'created_at': datetime.now().isoformat(),
        'visits': 0,
        'service': 'custom'
    })

    shortened_url = f"{base_url}/{short_code}"
    return jsonify({'shortened_url': shortened_url})

@app.route('/<short_code>')
def redirect_url(short_code):
    doc_ref = db.collection('urls').document(short_code)
    doc = doc_ref.get()
    
    if not doc.exists:
        return render_template('error.html', message='Link not found'), 404

    # Update visit count
    doc_ref.update({'visits': firestore.Increment(1)})
    
    # Redirect to the original URL
    return redirect(doc.to_dict()['long_url'])

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
