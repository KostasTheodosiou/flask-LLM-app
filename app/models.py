from ctransformers import AutoModelForCausalLM
import threading
import os
# Initialize all model state variables
llm = None
model_loaded = False
loading_progress = 0
loading_error = None
loading_lock = threading.Lock()

MODEL_DIR = os.getenv("LLM_MODEL_DIR", "./")


def load_model():
    global llm, model_loaded, loading_progress, loading_error
    print(f"[DEBUG] models.py loaded - id(model_loaded): {id(model_loaded)}")

    with loading_lock:
        if model_loaded or loading_error:
            return
        try:
            print("Loading LLM model...")
            loading_progress = 10
            
            llm = AutoModelForCausalLM.from_pretrained(
                MODEL_DIR,
                model_file="llama-2-7b-chat.Q4_K_M.gguf",
                model_type="llama",
                gpu_layers=0
            )
            
            loading_progress = 100
            model_loaded = True
            print("Model loaded successfully!")
        except Exception as e:
            loading_error = str(e)
            print(f"Model loading failed: {e}")