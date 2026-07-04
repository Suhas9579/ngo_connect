import os

class Config:
    # Base directory of the application
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # Security keys
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'ngo-super-secret-key-987654321-abcde'
    
    # Database Configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or f"sqlite:///{os.path.join(BASE_DIR, 'ngo.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload and generated assets folders
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    CERTIFICATE_FOLDER = os.path.join(BASE_DIR, 'certificates')
    REPORTS_FOLDER = os.path.join(BASE_DIR, 'reports')
    
    # Security limit for uploads: 16 Megabytes
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
