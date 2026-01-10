"""
# Setting Up ngrok for Live GitHub Webhooks

## 1. Install ngrok
```bash
# macOS
brew install ngrok

# Or download from https://ngrok.com/download
```

## 2. Start your server
```bash
uvicorn app.main:app --reload --port 8000
```

## 3. Start ngrok tunnel
```bash
ngrok http 8000
```

You'll see output like:
```
Forwarding  https://abc123.ngrok.io -> http://localhost:8000
```

## 4. Configure GitHub Webhook

1. Go to your repo → Settings → Webhooks → Add webhook
2. Payload URL: `https://abc123.ngrok.io/webhook/github`
3. Content type: `application/json`
4. Secret: (set in your .env as GITHUB_WEBHOOK_SECRET)
5. Events: Select "Pull requests"
6. Save

## 5. Test It

1. Create or update a PR in your repo
2. Watch ngrok terminal for incoming request
3. Watch your server logs for processing
4. Check the PR for the posted review!

## Troubleshooting

- **401 Unauthorized**: Check webhook secret matches .env
- **No request received**: Verify ngrok URL in webhook config
- **Timeout**: Increase timeout or check Gemini API key
"""