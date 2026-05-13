# WhatsApp Setup Guide

This guide walks through everything needed to connect the PostHarvest chatbot to WhatsApp — both the steps inside this app and the (more numerous) steps in Meta's developer platform.

---

## Background: how this integration works

WhatsApp messaging for businesses runs through Meta's **WhatsApp Business Platform (Cloud API)**. Your app does not talk to WhatsApp directly — it talks to Meta's servers, which relay messages to and from WhatsApp users.

The data flow looks like this:

```
User sends WhatsApp message
       │
       ▼
  Meta's servers
       │  POST /webhook/whatsapp
       ▼
  Your FastAPI server  ──►  RAG pipeline  ──►  Meta Graph API  ──►  User receives reply
```

Two credentials make this work:
- **WhatsApp Token** — proves to Meta that your server is authorised to send messages on behalf of your business phone number.
- **Verify Token** — a string you invent; Meta sends it to you during webhook registration to confirm you own the endpoint.

---

## Part 1: Meta setup (external steps)

### Step 1 — Create a Meta developer account

If you do not already have one, go to [developers.facebook.com](https://developers.facebook.com) and sign up. You need a personal Facebook account to do this (it is just used for identity — your users will never see it).

### Step 2 — Create a Meta Business Portfolio

WhatsApp for business requires a **Meta Business Portfolio** (previously called "Business Manager").

1. Go to [business.facebook.com](https://business.facebook.com)
2. Click **Create account** and fill in your business name and contact details
3. Verify your email address

> This is separate from a personal Facebook account. Think of it as a container that holds your business's WhatsApp number, ad accounts, and apps.

### Step 3 — Create a Meta app

1. In the [Meta Developer portal](https://developers.facebook.com), go to **My Apps → Create App**
2. Select **Business** as the app type
3. Give it a name (e.g. "PostHarvest AI"), enter your email, and link it to the Business Portfolio you created in Step 2
4. Click **Create App**

### Step 4 — Add the WhatsApp product

On your new app's dashboard:

1. Scroll down to the product list and find **WhatsApp**
2. Click **Set up**
3. Select (or create) a **WhatsApp Business Account (WABA)** when prompted

A WhatsApp Business Account is the official business entity on WhatsApp. If you are new, click **Create a new WhatsApp Business Account** and follow the prompts. You will need to enter your business's legal name and country.

### Step 5 — Get your test phone number and Phone Number ID

After adding WhatsApp, you will be taken to the **API Setup** page. Here you will see:

- A **test phone number** provided by Meta — this is a temporary number you can use to send yourself test messages before you register a real business number
- A **Phone Number ID** — a numeric string (looks like `123456789012345`) — **copy this, you will need it**

The test number lets you send messages to up to 5 pre-approved recipient numbers (your own phone) during development. You do not need a real business phone for initial testing.

### Step 6 — Add a test recipient phone number

Still on the API Setup page:

1. Under **Send and receive messages → To**, click **Manage phone number list**
2. Add your own WhatsApp phone number (in international format, e.g. `+256700000000`)
3. WhatsApp will send you a verification code — enter it to confirm

You can now receive test messages from the test number.

### Step 7 — Generate a permanent access token

The API Setup page gives you a **temporary token** that expires in 24 hours. For production you need a permanent one. The right way to do this is via a **System User**:

1. Go to your Business Portfolio at [business.facebook.com](https://business.facebook.com)
2. Navigate to **Settings → Users → System users**
3. Click **Add** → name it something like "postharvest-api", set role to **Admin**
4. Click **Generate new token**
5. Select your Meta app from the dropdown
6. Grant these permissions: `whatsapp_business_messaging`, `whatsapp_business_management`
7. Set token expiry to **Never**
8. Click **Generate token** and **copy it immediately** — you cannot view it again

> Never share this token. Treat it like a password. If it leaks, revoke it from the System Users page and generate a new one.

### Step 8 — Register a real phone number (production only)

The test number is fine for development. When you are ready for real users:

1. In the Meta Developer portal → WhatsApp → Phone numbers → **Add phone number**
2. You will need a phone number that:
   - Is not already registered on personal WhatsApp
   - Can receive an SMS or voice call for verification
3. You will go through **Business Verification** — Meta will ask for your business registration documents. This can take a few days.

> Until business verification is complete, you are limited to messaging the 5 pre-approved test recipients only.

---

## Part 2: Application setup

### Step 9 — Set environment variables

Add these four values to your `.env` file (or Dokku config):

```bash
WHATSAPP_TOKEN=your-permanent-token-from-step-7
WHATSAPP_PHONE_NUMBER_ID=your-phone-number-id-from-step-5
WHATSAPP_VERIFY_TOKEN=any-string-you-choose
WHATSAPP_APP_SECRET=your-app-secret
```

`WHATSAPP_VERIFY_TOKEN` is a secret string you invent. It can be anything — e.g. `postharvest-webhook-2024`. Write it down; you will enter it in the Meta portal in the next step.

`WHATSAPP_APP_SECRET` is found in the Meta Developer portal under your app's **Settings → Basic → App Secret**. Click **Show** and copy the value. This is used to verify that every webhook request genuinely comes from Meta — without it, anyone who discovers your webhook URL can send fake messages to your system.

### Step 10 — Make sure your server is publicly reachable over HTTPS

Meta's servers need to reach your webhook endpoint at:

```
https://your-domain.com/webhook/whatsapp
```

Requirements:
- **HTTPS is mandatory** — Meta will not send webhooks to plain HTTP
- The URL must be reachable from the internet (not `localhost`)
- The SSL certificate must be valid (not self-signed)

For local development, use a tunnel tool like [ngrok](https://ngrok.com):

```bash
ngrok http 8000
# Gives you a URL like https://abc123.ngrok.io
# Use https://abc123.ngrok.io/webhook/whatsapp as your callback URL
```

For production deployment (Dokku), follow the HTTPS setup in [DEPLOYMENT.md](DEPLOYMENT.md) — Dokku + Let's Encrypt handles this automatically.

### Step 11 — Register the webhook in Meta

1. In the Meta Developer portal → Your app → WhatsApp → **Configuration**
2. Under **Webhook**, click **Edit**
3. Fill in:
   - **Callback URL**: `https://your-domain.com/webhook/whatsapp`
   - **Verify token**: the string you set as `WHATSAPP_VERIFY_TOKEN`
4. Click **Verify and Save**

Meta will immediately make a GET request to your endpoint with the verify token. Your app will check it matches and return the challenge value. If it succeeds, you will see a green tick.

5. Under **Webhook fields**, find `messages` and click **Subscribe**

Without subscribing to `messages`, Meta will not forward inbound messages to your webhook.

### Step 12 — Test it end to end

Send a WhatsApp message from your personal phone to the test phone number. Within a few seconds you should receive a reply from the RAG pipeline.

Check your API logs if no reply arrives:

```bash
# Docker Compose (local)
docker compose logs api -f

# Dokku (production)
dokku logs postharvest-api -t
```

---

## Part 3: Important limits and rules to know

### The 24-hour messaging window

WhatsApp enforces a strict rule: **your bot can only reply to a user within 24 hours of their last message**. If a user messages you and you do not reply within 24 hours, you cannot send them anything until they message again.

This means:
- The current integration (reply-only) works fine — you only ever respond to inbound messages
- You cannot proactively message users (e.g. send a daily tip) without using **Message Templates**

### Message Templates

If you ever want to send messages to users outside the 24-hour window, or send the first message to a user who has never messaged you, you need **approved Message Templates**. These are pre-written message formats that Meta reviews and approves. They are not needed for the current reply-only use case.

### Message length

WhatsApp has a 4096 character limit per message. The RAG pipeline may occasionally generate longer answers. If an answer exceeds this limit, the API call to Meta will fail — the user will receive no reply. Watch your logs for `WhatsApp API error` entries.

### Rate limits

The app enforces **30 messages per hour per phone number**. Users who exceed this will receive an HTTP 429 response from the API (which means no reply to their WhatsApp message — they will not see an error).

Meta itself also has rate limits on the number of messages you can send per second; for low-volume usage this is not a concern.

### Response time

Meta expects your webhook to return a 200 response within **20 seconds**. The RAG pipeline (embedding + vector search + LLM generation) typically completes in 3–8 seconds under normal conditions, but could be slower if OpenAI is under load. Monitor response times in your logs.

---

## Environment variable reference

| Variable | Required | What it is |
|---|---|---|
| `WHATSAPP_TOKEN` | Yes (for WhatsApp) | Permanent System User token from Meta |
| `WHATSAPP_PHONE_NUMBER_ID` | Yes (for WhatsApp) | Numeric ID of your WhatsApp phone number |
| `WHATSAPP_VERIFY_TOKEN` | Yes (for WhatsApp) | Secret string you choose; entered in Meta portal |
| `WHATSAPP_APP_SECRET` | Strongly recommended | Meta App Secret (Settings → Basic → App Secret) — enables webhook signature verification |

The app starts without these variables — it just means the WhatsApp webhook will not authenticate or send replies.
