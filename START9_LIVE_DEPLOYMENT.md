# BitAgent Start9 Live Deployment Guide

## 🚀 **Step-by-Step Live Deployment**

### **Phase 1: Pre-Deployment Setup**

#### **1. Prepare Your Start9 Server**
```bash
# SSH into your Start9 server
ssh your-start9-server

# Create deployment directory
mkdir -p /opt/bitagent
cd /opt/bitagent
```

#### **2. Configure Environment Variables**
```bash
# Create secure environment file
sudo nano .env

# Add your configuration:
LNBITS_URL=https://your-lnbits-instance.com
LNBITS_API_KEY=your-lnbits-api-key-here
START9_NODE_ID=your-start9-node-id
HOST=0.0.0.0
PORT=8000
ENCRYPTION_KEY=your-encryption-key-here
CORS_ORIGINS=https://yourdomain.com,https://your-start9-server.com
RATE_LIMIT_MAX_REQUESTS=100
MAX_AUDIO_SIZE=100
MAX_TEXT_LENGTH=10000
LOG_LEVEL=INFO
```

#### **3. Update CORS Configuration**
```bash
# Edit start9_server.py to use your actual domains
nano start9_server.py

# Update the CORS origins:
allow_origins=[
    "https://your-actual-domain.com",  # Replace with your domain
    "https://your-start9-server.com",  # Replace with your Start9 server
    "http://localhost:3000",  # For development only
    "http://localhost:8000",  # For development only
]
```

### **Phase 2: Build and Deploy**

#### **1. Build Docker Image**
```bash
# Build the secure BitAgent image
docker build -t bitagent:secure .

# Tag for registry (if using external registry)
docker tag bitagent:secure your-registry/bitagent:latest
```

#### **2. Deploy with Docker Compose**
```bash
# Start the service
docker-compose up -d

# Check if it's running
docker-compose ps
docker-compose logs -f bitagent
```

#### **3. Verify Deployment**
```bash
# Check health endpoint
curl http://localhost:8000/health

# Check wallet balance
curl http://localhost:8000/wallet/balance

# Check agent status
curl http://localhost:8000/agents/status
```

### **Phase 3: Generate API Keys**

#### **1. Create API Keys for Your Agents**
```bash
# Run the API key generator
python3 -c "
from src.security.api_key_manager import create_agent_api_key

# Generate keys for each agent
polyglot_key = create_agent_api_key('polyglot_agent', ['read', 'write'])
coordinator_key = create_agent_api_key('coordinator_agent', ['read', 'write'])
streamfinder_key = create_agent_api_key('streamfinder_agent', ['read', 'write'])

print('=== API KEYS GENERATED ===')
print(f'PolyglotAgent: {polyglot_key}')
print(f'CoordinatorAgent: {coordinator_key}')
print(f'StreamfinderAgent: {streamfinder_key}')
print('========================')
"
```

#### **2. Save Your API Keys Securely**
```bash
# Save to secure file
echo "PolyglotAgent: your-polyglot-key" > api_keys.txt
echo "CoordinatorAgent: your-coordinator-key" >> api_keys.txt
echo "StreamfinderAgent: your-streamfinder-key" >> api_keys.txt

# Secure the file
chmod 600 api_keys.txt
```

### **Phase 4: Live Testing**

#### **1. Test Authentication**
```bash
# Test without API key (should fail)
curl -X POST "http://your-start9-server:8000/polyglot/translate" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "source_lang": "en", "target_lang": "es"}'

# Expected: 401 Unauthorized

# Test with API key (should work)
curl -X POST "http://your-start9-server:8000/polyglot/translate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_POLYGLOT_API_KEY" \
  -d '{"text": "Hello world", "source_lang": "en", "target_lang": "es", "payment_hash": "test"}'

# Expected: 402 Payment Required (or service result if payment verified)
```

#### **2. Test Payment Flow**
```bash
# Step 1: Request service without payment
curl -X POST "http://your-start9-server:8000/polyglot/translate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_POLYGLOT_API_KEY" \
  -d '{"text": "Hello world", "source_lang": "en", "target_lang": "es"}'

# Expected: 402 Payment Required with invoice data

# Step 2: Pay the invoice (use your Lightning wallet)
# Copy the payment_request from the response and pay it

# Step 3: Request service with payment hash
curl -X POST "http://your-start9-server:8000/polyglot/translate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_POLYGLOT_API_KEY" \
  -d '{"text": "Hello world", "source_lang": "en", "target_lang": "es", "payment_hash": "PAYMENT_HASH_FROM_STEP_1"}'

# Expected: Translation result
```

#### **3. Test All Agents**
```bash
# Test PolyglotAgent Translation
curl -X POST "http://your-start9-server:8000/polyglot/translate" \
  -H "Authorization: Bearer YOUR_POLYGLOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello", "source_lang": "en", "target_lang": "es", "payment_hash": "test"}'

# Test CoordinatorAgent Task Chaining
curl -X POST "http://your-start9-server:8000/coordinator/chain_tasks" \
  -H "Authorization: Bearer YOUR_COORDINATOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tasks": [{"service": "test", "parameters": {"param": "value"}}], "payment_hash": "test"}'

# Test StreamfinderAgent
curl -X POST "http://your-start9-server:8000/a2a" \
  -H "Content-Type: application/json" \
  -d '{"method": "streamfinder.search", "params": {"query": "Oppenheimer", "payment_hash": "test"}}'
```

### **Phase 5: Production Monitoring**

#### **1. Set Up Monitoring**
```bash
# Monitor logs in real-time
docker-compose logs -f bitagent

# Check system resources
docker stats bitagent

# Monitor wallet balance
watch -n 30 'curl -s http://localhost:8000/wallet/balance | jq'
```

#### **2. Set Up Alerts**
```bash
# Create monitoring script
cat > monitor_bitagent.sh << 'EOF'
#!/bin/bash
while true; do
    # Check if service is running
    if ! curl -f http://localhost:8000/health > /dev/null 2>&1; then
        echo "ALERT: BitAgent service is down!"
        # Send notification (email, Slack, etc.)
    fi
    
    # Check wallet balance
    balance=$(curl -s http://localhost:8000/wallet/balance | jq -r '.balance_sats')
    if [ "$balance" -lt 10000 ]; then
        echo "ALERT: Low wallet balance: $balance sats"
    fi
    
    sleep 60
done
EOF

chmod +x monitor_bitagent.sh
nohup ./monitor_bitagent.sh &
```

### **Phase 6: Security Testing**

#### **1. Run Security Tests**
```bash
# Run the security test suite
python3 test_security_fixes.py

# Test authentication bypass attempts
curl -X POST "http://your-start9-server:8000/polyglot/translate" \
  -H "Content-Type: application/json" \
  -d '{"text": "test"}'
# Should return 401 Unauthorized

# Test CORS
curl -H "Origin: https://malicious-site.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: X-Requested-With" \
  -X OPTIONS \
  http://your-start9-server:8000/polyglot/translate
# Should not include malicious-site.com in CORS headers
```

#### **2. Test Input Validation**
```bash
# Test oversized input
curl -X POST "http://your-start9-server:8000/polyglot/translate" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text": "'$(python3 -c "print('x' * 20000)")'", "source_lang": "en", "target_lang": "es", "payment_hash": "test"}'
# Should return 422 Validation Error
```

### **Phase 7: Production Optimization**

#### **1. Set Up Reverse Proxy (Optional)**
```bash
# Install nginx
sudo apt update && sudo apt install nginx

# Create nginx config
sudo nano /etc/nginx/sites-available/bitagent

# Add configuration:
server {
    listen 80;
    server_name your-start9-server.com;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Enable site
sudo ln -s /etc/nginx/sites-available/bitagent /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### **2. Set Up SSL (Recommended)**
```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d your-start9-server.com

# Update CORS to use HTTPS
# Edit start9_server.py and update CORS origins to use https://
```

### **Phase 8: Backup and Recovery**

#### **1. Set Up Backups**
```bash
# Create backup script
cat > backup_bitagent.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/opt/backups/bitagent"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup API keys
cp api_keys.json $BACKUP_DIR/api_keys_$DATE.json

# Backup logs
cp -r logs $BACKUP_DIR/logs_$DATE

# Backup database (if using)
cp data/bitagent.db $BACKUP_DIR/bitagent_$DATE.db

# Keep only last 7 days of backups
find $BACKUP_DIR -name "*.json" -mtime +7 -delete
find $BACKUP_DIR -name "*.db" -mtime +7 -delete
EOF

chmod +x backup_bitagent.sh

# Add to crontab for daily backups
echo "0 2 * * * /opt/bitagent/backup_bitagent.sh" | crontab -
```

## 🎯 **Quick Start Commands**

```bash
# 1. Deploy
docker-compose up -d

# 2. Generate API keys
python3 -c "from src.security.api_key_manager import create_agent_api_key; print(create_agent_api_key('test_agent', ['read', 'write']))"

# 3. Test authentication
curl -H "Authorization: Bearer YOUR_API_KEY" http://localhost:8000/health

# 4. Test payment flow
curl -X POST "http://localhost:8000/polyglot/translate" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello", "source_lang": "en", "target_lang": "es"}'

# 5. Monitor
docker-compose logs -f bitagent
```

## 🚨 **Troubleshooting**

### **Common Issues:**

1. **Service won't start**: Check logs with `docker-compose logs bitagent`
2. **Authentication fails**: Verify API key format and permissions
3. **Payment not working**: Check LNbits configuration and wallet balance
4. **CORS errors**: Update CORS origins in start9_server.py
5. **File upload fails**: Check file size limits and permissions

### **Debug Commands:**
```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs bitagent

# Check wallet connection
curl http://localhost:8000/wallet/balance

# Test individual endpoints
curl http://localhost:8000/health
curl http://localhost:8000/agents/status
```

## 🎉 **You're Live!**

Your secure BitAgent system is now running on Start9 and ready to collect sats from users worldwide! 

**Monitor your earnings at**: `http://your-start9-server:8000/wallet/balance`

**API Documentation**: `http://your-start9-server:8000/docs`
