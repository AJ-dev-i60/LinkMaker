# LinkMaker - URL Shortener

A modern URL shortening service built with Flask and Firebase, featuring Nginx integration for URL redirection.

## Features
- Custom URL shortening
- Firebase integration for URL storage
- Nginx redirection
- Integration with external URL shortening services (TinyURL, etc.)
- Error handling for invalid short URLs

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure Firebase:
- Create a Firebase project
- Download your Firebase service account key and save it as `firebase-credentials.json`
- Update the `.env` file with your Firebase configuration

3. Configure Nginx:
- Install Nginx
- Copy the provided nginx.conf to your Nginx configuration directory
- Restart Nginx

4. Run the application:
```bash
python app.py
```

## Security Setup

1. Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

2. Update `.env` with your Firebase credentials:
   - Get your Firebase service account key from Firebase Console
   - Fill in all the environment variables in `.env`
   - Never commit `.env` file to version control

3. Security Best Practices:
   - Keep your `.env` file secure and never share it
   - Use different Firebase projects for development and production
   - Regularly rotate your Firebase private keys
   - Monitor your Firebase usage and set up appropriate security rules

## Environment Variables
Create a `.env` file with the following variables:
```
FIREBASE_CREDENTIALS_PATH=firebase-credentials.json
BASE_URL=http://your-domain.com
```

## Development Setup
