import os
import re
from flask import Flask, redirect, request, session, url_for
from flask_session import Session
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# Flask-Session config
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
Session(app)

# Allow HTTP for local testing only (disable in production!)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

SCOPES = ['https://www.googleapis.com/auth/drive']
REDIRECT_URI = os.getenv("REDIRECT_URI")  # Use env variable

def build_flow():
    return Flow.from_client_config(
        {
            "web": {
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "project_id": os.getenv("GOOGLE_PROJECT_ID"),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "redirect_uris": [REDIRECT_URI]
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

@app.route('/')
def index():
    if 'credentials' not in session:
        return redirect(url_for('authorize'))
    return '''
<html>
<head>
    <title>Drive Copier</title>
    <style>
        body {
            font-family: 'Segoe UI', sans-serif;
            background: #f5f8fd;
            color: #333;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }

        .container {
            background: white;
            padding: 30px 40px;
            border-radius: 12px;
            box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
            width: 500px;
            text-align: center;
        }

        h2 {
            margin-bottom: 20px;
            color: #1a73e8;
        }

        label {
            font-weight: 500;
            display: block;
            margin-bottom: 8px;
            text-align: left;
        }

        input[type="text"] {
            width: 100%;
            padding: 10px 14px;
            border-radius: 6px;
            border: 1px solid #ccc;
            font-size: 15px;
            margin-bottom: 20px;
            box-sizing: border-box;
        }

        button {
            background: #1a73e8;
            color: white;
            padding: 12px 20px;
            font-size: 16px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            transition: background 0.3s ease;
        }

        button:hover {
            background: #155ac6;
        }

        .footer {
            margin-top: 30px;
            text-align: center;
        }

        .footer img {
            width: 300px;
            border-radius: 50%;
            margin-top: 10px;
            height:300px;
        }

        .footer h1 {
            font-size: 20px;
            color: #444;
            margin: 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <h2>Google Drive Folder Copier</h2>
        <form action="/copy" method="post">
            <label>Paste Source Folder Link or ID:</label>
            <input name="src_folder" type="text">
            <button type="submit">Copy to My Drive</button>
        </form>
    </div>

    <div class="footer">
        <h1>Created By Mr Shah</h1>
        <img src="https://skillspectrum.vercel.app/Hamza.jpg" alt="Mr Shah">
    </div>
</body>
</html>
    '''

@app.route('/authorize')
def authorize():
    flow = build_flow()
    auth_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    session['state'] = state
    return redirect(auth_url)

@app.route('/oauth2callback')
def oauth2callback():
    if 'state' not in session:
        return "Session expired. <a href='/'>Try again</a>.", 400

    flow = build_flow()
    flow.fetch_token(authorization_response=request.url)
    session['credentials'] = credentials_to_dict(flow.credentials)
    return redirect(url_for('index'))

@app.route('/copy', methods=['POST'])
def copy():
    if 'credentials' not in session:
        return redirect(url_for('authorize'))

    credentials = Credentials(**session['credentials'])
    drive = build('drive', 'v3', credentials=credentials)

    src_id = extract_folder_id(request.form['src_folder'])

    try:
        copy_folder_contents(drive, drive, src_id, 'root')
        return "<h3>✅ Folder copied successfully to your Drive!</h3>"
    except Exception as e:
        return f"<p>❌ Error: {e}</p>", 500

def extract_folder_id(link_or_id):
    match = re.search(r'/folders/([a-zA-Z0-9_-]+)', link_or_id)
    return match.group(1) if match else link_or_id.strip()

def copy_folder_contents(src_service, dst_service, src_folder_id, dst_parent_id):
    folder_meta = src_service.files().get(fileId=src_folder_id, fields='name').execute()
    dst_folder_metadata = {
        'name': folder_meta['name'],
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [dst_parent_id]
    }
    dst_folder = dst_service.files().create(body=dst_folder_metadata, fields='id').execute()
    dst_folder_id = dst_folder['id']

    query = f"'{src_folder_id}' in parents and trashed = false"
    items = src_service.files().list(q=query, fields="files(id, name, mimeType)").execute().get('files', [])

    for item in items:
        if item['mimeType'] == 'application/vnd.google-apps.folder':
            copy_folder_contents(src_service, dst_service, item['id'], dst_folder_id)
        else:
            file_metadata = {
                'name': item['name'],
                'parents': [dst_folder_id]
            }
            dst_service.files().copy(fileId=item['id'], body=file_metadata).execute()

def credentials_to_dict(credentials):
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

if __name__ == '__main__':
    app.run(debug=True)
