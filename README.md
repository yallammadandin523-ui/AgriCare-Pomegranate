# 🌱 AgriCare AI – Smart Agriculture Assistant

**AI-powered agriculture support platform designed to help farmers identify crop diseases, detect pests, monitor weather, and manage crop growth.**

## 🌍 Live Website

https://agricare-pomegranate.onrender.com

## 🚀 Project Overview

AgriCare AI is a smart agriculture web application that uses Artificial Intelligence to support farmers with crop health monitoring and agricultural guidance.

The application provides AI-based disease and pest detection, weather risk monitoring, a smart crop calendar, and a voice assistant with Kannada and English language support.

## ✨ Key Features

- 🌿 **AI Crop Disease Detection** – Upload crop images and receive AI-based disease analysis.
- 🐛 **AI Pest Detection** – Identify possible pests from uploaded images.
- 🌦️ **Weather Monitoring** – Monitor temperature, humidity, rainfall, and wind.
- ⚠️ **Weather Risk Analysis** – Identify potential weather-related agricultural risks.
- 📅 **Smart Crop Growth Calendar** – Track crop activities and growth stages.
- 🎙️ **AI Voice Assistant** – Ask agriculture-related questions.
- 🌐 **Bilingual Support** – English and Kannada language support.
- 👨‍🌾 **Farmer Dashboard** – Manage field information and view detection history.
- 📊 **Reports** – View agricultural detection records.

## 🛠️ Technologies Used

| Technology | Purpose |
|---|---|
| Python | Backend programming |
| Flask | Web framework |
| HTML | Page structure |
| CSS | User interface design |
| MySQL / TiDB | Database |
| Gemini AI | AI image analysis and assistance |
| Open-Meteo | Weather information |
| Render | Web application deployment |
| GitHub | Source code management |

## 📂 Project Structure

```text
AgriCare_Pomegranate/
│
├── app.py
├── database.py
├── translations.py
├── requirements.txt
├── templates/
├── static/
│   ├── css/
│   ├── images/
│   └── uploads/
├── models/
└── README.md
```

## ⚙️ Installation and Setup

1. Clone the repository:

```bash
git clone https://github.com/yallammadandin523-ui/AgriCare-Pomegranate.git
```

2. Open the project folder:

```bash
cd AgriCare-Pomegranate
```

3. Create a virtual environment:

```bash
python -m venv venv
```

4. Activate the environment on Windows:

```powershell
.\venv\Scripts\Activate.ps1
```

5. Install dependencies:

```bash
pip install -r requirements.txt
```

6. Configure the required environment variables for the database and Gemini API.

7. Run the application:

```bash
python app.py
```

## 🔐 Environment Variables

Configure these variables in your local `.env` file or deployment environment:

```env
DB_HOST=your_database_host
DB_PORT=4000
DB_USER=your_database_user
DB_PASSWORD=your_database_password
DB_NAME=agricare_db
GEMINI_API_KEY=your_gemini_api_key
```

**Important:** Never upload passwords, API keys, or private credentials to GitHub.

## 🎯 Project Goal

To make AI-powered agricultural guidance more accessible to farmers and support smarter crop management through technology.

## 👩‍💻 Developer

Developed as an AI-powered smart agriculture web application project.

---

**AgriCare AI – Detect • Monitor • Protect 🌱**