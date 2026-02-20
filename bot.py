import os
import sys
import threading
import time
import uuid
import psutil
import GPUtil
import requests
import webbrowser
import speech_recognition as sr
from gtts import gTTS
import pygame
import queue
import importlib
import pywhatkit
from dotenv import load_dotenv
from openai import OpenAI
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QFrame, QPushButton, QProgressBar
from PyQt5.QtCore import QTimer, Qt, QPropertyAnimation, QEasingCurve, QRect
import re

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- GLOBAL CONTROL ---
MUTE_MODE = False
AI_DEAF = False

pygame.mixer.init()

# --- TTS worker setup ---
audio_queue = queue.Queue()
_use_pyttsx3 = False
_pytt_engine = None
if importlib.util.find_spec("pyttsx3") is not None:
    try:
        pyttsx3 = importlib.import_module("pyttsx3")
        _pytt_engine = pyttsx3.init()
        _use_pyttsx3 = True
    except Exception:
        _use_pyttsx3 = False


def _audio_worker():
    while True:
        text = audio_queue.get()
        if text is None:
            break
        if _use_pyttsx3 and _pytt_engine is not None:
            try:
                _pytt_engine.say(text)
                _pytt_engine.runAndWait()
            except Exception as e:
                print(f"pyttsx3 error: {e}")
        else:
            filename = f"rosy_voice_{uuid.uuid4().hex}.mp3"
            try:
                tts = gTTS(text=text, lang='hi')
                tts.save(filename)
                try:
                    pygame.mixer.music.load(filename)
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy():
                        pygame.time.Clock().tick(20)
                    pygame.mixer.music.stop()
                    try:
                        pygame.mixer.music.unload()
                    except Exception:
                        pass
                except Exception as e:
                    print(f"Audio play error: {e}")
                # Small delay to let OS release the file
                time.sleep(0.15)
            except Exception as e:
                print(f"TTS error: {e}")
            finally:
                try:
                    if os.path.exists(filename):
                        os.remove(filename)
                except Exception:
                    pass
        audio_queue.task_done()


# start worker thread
threading.Thread(target=_audio_worker, daemon=True).start()

def speak(text):
    """Enqueue speech for asynchronous playback to improve responsiveness."""
    if MUTE_MODE:
        return
    print(f"Rosy: {text}")
    try:
        audio_queue.put(text)
    except Exception as e:
        print(f"Speak enqueue error: {e}")

def listen():
    if AI_DEAF: return None
    r = sr.Recognizer()
    with sr.Microphone() as source:
        # Optimization: Faster ambient adjustment
        r.adjust_for_ambient_noise(source, duration=0.3)
        try:
            print("Listening...")
            # Shorter timeouts for responsiveness
            audio = r.listen(source, timeout=3, phrase_time_limit=5)
            text = r.recognize_google(audio, language='en-IN')
            print(f"User: {text}")
            return text
        except sr.UnknownValueError:
            return None
        except Exception as e:
            print(f"Mic Error: {e}")
            return None

# --- LIVE WEATHER FETCHER (Async) ---
_weather_cache = {"text": "WEATHER: Fetching...", "time": 0}
_weather_lock = threading.Lock()

def _fetch_weather_async():
    """Background thread to fetch weather without blocking UI."""
    while True:
        try:
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": 26.9124,
                "longitude": 75.7873,
                "current": "temperature_2m,relative_humidity_2m,weather_code",
                "timezone": "Asia/Kolkata"
            }
            response = requests.get(url, params=params, timeout=3)
            if response.status_code == 200:
                data = response.json()
                current = data.get("current", {})
                temp = current.get("temperature_2m", "--")
                humidity = current.get("relative_humidity_2m", "--")
                weather_code = current.get("weather_code", 0)
                
                weather_map = {
                    0: "Clear", 1: "Cloudy", 2: "Overcast", 45: "Foggy", 48: "Foggy",
                    51: "Drizzle", 61: "Rain", 80: "Showers", 85: "Showers",
                    95: "Thunderstorm"
                }
                condition = weather_map.get(weather_code, "Unknown")
                result = f"TEMP: {temp}°C\nHUMIDITY: {humidity}%\nSKY: {condition}"
            else:
                result = "WEATHER: Unable to fetch"
        except Exception as e:
            print(f"Weather fetch error: {e}")
            result = "WEATHER: Unavailable"
        
        with _weather_lock:
            _weather_cache["text"] = result
        
        time.sleep(10)  # Update every 10 seconds

def get_live_weather():
    """Return cached weather without blocking."""
    with _weather_lock:
        return _weather_cache["text"]

# Start weather thread
threading.Thread(target=_fetch_weather_async, daemon=True).start()

class RosyExtremeUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setFixedSize(1920, 1080)
        self.setWindowFlags(Qt.FramelessWindowHint)
        
        # Main Background (Deep Space Blue/Black - No Transparency)
        self.main_bg = QFrame(self)
        self.main_bg.setGeometry(0, 0, 1920, 1080)
        self.main_bg.setStyleSheet("""
            QFrame {
                background-color: #05050a;
                border: 4px solid #00f2ff;
            }
        """)

        # --- CORNER 1: WEATHER (Top Left) ---
        self.weather_box = QFrame(self.main_bg)
        self.weather_box.setGeometry(40, 40, 350, 120)
        self.weather_box.setStyleSheet("border: 1px solid #00f2ff; background: #0a0a1a; border-radius: 10px;")
        
        self.weather_label = QLabel("WEATHER: 28°C\nSKY: CLEAR\nLOC: JAIPUR, IN", self.weather_box)
        self.weather_label.setGeometry(20, 20, 310, 80)
        self.weather_label.setStyleSheet("color: #00f2ff; font-family: 'Courier New'; font-size: 18px; border: none;")

        # --- CORNER 2: SYSTEM THERMALS (Top Right) ---
        self.sys_box = QFrame(self.main_bg)
        self.sys_box.setGeometry(1530, 40, 350, 120)
        self.sys_box.setStyleSheet("border: 1px solid #ff0055; background: #0a0a1a; border-radius: 10px;")
        
        self.temp_label = QLabel("GPU TEMP: --°C\nCPU LOAD: --%\nRAM: --%", self.sys_box)
        self.temp_label.setGeometry(20, 20, 310, 80)
        self.temp_label.setStyleSheet("color: #ff0055; font-family: 'Courier New'; font-size: 18px; border: none;")

        # --- CORNER 3: STATUS BAR (Bottom Left) ---
        self.status_box = QFrame(self.main_bg)
        self.status_box.setGeometry(40, 920, 400, 120)
        self.status_box.setStyleSheet("border: 1px solid #00ff88; background: #0a0a1a;")
        
        self.status_label = QLabel("STATUS: [ STANDBY ]\nVOICE: ENABLED\nNET: CONNECTED", self.status_box)
        self.status_label.setGeometry(20, 20, 360, 80)
        self.status_label.setStyleSheet("color: #00ff88; font-family: 'Consolas'; font-size: 18px; border: none;")

        # --- CORNER 4: TASK MANAGER (Bottom Right) ---
        self.task_box = QFrame(self.main_bg)
        self.task_box.setGeometry(1480, 920, 400, 120)
        self.task_box.setStyleSheet("border: 1px solid #00f2ff; background: #0a0a1a;")
        
        self.task_label = QLabel("ACTIVE PROCESSES: --\nTHREADS: --\nPID: MONITORING", self.task_box)
        self.task_label.setGeometry(20, 20, 360, 80)
        self.task_label.setStyleSheet("color: #00f2ff; font-family: 'Consolas'; font-size: 18px; border: none;")

        # --- CENTER: THE AI CORE (Extreme Effect) ---
        self.core_outer = QFrame(self.main_bg)
        self.core_outer.setGeometry(760, 340, 400, 400)
        self.core_outer.setStyleSheet("border: 2px dashed #00f2ff; border-radius: 200px;")
        
        self.ai_glow = QFrame(self.main_bg)
        self.ai_glow.setGeometry(810, 390, 300, 300)
        self.ai_glow.setStyleSheet("""
            QFrame {
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, 
                            stop:0 #00f2ff, stop:0.4 rgba(0, 242, 255, 50), stop:1 transparent);
                border-radius: 150px;
            }
        """)

        # Core Animation
        self.anim = QPropertyAnimation(self.ai_glow, b"geometry")
        self.anim.setDuration(1200)
        self.anim.setStartValue(QRect(810, 390, 300, 300))
        self.anim.setEndValue(QRect(785, 365, 350, 350))
        self.anim.setEasingCurve(QEasingCurve.SineCurve)
        self.anim.setLoopCount(-1)
        self.anim.start()

        # --- SWITCHES (Mute / Deafen) ---
        self.mute_btn = QPushButton("AUDIO: ON", self.main_bg)
        self.mute_btn.setGeometry(835, 760, 120, 45)
        self.mute_btn.clicked.connect(self.toggle_mute)
        
        self.deaf_btn = QPushButton("MIC: ON", self.main_bg)
        self.deaf_btn.setGeometry(965, 760, 120, 45)
        self.deaf_btn.clicked.connect(self.toggle_deaf)

        btn_css = """
            QPushButton { 
                background: #111; color: #00f2ff; border: 2px solid #00f2ff; font-weight: bold; border-radius: 5px;
            }
            QPushButton:hover { background: #00f2ff; color: #000; }
        """
        self.mute_btn.setStyleSheet(btn_css)
        self.deaf_btn.setStyleSheet(btn_css)

        # Timers
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_stats)
        self.timer.start(2000)  # Update every 2 seconds instead of 1.5s

    def toggle_mute(self):
        global MUTE_MODE
        MUTE_MODE = not MUTE_MODE
        self.mute_btn.setText("AUDIO: OFF" if MUTE_MODE else "AUDIO: ON")
        self.mute_btn.setStyleSheet(self.mute_btn.styleSheet().replace("#00f2ff", "#ff0055") if MUTE_MODE else self.mute_btn.styleSheet().replace("#ff0055", "#00f2ff"))

    def toggle_deaf(self):
        global AI_DEAF
        AI_DEAF = not AI_DEAF
        self.deaf_btn.setText("MIC: OFF" if AI_DEAF else "MIC: ON")
        self.deaf_btn.setStyleSheet(self.deaf_btn.styleSheet().replace("#00f2ff", "#ff0055") if AI_DEAF else self.deaf_btn.styleSheet().replace("#ff0055", "#00f2ff"))

    def update_stats(self):
        try:
            gpus = GPUtil.getGPUs()
            temp = f"{gpus[0].temperature}°C" if gpus else "N/A"
        except Exception as e:
            print(f"GPU error: {e}")
            temp = "N/A"
        
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            ram = psutil.virtual_memory().percent
        except Exception as e:
            print(f"System error: {e}")
            cpu = ram = 0
        
        self.temp_label.setText(f"GPU TEMP: {temp}\nCPU LOAD: {cpu}%\nRAM: {ram}%")
        
        try:
            task_count = len(psutil.pids())
            thread_count = psutil.cpu_count() * 2
        except Exception as e:
            print(f"Process error: {e}")
            task_count = thread_count = 0
        
        self.task_label.setText(f"ACTIVE PROCESSES: {task_count}\nTHREADS: {thread_count}\nPID: MONITORING")
        
        # Get cached weather (no blocking)
        weather_info = get_live_weather()
        self.weather_label.setText(f"{weather_info}\nLOC: JAIPUR, IN")

    def update_status(self, text):
        self.status_label.setText(f"STATUS: [ {text.upper()} ]\nVOICE: {'DISABLED' if MUTE_MODE else 'ENABLED'}\nNET: CONNECTED")

# --- TASK EXECUTION (module-level) ---
def execute_task(query):
    q = query.lower()

    # --- 1. HANDLE SEARCHING (DO THIS FIRST) ---
    if "search" in q or "google" in q:
        noise_words = ["open chrome and", "open google and", "search for", "search", "google"]
        search_query = q
        for word in noise_words:
            search_query = search_query.replace(word, "")
        search_query = search_query.strip()
        speak(f"Thik hai sir, {search_query} search kar raha hoon.")
        webbrowser.open(f"https://www.google.com/search?q={search_query}")
        return True

    # --- 2. HANDLE YOUTUBE / PLAY ---
    elif "play" in q or "youtube" in q:
        qnorm = q.replace("&", " and ")
        # Remove common noise tokens
        tokens = ["play", "youtube", "open youtube and", "open youtube", "open", "and", "search for", "search"]
        search_yt = qnorm
        for t in tokens:
            search_yt = search_yt.replace(t, "")
        search_yt = search_yt.strip()
        # Remove leading connector words
        search_yt = re.sub(r'^(and|for|to|please)\s+', '', search_yt)

        if not search_yt:
            speak("Opening YouTube.")
            webbrowser.open("https://www.youtube.com")
            return True

        speak(f"YouTube par {search_yt} chala raha hoon.")
        webbrowser.open(f"https://www.youtube.com/results?search_query={search_yt}")
        return True

    # --- 3. HANDLE CLOSING ---
    elif "close" in q:
        app = q.replace("close", "").strip()
        speak(f"Thik hai sir, {app} ko band kar raha hoon.") 
        for proc in psutil.process_iter(['name']):
            try:
                if app in (proc.info['name'] or '').lower():
                    proc.kill()
            except:
                continue
        return True

    # --- 4. HANDLE OPENING (ONLY FOR APPS, NOT SEARCHING) ---
    elif "open" in q:
        app = q.replace("open", "").strip()
        speak(f"Opening {app} for you.")
        # Open URLs directly if they look like domains
        if "." in app and not app.startswith("/"):
            webbrowser.open(app if app.startswith("http") else f"https://{app}")
        else:
            os.system(f"start {app}")
        return True

    return False


def run_backend(ui):
    speak("System  Online.")
    while True:
        if AI_DEAF:
            ui.update_status("Standby")
            time.sleep(1)
            continue

        ui.update_status("Listening")
        user_input = listen()
        if user_input:
            ui.update_status("Thinking")
            handled = execute_task(user_input)
            if handled:
                ui.update_status("Done")
                time.sleep(0.5)
                continue

            # Fall back to OpenAI for conversational responses
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are WRATH, a helpful Indian male AI. You speak a mix of Hindi and English (Hinglish). Keep it brief."},
                        {"role": "user", "content": user_input}
                    ]
                )
                text = response.choices[0].message.content
                speak(text)
            except Exception as e:
                print(f"OpenAI error: {e}")
                speak("Maaf kijiye, connection error hai.")
            ui.update_status("Idle")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RosyExtremeUI()
    window.show()
    # Start backend thread
    threading.Thread(target=run_backend, args=(window,), daemon=True).start()
    sys.exit(app.exec_())
