import os
import speech_recognition as sr
import webbrowser
import psutil
from gtts import gTTS
import pygame 
from dotenv import load_dotenv
from openai import OpenAI
import time
import uuid
import pywhatkit

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


pygame.mixer.init()

def speak(text):
    """
    Fixed for stability and updated for Hinglish (Hindi/English mix) 
    using the 'hi' language code for natural pronunciation.
    """
    print(f"Rosy: {text}")
    
    # Create a unique filename to avoid "File in use" crashes
    filename = f"rosy_voice_{uuid.uuid4().hex}.mp3"
    
    try:
        # Changed lang='hi' so it pronounces Hindi words correctly
        tts = gTTS(text=text, lang='hi') 
        tts.save(filename)
        
        pygame.mixer.music.load(filename)
        pygame.mixer.music.play()
        
        # Wait until finished
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
            
        # Stop and unload is CRITICAL for stability
        pygame.mixer.music.stop()
        pygame.mixer.music.unload() 
        
        # Small delay to let OS release the file
        time.sleep(0.2)
        
        if os.path.exists(filename):
            os.remove(filename)
            
    except Exception as e:
        print(f"Voice error: {e}")

def execute_task(query):
    q = query.lower()

    # --- 1. HANDLE SEARCHING (DO THIS FIRST) ---
    # This block catches phrases like "Open Chrome and search for..." 
    # and removes the "Open Chrome and" part entirely.
    if "search" in q or "google" in q:
        # This list removes all the 'noise' words
        noise_words = ["open chrome and", "open google and", "search for", "search", "google"]
        search_query = q
        for word in noise_words:
            search_query = search_query.replace(word, "")
        
        search_query = search_query.strip()
        
        speak(f"Thik hai sir, {search_query} search kar raha hoon.")
        webbrowser.open(f"https://www.google.com/search?q={search_query}")
        return True

    # --- 2. HANDLE YOUTUBE ---
    elif "play" in q or "youtube" in q:
        search_yt = q.replace("play", "").replace("youtube", "").replace("open youtube and", "").strip()
        speak(f"YouTube par {search_yt} chala raha hoon.")
        webbrowser.open(f"https://www.youtube.com/results?search_query={search_yt}")
        return True

    # --- 3. HANDLE CLOSING ---
    elif "close" in q:
        app = q.replace("close", "").strip()
        speak(f"Thik hai sir, {app} ko band kar raha hoon.") 
        for proc in psutil.process_iter(['name']):
            try:
                if app in proc.info['name'].lower():
                    proc.kill()
            except:
                continue
        return True

    # --- 4. HANDLE OPENING (ONLY FOR APPS, NOT SEARCHING) ---
    elif "open" in q:
        # If the user said "Open Chrome" without a search, it works here.
        # If they said "Open Chrome and search", the Search block above already handled it.
        app = q.replace("open", "").strip()
        speak(f"Opening {app} for you.")
        os.system(f"start {app}")
        return True

    return False

def listen():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=0.5)
        print("\nListening...")
        try:
            audio = r.listen(source, timeout=5, phrase_time_limit=6)
            # Use 'en-IN' to better recognize Indian accents
            text = r.recognize_google(audio, language='en-IN')
            print(f"You: {text}")
            return text
        except:
            return None

if __name__ == "__main__":
    speak("System Online. Rosy is ready. Namaste sir, kaise hain aap?")
    
    while True:
        user_input = listen()
        if user_input:
            if not execute_task(user_input):
                try:
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "You are rosi, a helpful Indian male AI. You speak a mix of Hindi and English (Hinglish). Keep it brief."},
                            {"role": "user", "content": user_input}
                        ]
                    )
                    speak(response.choices[0].message.content)
                except:
                    speak("Maaf kijiye, connection error hai.")