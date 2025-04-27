import sys
import os

# Add site-packages to Python path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'site-packages'))

from flask import Flask, render_template, request, send_file, make_response, jsonify
import os
from werkzeug.utils import secure_filename
import io
import time
import zipfile
import base64
import requests
import json

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'webp', 'avif', 'png', 'gif', 'tiff', 'psd', 'svg', 'heic', 'jpeg', 'jpg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def safe_remove(filepath):
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except (PermissionError, OSError):
        # If file is still in use, we'll just leave it for now
        pass

import subprocess

def convert_avif_to_jpg(input_path, output_path):
    # Determine ffmpeg path based on environment
    if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ffmpeg', 'bin', 'ffmpeg.exe')):
        # Local project ffmpeg folder
        ffmpeg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ffmpeg', 'bin', 'ffmpeg.exe')
    elif os.path.exists('/usr/bin/ffmpeg'):
        # Linux/Render.com system ffmpeg
        ffmpeg_path = 'ffmpeg'
    elif os.path.exists('C:\\ffmpeg\\bin\\ffmpeg.exe'):
        # Windows system ffmpeg
        ffmpeg_path = r'C:\ffmpeg\bin\ffmpeg.exe'
    else:
        # Fallback to just 'ffmpeg' and hope it's in PATH
        ffmpeg_path = 'ffmpeg'
    
    print(f"Using ffmpeg path: {ffmpeg_path}")
    
    try:
        result = subprocess.run([
            ffmpeg_path, '-y', '-i', input_path, output_path
        ], capture_output=True)
        if result.returncode == 0:
            return True
        else:
            print(f"ffmpeg error: {result.stderr}")
    except Exception as e:
        print(f"ffmpeg exception: {e}")
    # Fallback to API
    try:
        # Read the input file
        with open(input_path, 'rb') as image_file:
            # Convert the image to base64
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        # API endpoint for image conversion
        api_url = 'https://api.cloudmersive.com/image/convert/to/jpg'
        
        # API key - you'll need to sign up for a free API key at cloudmersive.com
        headers = {
            'Content-Type': 'application/json',
            'Apikey': 'YOUR-API-KEY-HERE'  # Replace with your API key
        }
        
        # Send request to API
        response = requests.post(
            api_url,
            json={"Base64Image": base64_image},
            headers=headers
        )
        
        if response.status_code == 200:
            # Save the converted image
            with open(output_path, 'wb') as f:
                f.write(response.content)
            return True
        return False
    except Exception as e:
        print(f"Error converting image (API fallback): {str(e)}")
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    if 'files[]' not in request.files:
        return jsonify({'error': 'No files uploaded'}), 400
    
    files = request.files.getlist('files[]')
    if not files or files[0].filename == '':
        return jsonify({'error': 'No files selected'}), 400
    
    # Get conversion type
    conversion_type = request.form.get('conversionType', 'allToJpg')
    sort_folders = request.form.get('sortFolders') == 'on'
    print(f"[DEBUG] sortFolders enabled: {sort_folders}")

    # Create a timestamp for this batch
    import datetime
    now = datetime.datetime.now()
    timestamp = now.strftime('%Y-%m-%d_%H-%M-%S')

    # Create a temporary zip file with date and time
    zip_filename = f'converted_{timestamp}.zip'
    zip_path = os.path.join(app.config['UPLOAD_FOLDER'], zip_filename)

    try:
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for file in files:
                if file and allowed_file(file.filename):
                    # Check if we should process this file based on conversion type
                    if conversion_type == 'pngToJpg' and not file.filename.lower().endswith('.png'):
                        continue
                    
                    # Generate unique filenames
                    base_filename, ext = os.path.splitext(secure_filename(file.filename))
                    ext = ext.lower()
                    input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_filename}_{timestamp}_input{ext}")
                    output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_filename}_{timestamp}_output.jpg")
                    
                    try:
                        # Save the uploaded file
                        file.save(input_path)
                        
                        # Decide subfolder if sorting enabled
                        zip_subfolder = ''
                        if sort_folders:
                            # Main: 122902699540481.jpg (no dash before extension)
                            # Additional: 122902699540481-1.jpg, 122902699540481-2.jpg
                            if '-' in base_filename and base_filename.split('-')[-1].isdigit():
                                zip_subfolder = 'Additional/'
                            else:
                                zip_subfolder = 'Main/'
                        print(f"[DEBUG] File: {file.filename}, zip_subfolder: {zip_subfolder}")
                        if ext == '.jpg':
                            # If already JPG, add as-is with original name
                            print(f"[DEBUG] Adding to ZIP: {zip_subfolder + file.filename}")
                            zipf.write(input_path, zip_subfolder + file.filename)
                        else:
                            # Convert to JPG
                            converted = False
                            if ext == '.avif':
                                # AVIF special handling
                                success = convert_avif_to_jpg(input_path, output_path)
                                if success:
                                    converted = True
                                else:
                                    # If AVIF conversion fails, skip
                                    print(f"Failed to convert AVIF: {file.filename}")
                                    continue
                            else:
                                # Use Pillow for all other formats
                                try:
                                    from PIL import Image
                                    im = Image.open(input_path)
                                    rgb_im = im.convert('RGB')
                                    rgb_im.save(output_path, 'JPEG', quality=95)
                                    converted = True
                                except Exception as e:
                                    print(f"Error converting {file.filename}: {e}")
                                    continue  # Skip this file if conversion fails
                            # Add converted file as base_filename.jpg
                            if converted:
                                print(f"[DEBUG] Adding to ZIP: {zip_subfolder + f'{base_filename}.jpg'}")
                                zipf.write(output_path, zip_subfolder + f"{base_filename}.jpg")
                        
                    finally:
                        # Clean up individual files
                        safe_remove(input_path)
                        safe_remove(output_path)
        
        # Read the zip file into memory
        with open(zip_path, 'rb') as f:
            zip_data = f.read()
        
        # Clean up the zip file
        safe_remove(zip_path)
        
        # Convert zip data to base64 for JSON response
        zip_base64 = base64.b64encode(zip_data).decode('utf-8')
        
        return jsonify({
            'success': True,
            'filename': 'converted_images.zip',
            'data': zip_base64
        })
        
    except Exception as e:
        # Clean up in case of error
        safe_remove(zip_path)
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True)
