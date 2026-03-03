import os, logging
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import requests as http_req
import google.genai as genai
from google.genai import types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cv-gemini")

# ── SaaS Engine Config (the technology is HIDDEN there) ──
SAAS_URL = "https://wasel-saas-engine-112458895076.europe-west1.run.app/api/v1/translate"
SAAS_API_KEY = "dx_egypt_key_2026"

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

PAGE = r"""
<!DOCTYPE html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Wasel v4 Pro - Konecta AI Engine</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;font-family:'Cairo',sans-serif;overflow:hidden;height:100vh;display:flex;flex-direction:column;color:#fff;}
#top-bar{padding:15px 25px;background:#1a1a1a;border-bottom:1px solid #333;display:flex;justify-content:space-between;align-items:center;}
#brand{color:#00ff88;font-size:18px;font-weight:700;letter-spacing:1px;}
.btn{padding:8px 20px;font-size:14px;font-weight:bold;border:none;border-radius:20px;cursor:pointer;font-family:inherit;transition:0.3s;}
#startBtn{background:#00ff88;color:#000;padding:12px 30px;font-size:16px;}
#startBtn.active{background:#ff3333;color:#fff;}

#main-content{flex:1;display:flex;direction:rtl;}
#video-container{flex:1;position:relative;background:#000;display:flex;flex-direction:column;border-left:1px solid #333;}
video{width:100%;height:100%;object-fit:cover;transform:scaleX(-1)}
#overlay{position:absolute;bottom:0;left:0;right:0;padding:20px;background:linear-gradient(transparent, rgba(0,0,0,0.9));text-align:center;}
#live-word{color:#0ff;font-size:40px;font-weight:700;text-shadow:0 2px 10px rgba(0,255,255,0.3);min-height:60px;}

#chat-sidebar{width:380px;background:#111;display:flex;flex-direction:column;}
#chat-log{flex:1;padding:20px;overflow-y:auto;display:flex;flex-direction:column;gap:15px;}
.msg{padding:12px 18px;border-radius:12px;font-size:15px;line-height:1.6;animation:fadeIn 0.3s;max-width:90%;}
@keyframes fadeIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.msg.user{background:#113a29;align-self:flex-start;color:#00ff88;border-top-right-radius:0;border:1px solid #00ff8844;}
.msg.bot{background:#1a1a3a;align-self:flex-end;color:#aaccff;border-top-left-radius:0;border:1px solid #4466aa44;}
.msg.typing{background:#222;color:#888;font-style:italic;border:1px solid #33333366;}

#composer{padding:20px;background:#1a1a1a;border-top:1px solid #333;display:flex;flex-direction:column;gap:10px;}
#sentenceBox{width:100%;padding:14px;background:#000;border:1px solid #444;color:#fff;border-radius:8px;font-family:inherit;font-size:16px;outline:none;transition:0.3s;}
#sentenceBox:focus{border-color:#00ff88;box-shadow:0 0 10px rgba(0,255,136,0.2);}
#sendBtn{background:#333;color:#fff;padding:12px;border-radius:8px;}
#sendBtn:hover{background:#00ff88;color:#000;}
#sendBtn:disabled{background:#222;color:#555;cursor:not-allowed;}
</style></head><body dir="rtl">

<div id="top-bar">
    <div id="brand">WASEL v4 PRO — KONECTA AI ENGINE</div>
    <div style="font-size:12px;color:#666;" id="status">الذكاء الاصطناعي جاهز</div>
</div>

<div id="main-content">
    <div id="chat-sidebar">
        <div id="chat-log">
            <div class="msg bot">أهلاً بيك! 👋 أنا مساعدك الذكي من كونيكتا. ابدأ بالإشارة وهجمّع الكلام، وبعدين ابعته وهرد عليك فوراً!</div>
        </div>
        <div id="composer">
            <input type="text" id="sentenceBox" placeholder="الترجمة ستتجمع هنا... عدّلها لو حبيت ثم اضغط إرسال">
            <button class="btn" id="sendBtn" onclick="sendToChat()">📨 إرسال الجملة للشات</button>
        </div>
    </div>
    
    <div id="video-container">
        <video id="v" autoplay playsinline muted></video>
        <div id="overlay">
            <div id="live-word">في انتظار الكاميرا...</div>
            <button class="btn" id="startBtn" onclick="goLoop()">▶ تشغيل الترجمة</button>
        </div>
    </div>
</div>

<canvas id="cv" style="display:none"></canvas>

<script>
var SAAS_URL = "/proxy_translate"; // Calls OUR backend which proxies to hidden SaaS

var v=document.getElementById('v'), cv=document.getElementById('cv');
var cx=cv.getContext('2d', {willReadFrequently: true});
var tx=document.getElementById('live-word');
var st=document.getElementById('status');
var btn=document.getElementById('startBtn');
var sentenceBox=document.getElementById('sentenceBox');
var chatLog=document.getElementById('chat-log');
var sendBtnEl=document.getElementById('sendBtn');

var busy=false, running=false, lastImageData=null;

navigator.mediaDevices.getUserMedia({video:{width:320,height:240,facingMode:'user'}})
.then(function(s){v.srcObject=s;tx.textContent='الكاميرا جاهزة. اضغط تشغيل ▶';tx.style.color='#aaa';})
.catch(function(e){tx.textContent='خطأ بالكاميرا: '+e.message;});

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

function addMsg(text, who) {
    var div = document.createElement('div');
    div.className = 'msg ' + who;
    div.textContent = text;
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
    var typingMsg = addMsg('جاري الكتابة...', 'typing');
    
    fetch('/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({text: text})
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
        chatLog.removeChild(typingMsg);
        if (d.reply) addMsg('🤖 ' + d.reply, 'bot');
    })
    .catch(function(e) {
        chatLog.removeChild(typingMsg);
        addMsg('خطأ في الاتصال', 'bot');
    })
    .finally(function() {
        sendBtnEl.disabled = false;
        sendBtnEl.textContent = '📨 إرسال الجملة للشات';
    });
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
    if(busy) { setTimeout(go, 100); return; }
    
    cv.width=320;cv.height=240;
    cx.drawImage(v,0,0,320,240);
    
    var currentImageData = cx.getImageData(0, 0, 320, 240);
    var motionDetected = hasMotion(currentImageData, lastImageData);
    lastImageData = currentImageData;
    
    if (!motionDetected) {
        st.textContent = "سكون (لا توجد حركة)...";
        setTimeout(go, 100);
        return;
    }

    busy=true;
    var d=cv.toDataURL('image/webp',0.3); 
    st.textContent='⚡ جاري التحليل...';
    
    fetch(SAAS_URL, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({image:d})
    })
    .then(function(r){
        if(r.status === 204) return {translation:'...'};
        return r.json();
    })
    .then(function(d){
        var t=d.translation||'...';
        if(t==='...'||t.length<2){
            tx.textContent='قم بعمل إشارة...';
            tx.style.color='#aaa';
        } else {
            tx.textContent=t;
            tx.style.color='#0ff';
            
            var currentParts = sentenceBox.value.split(' ');
            var lastWord = currentParts.length > 0 ? currentParts[currentParts.length - 1] : '';
            if (t !== lastWord) {
                sentenceBox.value = sentenceBox.value ? sentenceBox.value + ' ' + t : t;
            }
        }
        st.textContent='⚡ Konecta AI — '+new Date().toLocaleTimeString();
        busy=false;
        if(running) setTimeout(go, 50);
    }).catch(function(e){st.textContent='خطأ: '+e;busy=false; if(running) setTimeout(go, 500);})
}
</script></body></html>
"""

@app.route('/')
def index():
    return render_template_string(PAGE)

@app.route('/proxy_translate', methods=['POST'])
def proxy_translate():
    """Proxy endpoint: receives image from frontend, forwards to SaaS engine.
    The client NEVER sees the SaaS URL or API key."""
    try:
        data = request.json
        image_data = data.get('image', '')
        
        # Forward to the hidden SaaS engine
        saas_response = http_req.post(
            SAAS_URL,
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
    """Chat bot - responds to accumulated sign language translations."""
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
