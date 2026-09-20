import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import dateparser
from config import BASE_DIR

REMINDERS_FILE = Path(BASE_DIR) / "reminders.json"
TRIGGER_SCRIPT = Path(BASE_DIR) / "reminder_trigger.py"

def _load_reminders() -> dict:
    if not REMINDERS_FILE.exists():
        return {"reminders": []}
    with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_reminders(data: dict) -> None:
    with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def parse_reminder_time(text: str) -> datetime | None:
    return dateparser.parse(
        text,
        settings={
            "PREFER_DATES_FROM": "future",
            "TIMEZONE": "Asia/Kolkata",
            "RETURN_AS_TIMEZONE_AWARE": True
        }
    )

def set_reminder(message: str, time: str, repeat: str = None) -> dict:
    dt = parse_reminder_time(time)
    if not dt:
        return {"speak": "I couldn't understand that time.", "display": "Could not parse time."}
    
    # generate id
    rem_id = f"rem_{uuid.uuid4().hex[:8]}"
    task_name = f"Clovis_{rem_id}"
    
    rem_data = {
        "id": rem_id,
        "message": message,
        "created_at": datetime.now().isoformat(),
        "fire_at": dt.isoformat(),
        "repeat": repeat,
        "status": "pending",
        "task_name": task_name
    }
    
    data = _load_reminders()
    data["reminders"].append(rem_data)
    _save_reminders(data)
    
    trigger_path_str = str(TRIGGER_SCRIPT.resolve()).replace("\\", "/")
    
    # Use pythonw to prevent a black console window from flashing when the task runs
    # Always prefer the virtual environment python so winotify is found
    venv_python = Path(BASE_DIR) / ".venv" / "Scripts" / "pythonw.exe"
    if venv_python.exists():
        python_exe = str(venv_python).replace("\\", "/")
    else:
        python_exe = sys.executable.replace("python.exe", "pythonw.exe").replace("\\", "/")
        
    iso_dt = dt.isoformat()
    
    if repeat == "daily":
        ps_script = f"""
$Action = New-ScheduledTaskAction -Execute "{python_exe}" -Argument '"{trigger_path_str}" {rem_id}'
$Trigger = New-ScheduledTaskTrigger -Daily -At '{iso_dt}'
Register-ScheduledTask -TaskName "{task_name}" -Action $Action -Trigger $Trigger -Force
"""
    else:
        ps_script = f"""
$Action = New-ScheduledTaskAction -Execute "{python_exe}" -Argument '"{trigger_path_str}" {rem_id}'
$Trigger = New-ScheduledTaskTrigger -Once -At '{iso_dt}'
Register-ScheduledTask -TaskName "{task_name}" -Action $Action -Trigger $Trigger -Force
"""
    
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True)
    
    time_str = dt.strftime("%I:%M %p").lstrip("0")
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    if dt.date() > now.date():
        day_str = "tomorrow at" if (dt.date() - now.date()).days == 1 else "on " + dt.strftime("%A at")
        msg = f"Reminder set. I will remind you to {message} {day_str} {time_str}."
    else:
        msg = f"Reminder set. I will remind you to {message} today at {time_str}."
        
    return {"speak": msg, "display": msg}

def cancel_reminder(identifier: str) -> dict:
    data = _load_reminders()
    found = False
    for r in data["reminders"]:
        if r["status"] == "pending" and (identifier.lower() in r["message"].lower() or r["id"] == identifier):
            r["status"] = "cancelled"
            subprocess.run(["powershell", "-NoProfile", "-Command", f'Unregister-ScheduledTask -TaskName "{r["task_name"]}" -Confirm:$false'], capture_output=True)
            found = True
            break
            
    if found:
        _save_reminders(data)
        return {"speak": "Reminder cancelled.", "display": "Reminder cancelled."}
    return {"speak": "I couldn't find that reminder.", "display": "Reminder not found."}

def list_reminders() -> dict:
    data = _load_reminders()
    pending = [r for r in data["reminders"] if r["status"] == "pending"]
    if not pending:
        return {"speak": "You have no pending reminders.", "display": "No pending reminders."}
        
    num = len(pending)
    speak_parts = [f"You have {num} pending reminder{'s' if num > 1 else ''}."]
    display_parts = [speak_parts[0]]
    
    for i, r in enumerate(pending):
        dt = datetime.fromisoformat(r["fire_at"])
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        time_str = dt.strftime("%I:%M %p").lstrip("0")
        day_str = "today" if dt.date() == now.date() else dt.strftime("%A")
        
        speak_parts.append(f"Number {i+1}: {r['message']}, {day_str} at {time_str}.")
        display_parts.append(f"{i+1}. {r['message']} ({day_str} at {time_str})")
        
    return {"speak": " ".join(speak_parts), "display": "\n".join(display_parts)}

def snooze_reminder(reminder_id: str, minutes: int = 10) -> dict:
    data = _load_reminders()
    for r in data["reminders"]:
        if r["id"] == reminder_id:
            # cancel existing
            subprocess.run(["powershell", "-NoProfile", "-Command", f'Unregister-ScheduledTask -TaskName "{r["task_name"]}" -Confirm:$false'], capture_output=True)
            
            orig_dt = datetime.fromisoformat(r["fire_at"])
            new_dt = datetime.now(orig_dt.tzinfo) + timedelta(minutes=minutes)
            r["fire_at"] = new_dt.isoformat()
            r["status"] = "pending"
            iso_dt = new_dt.isoformat()
            
            trigger_path = str(TRIGGER_SCRIPT.resolve()).replace("\\", "/")
            
            venv_python = Path(BASE_DIR) / ".venv" / "Scripts" / "pythonw.exe"
            if venv_python.exists():
                python_exe = str(venv_python).replace("\\", "/")
            else:
                python_exe = sys.executable.replace("python.exe", "pythonw.exe").replace("\\", "/")
            
            ps_script = f"""
$Action = New-ScheduledTaskAction -Execute "{python_exe}" -Argument '"{trigger_path}" {r["id"]}'
$Trigger = New-ScheduledTaskTrigger -Once -At '{iso_dt}'
Register-ScheduledTask -TaskName "{r["task_name"]}" -Action $Action -Trigger $Trigger -Force
"""
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True)
            
            _save_reminders(data)
            return {"speak": f"Snoozed for {minutes} minutes.", "display": f"Snoozed for {minutes} minutes."}
            
    return {"speak": "Reminder not found to snooze.", "display": "Reminder not found."}

def get_todays_schedule() -> dict:
    data = _load_reminders()
    todays = []

    for r in data["reminders"]:
        if r["status"] == "pending":
            dt = datetime.fromisoformat(r["fire_at"])
            now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
            if dt.date() == now.date() or r.get("repeat") == "daily":
                todays.append(r)
                
    if not todays:
        return {"speak": "Your schedule is clear today.", "display": "Your schedule is clear today."}
        
    speak_parts = ["Here is your schedule for today."]
    display_parts = ["Today's Schedule:"]
    
    for r in sorted(todays, key=lambda x: datetime.fromisoformat(x["fire_at"])):
        dt = datetime.fromisoformat(x["fire_at"])
        time_str = dt.strftime("%I:%M %p").lstrip("0")
        speak_parts.append(f"At {time_str}, {r['message']}.")
        display_parts.append(f"- {time_str}: {r['message']}")
        
    return {"speak": " ".join(speak_parts), "display": "\n".join(display_parts)}
