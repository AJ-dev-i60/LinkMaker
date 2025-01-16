from flask import Flask, request, jsonify, render_template, redirect
from functools import wraps
import firebase_admin
from firebase_admin import credentials, firestore, auth
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
        app.logger.error(f"Error shortening URL with {service}: {str(e)}")
        return None

def get_firebase_config():
    return {
        'apiKey': os.getenv('FIREBASE_API_KEY'),
        'authDomain': os.getenv('FIREBASE_AUTH_DOMAIN'),
        'projectId': os.getenv('FIREBASE_PROJECT_ID'),
        'appId': os.getenv('FIREBASE_APP_ID')
    }

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        app.logger.info('Starting authentication check')
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            app.logger.error('No Authorization header found')
            return jsonify({'error': 'No token provided'}), 401
            
        if not auth_header.startswith('Bearer '):
            app.logger.error('Authorization header does not start with Bearer')
            return jsonify({'error': 'Invalid token format'}), 401
        
        id_token = auth_header.split('Bearer ')[1]
        app.logger.info(f'Got token from header (length: {len(id_token)})')
        
        try:
            app.logger.info('Verifying token...')
            # Get current server time
            current_time = datetime.now()
            app.logger.info(f'Current server time: {current_time.isoformat()}')
            
            decoded_token = auth.verify_id_token(id_token)
            token_issued_at = datetime.fromtimestamp(decoded_token['iat'])
            token_expires_at = datetime.fromtimestamp(decoded_token['exp'])
            app.logger.info(f'Token issued at: {token_issued_at.isoformat()}')
            app.logger.info(f'Token expires at: {token_expires_at.isoformat()}')
            
            request.user = decoded_token
            app.logger.info(f'Token verified for user: {decoded_token.get("email", "unknown")}')
            return f(*args, **kwargs)
        except Exception as e:
            app.logger.error(f'Authentication error: {str(e)}')
            return jsonify({'error': str(e)}), 401
    return decorated_function

@app.route('/login')
def login():
    return render_template('login.html',
                         firebase_api_key=os.getenv('FIREBASE_API_KEY'),
                         firebase_auth_domain=os.getenv('FIREBASE_AUTH_DOMAIN'),
                         firebase_project_id=os.getenv('FIREBASE_PROJECT_ID'),
                         firebase_app_id=os.getenv('FIREBASE_APP_ID'))

@app.route('/')
def index():
    return render_template('index.html', firebase_config=get_firebase_config())

@app.route('/shorten', methods=['POST'])
@require_auth
def shorten_url():
    data = request.get_json()
    long_url = data.get('url')
    service = data.get('service', 'custom')
    expiry = data.get('expiry')
    
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

    # Calculate expiry time if provided
    expires_at = None
    if expiry:
        try:
            # Parse the expiry string (e.g., "30 minutes" or "2 hours")
            value, unit = expiry.split()
            value = int(value)
            now = datetime.now()
            
            if 'minute' in unit:
                expires_at = now.replace(minute=now.minute + value)
            elif 'hour' in unit:
                expires_at = now.replace(hour=now.hour + value)
            elif 'day' in unit:
                expires_at = now.replace(day=now.day + value)
            elif 'week' in unit:
                expires_at = now.replace(day=now.day + (value * 7))
            
            expires_at = expires_at.isoformat()
        except Exception as e:
            app.logger.error(f"Error parsing expiry time: {str(e)}")
            return jsonify({'error': 'Invalid expiry format'}), 400

    # Store in Firebase with user information and expiry
    doc_data = {
        'long_url': long_url,
        'created_at': datetime.now().isoformat(),
        'visits': 0,
        'service': 'custom',
        'created_by': {
            'uid': request.user['uid'],
            'email': request.user['email'],
            'display_name': request.user.get('name', ''),
        },
        'last_visited': None,
        'expires_at': expires_at
    }

    doc_ref.set(doc_data)

    shortened_url = f"{base_url}/{short_code}"
    return jsonify({'shortened_url': shortened_url})

@app.route('/<short_code>')
def redirect_url(short_code):
    try:
        doc_ref = db.collection('urls').document(short_code)
        doc = doc_ref.get()
        
        if not doc.exists:
            return render_template('invalid_link.html', firebase_config=get_firebase_config())
        
        url_data = doc.to_dict()

        # Check if link has expired
        expires_at = url_data.get('expires_at')
        if expires_at and expires_at != 'never':
            try:
                expiry_time = datetime.fromisoformat(expires_at)
                if datetime.now() > expiry_time:
                    return render_template('invalid_link.html', 
                                         firebase_config=get_firebase_config(), 
                                         message="This link has expired")
            except ValueError as e:
                app.logger.error(f"Error parsing expiry time: {str(e)}")
                # Continue with redirect even if expiry time is invalid
        
        # Update visit count and last visited timestamp
        doc_ref.update({
            'visits': firestore.Increment(1),
            'last_visited': datetime.now().isoformat()
        })
        
        return redirect(url_data['long_url'])
    except Exception as e:
        app.logger.error(f"Error redirecting URL: {str(e)}")
        return render_template('invalid_link.html', 
                             firebase_config=get_firebase_config(),
                             message="An error occurred while processing this link")

@app.route('/api/my-links', methods=['GET'])
@require_auth
def get_user_links():
    try:
        app.logger.info(f'Fetching links for user: {request.user.get("email", "unknown")}')
        # Query links created by the current user
        links = db.collection('urls')\
            .where('created_by.uid', '==', request.user['uid'])\
            .order_by('created_at', direction=firestore.Query.DESCENDING)\
            .stream()

        links_data = []
        now = datetime.now()
        
        for link in links:
            data = link.to_dict()
            app.logger.debug(f'Processing link: {link.id}')
            expires_at = data.get('expires_at')
            is_expired = False
            
            if expires_at:
                expiry_time = datetime.fromisoformat(expires_at)
                is_expired = now > expiry_time

            links_data.append({
                'id': link.id,
                'short_url': f"{base_url}/{link.id}",
                'long_url': data['long_url'],
                'visits': data['visits'],
                'created_at': data['created_at'],
                'last_visited': data['last_visited'] or 'Never',
                'expires_at': expires_at,
                'is_expired': is_expired
            })

        app.logger.info(f'Successfully fetched {len(links_data)} links')
        return jsonify(links_data)
    except Exception as e:
        app.logger.error(f"Error fetching user links: {str(e)}")
        return jsonify({'error': f'Failed to fetch links: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
