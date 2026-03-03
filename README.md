# CV Gemini (Wasel v4 Pro - Colab Edition)

This repository contains the standalone web application version of the **Wasel v4 Live POC** Google Colab Notebook. 

It was automatically converted from the `.ipynb` file into a production-ready Flask application designed for deployment on Google Cloud Run.

## Features
- **Live Video Translation:** Captures webcam frames and translates Egyptian Sign Language in real-time.
- **Gemini 2.0 Flash Integration:** Uses Google's state-of-the-art vision models for gesture recognition.
- **Single-page Architecture:** Both the frontend (HTML/JS) and backend (Flask) are contained within `app.py` directly replicating the Colab cell constraints elegantly.

## Deployment to Cloud Run
To deploy this project:
```bash
gcloud run deploy cv-gemini --source . --region europe-west1 --allow-unauthenticated
```
