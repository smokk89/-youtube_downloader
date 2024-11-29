from flask import Flask, render_template, request, send_file, jsonify, Response
import yt_dlp
import os
import re
import certifi
import unicodedata
import string
import shutil
from datetime import datetime
import tempfile
import requests

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit
app.config['DOWNLOAD_FOLDER'] = tempfile.gettempdir() if os.environ.get('VERCEL') else 'downloads'

def is_valid_youtube_url(url):
    youtube_regex = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    return bool(re.match(youtube_regex, url))

def sanitize_filename(filename):
    # Remove invalid characters
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    filename = ''.join(c for c in filename if c in valid_chars)
    # Remove any leading/trailing spaces or dots
    filename = filename.strip('. ')
    return filename if filename else 'video'

def get_video_id(url):
    # Extract video ID from URL
    pattern = r'(?:v=|\/)([0-9A-Za-z_-]{11}).*'
    match = re.search(pattern, url)
    return match.group(1) if match else None

def clear_old_downloads(download_path, keep_minutes=30):
    """Clear downloads older than keep_minutes"""
    if not os.path.exists(download_path):
        return
        
    current_time = datetime.now()
    for filename in os.listdir(download_path):
        filepath = os.path.join(download_path, filename)
        file_modified_time = datetime.fromtimestamp(os.path.getmtime(filepath))
        age_minutes = (current_time - file_modified_time).total_seconds() / 60
        
        if age_minutes > keep_minutes:
            try:
                os.remove(filepath)
                print(f"Removed old file: {filepath}")
            except Exception as e:
                print(f"Error removing file {filepath}: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download_video():
    try:
        url = request.form.get('url')
        if not url:
            return jsonify({'error': 'No URL provided'}), 400
            
        if not is_valid_youtube_url(url):
            return jsonify({'error': 'Invalid YouTube URL'}), 400

        ydl_opts = {
            'format': 'best',
            'quiet': False,
            'no_warnings': False,
            'nocheckcertificate': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Get video info first
            info = ydl.extract_info(url, download=False)
            video_url = info['url']
            video_title = info['title']
            video_ext = info['ext']
            
            # Create a safe filename
            safe_title = sanitize_filename(video_title)
            filename = f"{safe_title}.{video_ext}"
            
            # Get the video stream
            response = requests.get(video_url, stream=True, headers=ydl_opts['http_headers'])
            
            # Create Flask response with streaming
            def generate():
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk

            # Create response with proper headers for download
            flask_response = Response(
                generate(),
                content_type=response.headers.get('content-type', 'video/mp4')
            )
            
            # Add headers to force download
            flask_response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            flask_response.headers['Content-Length'] = response.headers.get('content-length')
            flask_response.headers['Accept-Ranges'] = 'bytes'
            flask_response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            flask_response.headers['Pragma'] = 'no-cache'
            flask_response.headers['Expires'] = '0'
            
            return flask_response

    except Exception as e:
        app.logger.error(f"Error downloading video: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Use environment variable for port if available (for production)
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
