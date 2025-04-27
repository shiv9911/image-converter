# Bulk Image Converter Web App

This is a Flask-based web application for bulk image conversion to JPG format. It supports a wide range of image formats and offers advanced features such as:
- Drag-and-drop and file browsing for uploads
- Conversion of all non-JPG images to JPG
- Option to sort images into Main/Additional folders in the ZIP
- Download ZIP file named with current date and time
- AVIF support via ffmpeg or Cloudmersive API

## Requirements
- Python 3.8+
- All dependencies in `requirements.txt`
- ffmpeg installed (for AVIF conversion)

## Running Locally
```bash
pip install -r requirements.txt
python app.py
```

## Production Deployment
- Use a WSGI server (e.g., Gunicorn, uWSGI) and point to `wsgi:app`.
- Example (with Gunicorn):
```bash
gunicorn wsgi:app
```
- For Heroku/Render, use the included `Procfile`.

## ffmpeg for AVIF
- Place `ffmpeg.exe` in `C:\ffmpeg\bin` or ensure it is in your PATH.

## Cloudmersive API (optional for AVIF)
- Get a free API key from https://www.cloudmersive.com/image-api
- Add your API key in `app.py` where indicated.

## Security Note
- Do NOT use Flask's built-in server for production. Use Gunicorn, uWSGI, or a cloud platform.

---

For any issues, contact your developer or raise an issue on your deployment platform.
