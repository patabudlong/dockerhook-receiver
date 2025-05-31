module.exports = {
    apps: [{
      name: 'webhook-server',
      script: 'dockerhook-server.py',
      interpreter: 'none',
      args: '--port 9000',
      cwd: '/var/www/dockerhook-receiver',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',
      env: {
        NODE_ENV: 'production'
      }
    }]
  }