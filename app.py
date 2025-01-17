from flask import Flask, request, jsonify, render_template, redirect
from functools import wraps
import firebase_admin
from firebase_admin import credentials, firestore, auth
import os
from dotenv import load_dotenv
import string
import random
import pyshorteners
from datetime import datetime, timedelta

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
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')

# Initialize Firebase
try:
    app = firebase_admin.get_app()
except ValueError:
    private_key = os.getenv('FIREBASE_PRIVATE_KEY')
    if private_key.startswith('"') and private_key.endswith('"'):
        private_key = private_key[1:-1]  # Remove surrounding quotes
    
    cred = credentials.Certificate({
        "type": os.getenv('FIREBASE_TYPE'),
        "project_id": os.getenv('FIREBASE_PROJECT_ID'),
        "private_key_id": os.getenv('FIREBASE_PRIVATE_KEY_ID'),
        "private_key": private_key,
        "client_email": os.getenv('FIREBASE_CLIENT_EMAIL'),
        "client_id": os.getenv('FIREBASE_CLIENT_ID'),
        "auth_uri": os.getenv('FIREBASE_AUTH_URI'),
        "token_uri": os.getenv('FIREBASE_TOKEN_URI'),
        "auth_provider_x509_cert_url": os.getenv('FIREBASE_AUTH_PROVIDER_CERT_URL'),
        "client_x509_cert_url": os.getenv('FIREBASE_CLIENT_CERT_URL')
    })

    firebase_admin.initialize_app(cred)

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
        return None

def get_firebase_config():
    """Get Firebase configuration for frontend."""
    return {
        'FIREBASE_API_KEY': os.getenv('FIREBASE_API_KEY'),
        'FIREBASE_AUTH_DOMAIN': os.getenv('FIREBASE_AUTH_DOMAIN'),
        'FIREBASE_PROJECT_ID': os.getenv('FIREBASE_PROJECT_ID'),
        'FIREBASE_STORAGE_BUCKET': os.getenv('FIREBASE_STORAGE_BUCKET'),
        'FIREBASE_MESSAGING_SENDER_ID': os.getenv('FIREBASE_MESSAGING_SENDER_ID'),
        'FIREBASE_APP_ID': os.getenv('FIREBASE_APP_ID')
    }

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            if not request.headers.get('Authorization'):
                return jsonify({'error': 'No authorization header'}), 401

            token = request.headers['Authorization'].split('Bearer ')[1]
            decoded_token = auth.verify_id_token(token)
            request.user = decoded_token
            request.user_id = decoded_token.get('uid')
            return f(*args, **kwargs)
        except Exception as e:
            return jsonify({'error': 'Unauthorized'}), 401
    return decorated_function

@app.route('/login')
def login():
    """Render the login page."""
    firebase_config = get_firebase_config()
    return render_template('login.html', firebase_config=firebase_config)

@app.route('/')
def index():
    """Render the main page."""
    firebase_config = get_firebase_config()
    return render_template('index.html', firebase_config=firebase_config)

@app.route('/api/links', methods=['GET'])
@require_auth
def get_user_links():
    try:
        links_ref = db.collection('urls').where('created_by.uid', '==', request.user['uid'])
        links = []
        
        for doc in links_ref.stream():
            link_data = doc.to_dict()
            link_data['id'] = doc.id
            links.append(link_data)
        
        return jsonify({'links': links}), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch links'}), 500

@app.route('/api/delete_link', methods=['POST'])
@require_auth
def delete_link():
    try:
        data = request.get_json()
        link_id = data.get('link_id')
        
        if not link_id:
            return jsonify({'error': 'Link ID is required'}), 400

        link_ref = db.collection('urls').document(link_id)
        link = link_ref.get()
        
        if not link.exists:
            return jsonify({'error': 'Link not found'}), 404
            
        link_data = link.to_dict()
        if link_data.get('created_by', {}).get('uid') != request.user['uid']:
            return jsonify({'error': 'Unauthorized'}), 403

        link_ref.delete()
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'error': 'Failed to delete link'}), 500

@app.route('/shorten', methods=['POST'])
@require_auth
def shorten_url():
    try:
        data = request.get_json()
        long_url = data.get('url')
        expiry_days = data.get('expiry_days', 7)  # Default to 7 days if not specified
        
        if not long_url:
            return jsonify({'error': 'URL is required'}), 400

        # Generate short URL
        doc_ref = db.collection('urls').document()
        short_id = doc_ref.id[:8]  # Use first 8 chars of the document ID
        
        expires_at = datetime.now() + timedelta(days=expiry_days)
        
        url_data = {
            'long_url': long_url,
            'created_at': datetime.now(),
            'expires_at': expires_at,
            'created_by': {
                'uid': request.user['uid'],
                'email': request.user.get('email')
            },
            'visits': 0
        }
        
        doc_ref.set(url_data)
        
        return jsonify({
            'short_url': f"{request.host_url}{short_id}",
            'expires_at': expires_at
        }), 201
    except Exception as e:
        return jsonify({'error': 'Failed to create short URL'}), 500

@app.route('/<short_id>')
def redirect_to_url(short_id):
    try:
        # Query the URL from Firestore
        url_ref = db.collection('urls').document(short_id[:8])
        url_doc = url_ref.get()
        
        if not url_doc.exists:
            return render_template('error.html', message="This link doesn't exist"), 404
            
        url_data = url_doc.to_dict()
        
        # Check if URL has expired
        if url_data.get('expires_at') and datetime.now() > url_data['expires_at']:
            return render_template('error.html', message="This link has expired"), 410
            
        # Update visit count
        url_ref.update({
            'visits': firestore.Increment(1),
            'last_visited': datetime.now()
        })
        
        return redirect(url_data['long_url'])
    except Exception as e:
        return render_template('error.html', message="An error occurred"), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
