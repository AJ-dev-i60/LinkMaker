import requests
import time
import json
import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, auth
import pyrebase

# Load environment variables
load_dotenv()

def get_firebase_config():
    return {
        'apiKey': os.getenv('FIREBASE_API_KEY'),
        'authDomain': os.getenv('FIREBASE_AUTH_DOMAIN'),
        'projectId': os.getenv('FIREBASE_PROJECT_ID'),
        'storageBucket': f"{os.getenv('FIREBASE_PROJECT_ID')}.appspot.com",
        'messagingSenderId': os.getenv('FIREBASE_MESSAGING_SENDER_ID'),
        'appId': os.getenv('FIREBASE_APP_ID')
    }

def initialize_firebase_admin():
    try:
        app = firebase_admin.get_app()
    except ValueError:
        cred = credentials.Certificate({
            "type": os.getenv('FIREBASE_TYPE'),
            "project_id": os.getenv('FIREBASE_PROJECT_ID'),
            "private_key_id": os.getenv('FIREBASE_PRIVATE_KEY_ID'),
            "private_key": os.getenv('FIREBASE_PRIVATE_KEY').replace('\\n', '\n'),
            "client_email": os.getenv('FIREBASE_CLIENT_EMAIL'),
            "client_id": os.getenv('FIREBASE_CLIENT_ID'),
            "auth_uri": os.getenv('FIREBASE_AUTH_URI'),
            "token_uri": os.getenv('FIREBASE_TOKEN_URI'),
            "auth_provider_x509_cert_url": os.getenv('FIREBASE_AUTH_PROVIDER_CERT_URL'),
            "client_x509_cert_url": os.getenv('FIREBASE_CLIENT_CERT_URL')
        })
        firebase_admin.initialize_app(cred)

def test_auth_and_table_load():
    # Initialize Firebase Admin
    initialize_firebase_admin()
    
    # Initialize Pyrebase for client-side auth
    firebase = pyrebase.initialize_app(get_firebase_config())
    
    # Sign in with test credentials
    email = os.getenv('TEST_USER_EMAIL')
    password = os.getenv('TEST_USER_PASSWORD')
    
    try:
        # Sign in
        user = firebase.auth().sign_in_with_email_and_password(email, password)
        print("✓ Successfully signed in")
        
        # Get ID token
        id_token = user['idToken']
        
        # Test /api/my-links endpoint
        headers = {
            'Authorization': f'Bearer {id_token}'
        }
        
        # Make multiple requests to simulate page refreshes
        for i in range(5):
            print(f"\nTest {i+1}:")
            
            response = requests.get('http://localhost:5000/api/my-links', headers=headers)
            
            print(f"Status Code: {response.status_code}")
            if response.status_code == 200:
                links = response.json()
                print(f"✓ Successfully fetched {len(links)} links")
            else:
                print(f"✗ Failed to fetch links: {response.text}")
            
            # Small delay between requests
            time.sleep(1)
            
    except Exception as e:
        print(f"✗ Error during test: {str(e)}")

if __name__ == "__main__":
    test_auth_and_table_load()
