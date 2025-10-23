from llama_cpp import Llama
import threading
import os
import json

# Model state
llm = None
model_loaded = False
loading_progress = 0
loading_error = None
loading_lock = threading.Lock()
current_model = None

MODEL_DIR = os.getenv("LLM_MODEL_DIR", "../models")

# Define available models - updated with all your models
MODEL_DIR = os.getenv("LLM_MODEL_DIR", "../models")
MODELS_CONFIG_FILE = os.path.join(MODEL_DIR, "models.json")

# Default models configuration
DEFAULT_MODELS = {
    "llama-2-7b-chat": {
        "file": "llama-2-7b-chat.Q4_K_M.gguf",
        "type": "llama",
        "display_name": "Llama 2 7B Chat"
    },
    "capybarahermes-2.5-mistral-7b": {
        "file": "capybarahermes-2.5-mistral-7b.Q4_K_M.gguf",
        "type": "mistral",
        "display_name": "CapybaraHermes 2.5 Mistral 7B"
    },
    "phi-2": {
        "file": "phi-2.Q4_K_M.gguf",
        "type": "phi",
        "display_name": "Phi-2"
    },
}


def load_models_config():
    """Load models configuration from JSON file, or create default if not exists"""
    try:
        if os.path.exists(MODELS_CONFIG_FILE):
            with open(MODELS_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                print(f"[INFO] Loaded models configuration from {MODELS_CONFIG_FILE}")
                return config
        else:
            # Create default config file
            os.makedirs(MODEL_DIR, exist_ok=True)
            with open(MODELS_CONFIG_FILE, 'w') as f:
                json.dump(DEFAULT_MODELS, f, indent=2)
            print(f"[INFO] Created default models configuration at {MODELS_CONFIG_FILE}")
            return DEFAULT_MODELS
    except Exception as e:
        print(f"[WARNING] Error loading models config: {e}. Using defaults.")
        return DEFAULT_MODELS


# Load models from configuration file
AVAILABLE_MODELS = load_models_config()



def get_available_models():
    """Return list of models that actually exist in MODEL_DIR"""
    available = {}
    for model_id, config in AVAILABLE_MODELS.items():
        model_path = os.path.join(MODEL_DIR, config["file"])
        if os.path.exists(model_path):
            available[model_id] = config
    return available


def load_model(model_id=None, n_gpu_layers=0, n_ctx=2048, n_threads=None):
    """Load a specific model (default: llama-2-7b-chat)
    
    Args:
        model_id: Model identifier from AVAILABLE_MODELS
        n_gpu_layers: Number of layers to offload to GPU (0 for CPU only)
        n_ctx: Context window size (default: 2048)
        n_threads: Number of threads to use (None for auto)
    """
    global llm, model_loaded, loading_progress, loading_error, current_model

    if model_id is None:
        model_id = "llama-2-7b-chat"

    print(f"[DEBUG] load_model called — model_id: {model_id}")

    with loading_lock:
        try:
            # Unload any existing model
            if llm is not None:
                print(f"[DEBUG] Unloading previous model: {current_model}")
                del llm
                llm = None
                model_loaded = False
                current_model = None

            # Check model config
            if model_id not in AVAILABLE_MODELS:
                raise ValueError(f"Model '{model_id}' not defined in AVAILABLE_MODELS")

            model_config = AVAILABLE_MODELS[model_id]
            model_path = os.path.join(MODEL_DIR, model_config["file"])

            if not os.path.exists(model_path):
                raise FileNotFoundError(f"Model file not found: {model_path}")

            print(f"[INFO] Loading model: {model_config['display_name']}")
            loading_progress = 10
            loading_error = None

            # Load model using llama-cpp-python
            llm = Llama(
                model_path=model_path,
                n_gpu_layers=n_gpu_layers,  # Set to >0 if you have GPU
                n_ctx=n_ctx,                # Context window size
                n_threads=n_threads,        # Number of threads (None = auto)
                verbose=False               # Set to True for debug output
            )

            loading_progress = 100
            model_loaded = True
            current_model = model_id
            print(f"[SUCCESS] Model loaded: {model_config['display_name']}")

        except Exception as e:
            loading_error = str(e)
            model_loaded = False
            current_model = None
            print(f"[ERROR] Model loading failed: {e}")


def switch_model(model_id, n_gpu_layers=0, n_ctx=2048):
    """Switch to a different model"""
    if model_id not in AVAILABLE_MODELS:
        return False, f"Model '{model_id}' not available"

    try:
        load_model(model_id, n_gpu_layers=n_gpu_layers, n_ctx=n_ctx)
        return True, f"Switched to {AVAILABLE_MODELS[model_id]['display_name']}"
    except Exception as e:
        return False, str(e)


def get_model_info():
    """Get information about the currently loaded model"""
    if not model_loaded or current_model is None:
        return {"loaded": False, "current_model": None}
    
    return {
        "loaded": True,
        "current_model": current_model,
        "display_name": AVAILABLE_MODELS[current_model]["display_name"],
        "model_type": AVAILABLE_MODELS[current_model]["type"]
    }


def generate_text(prompt, max_tokens=256, temperature=0.7, top_p=0.9, 
                  stop=None, stream=False):
    """Generate text using the loaded model
    
    Args:
        prompt: Input prompt text
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature (0.0-1.0)
        top_p: Nucleus sampling parameter
        stop: Stop sequences (list of strings)
        stream: Whether to stream the output
    
    Returns:
        Generated text or generator if streaming
    """
    if not model_loaded or llm is None:
        raise RuntimeError("No model loaded. Call load_model() first.")
    
    return llm(
        prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        stop=stop,
        stream=stream,
        echo=False
    )