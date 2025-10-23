from app import app
from app.models import load_model, model_loaded, loading_error
import threading
import time

def initialize_app():
    # Check if we need to load the model
    if not model_loaded and loading_error is None:
        print("Starting model loading process...")
        model_thread = threading.Thread(target=load_model)
        model_thread.daemon = True
        model_thread.start()        
        # Give the model a moment to start loading

if __name__ == '__main__':
    initialize_app()
    print("Starting LLM Web App...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5000, threaded=True)
