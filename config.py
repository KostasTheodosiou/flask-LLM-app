import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
    MODEL_PATH = "./"
    MODEL_FILE = "llama-2-7b-chat.Q4_K_M.gguf"