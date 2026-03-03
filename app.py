import eventlet
eventlet.monkey_patch()

import os, logging, base64, io
from flask import Flask, request, jsonify, render_template_string, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import google.genai as genai
from google.genai import types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cv-gemini")

# ── SaaS Engine Config (the technology is HIDDEN there) ──
SAAS_REST_URL = "https://wasel-saas-engine-112458895076.europe-west1.run.app/api/v1/translate"
SAAS_API_KEY = os.environ.get("SAAS_API_KEY", "dx_egypt_key_2026")

# ── Gemini for Chat Bot only (client-side feature, NOT translation) ──
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
chat_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
CHAT_MODEL = "gemini-2.0-flash"

CHAT_PROMPT = """أنت موظف خدمة عملاء ذكي ولطيف في شركة "كونيكتا" (Konecta).
تتحدث بالعامية المصرية بأسلوب ودود ومحترف.
المستخدم شخص أصم يتواصل معك عبر لغة الإشارة (تمت ترجمتها لك تلقائياً).
مهمتك:
- افهم طلبه من الجملة المترجمة حتى لو كانت مختصرة أو غير مكتملة.
- رد بإجابة مفيدة ومختصرة (سطر أو سطرين).
- لو الطلب غير واضح، اسأل سؤال بسيط للتوضيح.
- كن إيجابي ومشجع دائماً."""

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet", ping_timeout=60, ping_interval=25)



# ═══════════════════════════════════════════════════════
# HTML Page — Premium UI with Socket.io + SSE Streaming
# ═══════════════════════════════════════════════════════

PAGE = r"""
<!DOCTYPE html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Wasel v4 Pro - Konecta AI Engine</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.socket.io/4.7.4/socket.io.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;font-family:'Cairo',sans-serif;overflow:hidden;height:100vh;display:flex;flex-direction:column;color:#fff;}

/* ── Top Bar ── */
#top-bar{padding:15px 25px;background:linear-gradient(135deg,#111 0%,#1a1a2e 100%);border-bottom:1px solid #222;display:flex;justify-content:space-between;align-items:center;}
#brand{color:#00ff88;font-size:18px;font-weight:700;letter-spacing:1px;text-shadow:0 0 20px rgba(0,255,136,0.15);}
#status{font-size:12px;color:#666;display:flex;align-items:center;gap:8px;}
#ws-dot{width:8px;height:8px;border-radius:50%;background:#ff3333;display:inline-block;transition:background 0.5s;box-shadow:0 0 6px currentColor;}
#ws-dot.on{background:#00ff88;box-shadow:0 0 8px rgba(0,255,136,0.6);}

/* ── Buttons ── */
.btn{padding:8px 20px;font-size:14px;font-weight:bold;border:none;border-radius:20px;cursor:pointer;font-family:inherit;transition:all 0.3s ease;}
#startBtn{background:linear-gradient(135deg,#00ff88,#00cc6a);color:#000;padding:12px 30px;font-size:16px;box-shadow:0 4px 15px rgba(0,255,136,0.3);}
#startBtn:hover{transform:translateY(-2px);box-shadow:0 6px 25px rgba(0,255,136,0.4);}
#startBtn.active{background:linear-gradient(135deg,#ff3333,#cc2222);color:#fff;box-shadow:0 4px 15px rgba(255,51,51,0.3);}

/* ── Main Layout ── */
#main-content{flex:1;display:flex;direction:rtl;}
#video-container{flex:1;position:relative;background:#000;display:flex;flex-direction:column;border-left:1px solid #222;}
video{width:100%;height:100%;object-fit:cover;transform:scaleX(-1)}
#overlay{position:absolute;bottom:0;left:0;right:0;padding:25px;background:linear-gradient(transparent 0%, rgba(0,0,0,0.85) 60%);text-align:center;}

/* ── Live Word with glow animation ── */
#live-word{color:#0ff;font-size:42px;font-weight:700;min-height:60px;transition:all 0.4s cubic-bezier(0.22,1,0.36,1);filter:drop-shadow(0 0 15px rgba(0,255,255,0.2));}
#live-word.flash{animation:wordFlash 0.5s ease;}
@keyframes wordFlash{0%{transform:scale(1.15);filter:drop-shadow(0 0 30px rgba(0,255,255,0.6))}100%{transform:scale(1);filter:drop-shadow(0 0 15px rgba(0,255,255,0.2))}}

/* ── Chat Sidebar ── */
#chat-sidebar{width:400px;background:linear-gradient(180deg,#0d0d1a 0%,#111 100%);display:flex;flex-direction:column;border-right:1px solid #1a1a2e;}
#chat-header{padding:15px 20px;background:#0f0f1f;border-bottom:1px solid #1a1a2e;font-size:14px;color:#8888cc;font-weight:600;display:flex;align-items:center;gap:8px;}
#chat-log{flex:1;padding:20px;overflow-y:auto;display:flex;flex-direction:column;gap:15px;scroll-behavior:smooth;}
#chat-log::-webkit-scrollbar{width:4px;}
#chat-log::-webkit-scrollbar-thumb{background:#333;border-radius:4px;}

/* ── Messages ── */
.msg{padding:14px 18px;border-radius:16px;font-size:15px;line-height:1.7;animation:msgIn 0.4s cubic-bezier(0.22,1,0.36,1);max-width:92%;word-wrap:break-word;}
@keyframes msgIn{from{opacity:0;transform:translateY(12px) scale(0.97)}to{opacity:1;transform:translateY(0) scale(1)}}
.msg.user{background:linear-gradient(135deg,#0a2e1c,#113a29);align-self:flex-start;color:#00ff88;border-top-right-radius:4px;border:1px solid rgba(0,255,136,0.15);box-shadow:0 2px 10px rgba(0,255,136,0.05);}
.msg.bot{background:linear-gradient(135deg,#141430,#1a1a3a);align-self:flex-end;color:#c0d0ff;border-top-left-radius:4px;border:1px solid rgba(68,102,170,0.2);box-shadow:0 2px 10px rgba(68,102,170,0.05);}
.msg.typing{background:#161622;color:#666;border:1px solid #222;display:flex;align-items:center;gap:8px;}
.typing-dots{display:flex;gap:4px;}
.typing-dots span{width:6px;height:6px;background:#555;border-radius:50%;animation:dotBounce 1.4s infinite ease-in-out;}
.typing-dots span:nth-child(2){animation-delay:0.2s;}
.typing-dots span:nth-child(3){animation-delay:0.4s;}
@keyframes dotBounce{0%,80%,100%{transform:scale(0.6);opacity:0.4}40%{transform:scale(1);opacity:1}}

/* ── Composer ── */
#composer{padding:20px;background:#0f0f1a;border-top:1px solid #1a1a2e;display:flex;flex-direction:column;gap:12px;}
#sentenceBox{width:100%;padding:14px 18px;background:#0a0a14;border:1px solid #2a2a44;color:#fff;border-radius:12px;font-family:inherit;font-size:16px;outline:none;transition:all 0.3s;}
#sentenceBox:focus{border-color:#00ff88;box-shadow:0 0 15px rgba(0,255,136,0.1);}
#sentenceBox::placeholder{color:#444;}
#sendBtn{background:linear-gradient(135deg,#1a1a3a,#2a2a5a);color:#8888cc;padding:12px;border-radius:12px;border:1px solid #2a2a44;font-family:inherit;font-size:14px;font-weight:600;cursor:pointer;transition:all 0.3s;}
#sendBtn:hover{background:linear-gradient(135deg,#00cc6a,#00ff88);color:#000;border-color:transparent;transform:translateY(-1px);box-shadow:0 4px 15px rgba(0,255,136,0.3);}
#sendBtn:disabled{background:#111;color:#333;cursor:not-allowed;transform:none;box-shadow:none;border-color:#1a1a1a;}

/* ── Performance Badge ── */
#perf-badge{position:absolute;top:15px;left:15px;padding:6px 14px;background:rgba(0,0,0,0.7);border:1px solid #333;border-radius:20px;font-size:11px;color:#888;backdrop-filter:blur(4px);}
</style></head><body dir="rtl">

<div id="top-bar">
    <div id="brand">WASEL v4 PRO — KONECTA AI ENGINE</div>
    <div id="status"><span id="ws-dot"></span> <span id="status-text">جاري الاتصال...</span></div>
</div>

<div id="main-content">
    <div id="chat-sidebar">
        <div id="chat-header">💬 محادثة خدمة العملاء</div>
        <div id="chat-log">
            <div class="msg bot">أهلاً بيك! 👋 أنا مساعدك الذكي من كونيكتا. ابدأ بالإشارة وهجمّع الكلام، وبعدين ابعته وهرد عليك فوراً!</div>
        </div>
        <div id="composer">
            <input type="text" id="sentenceBox" placeholder="الترجمة هتتجمع هنا... عدّلها لو حبيت ثم اضغط إرسال">
            <button class="btn" id="sendBtn" onclick="sendToChat()">📨 إرسال الجملة للشات</button>
        </div>
    </div>
    
    <div id="video-container">
        <div id="perf-badge">⚡ <span id="perf-ms">—</span>ms</div>
        <video id="v" autoplay playsinline muted></video>
        <div id="overlay">
            <div id="live-word">في انتظار الكاميرا...</div>
            <button class="btn" id="startBtn" onclick="goLoop()">▶ تشغيل الترجمة</button>
        </div>
    </div>
</div>

<canvas id="cv" style="display:none"></canvas>

<script>
// ═══ Socket.io Connection to our Backend (which proxies to SaaS) ═══
var socket = io({transports: ['websocket', 'polling'], reconnection: true, reconnectionDelay: 1000, reconnectionAttempts: 10});

var v=document.getElementById('v'), cv=document.getElementById('cv');
var cx=cv.getContext('2d', {willReadFrequently: true});
var tx=document.getElementById('live-word');
var stText=document.getElementById('status-text');
var wsDot=document.getElementById('ws-dot');
var btn=document.getElementById('startBtn');
var sentenceBox=document.getElementById('sentenceBox');
var chatLog=document.getElementById('chat-log');
var sendBtnEl=document.getElementById('sendBtn');
var perfMs=document.getElementById('perf-ms');

var busy=false, running=false, lastImageData=null, lastWord='';
var frameStartTime=0;

// ═══ WebSocket Events ═══
socket.on('connect', function() {
    wsDot.classList.add('on');
    stText.textContent = 'متصل ⚡';
    console.log('WS connected');
});

socket.on('disconnect', function() {
    wsDot.classList.remove('on');
    stText.textContent = 'غير متصل — جاري إعادة الاتصال...';
});

socket.on('reconnect', function() {
    wsDot.classList.add('on');
    stText.textContent = 'متصل ⚡';
});

socket.on('translation_result', function(data) {
    var t = data.translation || '...';
    var ms = data.roundtrip_ms || data.processing_time_ms || 0;
    
    perfMs.textContent = ms || Math.round(performance.now() - frameStartTime);
    
    if(t === '...' || t.length < 2) {
        tx.textContent = 'قم بعمل إشارة...';
        tx.style.color = '#aaa';
    } else {
        if (t !== lastWord) {
            tx.textContent = t;
            tx.style.color = '#0ff';
            tx.classList.remove('flash');
            void tx.offsetWidth; // trigger reflow
            tx.classList.add('flash');
            lastWord = t;
            
            // Accumulate in sentence box
            var currentParts = sentenceBox.value.split(' ');
            var lastPart = currentParts.length > 0 ? currentParts[currentParts.length - 1] : '';
            if (t !== lastPart) {
                sentenceBox.value = sentenceBox.value ? sentenceBox.value + ' ' + t : t;
            }
        }
    }
    
    stText.textContent = '⚡ ' + new Date().toLocaleTimeString();
    busy = false;
    if(running) setTimeout(go, 30);
});

// ═══ Camera Setup ═══
navigator.mediaDevices.getUserMedia({video:{width:320,height:240,facingMode:'user'}})
.then(function(s){v.srcObject=s;tx.textContent='الكاميرا جاهزة. اضغط تشغيل ▶';tx.style.color='#aaa';})
.catch(function(e){tx.textContent='خطأ بالكاميرا: '+e.message;});

// ═══ Translation Loop ═══
function goLoop() {
    if(!running) {
        running = true;
        btn.textContent = "⏹ إيقاف الترجمة";
        btn.classList.add('active');
        tx.textContent = 'قم بعمل إشارة...';
        tx.style.color = '#aaa';
        go();
    } else {
        running = false;
        btn.textContent = "▶ تشغيل الترجمة";
        btn.classList.remove('active');
        tx.textContent = 'الترجمة متوقفة';
        tx.style.color = '#aaa';
    }
}

function hasMotion(currentData, previousData) {
    if (!previousData) return true;
    var diffCount = 0, thresh = 35;
    for (var i = 0; i < currentData.data.length; i += 16) {
        if (Math.abs(currentData.data[i] - previousData.data[i]) > thresh ||
            Math.abs(currentData.data[i+1] - previousData.data[i+1]) > thresh ||
            Math.abs(currentData.data[i+2] - previousData.data[i+2]) > thresh) {
            diffCount++;
        }
    }
    return diffCount > (currentData.data.length / 16) * 0.015; 
}

function go(){
    if(!running) return;
    if(busy) { setTimeout(go, 50); return; }
    
    cv.width=320;cv.height=240;
    cx.drawImage(v,0,0,320,240);
    
    var currentImageData = cx.getImageData(0, 0, 320, 240);
    var motionDetected = hasMotion(currentImageData, lastImageData);
    lastImageData = currentImageData;
    
    if (!motionDetected) {
        stText.textContent = "سكون (لا توجد حركة)...";
        setTimeout(go, 80);
        return;
    }

    busy=true;
    frameStartTime = performance.now();
    var d=cv.toDataURL('image/webp',0.3);
    stText.textContent='⚡ جاري التحليل...';
    
    // Send via WebSocket (zero-overhead persistent connection!)
    if (socket.connected) {
        socket.emit('frame', {image: d});
    } else {
        // Fallback to HTTP if WebSocket is down
        fetch('/proxy_translate', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({image:d})
        })
        .then(function(r){
            if(r.status === 204) return {translation:'...'};
            return r.json();
        })
        .then(function(data){
            // Simulate WS result for uniform handling
            socket.emit = socket.emit; // no-op, just use direct
            var t = data.translation || '...';
            if(t === '...' || t.length < 2) {
                tx.textContent = 'قم بعمل إشارة...';
                tx.style.color = '#aaa';
            } else {
                tx.textContent = t;
                tx.style.color = '#0ff';
                var currentParts = sentenceBox.value.split(' ');
                var lastPart = currentParts[currentParts.length - 1] || '';
                if (t !== lastPart) sentenceBox.value = sentenceBox.value ? sentenceBox.value + ' ' + t : t;
            }
            busy = false;
            if(running) setTimeout(go, 50);
        })
        .catch(function(e){stText.textContent='خطأ: '+e;busy=false;if(running) setTimeout(go, 500);});
    }
}

// ═══ Chat with Streaming (SSE) ═══
function addMsg(text, who) {
    var div = document.createElement('div');
    div.className = 'msg ' + who;
    if (who === 'typing') {
        div.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div> جاري الكتابة...';
    } else {
        div.textContent = text;
    }
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
    return div;
}

function sendToChat() {
    var text = sentenceBox.value.trim();
    if(!text) return;
    
    addMsg('🤟 ' + text, 'user');
    sentenceBox.value = '';
    
    sendBtnEl.disabled = true;
    sendBtnEl.textContent = '⏳ جاري الرد...';
    var typingMsg = addMsg('', 'typing');
    
    // Use REST /chat with client-side typing animation
    fetch('/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({text: text})
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
        if (typingMsg.parentNode) chatLog.removeChild(typingMsg);
        if (d.reply) {
            // Word-by-word typing animation for premium feel
            var words = d.reply.split(' ');
            var botMsg = addMsg('🤖 ', 'bot');
            var i = 0;
            function typeWord() {
                if (i < words.length) {
                    botMsg.textContent += (i > 0 ? ' ' : '') + words[i];
                    chatLog.scrollTop = chatLog.scrollHeight;
                    i++;
                    setTimeout(typeWord, 40);
                }
            }
            typeWord();
        }
    })
    .catch(function(e) {
        if (typingMsg.parentNode) chatLog.removeChild(typingMsg);
        addMsg('🤖 حصل مشكلة تقنية، جرب تاني.', 'bot');
    })
    .finally(function() {
        sendBtnEl.disabled = false;
        sendBtnEl.textContent = '📨 إرسال الجملة للشات';
    });
}

// Allow Enter key to send
document.getElementById('sentenceBox').addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendToChat();
    }
});
</script></body></html>
"""

# ═══════════════════════════════════════════════════════
# Flask Routes
# ═══════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template_string(PAGE)

@app.route('/proxy_translate', methods=['POST'])
def proxy_translate():
    """REST fallback: receives image from frontend, forwards to SaaS engine via HTTP."""
    import requests as http_req
    try:
        data = request.json
        image_data = data.get('image', '')
        
        saas_response = http_req.post(
            SAAS_REST_URL,
            json={"images_base64": [image_data]},
            headers={"X-API-Key": SAAS_API_KEY, "Content-Type": "application/json"},
            timeout=6
        )
        
        if saas_response.status_code == 204:
            return "", 204
        elif saas_response.status_code == 200:
            return jsonify(saas_response.json()), 200
        else:
            logger.error(f"SaaS returned {saas_response.status_code}")
            return jsonify({"translation": "..."}), 200
            
    except Exception as e:
        logger.error(f"Proxy error: {e}")
        return jsonify({"translation": "..."}), 200

@app.route('/chat', methods=['POST'])
def chat():
    """Non-streaming chat fallback."""
    if not chat_client:
        return jsonify({'reply': 'مفتاح API مفقود'}), 500
        
    try:
        user_text = request.json.get('text', '')
        if not user_text:
            return jsonify({'reply': 'لم أفهم، ممكن تعيد الإشارة؟'})
        
        r = chat_client.models.generate_content(
            model=CHAT_MODEL,
            contents=[CHAT_PROMPT, f"المستخدم قال (عبر لغة الإشارة): {user_text}"],
            config=types.GenerateContentConfig(max_output_tokens=150, temperature=0.7)
        )
        return jsonify({'reply': r.text.strip()})
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return jsonify({'reply': 'حصل مشكلة تقنية، جرب تاني.'})

@app.route('/chat_stream')
def chat_stream():
    """SSE streaming chat — words appear one by one like ChatGPT."""
    import json as json_mod
    
    if not chat_client:
        def err():
            yield f"data: {json_mod.dumps({'chunk': 'مفتاح API مفقود', 'done': True})}\n\n"
        return Response(err(), mimetype='text/event-stream')
    
    user_text = request.args.get('text', '')
    if not user_text:
        def err():
            yield f"data: {json_mod.dumps({'chunk': 'لم أفهم، ممكن تعيد الإشارة؟', 'done': True})}\n\n"
        return Response(err(), mimetype='text/event-stream')
    
    def generate():
        contents = [CHAT_PROMPT, f"المستخدم قال (عبر لغة الإشارة): {user_text}"]
        config = types.GenerateContentConfig(max_output_tokens=150, temperature=0.7)
        
        try:
            # Try streaming first (generate_content_stream)
            try:
                response = chat_client.models.generate_content_stream(
                    model=CHAT_MODEL,
                    contents=contents,
                    config=config
                )
                for chunk in response:
                    if chunk.text:
                        yield f"data: {json_mod.dumps({'chunk': chunk.text})}\n\n"
                yield f"data: {json_mod.dumps({'done': True})}\n\n"
                return
            except AttributeError:
                pass  # Method doesn't exist in this version, fall through
            
            # Fallback: non-streaming, send full reply at once
            r = chat_client.models.generate_content(
                model=CHAT_MODEL,
                contents=contents,
                config=config
            )
            reply = r.text.strip() if r.text else "لم أفهم، ممكن تعيد تاني؟"
            yield f"data: {json_mod.dumps({'chunk': reply})}\n\n"
            yield f"data: {json_mod.dumps({'done': True})}\n\n"
            
        except Exception as e:
            logger.error(f"Stream chat error: {e}")
            yield f"data: {json_mod.dumps({'chunk': 'حصل مشكلة تقنية، جرب تاني.', 'done': True})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no'
    })

# ═══════════════════════════════════════════════════════
# WebSocket Events (Browser ↔ Client Backend ↔ SaaS)
# ═══════════════════════════════════════════════════════

@socketio.on('connect')
def handle_connect():
    logger.info("Browser WebSocket connected")
    emit('status', {'connected': True})

@socketio.on('frame')
def handle_frame(data):
    """Receive frame from browser via WS, forward to SaaS Engine via ultra-fast REST, return via WS."""
    import time, requests as http_req
    start = time.time()
    
    image = data.get('image', '') if isinstance(data, dict) else ''
    if not image:
        emit('translation_result', {'translation': '...'})
        return
    
    try:
        # Server-to-Server REST (safe, ultra-fast ~2-10ms within same cloud region, no race conditions)
        saas_response = http_req.post(
            SAAS_REST_URL,
            json={"images_base64": [image]},
            headers={"X-API-Key": SAAS_API_KEY, "Content-Type": "application/json"},
            timeout=5
        )
        
        ms = int((time.time() - start) * 1000)
        
        if saas_response.status_code == 204:
            emit('translation_result', {'translation': '...', 'roundtrip_ms': ms})
        elif saas_response.status_code == 200:
            result = saas_response.json()
            result['roundtrip_ms'] = ms
            emit('translation_result', result)
        else:
            logger.warning(f"SaaS Engine returned status {saas_response.status_code}")
            emit('translation_result', {'translation': '...', 'roundtrip_ms': ms})
            
    except Exception as e:
        logger.error(f"SaaS connection error: {e}")
        emit('translation_result', {'translation': '...'})

@socketio.on('disconnect')
def handle_disconnect():
    logger.info("Browser WebSocket disconnected")

# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    socketio.run(app, host="0.0.0.0", port=port, debug=False)
