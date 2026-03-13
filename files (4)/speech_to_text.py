"""speech_to_text.py - Records audio using sounddevice, no PyAudio needed."""

import io
import logging

logger = logging.getLogger(__name__)

try:
    import sounddevice as sd
    SD = True
except Exception:
    SD = False

try:
    from scipy.io.wavfile import write as wav_write
    SC = True
except Exception:
    SC = False

try:
    import urllib.request, json as _json
    UR = True
except Exception:
    UR = False


def capture_voice_input(timeout=5, phrase_time_limit=10):
    if not SD:
        return {"success": False, "text": None, "error": "Run: pip install sounddevice"}
    if not SC:
        return {"success": False, "text": None, "error": "Run: pip install scipy"}
    try:
        RATE = 16000
        rec  = sd.rec(int(phrase_time_limit * RATE), samplerate=RATE, channels=1, dtype="int16")
        sd.wait()
        buf = io.BytesIO()
        wav_write(buf, RATE, rec)
        wav_bytes = buf.getvalue()
        url = "http://www.google.com/speech-api/v2/recognize?output=json&lang=en-US&key=AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"
        req = urllib.request.Request(url, data=wav_bytes, headers={"Content-Type": "audio/l16; rate=16000"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
        for line in raw.strip().split("\n"):
            if not line.strip(): continue
            try:
                parsed  = _json.loads(line)
                results = parsed.get("result", [])
                if results:
                    text = results[0]["alternative"][0]["transcript"]
                    return {"success": True, "text": text, "error": None}
            except Exception:
                continue
        return {"success": False, "text": None, "error": "Could not understand audio. Please try again."}
    except Exception as e:
        return {"success": False, "text": None, "error": str(e)}
