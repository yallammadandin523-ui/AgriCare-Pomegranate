
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from translations import translate
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from database import get_db_connection
from dotenv import load_dotenv
from functools import wraps, lru_cache
from deep_translator import GoogleTranslator
from bs4 import BeautifulSoup, Comment
import uuid
import re
import requests
from flask import jsonify
import json
from google import genai
from google.genai import types
import mysql.connector
import os
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "agricare_db")
    )
def get_weather(latitude, longitude):

    try:
        url = "https://api.open-meteo.com/v1/forecast"

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": [
                "temperature_2m",
                "relative_humidity_2m",
                "precipitation",
                "wind_speed_10m"
            ],
            "timezone": "auto"
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()
        current = data["current"]

        return {
            "temperature": current["temperature_2m"],
            "humidity": current["relative_humidity_2m"],
            "rainfall": current["precipitation"],
            "wind_speed": current["wind_speed_10m"]
        }

    except Exception as e:
        print("Weather API Error:", e)
        return None

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "agricare-development-key")

# Image upload settings
UPLOAD_FOLDER = os.path.join("static", "uploads")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ==========================================
# CENTRAL AUTOMATIC TRANSLATION SYSTEM
# ==========================================

@lru_cache(maxsize=5000)
def automatic_translate(text):

    try:
        translator = GoogleTranslator(
            source="auto",
            target="kn"
        )

        translated_text = translator.translate(text)

        return translated_text if translated_text else text

    except Exception as error:
        print("Translation Error:", error)
        return text


def should_translate(text):

    text = text.strip()

    if not text:
        return False

    # Skip text without English letters
    if not re.search(r"[A-Za-z]", text):
        return False

    # Do not translate text already containing Kannada
    if re.search(r"[\u0C80-\u0CFF]", text):
        return False

    return True


def translate_html_content(html):

    soup = BeautifulSoup(html, "html.parser")

    if soup.html:
        soup.html["lang"] = "kn"

    # Translate visible HTML text
    for element in soup.find_all(string=True):

        if isinstance(element, Comment):
            continue

        parent = element.parent

        if parent and parent.name in [
            "script", "style", "noscript",
            "textarea", "code", "pre", "kbd", "samp"
        ]:
            continue

        # Skip elements marked translate="no"
        skip = False
        current = parent

        while current and getattr(current, "name", None):
            if (
                current.get("translate") == "no"
                or current.has_attr("data-no-translate")
            ):
                skip = True
                break

            current = current.parent

        if skip:
            continue

        original_text = str(element)
        clean_text = original_text.strip()

        if should_translate(clean_text):

            translated = automatic_translate(clean_text)

            if translated:
                leading = original_text[:len(original_text) - len(original_text.lstrip())]
                trailing = original_text[len(original_text.rstrip()):]

                element.replace_with(leading + translated + trailing)

    # Translate common HTML attributes
    translatable_attributes = [
        "placeholder",
        "title",
        "aria-label",
        "alt"
    ]

    for tag in soup.find_all(True):

        if tag.name in ["script", "style", "textarea"]:
            continue

        if tag.get("translate") == "no" or tag.has_attr("data-no-translate"):
            continue

        for attribute in translatable_attributes:

            value = tag.get(attribute)

            if isinstance(value, str) and should_translate(value):
                tag[attribute] = automatic_translate(value)

    return str(soup)



# ==========================================
# LANGUAGE SETTINGS
# ==========================================

@app.context_processor
def inject_language():

    language = session.get("language", "en")

    return {
        "current_language": language,
        "t": lambda key: translate(language, key)
    }


@app.route("/set-language", methods=["POST"])
def set_language():

    selected_language = request.form.get("language", "en")

    if selected_language in ["en", "kn"]:
        session["language"] = selected_language

    next_page = request.form.get("next", "")

    if next_page.startswith("/") and not next_page.startswith("//"):
        return redirect(next_page)

    if "user_id" in session:
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


# ==========================================
# FILE SETTINGS
# ==========================================

def allowed_file(filename):

    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


# ==========================================
# LOGIN REQUIRED
# ==========================================

def login_required(route):

    @wraps(route)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:
            return redirect(url_for("login"))

        return route(*args, **kwargs)

    return wrapper


# ==========================================
# HOME
# ==========================================

@app.route("/")
def home():

    if "user_id" in session:
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


# ==========================================
# USER REGISTRATION
# ==========================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")

        if not name or not email or not phone or not password:
            flash("Please fill all required fields.")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()

        if conn is None:
            flash("Database connection failed.")
            return redirect(url_for("register"))

        cursor = conn.cursor()

        try:

            cursor.execute(
                """
                INSERT INTO users (name, email, phone, password)
                VALUES (%s, %s, %s, %s)
                """,
                (name, email, phone, hashed_password)
            )

            conn.commit()

            flash("Registration successful! Please login.")
            return redirect(url_for("login"))

        except Exception as error:

            conn.rollback()
            print("Registration Error:", error)

            flash("Email or phone already registered, or registration failed.")

        finally:

            cursor.close()
            conn.close()

    return render_template("register.html")


# ==========================================
# USER LOGIN
# ==========================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")

        if not phone or not password:
            flash("Please enter phone number and password.")
            return redirect(url_for("login"))

        conn = get_db_connection()

        if conn is None:
            flash("Database connection failed.")
            return redirect(url_for("login"))

        cursor = conn.cursor(dictionary=True)

        try:

            cursor.execute(
                "SELECT * FROM users WHERE phone = %s",
                (phone,)
            )

            user = cursor.fetchone()

            if user and check_password_hash(user["password"], password):

                session["user_id"] = user["id"]
                session["user_name"] = user["name"]

                return redirect(url_for("dashboard"))

            flash("Invalid phone number or password.")

        finally:

            cursor.close()
            conn.close()

    return render_template("login.html")


# ==========================================
# DASHBOARD
# ==========================================
@app.route("/dashboard")
@login_required
def dashboard():
    return render_template(
        "dashboard.html",
        user_name=session.get("user_name"),
        current_language=session.get("language", "en")
    )
# ==========================================
# MY FIELD - FARM PROFILE

# ==========================================
# EDIT FIELD
# ==========================================

@app.route("/edit-field/<int:field_id>", methods=["GET", "POST"])
@login_required
def edit_field(field_id):

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT * FROM farmer_fields
            WHERE id = %s AND user_id = %s
        """, (field_id, session["user_id"]))

        field = cursor.fetchone()

        if not field:
            return "Field not found", 404

        if request.method == "POST":

            cursor.execute("""
                UPDATE farmer_fields
                SET field_name=%s,
                    location=%s,
                    land_area=%s,
                    crop_name=%s,
                    variety=%s,
                    planting_date=%s,
                    soil_type=%s,
                    irrigation_type=%s
                WHERE id=%s AND user_id=%s
            """, (
                request.form.get("field_name"),
                request.form.get("location"),
                request.form.get("land_area"),
                request.form.get("crop_name"),
                request.form.get("variety"),
                request.form.get("planting_date") or None,
                request.form.get("soil_type"),
                request.form.get("irrigation_type"),
                field_id,
                session["user_id"]
            ))

            db.commit()
            flash("Farm details updated successfully!")
            return redirect(url_for("my_field"))

        return render_template(
            "edit_field.html",
            field=field,
            current_language=session.get("language", "en")
        )

    finally:
        cursor.close()
        db.close()


# ==========================================
# DELETE FIELD
# ==========================================

@app.route("/delete-field/<int:field_id>", methods=["POST"])
@login_required
def delete_field(field_id):

    db = get_db_connection()
    cursor = db.cursor()

    try:
        cursor.execute("""
            DELETE FROM farmer_fields
            WHERE id=%s AND user_id=%s
        """, (field_id, session["user_id"]))

        db.commit()

        flash("Farm details deleted successfully!")

        return redirect(url_for("my_field"))

    finally:
        cursor.close()
        db.close()

# ==========================================

@app.route("/my-field", methods=["GET", "POST"])
@login_required
def my_field():

    db = None
    cursor = None

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        if request.method == "POST":

            field_name = request.form.get("field_name", "").strip()
            location = request.form.get("location", "").strip()
            land_area = request.form.get("land_area", "").strip()
            crop_name = request.form.get("crop_name", "Pomegranate")
            variety = request.form.get("variety", "").strip()
            planting_date = request.form.get("planting_date") or None
            soil_type = request.form.get("soil_type", "").strip()
            irrigation_type = request.form.get("irrigation_type", "").strip()

            if not field_name or not location or not land_area:
                flash("Please fill all required fields.")
            else:
                cursor.execute("""
                    INSERT INTO farmer_fields
                    (user_id, field_name, location, land_area,
                     crop_name, variety, planting_date,
                     soil_type, irrigation_type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    session["user_id"],
                    field_name,
                    location,
                    land_area,
                    crop_name,
                    variety,
                    planting_date,
                    soil_type,
                    irrigation_type
                ))

                db.commit()
                flash("Farm details saved successfully!")
                return redirect(url_for("my_field"))

        cursor.execute("""
            SELECT * FROM farmer_fields
            WHERE user_id = %s
            ORDER BY created_at DESC
        """, (session["user_id"],))

        fields = cursor.fetchall()

        return render_template(
            "my_field.html",
            fields=fields,
            current_language=session.get("language", "en")
        )

    except Exception as e:
        print("MY FIELD ERROR:", repr(e))
        return "Unable to load My Field. Check terminal.", 500

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()

# ==========================================
# DISEASE DETECTION
# ==========================================


@app.route("/disease-detection", methods=["GET", "POST"])
@login_required
def disease_detection():

    if request.method == "POST":

        image = request.files.get("crop_image")

        # 1. Validate image
        if image is None or image.filename == "":
            flash("Please upload a crop image.")
            return redirect(url_for("disease_detection"))

        if not allowed_file(image.filename):
            flash("Only JPG, JPEG, PNG and WEBP images are allowed.")
            return redirect(url_for("disease_detection"))

        # 2. Check image size (5 MB)
        image_bytes = image.read()

        if len(image_bytes) > 5 * 1024 * 1024:
            flash("Image size must be less than 5 MB.")
            return redirect(url_for("disease_detection"))

        if not image_bytes:
            flash("The uploaded image is empty.")
            return redirect(url_for("disease_detection"))

        image.seek(0)

        original_name = secure_filename(image.filename)
        extension = original_name.rsplit(".", 1)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}.{extension}"

        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

        image_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            unique_filename
        )

        try:

            # 3. Save image
            image.save(image_path)

            print("Uploaded image:", unique_filename)

            # 4. Check Gemini API key
            api_key = os.getenv("GEMINI_API_KEY")

            if not api_key:
                raise ValueError("GEMINI_API_KEY is missing in .env file.")

            # 5. Selected language
            output_language = (
                "Kannada"
                if session.get("language", "en") == "kn"
                else "English"
            )

            # 6. Prepare image MIME type
            mime_type = image.mimetype

            if mime_type not in [
                "image/jpeg",
                "image/png",
                "image/webp"
            ]:
                mime_type = {
                    "jpg": "image/jpeg",
                    "jpeg": "image/jpeg",
                    "png": "image/png",
                    "webp": "image/webp"
                }.get(extension, "image/jpeg")

            # 7. AI image analysis prompt
            prompt = f"""
You are an expert agricultural plant identification
and disease diagnosis specialist.

Analyze ONLY the uploaded image.

The farmer has NOT selected any crop or entered any location.

First identify the plant or crop visible in the image.
Then analyze whether it shows disease symptoms.

Write every text value in {output_language}.
Keep JSON keys exactly as provided.

Important instructions:

- Identify the crop from the image itself.
- Never assume the crop is pomegranate.
- Do not use any manually supplied crop or location.
- If the crop cannot be identified, say Unknown.
- Identify only diseases supported by visible evidence.
- Do not invent symptoms or visual evidence.
- If the image is unclear, explain uncertainty.
- If no disease symptoms are visible, set is_disease to false.
- Do not identify insects as plant diseases.
- Recommend safe agricultural practices.
- Do not invent pesticide names or chemical doses.
- Recommend expert inspection when necessary.
- Confidence values are estimates, not guarantees.

Return ONLY valid JSON in this structure:

{{
    "crop_name": "Identified crop name or Unknown",
    "is_disease": true,
    "possible_causes": [
        {{
            "name": "Disease name",
            "confidence": 85,
            "evidence": "Visible evidence in the image",
            "distinguishing_symptoms": "Symptoms",
            "damage": "Damage caused to the crop",
            "treatment": [
                "Treatment method 1",
                "Treatment method 2"
            ],
            "prevention": [
                "Prevention method 1",
                "Prevention method 2"
            ]
        }}
    ],
    "needs_expert_inspection": false,
    "overall_note": "Additional observation for the farmer"
}}

If no disease is visible, return an empty possible_causes list.
If the crop cannot be identified, clearly mention that.
"""

            # 8. Connect Gemini AI
            client = genai.Client(api_key=api_key)

            response = client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=[
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type=mime_type
                    ),
                    prompt
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )

            # 9. Read AI response
            response_text = response.text.strip()

            if response_text.startswith("```"):
                response_text = response_text.replace(
                    "```json", "", 1
                )
                response_text = response_text.replace(
                    "```", ""
                ).strip()

            disease_result = json.loads(response_text)

            if not isinstance(disease_result, dict):
                raise ValueError("Invalid AI response format.")

            disease_result.setdefault("crop_name", "Unknown")
            disease_result.setdefault("is_disease", False)
            disease_result.setdefault("possible_causes", [])
            disease_result.setdefault(
                "needs_expert_inspection", False
            )
            disease_result.setdefault("overall_note", "")

            # AI identified crop
            detected_crop = disease_result.get(
                "crop_name", "Unknown"
            )

            print("Detected crop:", detected_crop)
            print("Disease AI Analysis Completed")

            # 10. Save analysis in MySQL history
            db = None
            cursor = None

            try:
                db = get_db_connection()
                cursor = db.cursor()

                possible_causes = disease_result.get(
                    "possible_causes", []
                )

                if possible_causes:
                    main_disease = possible_causes[0]

                    disease_name = main_disease.get(
                        "name", "Unknown Disease"
                    )

                    confidence = float(
                        main_disease.get("confidence", 0)
                    )
                else:
                    disease_name = "No Disease Detected"
                    confidence = 0

                recommendation_text = json.dumps(
                    disease_result,
                    ensure_ascii=False
                )

                cursor.execute("""
                    INSERT INTO detection_history
                    (
                        user_id,
                        crop_name,
                        detection_type,
                        image_filename,
                        disease_name,
                        confidence,
                        recommendation
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    session.get("user_id"),
                    detected_crop,
                    "Crop Disease Detection",
                    unique_filename,
                    disease_name,
                    confidence,
                    recommendation_text
                ))

                db.commit()

                print("Crop Disease History Saved Successfully")

            except Exception as history_error:
                print(
                    "Crop History Save Error:",
                    repr(history_error)
                )

            finally:
                if cursor:
                    cursor.close()

                if db:
                    db.close()

            # 11. Display result
            return render_template(
                "disease_detection.html",
                disease_result=disease_result,
                crop=detected_crop,
                image_filename=unique_filename
            )

        except Exception as error:

            print("Disease AI Error:", repr(error))

            flash(
                "AI disease analysis failed. Please try again."
            )

            return redirect(url_for("disease_detection"))

    return render_template("disease_detection.html")

@app.route('/get_weather')
def weather_api():

    latitude = request.args.get('lat')
    longitude = request.args.get('lon')

    if not latitude or not longitude:
        return jsonify({
            "error": "Location is required"
        }), 400

    try:
        latitude = float(latitude)
        longitude = float(longitude)

        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return jsonify({"error": "Invalid location"}), 400

    except ValueError:
        return jsonify({"error": "Invalid coordinates"}), 400

    weather = get_weather(latitude, longitude)

    if weather is None:
        return jsonify({"error": "Weather data unavailable"}), 503

    return jsonify(weather)
@app.route('/weather_risk')
def weather_risk():
    latitude = request.args.get('lat')
    longitude = request.args.get('lon')

    if not latitude or not longitude:
        return jsonify({"error": "Location is required"}), 400

    try:
        latitude = float(latitude)
        longitude = float(longitude)

        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return jsonify({"error": "Invalid location"}), 400

    except ValueError:
        return jsonify({"error": "Invalid coordinates"}), 400

    weather = get_weather(latitude, longitude)

    if weather is None:
        return jsonify({"error": "Weather data unavailable"}), 503

    temperature = weather["temperature"]
    humidity = weather["humidity"]
    rainfall = weather["rainfall"]
    wind_speed = weather["wind_speed"]

    alerts = []

    # High humidity
    if humidity >= 85:
        alerts.append({
            "type": "high",
            "title_en": "High Humidity Warning",
            "title_kn": "ಹೆಚ್ಚಿನ ತೇವಾಂಶದ ಎಚ್ಚರಿಕೆ",
            "message_en": "High humidity may favour fungal diseases. Monitor pomegranate plants.",
            "message_kn": "ಹೆಚ್ಚಿನ ತೇವಾಂಶವು ಶಿಲೀಂಧ್ರ ರೋಗಗಳಿಗೆ ಅನುಕೂಲವಾಗಬಹುದು. ದಾಳಿಂಬೆ ಗಿಡಗಳನ್ನು ಗಮನಿಸಿ.",
            "recommendation_title_en": "Crop Protection Recommendations",
            "recommendation_title_kn": "ಬೆಳೆ ರಕ್ಷಣೆಯ ಸಲಹೆಗಳು",
            "recommendation_en": [
                "Inspect leaves, stems and fruits regularly.",
                "Maintain proper airflow between plants.",
                "Avoid unnecessary overhead watering.",
                "Remove visibly diseased plant parts safely."
            ],
            "recommendation_kn": [
                "ಎಲೆಗಳು, ಕಾಂಡಗಳು ಮತ್ತು ಹಣ್ಣುಗಳನ್ನು ನಿಯಮಿತವಾಗಿ ಪರಿಶೀಲಿಸಿ.",
                "ಗಿಡಗಳ ನಡುವೆ ಸರಿಯಾದ ಗಾಳಿಯ ಸಂಚಾರ ಇರಲಿ.",
                "ಅಗತ್ಯವಿಲ್ಲದ ಮೇಲಿನಿಂದ ನೀರು ಹಾಕುವುದನ್ನು ತಪ್ಪಿಸಿ.",
                "ರೋಗ ಲಕ್ಷಣಗಳಿರುವ ಭಾಗಗಳನ್ನು ಸುರಕ್ಷಿತವಾಗಿ ತೆಗೆದುಹಾಕಿ."
            ]
        })

    elif humidity >= 75:
        alerts.append({
            "type": "moderate",
            "title_en": "Humidity Alert",
            "title_kn": "ತೇವಾಂಶದ ಸೂಚನೆ",
            "message_en": "Humidity is elevated. Inspect leaves and fruits.",
            "message_kn": "ತೇವಾಂಶ ಹೆಚ್ಚಾಗಿದೆ. ಎಲೆಗಳು ಮತ್ತು ಹಣ್ಣುಗಳನ್ನು ಪರಿಶೀಲಿಸಿ.",
            "recommendation_title_en": "Crop Protection Recommendations",
            "recommendation_title_kn": "ಬೆಳೆ ರಕ್ಷಣೆಯ ಸಲಹೆಗಳು",
            "recommendation_en": [
                "Check leaves and fruits for fungal symptoms.",
                "Maintain good airflow around plants.",
                "Avoid excess irrigation."
            ],
            "recommendation_kn": [
                "ಎಲೆಗಳು ಮತ್ತು ಹಣ್ಣುಗಳಲ್ಲಿ ಶಿಲೀಂಧ್ರದ ಲಕ್ಷಣಗಳನ್ನು ಪರಿಶೀಲಿಸಿ.",
                "ಗಿಡಗಳ ಸುತ್ತ ಉತ್ತಮ ಗಾಳಿಯ ಸಂಚಾರ ಇರಲಿ.",
                "ಅತಿಯಾದ ನೀರಾವರಿ ತಪ್ಪಿಸಿ."
            ]
        })

    # Heavy rainfall
    if rainfall >= 10:
        alerts.append({
            "type": "high",
            "title_en": "Heavy Rain Warning",
            "title_kn": "ಭಾರೀ ಮಳೆಯ ಎಚ್ಚರಿಕೆ",
            "message_en": "Heavy rainfall detected. Check field drainage.",
            "message_kn": "ಭಾರೀ ಮಳೆ ದಾಖಲಾಗಿದೆ. ಹೊಲದ ನೀರು ಹರಿಯುವ ವ್ಯವಸ್ಥೆ ಪರಿಶೀಲಿಸಿ.",
            "recommendation_title_en": "Rain Protection Recommendations",
            "recommendation_title_kn": "ಮಳೆ ಸಮಯದ ಬೆಳೆ ರಕ್ಷಣೆಯ ಸಲಹೆಗಳು",
            "recommendation_en": [
                "Check drainage channels in the field.",
                "Remove standing water near plant roots.",
                "Avoid irrigation when the soil is waterlogged.",
                "Inspect plants after heavy rainfall."
            ],
            "recommendation_kn": [
                "ಹೊಲದಲ್ಲಿನ ನೀರು ಹರಿಯುವ ಕಾಲುವೆಗಳನ್ನು ಪರಿಶೀಲಿಸಿ.",
                "ಗಿಡಗಳ ಬೇರುಗಳ ಬಳಿ ನಿಂತ ನೀರನ್ನು ಹೊರಹಾಕಿ.",
                "ಮಣ್ಣು ನೀರಿನಿಂದ ತುಂಬಿರುವಾಗ ನೀರಾವರಿ ಮಾಡಬೇಡಿ.",
                "ಭಾರೀ ಮಳೆಯ ನಂತರ ಗಿಡಗಳನ್ನು ಪರಿಶೀಲಿಸಿ."
            ]
        })

    elif rainfall >= 2:
        alerts.append({
            "type": "moderate",
            "title_en": "Rain Alert",
            "title_kn": "ಮಳೆಯ ಸೂಚನೆ",
            "message_en": "Rain has been recorded. Check soil moisture before irrigation.",
            "message_kn": "ಮಳೆ ದಾಖಲಾಗಿದೆ. ನೀರಾವರಿಗೆ ಮೊದಲು ಮಣ್ಣಿನ ತೇವಾಂಶ ಪರಿಶೀಲಿಸಿ.",
            "recommendation_title_en": "Rain Protection Recommendations",
            "recommendation_title_kn": "ಮಳೆ ಸಮಯದ ಬೆಳೆ ರಕ್ಷಣೆಯ ಸಲಹೆಗಳು",
            "recommendation_en": [
                "Check soil moisture before watering.",
                "Keep drainage channels clear.",
                "Monitor plants for rain-related damage."
            ],
            "recommendation_kn": [
                "ನೀರು ಹಾಕುವ ಮೊದಲು ಮಣ್ಣಿನ ತೇವಾಂಶ ಪರಿಶೀಲಿಸಿ.",
                "ನೀರು ಹರಿಯುವ ಕಾಲುವೆಗಳನ್ನು ಸ್ವಚ್ಛವಾಗಿಡಿ.",
                "ಮಳೆಯಿಂದ ಗಿಡಗಳಿಗೆ ಹಾನಿಯಾಗಿದೆಯೇ ಎಂದು ಗಮನಿಸಿ."
            ]
        })

    # High temperature
    if temperature >= 38:
        alerts.append({
            "type": "high",
            "title_en": "High Temperature Warning",
            "title_kn": "ಹೆಚ್ಚಿನ ತಾಪಮಾನದ ಎಚ್ಚರಿಕೆ",
            "message_en": "High temperature may cause heat stress.",
            "message_kn": "ಹೆಚ್ಚಿನ ತಾಪಮಾನವು ಗಿಡಗಳಿಗೆ ಬಿಸಿಲಿನ ಒತ್ತಡ ಉಂಟುಮಾಡಬಹುದು.",
            "recommendation_title_en": "Heat Protection Recommendations",
            "recommendation_title_kn": "ಬಿಸಿಲಿನಿಂದ ಬೆಳೆ ರಕ್ಷಣೆಯ ಸಲಹೆಗಳು",
            "recommendation_en": [
                "Monitor soil moisture regularly.",
                "Irrigate according to soil moisture and crop needs.",
                "Use suitable organic mulch to conserve soil moisture.",
                "Watch for leaf wilting and scorching."
            ],
            "recommendation_kn": [
                "ಮಣ್ಣಿನ ತೇವಾಂಶವನ್ನು ನಿಯಮಿತವಾಗಿ ಗಮನಿಸಿ.",
                "ಮಣ್ಣಿನ ತೇವಾಂಶ ಮತ್ತು ಬೆಳೆಯ ಅಗತ್ಯಕ್ಕೆ ಅನುಗುಣವಾಗಿ ನೀರು ಹಾಕಿ.",
                "ಮಣ್ಣಿನ ತೇವಾಂಶ ಕಾಪಾಡಲು ಸೂಕ್ತ ಸಾವಯವ ಹೊದಿಕೆ ಬಳಸಿ.",
                "ಎಲೆಗಳು ಬಾಡುವುದು ಅಥವಾ ಸುಡುವ ಲಕ್ಷಣಗಳನ್ನು ಗಮನಿಸಿ."
            ]
        })

    elif temperature >= 35:
        alerts.append({
            "type": "moderate",
            "title_en": "Temperature Alert",
            "title_kn": "ತಾಪಮಾನದ ಸೂಚನೆ",
            "message_en": "Temperature is elevated. Monitor plants for heat stress.",
            "message_kn": "ತಾಪಮಾನ ಹೆಚ್ಚಾಗಿದೆ. ಗಿಡಗಳಲ್ಲಿ ಬಿಸಿಲಿನ ಒತ್ತಡದ ಲಕ್ಷಣಗಳನ್ನು ಗಮನಿಸಿ.",
            "recommendation_title_en": "Heat Protection Recommendations",
            "recommendation_title_kn": "ಬಿಸಿಲಿನಿಂದ ಬೆಳೆ ರಕ್ಷಣೆಯ ಸಲಹೆಗಳು",
            "recommendation_en": [
                "Check soil moisture regularly.",
                "Avoid water stress.",
                "Monitor leaves for wilting."
            ],
            "recommendation_kn": [
                "ಮಣ್ಣಿನ ತೇವಾಂಶವನ್ನು ನಿಯಮಿತವಾಗಿ ಪರಿಶೀಲಿಸಿ.",
                "ನೀರಿನ ಕೊರತೆಯಿಂದ ಗಿಡಗಳಿಗೆ ಒತ್ತಡ ಉಂಟಾಗದಂತೆ ನೋಡಿಕೊಳ್ಳಿ.",
                "ಎಲೆಗಳು ಬಾಡುತ್ತಿವೆಯೇ ಎಂದು ಗಮನಿಸಿ."
            ]
        })

    # Strong wind
    if wind_speed >= 30:
        alerts.append({
            "type": "high",
            "title_en": "Strong Wind Warning",
            "title_kn": "ಬಲವಾದ ಗಾಳಿಯ ಎಚ್ಚರಿಕೆ",
            "message_en": "Strong winds may damage branches.",
            "message_kn": "ಬಲವಾದ ಗಾಳಿಯಿಂದ ಗಿಡದ ಕೊಂಬೆಗಳಿಗೆ ಹಾನಿಯಾಗಬಹುದು.",
            "recommendation_title_en": "Wind Protection Recommendations",
            "recommendation_title_kn": "ಗಾಳಿಯಿಂದ ಬೆಳೆ ರಕ್ಷಣೆಯ ಸಲಹೆಗಳು",
            "recommendation_en": [
                "Check support for young plants.",
                "Secure loose plant supports.",
                "Inspect branches for damage."
            ],
            "recommendation_kn": [
                "ಎಳೆಯ ಗಿಡಗಳ ಆಸರೆಯನ್ನು ಪರಿಶೀಲಿಸಿ.",
                "ಸಡಿಲವಾಗಿರುವ ಗಿಡದ ಆಸರೆಗಳನ್ನು ಭದ್ರಪಡಿಸಿ.",
                "ಕೊಂಬೆಗಳಿಗೆ ಹಾನಿಯಾಗಿದೆಯೇ ಎಂದು ಪರಿಶೀಲಿಸಿ."
            ]
        })

    # Safe weather
    if not alerts:
        alerts.append({
            "type": "safe",
            "title_en": "No Weather Warning",
            "title_kn": "ಹವಾಮಾನದ ಎಚ್ಚರಿಕೆ ಇಲ್ಲ",
            "message_en": "No major weather warning detected. Continue regular crop monitoring.",
            "message_kn": "ಪ್ರಮುಖ ಹವಾಮಾನ ಎಚ್ಚರಿಕೆ ಕಂಡುಬಂದಿಲ್ಲ. ಬೆಳೆಗಳನ್ನು ನಿಯಮಿತವಾಗಿ ಗಮನಿಸುತ್ತಿರಿ.",
            "recommendation_title_en": "General Crop Care",
            "recommendation_title_kn": "ಸಾಮಾನ್ಯ ಬೆಳೆ ಆರೈಕೆ",
            "recommendation_en": [
                "Inspect leaves, stems and fruits regularly.",
                "Monitor soil moisture.",
                "Maintain proper field drainage.",
                "Watch for unusual crop symptoms."
            ],
            "recommendation_kn": [
                "ಎಲೆಗಳು, ಕಾಂಡಗಳು ಮತ್ತು ಹಣ್ಣುಗಳನ್ನು ನಿಯಮಿತವಾಗಿ ಪರಿಶೀಲಿಸಿ.",
                "ಮಣ್ಣಿನ ತೇವಾಂಶವನ್ನು ಗಮನಿಸಿ.",
                "ಹೊಲದಲ್ಲಿ ಸರಿಯಾದ ನೀರು ಹರಿಯುವ ವ್ಯವಸ್ಥೆ ಇರಲಿ.",
                "ಬೆಳೆಯಲ್ಲಿ ಅಸಾಮಾನ್ಯ ಲಕ್ಷಣಗಳಿವೆಯೇ ಎಂದು ಗಮನಿಸಿ."
            ]
        })

    return jsonify({
        "weather": weather,
        "alerts": alerts
    })





@app.route('/pest-detection', methods=['GET', 'POST'])
@login_required
def pest_detection():

    if request.method == 'GET':
        return render_template('pest_detection.html')

    file = request.files.get('pest_image')

    if file is None or file.filename == '':
        flash("Please select a pest image.")
        return redirect(url_for('pest_detection'))

    allowed_extensions = {'jpg', 'jpeg', 'png', 'webp'}

    original_filename = secure_filename(file.filename)

    if (
        '.' not in original_filename
        or original_filename.rsplit('.', 1)[1].lower()
        not in allowed_extensions
    ):
        flash("Only JPG, JPEG, PNG and WEBP images are allowed.")
        return redirect(url_for('pest_detection'))

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        flash("Gemini API key is missing. Check your .env file.")
        return redirect(url_for('pest_detection'))

    extension = original_filename.rsplit('.', 1)[1].lower()

    mime_types = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'webp': 'image/webp'
    }

    mime_type = mime_types[extension]

    upload_folder = os.path.join(
        app.static_folder,
        'uploads',
        'pests'
    )

    os.makedirs(upload_folder, exist_ok=True)

    safe_filename = f"{uuid.uuid4().hex}.{extension}"
    image_path = os.path.join(upload_folder, safe_filename)

    db = None
    cursor = None

    try:
        # 1. Read and validate image
        image_bytes = file.read()

        if not image_bytes:
            raise ValueError("Uploaded image is empty.")

        if len(image_bytes) > 5 * 1024 * 1024:
            raise ValueError("Image size must be below 5 MB.")

        # 2. Save uploaded image
        with open(image_path, 'wb') as image_file:
            image_file.write(image_bytes)

        # 3. Language selection
        language = session.get('language', 'en')

        output_language = (
            "Kannada"
            if language == "kn"
            else "English"
        )

        # 4. Gemini AI connection
        client = genai.Client(api_key=api_key)

        # 5. Specialist pest identification prompt
        prompt = f"""
You are an expert agricultural entomologist and crop protection specialist.

Your task is to carefully examine the uploaded crop image.

The image may contain any crop, including:
Pomegranate, tomato, mango, grape, chilli, cotton,
vegetables, pulses or other agricultural crops.

OUTPUT LANGUAGE:
Write every descriptive value in {output_language}.
Keep JSON keys in English exactly as specified.

IMPORTANT ANALYSIS:

A. CROP IDENTIFICATION
- Identify the crop if possible.
- If uncertain, say Unknown.
- Do not guess the crop without visual evidence.

B.
B. ADVANCED DIFFERENTIAL PEST IDENTIFICATION

Act as a senior agricultural entomologist with expertise in
visual insect identification and crop protection.

Carefully inspect the complete uploaded image before identifying pests.

Examine:
- Upper and lower leaf surfaces
- Leaf edges and veins
- Stems and branches
- Flowers and fruits
- Insects, eggs, larvae and feeding marks
- Clusters of insects and visible damage patterns

IDENTIFICATION PROCESS:

1. Identify the crop using visible evidence.
2. Identify every visually distinguishable pest.
3. Consider alternative pest species that could explain the same evidence.
4. Compare candidates based on body shape, colour, markings,
   size, location and feeding pattern.
5. Rank up to 4 distinct possible pests by visual likelihood.
6. Give a separate evidence-based explanation for every candidate.

STRICT RULES:

- Do not stop after the first familiar pest.
- Do not assume a pest based only on crop name.
- Do not invent additional pest candidates.
- Do not duplicate the same pest using different names.
- Do not include pests without supporting visual evidence.
- If only one pest is supported, return only one.
- If identification is uncertain, clearly mention it.
- Never claim laboratory-level certainty from an image.

For each pest return:
- Common name
- Scientific name
- Independent confidence estimate (0-100)
- Specific visible evidence
- Affected crops
- Damage caused
- Individual control methods
- Individual prevention methods

Confidence scores must represent visual confidence,
not a requirement to fill four results.


C. DISEASE IDENTIFICATION
- Examine the image for visible disease symptoms.
- Identify up to 3 possible diseases if supported by evidence.
- Do not confuse insect damage with disease.
- Explain the visible evidence for each disease.
- Include symptoms, damage, treatment and prevention.

D. FARMER SAFETY
- Prefer Integrated Pest Management (IPM).
- Include cultural, mechanical and biological control where suitable.
- Do not invent pesticide names.
- Do not provide unsupported chemical doses.
- Recommend local agricultural expert inspection when uncertain.

E. IMAGE QUALITY
- If the image is blurry or unclear, explain the limitation.
- Do not claim a pest is present when it is not visible.
- If the crop appears healthy, clearly mention that no obvious pest
  or disease symptoms were detected.

CONFIDENCE:
- Confidence is an estimate, not a laboratory-confirmed probability.
- Each confidence score is an independent estimate.
- Scores do not need to add up to 100.
- Never use 100% unless the visual evidence is exceptionally clear.

Return ONLY valid JSON.
Do not include Markdown or code fences.

Use exactly this structure:

{{
  "crop_name": "",
  "is_pest_visible": false,

  "pest_details": {{
    "name": "",
    "scientific_name": "",
    "confidence": 0,
    "evidence": "",
    "affected_crops": [],
    "damage": "",
    "control_methods": [],
    "prevention": []
  }},

  "possible_pests": [
    {{
      "name": "",
      "scientific_name": "",
      "confidence": 0,
      "evidence": "",
      "affected_crops": [],
      "damage": "",
      "control_methods": [],
      "prevention": []
    }}
  ],

  "is_disease_visible": false,

  "possible_diseases": [
    {{
      "name": "",
      "confidence": 0,
      "evidence": "",
      "symptoms": "",
      "damage": "",
      "treatment": [],
      "prevention": []
    }}
  ],

  "needs_expert_inspection": false,
  "overall_note": ""
}}

If no pest is visible:
- is_pest_visible must be false.
- possible_pests must be [].
- pest_details.name must be empty.

If pests are visible:
- is_pest_visible must be true.
- pest_details must contain the highest-ranked pest.
- possible_pests must contain the supported pest results.

If no disease is visible:
- is_disease_visible must be false.
- possible_diseases must be [].
"""

        # 6. Send image to Gemini
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type
                ),
                prompt
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        if not response.text:
            raise ValueError("Gemini returned an empty response.")

        # 7. Parse AI JSON
        response_text = response.text.strip()

        if response_text.startswith("```"):
            response_text = response_text.replace(
                "```json", "", 1
            )
            response_text = response_text.replace(
                "```", ""
            ).strip()

        pest_result = json.loads(response_text)

        if not isinstance(pest_result, dict):
            raise ValueError("Invalid AI response format.")

        # 8. Ensure required fields exist
        pest_result.setdefault("crop_name", "Unknown")
        pest_result.setdefault("is_pest_visible", False)
        pest_result.setdefault("is_disease_visible", False)
        pest_result.setdefault("possible_pests", [])
        pest_result.setdefault("possible_diseases", [])
        pest_result.setdefault("needs_expert_inspection", False)
        pest_result.setdefault("overall_note", "")
        possible_diseases = pest_result.get("possible_diseases", [])
        clean_diseases = []

        default_pest = {
            "name": "",
            "scientific_name": "",
            "confidence": 0,
            "evidence": "",
            "affected_crops": [],
            "damage": "",
            "control_methods": [],
            "prevention": []
        }

        pest_details = pest_result.get("pest_details")

        if not isinstance(pest_details, dict):
            pest_details = default_pest.copy()

        pest_result["pest_details"] = {
            **default_pest,
            **pest_details
        }

       
        # 9. Validate and normalize possible pest list
        possible_pests = pest_result.get("possible_pests", [])

        if not isinstance(possible_pests, list):
            possible_pests = []

        # IMPORTANT:
        # If Gemini returns pest_details but forgets possible_pests,
        # preserve the actual Gemini identification.
        if not possible_pests:
            existing_pest = pest_result.get("pest_details", {})

            if isinstance(existing_pest, dict) and existing_pest.get("name"):
                possible_pests = [existing_pest]

        clean_pests = []
        seen_pests = set()

        for pest in possible_pests[:4]:

            if not isinstance(pest, dict):
                continue

            pest_name = str(pest.get("name", "")).strip()

            if not pest_name:
                continue

            # Avoid duplicate pest names
            if pest_name.lower() in seen_pests:
                continue

            seen_pests.add(pest_name.lower())

            clean_pest = {
                **default_pest,
                **pest
            }

            try:
                clean_pest["confidence"] = max(
                    0,
                    min(100, float(clean_pest.get("confidence", 0) or 0))
                )
            except (ValueError, TypeError):
                clean_pest["confidence"] = 0

            clean_pests.append(clean_pest)

        pest_result["possible_pests"] = clean_pests

        # 10. Keep the highest-ranked pest compatible with old template
        if clean_pests:
            pest_result["is_pest_visible"] = True
            pest_result["pest_details"] = clean_pests[0]
        else:
            pest_result["is_pest_visible"] = False
            pest_result["pest_details"] = default_pest.copy()


        if not isinstance(possible_diseases, list):
            possible_diseases = []

        clean_diseases = []

        for disease in possible_diseases[:3]:

            if not isinstance(disease, dict):
                continue

            if not disease.get("name"):
                continue

            try:
                disease["confidence"] = max(
                    0,
                    min(100, float(disease.get("confidence", 0) or 0))
                )
            except (ValueError, TypeError):
                disease["confidence"] = 0

            clean_diseases.append(disease)

        pest_result["possible_diseases"] = clean_diseases

        if clean_diseases:
            pest_result["is_disease_visible"] = True
        else:
            pest_result["is_disease_visible"] = False

        print("PEST AI ANALYSIS COMPLETED")
        print("CROP:", pest_result.get("crop_name"))
        print("PESTS FOUND:", len(clean_pests))
        print("DISEASES FOUND:", len(clean_diseases))
        
        
        # 10. Keep the highest-ranked pest compatible with old template
        if clean_pests:
            pest_result["is_pest_visible"] = True
            pest_result["pest_details"] = clean_pests[0]
        else:
            pest_result["is_pest_visible"] = False
            pest_result["pest_details"] = default_pest.copy()

        # 11. Validate disease list
        possible_diseases = pest_result.get(
            "possible_diseases", []
        )

        if not isinstance(possible_diseases, list):
            possible_diseases = []

        clean_diseases = []

        for disease in possible_diseases[:3]:

            if not isinstance(disease, dict):
                continue

            if not disease.get("name"):
                continue

            disease = disease.copy()

            try:
                disease["confidence"] = max(
                    0,
                    min(100, float(disease.get("confidence", 0) or 0))
                )
            except (ValueError, TypeError):
                disease["confidence"] = 0

            clean_diseases.append(disease)

        pest_result["possible_diseases"] = clean_diseases

        pest_result["is_disease_visible"] = bool(clean_diseases)
        
        print("PEST AI ANALYSIS COMPLETED")
        print("CROP:", pest_result.get("crop_name"))
        print("PESTS FOUND:", len(clean_pests))

        print("GEMINI IDENTIFIED PESTS:")

        for index, pest in enumerate(clean_pests, start=1):
            print(
                index,
                pest.get("name"),
                pest.get("confidence"),
                pest.get("evidence")
            )

        print("DISEASES FOUND:", len(clean_diseases))



        # 12. SAVE ANALYSIS IN MYSQL HISTORY
        try:
            db = get_db_connection()

            if db is None:
                raise Exception("Database connection failed.")

            cursor = db.cursor()

            user_id = session.get('user_id')

            if clean_pests:
                detected_name = clean_pests[0].get(
                    "name", "Unknown Pest"
                )
                confidence = clean_pests[0].get(
                    "confidence", 0
                )

            elif clean_diseases:
                detected_name = clean_diseases[0].get(
                    "name", "Unknown Disease"
                )
                confidence = clean_diseases[0].get(
                    "confidence", 0
                )

            else:
                detected_name = "No visible pest or disease"
                confidence = 0

            recommendation_text = json.dumps(
                pest_result,
                ensure_ascii=False
            )

            cursor.execute("""
                INSERT INTO detection_history
                (
                    user_id,
                    crop_name,
                    detection_type,
                    image_filename,
                    disease_name,
                    confidence,
                    recommendation
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                user_id,
                pest_result.get("crop_name", ""),
                "Pest Detection",
                safe_filename,
                detected_name,
                confidence,
                recommendation_text
            ))

            db.commit()

            print("Pest Detection History Saved Successfully")

        except Exception as history_error:

            print(
                "Pest History Save Error:",
                repr(history_error)
            )

        finally:

            if cursor:
                cursor.close()

            if db:
                db.close()

        # 13. DISPLAY RESULT
        return render_template(
            "pest_detection.html",
            pest_result=pest_result,
            image_filename=safe_filename
        )

   
    except Exception as error:

        import traceback

        print("\n========== PEST AI ERROR ==========")
        traceback.print_exc()
        print("===================================\n")

        flash(f"Pest analysis failed: {str(error)}")

        return redirect(url_for('pest_detection'))


@app.route('/history')
@login_required
def history():

    db = None
    cursor = None

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT *
            FROM detection_history
            WHERE user_id = %s
            ORDER BY detected_at DESC
        """, (session.get('user_id'),))

        history_records = cursor.fetchall()

        # Convert saved JSON into Python dictionary
        for record in history_records:
            try:
                if record.get('recommendation'):
                    record['recommendation_data'] = json.loads(
                        record['recommendation']
                    )
                else:
                    record['recommendation_data'] = {}
            except (ValueError, TypeError):
                record['recommendation_data'] = {}

        return render_template(
            'history.html',
            history_records=history_records
        )

    except Exception as e:
        print("History Error:", repr(e))
        flash("Unable to load analysis history.")
        return redirect(url_for('dashboard'))

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


            db.close()
    
@app.route('/reports')
@login_required
def reports():
    db = None
    cursor = None

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT *
            FROM detection_history
            WHERE user_id = %s
            ORDER BY detected_at DESC
        """, (session.get('user_id'),))

        report_records = cursor.fetchall()

        # Automatically find images in all upload folders
        uploads_folder = os.path.join(app.static_folder, "uploads")
        image_files = {}

        for root, dirs, files in os.walk(uploads_folder):
            for filename in files:
                image_files[filename] = os.path.relpath(
                    os.path.join(root, filename),
                    app.static_folder
                ).replace("\\", "/")

        for record in report_records:
            filename = record.get('image_filename')

            if filename and filename in image_files:
                record['image_url'] = url_for(
                    'static',
                    filename=image_files[filename]
                )
            else:
                record['image_url'] = None

        disease_count = 0
        pest_count = 0

        for record in report_records:
            detection_type = str(
                record.get('detection_type') or ''
            ).lower()

            if 'disease' in detection_type:
                disease_count += 1
            elif 'pest' in detection_type:
                pest_count += 1

            try:
                if record.get('recommendation'):
                    record['recommendation_data'] = json.loads(
                        record['recommendation']
                    )
                else:
                    record['recommendation_data'] = {}

            except (ValueError, TypeError):
                record['recommendation_data'] = {}

        return render_template(
            'reports.html',
            report_records=report_records,
            total_count=len(report_records),
            disease_count=disease_count,
            pest_count=pest_count,
            current_language=session.get('language', 'en')
        )

    except Exception as e:
        print("Reports Error:", repr(e))
        flash("Unable to load reports.")
        return redirect(url_for('dashboard'))

    finally:
        if cursor:
            cursor.close()

        if db:
            db.close()

@app.route('/delete-history/<int:history_id>', methods=['POST'])
def delete_history(history_id):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = None
    cursor = None

    try:
        db = get_db_connection()
        cursor = db.cursor()

        cursor.execute("""
            DELETE FROM detection_history
            WHERE id = %s AND user_id = %s
        """, (history_id, session['user_id']))

        db.commit()
        flash("Analysis history deleted successfully.")

    except Exception as e:
        print("Delete History Error:", repr(e))
        flash("Unable to delete history.")

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()

    return redirect(url_for('history'))

@app.route('/crop_check')
def crop_check():
    return render_template(
        'crop_check.html',
        current_language=session.get('language', 'en')
    )


# ==========================================
# VOICE ASSISTANT
# ==========================================

@app.route('/voice-assistant')
@login_required
def voice_assistant():
    return render_template(
        'voice_assistant.html',
        current_language=session.get('language', 'en')
    )


# ==========================================
# VOICE ASSISTANT - GEMINI AI API
# ==========================================

@app.route('/voice-assistant/ask', methods=['POST'])
@login_required
def voice_assistant_ask():

    db = None
    cursor = None

    try:
        data = request.get_json(silent=True) or {}

        question = data.get('question', '').strip()
        language = data.get('language', 'en-IN')

        if not question:
            return jsonify({
                'error': 'Please enter your question.'
            }), 400

        api_key = os.getenv('GEMINI_API_KEY')

        if not api_key:
            return jsonify({
                'error': 'Gemini API key is missing.'
            }), 500

        selected_language = (
            'Kannada' if language in ['kn', 'kn-IN']
            else 'English'
        )

        prompt = f"""
You are AgriCare AI, an intelligent agricultural voice assistant.

Farmer's question:
{question}

Instructions:
1. Answer only in {selected_language}.
2. Give clear and practical farming advice.
3. Understand questions about crops, diseases, pests,
   fertilizers, irrigation and farming.
4. Give useful solutions in simple language.
5. Do not invent facts or guarantee results.
6. Keep the answer suitable for voice listening.
7. If the question is unrelated to agriculture,
   politely explain that you are an agricultural assistant.
"""

        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt
        )

        answer = response.text

        if not answer or not answer.strip():
            raise ValueError("Gemini returned an empty response.")

        # Save conversation in MySQL
        db = get_db_connection()
        cursor = db.cursor()

        cursor.execute("""
            INSERT INTO voice_history
            (user_id, question, answer, language)
            VALUES (%s, %s, %s, %s)
        """, (
            session['user_id'],
            question,
            answer,
            language
        ))

        db.commit()

        print("VOICE ASSISTANT RESPONSE GENERATED")
        print("VOICE HISTORY SAVED SUCCESSFULLY")

        return jsonify({
            'answer': answer
        }), 200

    except Exception as e:

        print("VOICE ASSISTANT ERROR:", repr(e))

        if db:
            try:
                db.rollback()
            except Exception:
                pass

        return jsonify({
            'error': 'AI response failed. Please check the server terminal.'
        }), 500

    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


# ==========================================
# VOICE HISTORY
# ==========================================

@app.route('/voice-history')
@login_required
def voice_history():

    db = None
    cursor = None

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT id, question, answer, language, created_at
            FROM voice_history
            WHERE user_id = %s
            ORDER BY created_at DESC
        """, (session['user_id'],))

        history = cursor.fetchall()

        return render_template(
            'voice_history.html',
            history=history,
            current_language=session.get('language', 'en')
        )

    except Exception as e:

        print("VOICE HISTORY ERROR:", repr(e))

        return "Unable to load voice history. Check Flask terminal.", 500

    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


# ==========================================
# RUN APPLICATION
# ==========================================
@app.route('/crop-growth-calendar')
def crop_growth_calendar():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT planting_date, completed_tasks
            FROM crop_calendar_progress
            WHERE user_id = %s
            """,
            (session["user_id"],)
        )

        calendar_data = cursor.fetchone()

    finally:
        cursor.close()
        conn.close()

    return render_template(
        'crop_growth_calendar.html',
        calendar_data=calendar_data
    )

@app.route('/save-crop-calendar', methods=['POST'])
def save_crop_calendar():

    if "user_id" not in session:
        return {"success": False, "message": "Please login"}, 401

    data = request.get_json(silent=True) or {}

    planting_date = data.get("planting_date")
    completed_tasks = data.get("completed_tasks", {})

    if not planting_date:
        return {"success": False, "message": "Planting date required"}, 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()

        if conn is None:
            return {"success": False, "message": "Database connection failed"}, 500

        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO crop_calendar_progress
            (user_id, planting_date, completed_tasks)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
            planting_date = VALUES(planting_date),
            completed_tasks = VALUES(completed_tasks)
            """,
            (
                session["user_id"],
                planting_date,
                json.dumps(completed_tasks)
            )
        )

        conn.commit()

        print("CROP CALENDAR SAVED:", session["user_id"], planting_date)

        return {"success": True, "message": "Calendar saved successfully"}

    except Exception as e:
        if conn:
            conn.rollback()

        print("Calendar save error:", e)

        return {"success": False, "message": str(e)}, 500

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

        conn.close()

if __name__ == "__main__":
    app.run(debug=True)
