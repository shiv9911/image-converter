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
    # Check if we're on Render.com (they set this environment variable)
    is_render = os.environ.get('RENDER', '') == 'true'
    
    # Determine ffmpeg path based on environment
    possible_paths = [
        # Project-local ffmpeg (Windows)
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ffmpeg', 'bin', 'ffmpeg.exe'),
        # Standard Linux locations (Render.com)
        '/usr/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
        # Windows system ffmpeg
        r'C:\ffmpeg\bin\ffmpeg.exe',
        # Just the command name (rely on PATH)
        'ffmpeg'
    ]
    
    # Find the first path that exists
    ffmpeg_path = None
    for path in possible_paths:
        # On Render.com, we'll just use 'ffmpeg' directly
        if is_render:
            ffmpeg_path = 'ffmpeg'
            break
        # Otherwise check if the path exists
        if os.path.exists(path):
            ffmpeg_path = path
            break
    
    # If no path was found, default to 'ffmpeg'
    if not ffmpeg_path:
        ffmpeg_path = 'ffmpeg'
    
    print(f"[DEBUG] AVIF Conversion - Using ffmpeg path: {ffmpeg_path}")
    print(f"[DEBUG] AVIF Conversion - Input path: {input_path}")
    print(f"[DEBUG] AVIF Conversion - Output path: {output_path}")
    print(f"[DEBUG] AVIF Conversion - Running on Render.com: {is_render}")
    
    # Check if input file exists and has content
    if not os.path.exists(input_path):
        print(f"[DEBUG] AVIF Conversion - ERROR: Input file does not exist: {input_path}")
        return False
    
    file_size = os.path.getsize(input_path)
    print(f"[DEBUG] AVIF Conversion - Input file size: {file_size} bytes")
    if file_size == 0:
        print(f"[DEBUG] AVIF Conversion - ERROR: Input file is empty")
        return False
    
    # First try: Use ffmpeg directly with full command logging
    try:
        print(f"[DEBUG] AVIF Conversion - Running ffmpeg command")
        
        # Build the command
        cmd = [ffmpeg_path, '-y', '-i', input_path, output_path]
        print(f"[DEBUG] AVIF Conversion - Command: {' '.join(cmd)}")
        
        # Run the command with full output capture
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True)
        if result.returncode == 0:
            print(f"[DEBUG] AVIF Conversion - ffmpeg successful")
            
            # Verify the output file was created and has content
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                print(f"[DEBUG] AVIF Conversion - Output file created successfully: {os.path.getsize(output_path)} bytes")
                return True
            else:
                print(f"[DEBUG] AVIF Conversion - ffmpeg did not create a valid output file")
        else:
            print(f"[DEBUG] AVIF Conversion - ffmpeg error code: {result.returncode}")
            print(f"[DEBUG] AVIF Conversion - ffmpeg stderr: {result.stderr}")
            print(f"[DEBUG] AVIF Conversion - ffmpeg stdout: {result.stdout}")
    except Exception as e:
        print(f"[DEBUG] AVIF Conversion - ffmpeg exception: {e}")
    
    # Second try: Try ffmpeg with different arguments (sometimes helps on Linux)
    try:
        print(f"[DEBUG] AVIF Conversion - Trying alternative ffmpeg command")
        
        # Different command format that sometimes works better on Linux
        alt_cmd = [ffmpeg_path, '-y', '-i', input_path, '-pix_fmt', 'yuv420p', output_path]
        print(f"[DEBUG] AVIF Conversion - Alternative command: {' '.join(alt_cmd)}")
        
        alt_result = subprocess.run(alt_cmd, capture_output=True, text=True)
        
        if alt_result.returncode == 0:
            print(f"[DEBUG] AVIF Conversion - Alternative ffmpeg successful")
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
        else:
            print(f"[DEBUG] AVIF Conversion - Alternative ffmpeg error: {alt_result.stderr}")
    except Exception as e:
        print(f"[DEBUG] AVIF Conversion - Alternative ffmpeg exception: {e}")
    
    # Third try: Use Pillow with AVIF plugin
    try:
        print(f"[DEBUG] AVIF Conversion - Trying Pillow with AVIF plugin")
        from PIL import Image
        import pillow_avif
        
        # Open AVIF image
        img = Image.open(input_path)
        # Convert to RGB (remove alpha channel if present)
        rgb_img = img.convert('RGB')
        # Save as JPEG
        rgb_img.save(output_path, 'JPEG', quality=95)
        print(f"[DEBUG] AVIF Conversion - Pillow successful")
        return True
    except Exception as e:
        print(f"[DEBUG] AVIF Conversion - Pillow exception: {e}")
    
    # Fallback to API
    try:
        print(f"[DEBUG] AVIF Conversion - Trying API fallback")
        # Read the input file
        with open(input_path, 'rb') as image_file:
            # Convert the image to base64
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        # Get API key from environment variable or use default
        api_key = os.environ.get('CLOUDMERSIVE_API_KEY', 'YOUR-API-KEY-HERE')
        
        # API endpoint for image conversion
        api_url = 'https://api.cloudmersive.com/image/convert/to/jpg'
        
        # API key - you'll need to sign up for a free API key at cloudmersive.com
        headers = {
            'Content-Type': 'application/json',
            'Apikey': api_key
        }
        
        print(f"[DEBUG] AVIF Conversion - Sending API request")
        # Send request to API
        response = requests.post(
            api_url,
            json={"Base64Image": base64_image},
            headers=headers
        )
        
        print(f"[DEBUG] AVIF Conversion - API response status: {response.status_code}")
        if response.status_code == 200:
            # Save the converted image
            with open(output_path, 'wb') as f:
                f.write(response.content)
            print(f"[DEBUG] AVIF Conversion - API successful")
            return True
        else:
            print(f"[DEBUG] AVIF Conversion - API error: {response.text[:200]}")
        return False
    except Exception as e:
        print(f"[DEBUG] AVIF Conversion - API exception: {str(e)}")
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
    
    # Track folder structure for uploaded files
    folder_structure = {}

    try:
        # Track all folders we've seen to preserve empty folders
        folder_paths = set()
        
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            # First pass: collect all folder paths
            for file in files:
                if file:
                    # Extract folder structure
                    original_path = file.filename.replace('\\', '/')
                    dir_path = os.path.dirname(original_path)
                    
                    # Add this folder and all parent folders to our set
                    current_path = ''
                    for part in dir_path.split('/'):
                        if part:
                            current_path = current_path + part + '/'
                            folder_paths.add(current_path)
            
            # Add all folders to the ZIP first (ensures empty folders are preserved)
            for folder in sorted(folder_paths):
                # Create directory entry in the ZIP
                zipinfo = zipfile.ZipInfo(folder)
                zipinfo.external_attr = 0o755 << 16  # Permissions for folder
                zipf.writestr(zipinfo, '')
                print(f"[DEBUG] Adding folder to ZIP: {folder}")
            
            # Second pass: process files
            for file in files:
                if file and allowed_file(file.filename):
                    # Check if we should process this file based on conversion type
                    if conversion_type == 'pngToJpg' and not file.filename.lower().endswith('.png'):
                        continue
                    
                    # Extract folder structure and filename
                    original_path = file.filename
                    # Replace backslashes with forward slashes for consistency
                    original_path = original_path.replace('\\', '/')
                    
                    # Get the directory path and filename
                    dir_path = os.path.dirname(original_path)
                    just_filename = os.path.basename(original_path)
                    
                    # Generate unique filenames for processing
                    base_filename, ext = os.path.splitext(secure_filename(just_filename))
                    ext = ext.lower()
                    input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_filename}_{timestamp}_input{ext}")
                    output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_filename}_{timestamp}_output.jpg")
                    
                    # Determine the ZIP path (preserving folder structure)
                    if sort_folders:
                        # Main/Additional sorting takes precedence if enabled
                        if '-' in base_filename and base_filename.split('-')[-1].isdigit():
                            zip_subfolder = 'Additional/'
                        else:
                            zip_subfolder = 'Main/'
                            
                        # If there was an original folder path, append it after Main/Additional
                        if dir_path:
                            zip_path_in_archive = os.path.join(zip_subfolder, dir_path)
                        else:
                            zip_path_in_archive = zip_subfolder
                    else:
                        # Just use the original folder structure
                        zip_path_in_archive = dir_path
                    
                    # Ensure the path ends with a slash if not empty
                    if zip_path_in_archive and not zip_path_in_archive.endswith('/'):
                        zip_path_in_archive += '/'
                        
                    print(f"[DEBUG] File: {file.filename}, zip_path: {zip_path_in_archive}")
                    
                    try:
                        # Save the uploaded file
                        file.save(input_path)
                        
                        if ext == '.jpg':
                            # If already JPG, add as-is with original name
                            output_filename = just_filename
                            print(f"[DEBUG] Adding to ZIP: {zip_path_in_archive + output_filename}")
                            zipf.write(input_path, zip_path_in_archive + output_filename)
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
                                    
                            # Add converted file with .jpg extension
                            if converted:
                                output_filename = f"{base_filename}.jpg"
                                print(f"[DEBUG] Adding to ZIP: {zip_path_in_archive + output_filename}")
                                zipf.write(output_path, zip_path_in_archive + output_filename)
                        
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
