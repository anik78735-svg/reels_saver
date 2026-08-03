"""
API Middleware - Authentication, Rate Limiting, Logging
"""

import os
import time
import hashlib
import functools
from flask import request, jsonify, g
from typing import Callable, Dict, Any
from collections import defaultdict
import threading

# ============================================
# API KEY MIDDLEWARE
# ============================================

class APIKeyMiddleware:
    """API Key authentication middleware"""
    
    def __init__(self):
        # Store API keys with their permissions
        self.api_keys: Dict[str, Dict[str, Any]] = {}
        self._load_api_keys()
    
    def _load_api_keys(self):
        """Load API keys from environment or config"""
        # Default API key for testing
        default_key = os.environ.get('API_KEY', 'dev-api-key-12345')
        self.api_keys[default_key] = {
            'name': 'Default Key',
            'permissions': ['download', 'preview', 'bulk', 'drive'],
            'rate_limit': 100,  # requests per minute
            'created_at': time.time()
        }
        
        # Load additional keys from environment
        # Format: API_KEY_1=name:key:permissions
        for key, value in os.environ.items():
            if key.startswith('API_KEY_'):
                parts = value.split(':')
                if len(parts) >= 2:
                    api_key = parts[0]
                    name = parts[1] if len(parts) > 1 else f'API Key {key}'
                    permissions = parts[2].split(',') if len(parts) > 2 else ['download', 'preview', 'bulk']
                    self.api_keys[api_key] = {
                        'name': name,
                        'permissions': permissions,
                        'rate_limit': 100,
                        'created_at': time.time()
                    }
    
    def authenticate(self, f: Callable) -> Callable:
        """Decorator to authenticate API requests"""
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            # Check if API is enabled
            if not os.environ.get('ENABLE_API', 'true').lower() == 'true':
                return jsonify({
                    'status': 'error',
                    'message': 'API is disabled',
                    'code': 503
                }), 503
            
            # Skip auth for health check
            if request.path == '/api/health':
                return f(*args, **kwargs)
            
            # Get API key from header or query param
            api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
            
            if not api_key:
                return jsonify({
                    'status': 'error',
                    'message': 'API key required. Provide X-API-Key header or api_key query param',
                    'code': 401
                }), 401
            
            # Validate API key
            if api_key not in self.api_keys:
                return jsonify({
                    'status': 'error',
                    'message': 'Invalid API key',
                    'code': 401
                }), 401
            
            # Store API key info in request context
            g.api_key_info = self.api_keys[api_key]
            g.api_key = api_key
            
            return f(*args, **kwargs)
        
        return decorated

# ============================================
# RATE LIMIT MIDDLEWARE
# ============================================

class RateLimitMiddleware:
    """Rate limiting middleware"""
    
    def __init__(self):
        self.requests: Dict[str, list] = defaultdict(list)
        self.lock = threading.Lock()
    
    def _cleanup_old_requests(self, key: str, window: int = 60):
        """Remove requests older than window"""
        current_time = time.time()
        with self.lock:
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if current_time - req_time < window
            ]
    
    def _get_rate_limit(self, api_key: str) -> int:
        """Get rate limit for API key"""
        if hasattr(g, 'api_key_info'):
            return g.api_key_info.get('rate_limit', 100)
        return 100
    
    def limit(self, window: int = 60) -> Callable:
        """Decorator to apply rate limiting"""
        def decorator(f: Callable) -> Callable:
            @functools.wraps(f)
            def decorated(*args, **kwargs):
                # Get API key
                api_key = request.headers.get('X-API-Key') or request.args.get('api_key') or 'default'
                rate_limit = self._get_rate_limit(api_key)
                
                # Cleanup old requests
                self._cleanup_old_requests(api_key, window)
                
                # Check rate limit
                with self.lock:
                    if len(self.requests[api_key]) >= rate_limit:
                        return jsonify({
                            'status': 'error',
                            'message': f'Rate limit exceeded. Maximum {rate_limit} requests per {window} seconds',
                            'code': 429
                        }), 429
                    
                    # Add current request
                    self.requests[api_key].append(time.time())
                
                return f(*args, **kwargs)
            
            return decorated
        return decorator

# ============================================
# LOGGING MIDDLEWARE
# ============================================

def log_request(f: Callable) -> Callable:
    """Log API requests"""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        start_time = time.time()
        
        # Log request
        print(f"[API] {request.method} {request.path}")
        print(f"[API] Client: {request.remote_addr}")
        print(f"[API] User-Agent: {request.headers.get('User-Agent', 'Unknown')}")
        
        # Execute request
        response = f(*args, **kwargs)
        
        # Log response time
        elapsed = time.time() - start_time
        print(f"[API] Response time: {elapsed:.2f}s")
        
        return response
    
    return decorated
