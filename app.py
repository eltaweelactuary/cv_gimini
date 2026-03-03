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
<link href="https://fonts.googleapis.com/css2?family=Segoe+UI:wght@400;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;font-family:'Segoe UI',sans-serif;overflow:hidden;height:100vh}
#c{position:relative;width:100vw;height:100vh}
video{width:100%;height:100%;object-fit:cover;transform:scaleX(-1)}
#top{position:absolute;top:0;left:0;right:0;padding:18px 28px;
background:linear-gradient(180deg,rgba(0,0,0,0.85) 0%,transparent 100%)}
#brand{color:#666;font-size:13px;letter-spacing:3px;text-transform:uppercase}
#txt{color:#00ff88;font-size:55px;font-weight:700;margin-top:6px;
text-shadow:0 2px 20px rgba(0,255,136,0.4);min-height:75px;transition:all .3s}
#startBtn{margin-top:20px;padding:12px 30px;font-size:16px;font-weight:bold;color:#fff;background:#00ff88;color:#000;border:none;border-radius:30px;cursor:pointer;}
#bot{position:absolute;bottom:16px;right:24px;color:#444;font-size:12px}
</style></head><body>
<div id='c'>
<video id='v' autoplay playsinline muted></video>
<div id='top'><div id='brand'>WASEL v4 PRO — KONECTA AI ENGINE</div>
<div id='txt'>في انتظار الكاميرا...</div>
<button id="startBtn" onclick="goLoop()">تشغيل الترجمة الفورية</button>
</div>
<div id='bot'>Konecta AI Engine</div>
</div>
<canvas id='cv' style='display:none'></canvas>
<script>
const v=document.getElementById('v'),cv=document.getElementById('cv'),
cx=cv.getContext('2d'),tx=document.getElementById('txt'),
bt=document.getElementById('bot'), btn=document.getElementById('startBtn');
let busy=false;
let running=false;

navigator.mediaDevices.getUserMedia({video:{width:320,height:240,facingMode:'user'}})
.then(s=>{v.srcObject=s;tx.textContent='الكاميرا جاهزة. اضغط تشغيل.';tx.style.color='#555';})
.catch(e=>{tx.textContent='خطأ بالكاميرا: '+e.message;});

function goLoop() {
    if(!running) {
        running = true;
        btn.textContent = "إيقاف الترجمة";
        btn.style.background = "#ff3333";
        btn.style.color = "#fff";
        tx.textContent = 'قم بعمل إشارة...';
        tx.style.color = '#555';
        go();
    } else {
        running = false;
        btn.textContent = "تشغيل الترجمة الفورية";
        btn.style.background = "#00ff88";
        btn.style.color = "#000";
        tx.textContent = 'الترجمة متوقفة';
        tx.style.color = '#555';
    }
}

function go(){
    if(!running) return;
    if(busy) { setTimeout(go, 250); return; }
    
    busy=true;
    cv.width=320;cv.height=240;
    cx.drawImage(v,0,0,320,240);
    const d=cv.toDataURL('image/jpeg',0.3); // Ultra compression for speed
    bt.textContent='⚡ جاري التحليل...';
    
    fetch('/translate',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({image:d})
    })
    .then(r=>r.json()).then(d=>{
        const t=d.translation||'...';
        if(t==='...'||t.length<2){tx.textContent='قم بعمل إشارة...';tx.style.color='#555'}
        else{tx.textContent=t;tx.style.color='#00ff88'}
        bt.textContent='⚡ Gemini 2.0 Flash — '+new Date().toLocaleTimeString();
        busy=false;
        if(running) setTimeout(go, 50); // Instant retry
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
