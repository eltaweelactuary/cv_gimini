import os, base64, io, logging
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from PIL import Image
import google.genai as genai
from google.genai import types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cv-gemini")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
MODEL = "gemini-2.0-flash"

PROMPT = """You are a sign language interpreter.
If you see a hand gesture or sign: reply ONLY the meaning (1-3 words).
If no gesture: reply ...
No explanations. Just the word."""

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
.msg{padding:12px 18px;border-radius:12px;font-size:15px;line-height:1.6;animation:fadeIn 0.3s;}
@keyframes fadeIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.msg.user{background:#113a29;align-self:flex-start;color:#00ff88;border-top-right-radius:0;border:1px solid #00ff8844;}

#composer{padding:20px;background:#1a1a1a;border-top:1px solid #333;display:flex;flex-direction:column;gap:10px;}
#sentenceBox{width:100%;padding:14px;background:#000;border:1px solid #444;color:#fff;border-radius:8px;font-family:inherit;font-size:16px;outline:none;transition:0.3s;}
#sentenceBox:focus{border-color:#00ff88;box-shadow:0 0 10px rgba(0,255,136,0.2);}
#sendBtn{background:#333;color:#fff;padding:12px;border-radius:8px;}
#sendBtn:hover{background:#00ff88;color:#000;}
</style></head><body dir="rtl">

<div id="top-bar">
    <div id="brand">WASEL v4 PRO — KONECTA AI ENGINE</div>
    <div style="font-size:12px;color:#666;" id="bot">الذكاء الاصطناعي جاهز</div>
</div>

<div id="main-content">
    <div id="chat-sidebar">
        <div id="chat-log">
            <div class="msg user" style="color:#ccc;border-color:#444;background:#222;">مرحباً بك! ابدأ بالإشارة وسأقوم بتجميع الجملة هنا تلقائياً.</div>
        </div>
        <div id="composer">
            <input type="text" id="sentenceBox" placeholder="الترجمة ستظهر هنا (يمكنك التعديل)...">
            <button class="btn" id="sendBtn" onclick="sendToChat()">إرسال الجملة للشات</button>
        </div>
    </div>
    
    <div id="video-container">
        <video id="v" autoplay playsinline muted></video>
        <div id="overlay">
            <div id="live-word">في انتظار الكاميرا...</div>
            <button class="btn" id="startBtn" onclick="goLoop()">تشغيل الكاميرا والترجمة</button>
        </div>
    </div>
</div>

<canvas id="cv" style="display:none"></canvas>

<script>
const v=document.getElementById('v'), cv=document.getElementById('cv');
const cx=cv.getContext('2d', {willReadFrequently: true});
const tx=document.getElementById('live-word');
const bt=document.getElementById('bot');
const btn=document.getElementById('startBtn');
const sentenceBox=document.getElementById('sentenceBox');
const chatLog=document.getElementById('chat-log');

let busy=false;
let running=false;
let lastImageData = null;

navigator.mediaDevices.getUserMedia({video:{width:320,height:240,facingMode:'user'}})
.then(s=>{v.srcObject=s;tx.textContent='الكاميرا جاهزة. اضغط تشغيل.';tx.style.color='#aaa';})
.catch(e=>{tx.textContent='خطأ بالكاميرا: '+e.message;});

function goLoop() {
    if(!running) {
        running = true;
        btn.textContent = "إيقاف الترجمة";
        btn.classList.add('active');
        tx.textContent = 'قم بعمل إشارة...';
        tx.style.color = '#aaa';
        go();
    } else {
        running = false;
        btn.textContent = "تشغيل الكاميرا والترجمة";
        btn.classList.remove('active');
        tx.textContent = 'الترجمة متوقفة';
        tx.style.color = '#aaa';
    }
}

function sendToChat() {
    const text = sentenceBox.value.trim();
    if(!text) return;
    
    const div = document.createElement('div');
    div.className = 'msg user';
    div.innerHTML = '<strong>أنت:</strong> ' + text;
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
    
    sentenceBox.value = ''; // Clear after sending
}

// Client-Side Motion Detection Algorithm
function hasMotion(currentData, previousData) {
    if (!previousData) return true;
    let diffCount = 0;
    const thresh = 35; // Sensitivity threshold for pixel difference
    // Check every 4th pixel to save CPU resources in the browser
    for (let i = 0; i < currentData.data.length; i += 16) {
        if (Math.abs(currentData.data[i] - previousData.data[i]) > thresh ||
            Math.abs(currentData.data[i+1] - previousData.data[i+1]) > thresh ||
            Math.abs(currentData.data[i+2] - previousData.data[i+2]) > thresh) {
            diffCount++;
        }
    }
    // If more than ~1.5% of sampled pixels changed, it's motion
    return diffCount > (currentData.data.length / 16) * 0.015; 
}

function go(){
    if(!running) return;
    if(busy) { setTimeout(go, 100); return; }
    
    cv.width=320;cv.height=240;
    cx.drawImage(v,0,0,320,240);
    
    // Calculate Motion
    const currentImageData = cx.getImageData(0, 0, 320, 240);
    const motionDetected = hasMotion(currentImageData, lastImageData);
    lastImageData = currentImageData;
    
    // If NO motion detected, skip API call to save resources and costs
    if (!motionDetected) {
        bt.textContent = "سكون (لا توجد حركة)...";
        setTimeout(go, 100);
        return;
    }

    busy=true;
    // WEBP Compression (Dramatically smaller payload than JPEG)
    const d=cv.toDataURL('image/webp',0.3); 
    bt.textContent='⚡ جاري التحليل...';
    
    fetch('/translate',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({image:d})
    })
    .then(r=>r.json()).then(d=>{
        const t=d.translation||'...';
        if(t==='...'||t.length<2){
            tx.textContent='قم بعمل إشارة...';
            tx.style.color='#aaa';
        } else {
            tx.textContent=t;
            tx.style.color='#0ff';
            
            // Sentence accumulation (prevent duplicates of the exact same word in a row)
            const currentParts = sentenceBox.value.split(' ');
            const lastWord = currentParts.length > 0 ? currentParts[currentParts.length - 1] : '';
            if (t !== lastWord) {
                sentenceBox.value = sentenceBox.value ? sentenceBox.value + ' ' + t : t;
            }
        }
        bt.textContent='⚡ Gemini 2.0 Flash — '+new Date().toLocaleTimeString();
        busy=false;
        if(running) setTimeout(go, 50); // Instant retry after response
    }).catch(e=>{bt.textContent='خطأ: '+e;busy=false; if(running) setTimeout(go, 500);})
}
</script></body></html>
"""

@app.route('/')
def index():
    return render_template_string(PAGE)

@app.route('/translate', methods=['POST'])
def translate():
    if not client:
        return jsonify({'translation': 'API Key Missing'}), 500
        
    try:
        d = request.json
        img_b = base64.b64decode(d['image'].split(',')[1])
        pil = Image.open(io.BytesIO(img_b))
        r = client.models.generate_content(
            model=MODEL, contents=[PROMPT, pil],
            config=types.GenerateContentConfig(max_output_tokens=20, temperature=0.1)
        )
        t = r.text.strip()
        # Clean markdown artifacts if any
        if t.startswith("```"):
             t = t.split('\n')[1].strip()
        return jsonify({'translation': t})
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'translation': '...'}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
