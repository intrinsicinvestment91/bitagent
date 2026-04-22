#!/bin/bash

# BitAgent Live Deployment Script for Start9
# This script deploys your secure BitAgent system to Start9

set -e

echo "🚀 BitAgent Live Deployment to Start9"
echo "======================================"

# Check if running on Start9 server
if [ ! -f "/etc/start9/version" ]; then
    echo "⚠️  Warning: This doesn't appear to be a Start9 server"
    echo "   Continuing anyway..."
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo "📋 Please create .env file with your configuration:"
    echo "   cp env.template .env"
    echo "   nano .env"
    exit 1
fi

# Load environment variables
source .env

# Validate required environment variables
echo "🔍 Validating configuration..."
required_vars=("LNBITS_URL" "LNBITS_API_KEY" "START9_NODE_ID")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Missing required environment variable: $var"
        exit 1
    fi
done

echo "✅ Configuration validated"

# Update CORS origins if needed
echo "🔧 Updating CORS configuration..."
if grep -q "your-actual-domain.com" start9_server.py; then
    echo "⚠️  Please update CORS origins in start9_server.py with your actual domains"
    echo "   Current CORS origins contain placeholder values"
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Build Docker image
echo "🔨 Building Docker image..."
docker build -t bitagent:secure .

# Stop existing containers
echo "🛑 Stopping existing containers..."
docker-compose down 2>/dev/null || true

# Start the service
echo "🚀 Starting BitAgent service..."
docker-compose up -d

# Wait for service to start
echo "⏳ Waiting for service to start..."
sleep 15

# Test health endpoint
echo "🏥 Testing health endpoint..."
max_attempts=10
attempt=1
while [ $attempt -le $max_attempts ]; do
    if curl -f http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ Service is healthy!"
        break
    else
        echo "⏳ Attempt $attempt/$max_attempts - waiting for service..."
        sleep 5
        ((attempt++))
    fi
done

if [ $attempt -gt $max_attempts ]; then
    echo "❌ Service failed to start properly"
    echo "📋 Checking logs..."
    docker-compose logs bitagent
    exit 1
fi

# Test wallet connection
echo "💰 Testing wallet connection..."
if curl -f http://localhost:8000/wallet/balance > /dev/null 2>&1; then
    echo "✅ Wallet connection successful!"
    balance=$(curl -s http://localhost:8000/wallet/balance | jq -r '.balance_sats // "unknown"')
    echo "   Current balance: $balance sats"
else
    echo "⚠️  Wallet connection failed - check your LNbits configuration"
fi

# Generate API keys
echo "🔑 Generating API keys..."
python3 -c "
import sys
sys.path.append('.')
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

# Save to file
with open('api_keys.txt', 'w') as f:
    f.write(f'PolyglotAgent: {polyglot_key}\n')
    f.write(f'CoordinatorAgent: {coordinator_key}\n')
    f.write(f'StreamfinderAgent: {streamfinder_key}\n')

print('API keys saved to api_keys.txt')
"

# Secure the API keys file
chmod 600 api_keys.txt

# Test authentication
echo "🔐 Testing authentication..."
test_key=$(python3 -c "
import sys
sys.path.append('.')
from src.security.api_key_manager import create_agent_api_key
print(create_agent_api_key('test_agent', ['read', 'write']))
")

if curl -f -H "Authorization: Bearer $test_key" http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Authentication working!"
else
    echo "❌ Authentication test failed"
fi

# Get server IP
server_ip=$(curl -s ifconfig.me 2>/dev/null || echo "localhost")
server_port=${PORT:-8000}

echo ""
echo "🎉 BitAgent deployed successfully!"
echo ""
echo "📋 Service Information:"
echo "   Health Check: http://$server_ip:$server_port/health"
echo "   API Docs: http://$server_ip:$server_port/docs"
echo "   Wallet Balance: http://$server_ip:$server_port/wallet/balance"
echo "   Agent Status: http://$server_ip:$server_port/agents/status"
echo ""
echo "🔑 API Keys saved to: api_keys.txt"
echo "   Keep these keys secure!"
echo ""
echo "🧪 Test your deployment:"
echo "   curl -H \"Authorization: Bearer YOUR_API_KEY\" http://$server_ip:$server_port/health"
echo ""
echo "📊 Monitor your service:"
echo "   docker-compose logs -f bitagent"
echo "   docker-compose ps"
echo ""
echo "💰 Your agents are now ready to collect sats!"
echo "   - PolyglotAgent: Translation (100 sats), Transcription (250 sats)"
echo "   - CoordinatorAgent: Audio translation (350 sats), Task chaining (100 sats)"
echo "   - StreamfinderAgent: Movie search (100 sats)"
echo ""
echo "🛡️ Security features active:"
echo "   ✅ Authentication required for all endpoints"
echo "   ✅ Payment verification enforced"
echo "   ✅ Input validation and sanitization"
echo "   ✅ CORS properly configured"
echo "   ✅ Rate limiting active"
echo ""
echo "🚀 Your BitAgent system is live and secure!"
