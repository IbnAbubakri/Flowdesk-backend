/**
 * FlowDesk WhatsApp Bridge (Cloud-ready)
 * Uses pairing code instead of QR — works on Render/Railway/VPS
 *
 * Usage: node bridge.js [phone_number]
 *   phone_number: International format without +, e.g. 234801234567
 *   If omitted, a pairing code will be displayed in logs
 */

const { makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require('@whiskeysockets/baileys');
const http = require('http');
const fs = require('fs');
const path = require('path');

const API_URL = process.env.FLOWDESK_API || process.env.API_URL || 'http://localhost:3001';
const SESSION_DIR = process.env.AUTH_DIR || path.join(__dirname, 'auth_info');
const PAIRING_CODE = process.env.PAIRING_PHONE || process.argv[2] || '';

if (!fs.existsSync(SESSION_DIR)) fs.mkdirSync(SESSION_DIR, { recursive: true });

function postToAPI(from, text, name) {
  const data = JSON.stringify({ from, text, name });
  return new Promise((resolve, reject) => {
    const url = new URL('/api/webhook/whatsapp', API_URL);
    const options = {
      hostname: url.hostname,
      port: url.port,
      path: url.pathname,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) },
    };
    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', (chunk) => (body += chunk));
      res.on('end', () => { try { resolve(JSON.parse(body)); } catch { resolve(null); } });
    });
    req.on('error', reject);
    req.write(data);
    req.end();
  });
}

async function start() {
  const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR);
  const { version } = await fetchLatestBaileysVersion();

  const sock = makeWASocket({
    version,
    auth: state,
    printQRInTerminal: false,
    syncFullHistory: false,
    markOnlineOnConnect: false,
    browser: ['FlowDesk AI', 'Chrome', '1.0'],
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async ({ connection, lastDisconnect }) => {
    if (connection === 'open') {
      console.log('✅ WhatsApp connected!');
      if (PAIRING_CODE) {
        console.log(`Pairing with ${PAIRING_CODE}...`);
        try {
          const code = await sock.requestPairingCode(PAIRING_CODE);
          console.log(`\n📱 Pairing code: ${code}\n`);
          console.log('Open WhatsApp → Linked Devices → Link a device → Enter this code');
        } catch (e) {
          console.error('Pairing failed:', e.message);
        }
      }
    }
    if (connection === 'close') {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const reason = lastDisconnect?.error?.output?.payload?.description || statusCode;
      console.log(`Disconnected (${reason}). Reconnecting in 3s...`);
      setTimeout(() => start(), 3000);
    }
  });

  sock.ev.on('messages.upsert', async ({ messages }) => {
    for (const msg of messages) {
      if (!msg.key || msg.key.fromMe) continue;
      if (msg.key.remoteJid.endsWith('@g.us')) continue;
      const text = msg.message?.conversation || msg.message?.extendedTextMessage?.text || '';
      if (!text.trim()) continue;

      const phone = msg.key.remoteJid.replace('@s.whatsapp.net', '');
      const pushName = msg.pushName || phone;
      console.log(`📩 ${pushName}: ${text.slice(0, 80)}`);

      try {
        const result = await postToAPI(phone, text, pushName);
        if (result?.reply) {
          await sock.sendMessage(msg.key.remoteJid, { text: result.reply });
          console.log(`✅ Replied: ${result.reply.slice(0, 60)}...`);
        }
      } catch (err) {
        console.error('❌ Error:', err.message);
      }
    }
  });
}

start().catch((e) => {
  console.error('Fatal:', e);
  process.exit(1);
});
