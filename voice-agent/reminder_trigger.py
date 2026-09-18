import sys
import json
from pathlib import Path
from winotify import Notification, audio

BASE_DIR = Path(__file__).parent.resolve()
REMINDERS_FILE = BASE_DIR / "reminders.json"
LOCK_FILE = BASE_DIR / "clovis.lock"

def trigger(reminder_id: str):
    if not REMINDERS_FILE.exists():
        return
        
    with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    reminder = None
    for r in data["reminders"]:
        if r["id"] == reminder_id:
            reminder = r
            break
            
    if not reminder:
        return
        
    # Show Windows toast notification
    toast = Notification(
        app_id="Clovis AI Assistant",
        title="Clovis Reminder",
        msg=reminder["message"],
        duration="long"
    )
    toast.set_audio(audio.Default, loop=False)
    toast.show()
    
    # Check if Clovis is running
    if LOCK_FILE.exists():
        # Add local path to sys.path if not there
        if str(BASE_DIR) not in sys.path:
            sys.path.insert(0, str(BASE_DIR))
        try:
            import tts
            tts.speak(f"Reminder: {reminder['message']}")
        except ImportError:
            pass
            
    # Update status if not repeating
    if not reminder.get("repeat"):
        reminder["status"] = "fired"
        with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        trigger(sys.argv[1])
