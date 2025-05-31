#!/usr/bin/env python3
import os
import json
import hmac
import hashlib
import subprocess
import logging
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

# Configuration
WEBHOOK_SECRET = "your-secret-key-here"  # Change this!

# Cross-platform log file path
if os.name == 'nt':  # Windows
    LOG_FILE = os.path.join(os.getcwd(), "webhook-deploy.log")
else:  # Unix/Linux
    LOG_FILE = "/var/log/webhook-deploy.log"

# Ensure log directory exists
log_dir = os.path.dirname(LOG_FILE)
if log_dir and not os.path.exists(log_dir):
    os.makedirs(log_dir, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

def log_message(message):
    """Log message to file and console"""
    logging.info(message)

def verify_signature(payload_body, signature_header):
    """Verify GitHub webhook signature"""
    if not signature_header:
        return False
    
    sha_name, signature = signature_header.split('=')
    if sha_name != 'sha256':
        return False
    
    mac = hmac.new(WEBHOOK_SECRET.encode(), payload_body, hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), signature)

def update_container(branch):
    """Update Docker container based on branch"""
    try:
        if branch == "develop":
            log_message("Starting development deployment...")
            
            # Pull latest dev image
            subprocess.run(["docker", "pull", "patabudlong/tripbundles-website:latest-dev"], check=True)
            
            # Stop and remove existing container
            subprocess.run(["docker", "stop", "tripbundles-dev"], check=False)
            subprocess.run(["docker", "rm", "tripbundles-dev"], check=False)
            
            # Start new container
            subprocess.run([
                "docker", "run", "-d",
                "--name", "tripbundles-dev",
                "-p", "3001:3000",
                "-e", "NODE_ENV=development",
                "-e", "PORT=3000",
                "--restart", "unless-stopped",
                "patabudlong/tripbundles-website:latest-dev"
            ], check=True)
            
            log_message("Development deployment completed successfully")
            return True
            
        elif branch == "master":
            log_message("Starting production deployment...")
            
            # Pull latest prod image
            subprocess.run(["docker", "pull", "patabudlong/tripbundles-website:latest"], check=True)
            
            # Stop and remove existing container
            subprocess.run(["docker", "stop", "tripbundles-prod"], check=False)
            subprocess.run(["docker", "rm", "tripbundles-prod"], check=False)
            
            # Start new container
            subprocess.run([
                "docker", "run", "-d",
                "--name", "tripbundles-prod",
                "-p", "3000:3000",
                "-e", "NODE_ENV=production",
                "-e", "PORT=3000",
                "--restart", "unless-stopped",
                "patabudlong/tripbundles-website:latest"
            ], check=True)
            
            log_message("Production deployment completed successfully")
            return True
            
        else:
            log_message(f"No deployment configured for branch: {branch}")
            return False
            
    except subprocess.CalledProcessError as e:
        log_message(f"Deployment failed: {e}")
        return False
    except Exception as e:
        log_message(f"Unexpected error during deployment: {e}")
        return False

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Handle GitHub webhook"""
    try:
        # Get the payload
        payload_body = request.get_data()
        signature_header = request.headers.get('X-Hub-Signature-256')
        
        # Verify signature (optional but recommended)
        if WEBHOOK_SECRET and not verify_signature(payload_body, signature_header):
            log_message("Invalid webhook signature")
            return jsonify({"error": "Invalid signature"}), 401
        
        # Parse JSON payload
        payload = request.get_json()
        
        # Only handle push events
        if request.headers.get('X-GitHub-Event') != 'push':
            log_message(f"Ignoring non-push event: {request.headers.get('X-GitHub-Event')}")
            return jsonify({"message": "Event ignored"}), 200
        
        # Extract branch name
        ref = payload.get('ref', '')
        branch = ref.replace('refs/heads/', '')
        
        log_message(f"Webhook received for branch: {branch}")
        
        # Update container
        success = update_container(branch)
        
        if success:
            return jsonify({"message": f"Deployment triggered for {branch}"}), 200
        else:
            return jsonify({"error": f"Deployment failed for {branch}"}), 500
            
    except Exception as e:
        log_message(f"Webhook handling error: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()}), 200

@app.route('/status', methods=['GET'])
def deployment_status():
    """Check deployment status"""
    try:
        # Check if containers are running
        dev_status = subprocess.run(["docker", "ps", "--filter", "name=tripbundles-dev", "--format", "{{.Status}}"], 
                                   capture_output=True, text=True)
        prod_status = subprocess.run(["docker", "ps", "--filter", "name=tripbundles-prod", "--format", "{{.Status}}"], 
                                    capture_output=True, text=True)
        
        return jsonify({
            "development": {
                "container": "tripbundles-dev",
                "status": dev_status.stdout.strip() or "Not running"
            },
            "production": {
                "container": "tripbundles-prod", 
                "status": prod_status.stdout.strip() or "Not running"
            }
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/', methods=['GET'])
def index():
    """Root endpoint with basic info"""
    return jsonify({
        "service": "Docker Webhook Server",
        "status": "running",
        "endpoints": {
            "/webhook": "POST - GitHub webhook handler",
            "/health": "GET - Health check",
            "/status": "GET - Deployment status"
        },
        "timestamp": datetime.now().isoformat()
    }), 200

if __name__ == '__main__':
    log_message("Starting webhook server on port 9000...")
    app.run(host='0.0.0.0', port=9000, debug=False)