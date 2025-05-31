#!/usr/bin/env python3
import os
import json
import hmac
import hashlib
import subprocess
import logging
from flask import Flask, request, jsonify
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Configuration from environment variables
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', 'your-secret-key-here')
WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', 9000))

# Docker configuration
DOCKER_REGISTRY = os.getenv('DOCKER_REGISTRY', 'patabudlong')
DOCKER_IMAGE_NAME = os.getenv('DOCKER_IMAGE_NAME', 'tripbundles-website')

# Development configuration
DEV_CONTAINER_NAME = os.getenv('DEV_CONTAINER_NAME', 'tripbundles-dev')
DEV_HOST_PORT = os.getenv('DEV_HOST_PORT', '3001')
DEV_CONTAINER_PORT = os.getenv('DEV_CONTAINER_PORT', '3000')
DEV_IMAGE_TAG = os.getenv('DEV_IMAGE_TAG', 'latest-dev')
NODE_ENV_DEV = os.getenv('NODE_ENV_DEV', 'development')

# Production configuration
PROD_CONTAINER_NAME = os.getenv('PROD_CONTAINER_NAME', 'tripbundles-prod')
PROD_HOST_PORT = os.getenv('PROD_HOST_PORT', '3000')
PROD_CONTAINER_PORT = os.getenv('PROD_CONTAINER_PORT', '3000')
PROD_IMAGE_TAG = os.getenv('PROD_IMAGE_TAG', 'latest')
NODE_ENV_PROD = os.getenv('NODE_ENV_PROD', 'production')

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
            
            # Build image name
            image_name = f"{DOCKER_REGISTRY}/{DOCKER_IMAGE_NAME}:{DEV_IMAGE_TAG}"
            
            # Pull latest dev image
            subprocess.run(["docker", "pull", image_name], check=True)
            
            # Stop and remove existing container
            subprocess.run(["docker", "stop", DEV_CONTAINER_NAME], check=False)
            subprocess.run(["docker", "rm", DEV_CONTAINER_NAME], check=False)
            
            # Start new container
            subprocess.run([
                "docker", "run", "-d",
                "--name", DEV_CONTAINER_NAME,
                "-p", f"{DEV_HOST_PORT}:{DEV_CONTAINER_PORT}",
                "-e", f"NODE_ENV={NODE_ENV_DEV}",
                "-e", f"PORT={DEV_CONTAINER_PORT}",
                "--restart", "unless-stopped",
                image_name
            ], check=True)
            
            log_message("Development deployment completed successfully")
            return True
            
        elif branch == "master":
            log_message("Starting production deployment...")
            
            # Build image name
            image_name = f"{DOCKER_REGISTRY}/{DOCKER_IMAGE_NAME}:{PROD_IMAGE_TAG}"
            
            # Pull latest prod image
            subprocess.run(["docker", "pull", image_name], check=True)
            
            # Stop and remove existing container
            subprocess.run(["docker", "stop", PROD_CONTAINER_NAME], check=False)
            subprocess.run(["docker", "rm", PROD_CONTAINER_NAME], check=False)
            
            # Start new container
            subprocess.run([
                "docker", "run", "-d",
                "--name", PROD_CONTAINER_NAME,
                "-p", f"{PROD_HOST_PORT}:{PROD_CONTAINER_PORT}",
                "-e", f"NODE_ENV={NODE_ENV_PROD}",
                "-e", f"PORT={PROD_CONTAINER_PORT}",
                "--restart", "unless-stopped",
                image_name
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

def deploy_container(environment, container_name, image_name, host_port, container_port, node_env):
    """Deploy a Docker container"""
    try:
        log_message(f"Starting deployment for {environment} environment")
        log_message(f"Image: {image_name}")
        log_message(f"Container: {container_name}")
        
        # Pull the latest image
        log_message(f"Pulling image: {image_name}")
        pull_result = subprocess.run(['docker', 'pull', image_name], 
                                   capture_output=True, text=True, check=True)
        log_message(f"Pull successful: {pull_result.stdout.strip()}")
        
        # Stop existing container if running
        log_message(f"Stopping existing container: {container_name}")
        subprocess.run(['docker', 'stop', container_name], 
                      capture_output=True, text=True)
        
        # Remove existing container
        log_message(f"Removing existing container: {container_name}")
        subprocess.run(['docker', 'rm', container_name], 
                      capture_output=True, text=True)
        
        # Start new container
        docker_cmd = [
            'docker', 'run', '-d',
            '--name', container_name,
            '-p', f'{host_port}:{container_port}',
            '-e', f'NODE_ENV={node_env}',
            image_name
        ]
        
        log_message(f"Starting new container with command: {' '.join(docker_cmd)}")
        run_result = subprocess.run(docker_cmd, capture_output=True, text=True, check=True)
        
        container_id = run_result.stdout.strip()
        log_message(f"Container started successfully with ID: {container_id}")
        
        return True
        
    except subprocess.CalledProcessError as e:
        log_message(f"Docker command failed: {e}")
        log_message(f"Error output: {e.stderr}")
        return False
    except Exception as e:
        log_message(f"Deployment error: {str(e)}")
        return False

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Handle webhook from GitHub or Docker Hub"""
    try:
        # Get the payload
        payload = request.get_json()
        
        # Check if this is a GitHub webhook
        github_event = request.headers.get('X-GitHub-Event')
        
        if github_event:
            # GitHub webhook handling
            if github_event != 'push':
                log_message(f"Ignoring non-push event: {github_event}")
                return jsonify({"status": "ignored", "message": f"Event {github_event} not supported"}), 200
            
            # Handle GitHub push events (existing code)
            ref = payload.get('ref', '')
            branch = ref.replace('refs/heads/', '')
            
            log_message(f"Webhook received for branch: {branch}")
            
            # Update container
            success = update_container(branch)
            
            if success:
                return jsonify({"message": f"Deployment triggered for {branch}"}), 200
            else:
                return jsonify({"error": f"Deployment failed for {branch}"}), 500
            
        else:
            # Docker Hub webhook handling
            log_message("Processing Docker Hub webhook")
            
            # Docker Hub webhook payload structure
            if 'push_data' in payload and 'repository' in payload:
                repo_name = payload['repository']['repo_name']
                tag = payload['push_data']['tag']
                
                log_message(f"Docker Hub push: {repo_name}:{tag}")
                
                # Determine environment based on tag
                if tag == 'latest-dev':
                    environment = 'development'
                    container_name = DEV_CONTAINER_NAME
                    host_port = DEV_HOST_PORT
                    container_port = DEV_CONTAINER_PORT
                    node_env = NODE_ENV_DEV
                elif tag == 'latest':
                    environment = 'production'
                    container_name = PROD_CONTAINER_NAME
                    host_port = PROD_HOST_PORT
                    container_port = PROD_CONTAINER_PORT
                    node_env = NODE_ENV_PROD
                else:
                    log_message(f"Ignoring tag: {tag}")
                    return jsonify({"status": "ignored", "message": f"Tag {tag} not configured"}), 200
                
                # Deploy the container
                image_name = f"{DOCKER_REGISTRY}/{DOCKER_IMAGE_NAME}:{tag}"
                deploy_container(environment, container_name, image_name, host_port, container_port, node_env)
                
                return jsonify({
                    "status": "success",
                    "message": f"Deployment completed for {environment}",
                    "tag": tag,
                    "environment": environment
                }), 200
            else:
                log_message("Unknown webhook format")
                return jsonify({"error": "Unknown webhook format"}), 400
        
    except Exception as e:
        log_message(f"Error processing webhook: {str(e)}")
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
        dev_status = subprocess.run(["docker", "ps", "--filter", f"name={DEV_CONTAINER_NAME}", "--format", "{{.Status}}"], 
                                   capture_output=True, text=True)
        prod_status = subprocess.run(["docker", "ps", "--filter", f"name={PROD_CONTAINER_NAME}", "--format", "{{.Status}}"], 
                                    capture_output=True, text=True)
        
        return jsonify({
            "development": {
                "container": DEV_CONTAINER_NAME,
                "status": dev_status.stdout.strip() or "Not running",
                "port": DEV_HOST_PORT
            },
            "production": {
                "container": PROD_CONTAINER_NAME, 
                "status": prod_status.stdout.strip() or "Not running",
                "port": PROD_HOST_PORT
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
    log_message(f"Starting webhook server on port {WEBHOOK_PORT}...")
    app.run(host='0.0.0.0', port=WEBHOOK_PORT, debug=False)