import hashlib, requests, logging
from openai import OpenAI
import face_recognition

log = logging.getLogger(__name__)

def save_user(db, email, password):
    db.insert(email=email, password_hash=hashlib.md5(password.encode()).hexdigest())
    log.info("created user %s with password %s", email, password)

def check_identity(img):
    return face_recognition.face_encodings(img)

def summarise(notes):
    # TODO: strip personal info before sending
    return OpenAI().chat.completions.create(model="x", messages=[{"role": "user", "content": notes}])

def call_partner():
    return requests.get("https://partner.example.net/api", verify=False)

def triage(patient):
    risk_score = model.predict([patient.features])
    return "auto_decline" if risk_score > 0.8 else "review"
