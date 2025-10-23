from flask import request, jsonify, render_template
import app.models as models
from app import app
import json
import threading
import time
import psutil
from datetime import datetime
from collections import deque
import os

# Global metrics storage
llm_metrics = {
    'requests': deque(maxlen=100),  # Stores last 100 requests
    'system': {
        'active_streams': 0,
        'total_requests': 0,
        'errors': 0,
        'model_loaded': False
    }
}

@app.route('/')
def index():
    return render_template('index.html')    

@app.route('/health')
def health():
    llm_metrics['system']['model_loaded'] = models.model_loaded
    return jsonify({
        'status': 'ready' if models.model_loaded else 'loading',
        'model_loaded': models.model_loaded,
        'system_metrics': llm_metrics['system']
    })

@app.route('/node-info', methods=['GET'])
def get_node_info():
    """Get node name from environment variable"""
    node_name = os.getenv('NODE_NAME', 'Unknown')
    return jsonify({
        'node_name': node_name
    })


import time
import json
import psutil
from flask import request, jsonify
import app.models as models
from app import app

# Example global metrics
llm_metrics = {
    'system': {
        'errors': 0,
        'active_streams': 0,
        'total_requests': 0
    },
    'requests': []
}




@app.route('/generate', methods=['POST'])
def generate():
    # Check if another stream is already active
    if llm_metrics['system']['active_streams'] > 0:
        error_response = {
            'error': 'Server busy processing another request',
            'status': 'busy',
            'active_streams': llm_metrics['system']['active_streams']
        }
        log_request_response(request, error_response, 429)
        return jsonify(error_response), 429  # 429 Too Many Requests

    request_metrics = {
        'timing': {
            'start': time.time(),
            'first_token': None,
            'end': None
        },
        'tokens': {
            'count': 0,
            'empty': 0,
            'lengths': []
        },
        'prompt': {
            'length': 0,
            'tokens': 0
        },
        'config': {
            'max_tokens': 0,
            'temperature': 0
        },
        'system': {
            'memory_start': psutil.Process().memory_info().rss / 1024 / 1024
        },
        'error': None
    }

    try:
        if not models.model_loaded or models.llm is None:
            llm_metrics['system']['errors'] += 1
            error_response = {'error': 'Model not ready', 'status': 'loading'}
            log_request_response(request, error_response, 503)
            return jsonify(error_response), 503

        if not request.is_json:
            llm_metrics['system']['errors'] += 1
            error_response = {'error': 'Request must be JSON'}
            log_request_response(request, error_response, 400)
            return jsonify(error_response), 400

        data = request.get_json()
        prompt = data.get('prompt', '').strip()
        max_tokens = min(int(data.get('max_tokens', 500)), 2000)
        temperature = max(0.1, min(float(data.get('temperature', 0.7)), 2.0))
        top_p = max(0.1, min(float(data.get('top_p', 0.9)), 1.0))
        stop = data.get('stop', None)  # Optional stop sequences

        request_metrics['prompt']['length'] = len(prompt)
        request_metrics['config']['max_tokens'] = max_tokens
        request_metrics['config']['temperature'] = temperature

        if not prompt:
            llm_metrics['system']['errors'] += 1
            error_response = {'error': 'No prompt provided'}
            log_request_response(request, error_response, 400)
            return jsonify(error_response), 400

        llm_metrics['system']['active_streams'] += 1
        
        llm_metrics['system']['total_requests'] += 1

        # Capture request data before streaming (while still in request context)
        request_data = {
            'timestamp': datetime.now().isoformat(),
            'method': request.method,
            'endpoint': request.path,
            'request': {
                'headers': dict(request.headers),
                'body': request.get_json(),
                'remote_addr': request.remote_addr,
                'user_agent': request.user_agent.string if request.user_agent else None
            },
            'config': {
                'prompt_length': len(prompt),
                'max_tokens': max_tokens,
                'temperature': temperature,
                'top_p': top_p
            }
        }

        def generate_stream():
            full_response = ""  # Accumulate the complete response
            try:
                print(f"Starting generation with: {prompt[:50]}...")
                
                # llama-cpp-python streaming interface
                stream = models.llm(
                    prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    stop=stop,
                    stream=True,
                    echo=False
                )

                for output in stream:
                    # llama-cpp-python returns dict with 'choices' array
                    if 'choices' not in output or len(output['choices']) == 0:
                        request_metrics['tokens']['empty'] += 1
                        continue
                    
                    # Extract token text from the response
                    token = output['choices'][0].get('text', '')
                    
                    if not token:
                        request_metrics['tokens']['empty'] += 1
                        continue

                    if request_metrics['timing']['first_token'] is None:
                        request_metrics['timing']['first_token'] = time.time() - request_metrics['timing']['start']

                    request_metrics['tokens']['count'] += 1
                    request_metrics['tokens']['lengths'].append(len(token))
                    full_response += token  # Accumulate tokens

                    yield f"data: {json.dumps({'token': token})}\n\n"

                request_metrics['timing']['end'] = time.time()
                request_metrics['system']['memory_end'] = psutil.Process().memory_info().rss / 1024 / 1024
                request_metrics['response'] = full_response  # Store complete response
                yield "data: [DONE]\n\n"

            except Exception as e:
                error_msg = f"Generation error: {str(e)}"
                request_metrics['error'] = error_msg
                llm_metrics['system']['errors'] += 1
                print(error_msg)
                yield f"data: {json.dumps({'error': error_msg})}\n\n"

            finally:
                # Calculate derived metrics
                end_time = time.time()
                if request_metrics['timing']['end'] is None:
                    request_metrics['timing']['end'] = end_time
                total_time = request_metrics['timing']['end'] - request_metrics['timing']['start']

                request_metrics['timing']['total'] = total_time
                request_metrics['tokens']['per_second'] = (
                    request_metrics['tokens']['count'] / total_time if total_time > 0 else 0
                )
                request_metrics['tokens']['avg_length'] = (
                    sum(request_metrics['tokens']['lengths']) / request_metrics['tokens']['count']
                    if request_metrics['tokens']['count'] > 0 else 0
                )
                request_metrics['system']['memory_delta'] = (
                    request_metrics['system']['memory_end'] - request_metrics['system']['memory_start']
                    if 'memory_end' in request_metrics['system'] else 0
                )

                # Create complete log entry with request and response data
                log_entry = {
                    **request_data,
                    'status_code': 200,
                    'response': {
                        'status': 'completed',
                        'response_text': request_metrics.get('response', ''),
                        'tokens_generated': request_metrics['tokens']['count'],
                        'tokens_per_second': round(request_metrics['tokens']['per_second'], 4),
                        'total_time': round(request_metrics['timing']['total'], 4),
                        'error': request_metrics['error']
                    }
                }
                
                if 'request_logs' not in llm_metrics:
                    llm_metrics['request_logs'] = deque(maxlen=500)
                
                llm_metrics['request_logs'].append(log_entry)
                print(f"[LOG] {log_entry['timestamp']} - {request_data['method']} {request_data['endpoint']} - Status: 200")
                
                llm_metrics['requests'].append(request_metrics)
                llm_metrics['system']['active_streams'] -= 1
                print("Stream generation ended")

        # Prepare the streaming response
        response = app.response_class(
            generate_stream(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Access-Control-Allow-Origin': '*',
                'X-Accel-Buffering': 'no'
            }
        )

        @response.call_on_close
        def on_close():
            print(f"Client disconnected for prompt: {prompt[:50]}...")

        return response

    except Exception as e:
        error_msg = f"Endpoint error: {str(e)}"
        request_metrics['error'] = error_msg
        llm_metrics['system']['errors'] += 1
        print(error_msg)
        error_response = {'error': f"Internal server error: {str(e)}"}
        log_request_response(request, error_response, 500)
        return jsonify(error_response), 500

def log_request_response(req, response_data, status_code):
    """Log request and response details"""
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'method': req.method,
        'endpoint': req.path,
        'status_code': status_code,
        'request': {
            'headers': dict(req.headers),
            'body': req.get_json() if req.is_json else None,
            'remote_addr': req.remote_addr,
            'user_agent': req.user_agent.string if req.user_agent else None
        },
        'response': response_data
    }
    
    if 'request_logs' not in llm_metrics:
        llm_metrics['request_logs'] = deque(maxlen=500)  # Keep last 500 logs
    
    llm_metrics['request_logs'].append(log_entry)
    print(f"[LOG] {log_entry['timestamp']} - {req.method} {req.path} - Status: {status_code}")


@app.route('/logs', methods=['GET'])
def get_logs():
    """Retrieve all logged requests and responses"""
    logs = list(llm_metrics.get('request_logs', []))
    return jsonify({
        'total_logs': len(logs),
        'logs': logs
    })


@app.route('/logs/latest', methods=['GET'])
def get_latest_logs():
    """Retrieve the latest N logs (default 10)"""
    limit = request.args.get('limit', 10, type=int)
    logs = list(llm_metrics.get('request_logs', []))
    return jsonify({
        'total_logs': len(logs),
        'logs': logs[-limit:]
    })


@app.route('/logs/filter', methods=['GET'])
def filter_logs():
    """Filter logs by endpoint or status code"""
    endpoint = request.args.get('endpoint', None)
    status_code = request.args.get('status_code', None, type=int)
    
    logs = list(llm_metrics.get('request_logs', []))
    
    if endpoint:
        logs = [log for log in logs if endpoint in log['endpoint']]
    
    if status_code:
        logs = [log for log in logs if log['status_code'] == status_code]
    
    return jsonify({
        'total_logs': len(logs),
        'filters': {
            'endpoint': endpoint,
            'status_code': status_code
        },
        'logs': logs
    })


@app.route('/logs/clear', methods=['POST'])
def clear_logs():
    """Clear all logs"""
    if 'request_logs' in llm_metrics:
        llm_metrics['request_logs'].clear()
    
    return jsonify({
        'status': 'success',
        'message': 'All logs cleared'
    })


@app.route('/metrics')
def get_metrics():
    if not llm_metrics['requests']:
        return jsonify({
            'message': 'No requests processed yet',
            'aggregate': {},
            'system': llm_metrics['system'],
            'recent_requests_count': 0,
            'sample_request': None
        })

    recent_requests = list(llm_metrics['requests'])

    successful_requests = [
        r for r in recent_requests if r['error'] is None and r['timing']['first_token'] is not None
    ]

    avg_time_to_first_token = (
        sum(r['timing']['first_token'] for r in successful_requests) / len(successful_requests)
        if successful_requests else 0
    )

    avg_tokens_per_second = (
        sum(r['tokens']['per_second'] for r in successful_requests) / len(successful_requests)
        if successful_requests else 0
    )

    total_requests = max(llm_metrics['system']['total_requests'], 1)  # Avoid division by zero

    aggregate = {
        'avg_time_to_first_token': round(avg_time_to_first_token, 4),
        'avg_tokens_per_second': round(avg_tokens_per_second, 4),
        'error_rate': round(llm_metrics['system']['errors'] / total_requests, 4),
        'current_active_streams': llm_metrics['system']['active_streams'],
        'total_requests': llm_metrics['system']['total_requests'],
        'total_errors': llm_metrics['system']['errors'],
        'model_loaded': models.model_loaded
    }

    return jsonify({
        'aggregate': aggregate,
        'system': llm_metrics['system'],
        'recent_requests_count': len(recent_requests),
        'sample_request': recent_requests[-1] if recent_requests else None
    })


@app.route('/metrics/raw')
def get_raw_metrics():
    return jsonify({
        'requests': list(llm_metrics['requests']),
        'system': llm_metrics['system']
    })

@app.route('/models/available', methods=['GET'])
def get_available_models():
    """Return list of available models"""
    available = models.get_available_models()
    return jsonify({
        'models': [
            {
                'id': model_id,
                'display_name': config['display_name'],
                'type': config['type']
            }
            for model_id, config in available.items()
        ],
        'current_model': models.current_model
    })

@app.route('/models/switch', methods=['POST'])
def switch_model():
    """Switch to a different model"""
    from app.routes import llm_metrics  # Import your metrics object
    
    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 400
    
    data = request.get_json()
    model_id = data.get('model_id')
    
    if not model_id:
        return jsonify({'error': 'No model_id provided'}), 400
    
    # Check if another stream is active
    if llm_metrics['system']['active_streams'] > 0:
        return jsonify({
            'error': 'Cannot switch models while processing requests',
            'status': 'busy'
        }), 429
    
    # Switch model in a background thread
    def switch_thread():
        success, message = models.switch_model(model_id)
        if not success:
            print(f"Model switch failed: {message}")
    
    thread = threading.Thread(target=switch_thread)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'status': 'switching',
        'message': f'Switching to {model_id}...',
        'model_id': model_id
    })

@app.route('/models/current', methods=['GET'])
def get_current_model():
    """Get currently loaded model"""
    return jsonify({
        'model_id': models.current_model,
        'display_name': models.AVAILABLE_MODELS.get(models.current_model, {}).get('display_name', 'Unknown'),
        'loaded': models.model_loaded,
        'loading_progress': models.loading_progress,
        'loading_error': models.loading_error
    })