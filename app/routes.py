from flask import request, jsonify, render_template
import app.models as models
from app import app
import json
import threading
import time
import psutil
from datetime import datetime
from collections import deque

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
        return jsonify({
            'error': 'Server busy processing another request',
            'status': 'busy',
            'active_streams': llm_metrics['system']['active_streams']
        }), 429  # 429 Too Many Requests

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
            return jsonify({'error': 'Model not ready', 'status': 'loading'}), 503

        if not request.is_json:
            llm_metrics['system']['errors'] += 1
            return jsonify({'error': 'Request must be JSON'}), 400

        data = request.get_json()
        prompt = data.get('prompt', '').strip()
        max_tokens = min(int(data.get('max_tokens', 500)), 2000)
        temperature = max(0.1, min(float(data.get('temperature', 0.7)), 2.0))

        request_metrics['prompt']['length'] = len(prompt)
        request_metrics['config']['max_tokens'] = max_tokens
        request_metrics['config']['temperature'] = temperature

        if not prompt:
            llm_metrics['system']['errors'] += 1
            return jsonify({'error': 'No prompt provided'}), 400

        llm_metrics['system']['active_streams'] += 1
        
        llm_metrics['system']['total_requests'] += 1

        def generate_stream():
            try:
                print(f"Starting generation with: {prompt[:50]}...")
                stream = models.llm(
                    prompt,
                    stream=True,
                    max_new_tokens=max_tokens,
                    temperature=temperature
                )

                for token in stream:
                    if not token:
                        request_metrics['tokens']['empty'] += 1
                        continue

                    if request_metrics['timing']['first_token'] is None:
                        request_metrics['timing']['first_token'] = time.time() - request_metrics['timing']['start']

                    request_metrics['tokens']['count'] += 1
                    request_metrics['tokens']['lengths'].append(len(token))

                    yield f"data: {json.dumps({'token': token})}\n\n"

                request_metrics['timing']['end'] = time.time()
                request_metrics['system']['memory_end'] = psutil.Process().memory_info().rss / 1024 / 1024
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
        return jsonify({'error': f"Internal server error: {str(e)}"}), 500


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