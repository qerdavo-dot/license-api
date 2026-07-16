from flask import Flask, request, jsonify, send_from_directory
import os, time

app = Flask(__name__)
UPLOAD_FOLDER = '/tmp/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No filename'}), 400
    filename = str(int(time.time())) + '_' + file.filename
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)
    url = f"https://{request.host}/download/{filename}"
    return jsonify({'url': url, 'filename': filename})

@app.route('/download/<filename>')
def download(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
