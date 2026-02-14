#!/usr/bin/env python3
"""
Flask web server for Smart File Organizer AI
"""

import os
import json
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from smart_file_organizer import Config, FileOrganizer, AnalysisCache, load_config

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
app.config['UPLOAD_FOLDER'] = Path.home() / '.config' / 'smart-file-organizer' / 'uploads'
app.config['UPLOAD_FOLDER'].mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {
    'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp',
    'mp3', 'wav', 'flac', 'm4a', 'ogg',
    'mp4', 'mov', 'avi', 'webm',
    'doc', 'docx', 'md', 'py', 'js', 'java', 'cpp'
}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    """Serve the web interface"""
    return send_from_directory('.', 'web_interface.html')


@app.route('/api/upload', methods=['POST'])
def upload_files():
    """Handle file uploads"""
    if 'files[]' not in request.files:
        return jsonify({'error': 'No files provided'}), 400
    
    files = request.files.getlist('files[]')
    uploaded_files = []
    
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = app.config['UPLOAD_FOLDER'] / filename
            file.save(filepath)
            uploaded_files.append({
                'name': filename,
                'path': str(filepath),
                'size': filepath.stat().st_size
            })
    
    return jsonify({'files': uploaded_files})


@app.route('/api/process', methods=['POST'])
def process_files():
    """Process uploaded files"""
    data = request.json
    
    # Get configuration from request
    config = load_config()
    config.use_local = data.get('model') == 'ollama'
    config.rename_files = data.get('rename', False)
    config.embed_metadata = data.get('embed_metadata', True)
    config.create_json_sidecar = data.get('create_sidecar', True)
    config.dry_run = data.get('dry_run', False)
    
    # Get file paths
    file_paths = [Path(f['path']) for f in data.get('files', [])]
    
    if not file_paths:
        return jsonify({'error': 'No files to process'}), 400
    
    # Process files
    organizer = FileOrganizer(config)
    
    try:
        results = []
        for file_path in file_paths:
            if file_path.exists():
                result = organizer.process_file(file_path)
                results.append(result)
        
        organizer.cleanup()
        
        return jsonify({'results': results})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    config = load_config()
    return jsonify({
        'model': config.model,
        'ollama_model': config.ollama_model,
        'use_local': config.use_local,
        'cache_enabled': config.cache_enabled,
        'allowed_categories': config.allowed_categories,
        'allowed_tags': config.allowed_tags
    })


@app.route('/api/cleanup', methods=['POST'])
def cleanup_uploads():
    """Clean up uploaded files"""
    try:
        for file in app.config['UPLOAD_FOLDER'].glob('*'):
            if file.is_file():
                file.unlink()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("=" * 60)
    print("Smart File Organizer AI - Web Server")
    print("=" * 60)
    print("Server running at: http://localhost:5000")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)
