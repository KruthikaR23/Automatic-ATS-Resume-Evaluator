from dotenv import load_dotenv
import os
from flask import Flask, request, render_template, jsonify, session, redirect, url_for, send_from_directory, flash
import PyPDF2
import re
import pytesseract
from pdf2image import convert_from_path
from werkzeug.utils import secure_filename
from email_sender import send_email

# Load environment variables early
load_dotenv()

EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ========== JOB ROLES & THEIR KEYWORDS ==========
ROLE_KEYWORDS = {
    'Frontend Developer': ['html', 'css', 'javascript', 'react', 'frontend', 'bootstrap', 'tailwind', 'responsive', 'ui', 'ux', 'webpack', 'dom manipulation', 'figma to code'],
    'Data Analyst': ['excel', 'power bi', 'tableau', 'data analysis', 'visualization', 'statistics', 'sql', 'python', 'insights'],
    'DevOps Developer': ['docker', 'kubernetes', 'aws', 'azure', 'ci/cd', 'linux', 'shell', 'git', 'terraform', 'jenkins'],
    'UI/UX Designer': ['figma', 'adobe xd', 'sketch', 'wireframe', 'prototype', 'user experience', 'ui', 'design thinking', 'ux research'],
    'Web Developer': ['html', 'css', 'javascript', 'php', 'laravel', 'nodejs', 'express', 'mongodb', 'web development'],
    'Software Engineer': ['python', 'java', 'c++', 'oop', 'dbms', 'algorithms', 'data structures', 'system design', 'problem solving']
}

USER_CREDENTIALS = {
    "admin123": {"password": "Admin@123", "role": "Admin"},
    "oviya28": {"password": "OviyaV@2802", "role": "HR"},
    "kruthi22": {"password": "Kruthika@2322", "role": "Interviewer"}
}

# ========== Helper Functions ==========

def extract_text_from_pdf(file_path):
    text = ''
    try:
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text
        if not text.strip():
            images = convert_from_path(file_path)
            for image in images:
                text += pytesseract.image_to_string(image)
    except Exception as e:
        print(f"Error processing PDF: {e}")
    return text.lower()

def extract_personal_details(text):
    email_pattern = r'(?<!\S)[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?!\S)'
    email_matches = re.findall(email_pattern, text)
    email = next((e for e in email_matches if e.endswith('@gmail.com')), email_matches[0] if email_matches else 'Not Found')

    phone_match = re.search(r'\b\d{10,}\b', text)
    phone = phone_match.group(0) if phone_match else 'Not Found'

    lines = text.split('\n')
    name = next((line.strip() for line in lines if line.strip()), 'Not Found')

    return name, phone, email

def calculate_ats_score(text, role):
    if role in ROLE_KEYWORDS:
        keywords = ROLE_KEYWORDS[role]
    else:
        return 0, [], []
    matched = [kw for kw in keywords if kw in text]
    missing = [kw for kw in keywords if kw not in text]
    score = (len(matched) / len(keywords)) * 100 if keywords else 0
    return round(score, 2), matched, missing

def generate_improvement_suggestions(missing):
    return [f"Consider adding '{kw}' to improve your match." for kw in missing]

def get_all_resumes():
    return session.get('resume_results', [])

# ========== Routes ==========

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/choose_role')
def choose_role():
    return render_template('choose_role.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html', selected_role=request.args.get('role'))

    user_id = request.form.get("userID")
    password = request.form.get("password")
    selected_role = request.form.get("role")

    user = USER_CREDENTIALS.get(user_id)
    if not user:
        return render_template('login.html', error="User ID not found", selected_role=selected_role)
    if user["password"] != password:
        return render_template('login.html', error="Incorrect password", selected_role=selected_role)
    if selected_role and user["role"].lower() != selected_role.lower():
        return render_template('login.html', error="Role mismatch", selected_role=selected_role)

    session['user'] = user_id
    session['role'] = user['role']

    if user["role"] == "HR":
        return redirect('/vacancies')
    elif user["role"] == "Interviewer":
        return redirect('/shortlisted')
    elif user["role"] == "Admin":
        return redirect('/admin')

    return redirect('/')

@app.route('/vacancies', methods=['GET', 'POST'])
def vacancies():
    if session.get('role') != "HR":
        return redirect('/')
    if request.method == 'POST':
        role = request.form.get('selected_role')
        if not role:
            return render_template('vacancies.html', roles=ROLE_KEYWORDS.keys(), error="Please select a role.")
        session['selected_role'] = role
        return redirect('/dashboard')
    return render_template('vacancies.html', roles=ROLE_KEYWORDS.keys())

@app.route('/dashboard')
def dashboard():
    if session.get('role') != "HR":
        return redirect('/')

    role_from_get = request.args.get('role')
    if role_from_get:
        session['selected_role'] = role_from_get

    if 'selected_role' not in session:
        return redirect('/vacancies')

    return render_template("dashboard.html", selected_role=session['selected_role'])

@app.route('/analyze', methods=['POST'])
def analyze_resume():
    # Your resume processing logic here...
    # After processing:
    return jsonify({"redirect": "/results.html"})

@app.route('/bulk-upload', methods=['POST'])
def bulk_upload():
    if session.get('role') != "HR":
        return jsonify({'error': 'Unauthorized'}), 401

    if 'resumes' not in request.files:
        return jsonify({'error': 'No files uploaded'}), 400

    selected_role = session.get('selected_role')
    if not selected_role:
        return jsonify({'error': 'Role not selected'}), 400

    files = request.files.getlist('resumes')
    result = []

    for file in files:
        if file and file.filename.lower().endswith('.pdf'):
            filename = secure_filename(file.filename)
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(save_path)

            resume_text = extract_text_from_pdf(save_path)
            name, phone, email = extract_personal_details(resume_text)
            score, matched, missing = calculate_ats_score(resume_text, selected_role)
            suggestions = generate_improvement_suggestions(missing)

            result.append({
                'name': name,
                'phone': phone,
                'email': email,
                'filename': filename,
                'score': score,
                'matched_keywords': matched,
                'missing_keywords': missing,
                'improvement_suggestions': suggestions
            })

    result.sort(key=lambda x: x['score'], reverse=True)
    session['resume_results'] = result

    return jsonify({'redirect': '/results'})

@app.route("/results")
def results():
    if session.get('role') != "HR":
        return redirect('/')
    if 'resume_results' not in session:
        return redirect('/dashboard')
    return render_template("results.html", resumes=session['resume_results'])

@app.route('/shortlisted')
def shortlisted_candidates():
    resumes = get_all_resumes()
    shortlisted = [r for r in resumes if r['score'] > 50]
    return render_template('shortlisted.html', resumes=shortlisted)

@app.route('/email_form', methods=['GET', 'POST'])
def email_form():
    if request.method == 'POST':
        to_email = request.form.get('to_email')
        subject = request.form.get('subject')
        body = request.form.get('body')

        if send_email(to_email, subject, body):
            flash(f"✅ Email sent to {to_email}","Success")
            # IMPORTANT: Use the function name, NOT the template name here
            return redirect(url_for('shortlisted_candidates'))  # Redirect to the function/route
        else:
            flash(f"❌ Failed to send email to {to_email}")

    else:
        to_email = request.args.get('to_email', '')

    return render_template('email_form.html', to_email=to_email)
   
@app.route('/download/<filename>')
def download_resume(filename):
    if 'user' not in session:
        return redirect('/')
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
