# [Keep your existing imports]
import threading
import time
# ... other imports remain unchanged

# [Your .env, Flask setup remains unchanged]

@app.route('/')
def index():
    if 'credentials' not in session:
        return redirect(url_for('authorize'))
    return '''
<html>
<head>
    <title>Drive Copier</title>
    <script>
        function checkStatus() {
            fetch('/status')
                .then(response => response.json())
                .then(data => {
                    const status = document.getElementById("status");
                    if (data.status === "done") {
                        status.innerHTML = "<h3>✅ Folder copied successfully to your Drive!</h3>";
                    } else if (data.status === "error") {
                        status.innerHTML = "<p>❌ Error: " + data.message + "</p>";
                    } else {
                        setTimeout(checkStatus, 2000); // poll again
                    }
                });
        }
    </script>
    <style>
        /* [same CSS styles as before] */
    </style>
</head>
<body>
    <div class="container">
        <h2>Google Drive Folder Copier</h2>
        <form action="/copy" method="post" onsubmit="document.getElementById('status').innerHTML = '<p>🔄 Copying in progress...</p><p>Please wait...</p>'; setTimeout(checkStatus, 2000);">
            <label>Paste Source Folder Link or ID:</label>
            <input name="src_folder" type="text" required>
            <button type="submit">Copy to My Drive</button>
        </form>
        <div id="status" style="margin-top: 20px;"></div>
    </div>

    <div class="footer">
        <h1>Created By Mr Shah</h1>
        <img src="https://skillspectrum.vercel.app/Hamza.jpg" alt="Mr Shah">
    </div>
</body>
</html>
    '''

@app.route('/status')
def status():
    return {
        "status": session.get("copy_status", "idle"),
        "message": session.get("copy_message", "")
    }

@app.route('/copy', methods=['POST'])
def copy():
    if 'credentials' not in session:
        return redirect(url_for('authorize'))

    session['copy_status'] = 'in_progress'
    session['copy_message'] = ''

    credentials = Credentials(**session['credentials'])
    drive = build('drive', 'v3', credentials=credentials)
    src_id = extract_folder_id(request.form['src_folder'])

    # Run in background to not block request
    threading.Thread(target=start_copy, args=(drive, src_id)).start()

    return '''
        <p>🔄 Copying in progress... Please wait...</p>
        <script>setTimeout(() => checkStatus(), 2000);</script>
    '''

def start_copy(drive, src_id):
    try:
        copy_folder_contents(drive, drive, src_id, 'root')
        session['copy_status'] = 'done'
    except Exception as e:
        session['copy_status'] = 'error'
        session['copy_message'] = str(e)

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
    items = []
    page_token = None

    while True:
        response = src_service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=page_token
        ).execute()
        items.extend(response.get('files', []))
        page_token = response.get('nextPageToken')
        if not page_token:
            break

    for item in items:
        if item['mimeType'] == 'application/vnd.google-apps.folder':
            copy_folder_contents(src_service, dst_service, item['id'], dst_folder_id)
        else:
            file_metadata = {
                'name': item['name'],
                'parents': [dst_folder_id]
            }
            dst_service.files().copy(fileId=item['id'], body=file_metadata).execute()

def extract_folder_id(link_or_id):
    match = re.search(r'/folders/([a-zA-Z0-9_-]+)', link_or_id)
    return match.group(1) if match else link_or_id.strip()

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
