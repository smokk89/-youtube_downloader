import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from flask import Flask, render_template, request, send_file, jsonify, Response
from pytube import YouTube
import os
import re
import string
from datetime import datetime
import certifi
import unicodedata
import tempfile
import requests
import shutil

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

        try:
            # Create YouTube object
            yt = YouTube(url)
            
            # Get the highest resolution stream
            video = yt.streams.get_highest_resolution()
            
            if not video:
                return jsonify({'error': 'No suitable video stream found'}), 400

            # Get video info
            video_title = yt.title
            video_ext = 'mp4'  # pytube downloads in MP4 format
            
            # Create a safe filename
            safe_title = sanitize_filename(video_title)
            filename = f"{safe_title}.{video_ext}"
            
            # Stream the video
            def generate():
                stream_url = video.url
                with requests.get(stream_url, stream=True) as r:
                    r.raise_for_status()
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            yield chunk

            # Create response with proper headers
            response = Response(
                generate(),
                mimetype='video/mp4',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}"',
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                }
            )
            return response

        except Exception as e:
            app.logger.error(f"Error processing video: {str(e)}")
            return jsonify({'error': f'Error processing video: {str(e)}'}), 500

    except Exception as e:
        app.logger.error(f"Error downloading video: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Use environment variable for port if available (for production)
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
