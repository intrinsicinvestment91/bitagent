#!/bin/bash

# BitAgent Start9 Deployment Script
# This script helps deploy BitAgent to your Start9 server

set -e

echo "🚀 BitAgent Start9 Deployment Script"
echo "====================================="

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo "📋 Please copy env.template to .env and configure your settings:"
    echo "   cp env.template .env"
    echo "   nano .env"
    exit 1
fi

# Load environment variables
source .env

# Validate required environment variables
if [ -z "$LNBITS_URL" ] || [ -z "$LNBITS_API_KEY" ]; then
    echo "❌ Missing required LNbits configuration!"
    echo "   Please set LNBITS_URL and LNBITS_API_KEY in .env"
    exit 1
fi

if [ -z "$START9_NODE_ID" ]; then
    echo "❌ Missing START9_NODE_ID!"
    echo "   Please set your Start9 node ID in .env"
    exit 1
fi

echo "✅ Environment configuration validated"

# Build Docker image
echo "🔨 Building Docker image..."
docker build -t bitagent:latest .

# Test the image locally
echo "🧪 Testing Docker image..."
docker run --rm -d --name bitagent-test \
    -p 8000:8000 \
    --env-file .env \
    bitagent:latest

# Wait for service to start
echo "⏳ Waiting for service to start..."
sleep 10

# Test health endpoint
echo "🏥 Testing health endpoint..."
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Service is healthy!"
else
    echo "❌ Service health check failed!"
    docker logs bitagent-test
    docker stop bitagent-test
    exit 1
fi

# Test wallet balance endpoint
echo "💰 Testing wallet connection..."
if curl -f http://localhost:8000/wallet/balance > /dev/null 2>&1; then
    echo "✅ Wallet connection successful!"
else
    echo "⚠️  Wallet connection failed - check your LNbits configuration"
fi

# Stop test container
docker stop bitagent-test

echo ""
echo "🎉 BitAgent is ready for Start9 deployment!"
echo ""
echo "📋 Next steps:"
echo "1. Push your Docker image to a registry:"
echo "   docker tag bitagent:latest your-registry/bitagent:latest"
echo "   docker push your-registry/bitagent:latest"
echo ""
echo "2. Create a Start9 service package with:"
echo "   - manifest.yaml (see START9_DEPLOYMENT_GUIDE.md)"
echo "   - Your Docker image"
echo "   - Environment configuration"
echo ""
echo "3. Install on your Start9 server"
echo ""
echo "💰 Your agents will collect sats for:"
echo "   - PolyglotAgent: Translation (100 sats), Transcription (250 sats)"
echo "   - CoordinatorAgent: Audio translation (350 sats), Task chaining (100 sats)"
echo "   - StreamfinderAgent: Movie search (100 sats)"
echo ""
echo "📡 Monitor payments at: http://your-start9-server:8000/wallet/balance"
