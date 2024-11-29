from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import os
import re
import certifi
import unicodedata
import string
import shutil
from datetime import datetime

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit

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
        url = request.form['url']
        
        if not is_valid_youtube_url(url):
            return jsonify({'error': 'Invalid YouTube URL'}), 400

        # Create downloads directory in the same folder as app.py
        download_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads')
        os.makedirs(download_path, exist_ok=True)
        
        # Clear old downloads
        clear_old_downloads(download_path)
        
        # Get video ID and create a unique directory for this download
        video_id = get_video_id(url)
        if not video_id:
            return jsonify({'error': 'Could not extract video ID from URL'}), 400
            
        # Create a unique download directory for this video
        video_download_path = os.path.join(download_path, video_id)
        if os.path.exists(video_download_path):
            shutil.rmtree(video_download_path)  # Remove existing directory and its contents
        os.makedirs(video_download_path)

        # Clear any existing downloads for this video
        for file in os.listdir(download_path):
            if file.startswith(video_id):
                file_path = os.path.join(download_path, file)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print(f"Error removing file {file_path}: {e}")

        ydl_opts = {
            'format': 'best',
            'outtmpl': os.path.join(video_download_path, '%(title)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'socket_timeout': 30,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            },
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'nocheckcertificate': True,  # Add this if you encounter SSL issues
            'force_generic_extractor': False
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                # Force cache clearing
                ydl.cache.remove()
                
                print(f"Extracting info for: {url}")
                info = ydl.extract_info(url, download=True)
                
                if not info:
                    raise Exception("Failed to extract video information")
                
                # Get the downloaded file
                files = os.listdir(video_download_path)
                if not files:
                    raise Exception("No files were downloaded")
                
                # Get the first (and should be only) file
                filename = files[0]
                filepath = os.path.join(video_download_path, filename)
                
                if not os.path.exists(filepath):
                    raise Exception("Downloaded file not found")
                
                print(f"Sending file: {filepath}")
                response = send_file(
                    filepath,
                    as_attachment=True,
                    download_name=filename,
                    mimetype='video/mp4'
                )
                
                # Add headers to prevent caching
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
                
                return response
                
            except Exception as e:
                print(f"Inner error: {str(e)}")
                raise e

    except Exception as e:
        error_msg = str(e)
        print(f"Error downloading video: {error_msg}")
        return jsonify({'error': f'Failed to download video: {error_msg}'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=8000)
