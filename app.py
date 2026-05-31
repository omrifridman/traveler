import os
import sqlite3
import json
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from game_engine import execute_tournament, run_match

app = Flask(__name__)
app.secret_key = "super_secret_cyber_key_change_me"
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'submissions')
DATABASE = os.path.join(os.path.dirname(__file__), 'database.db')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT,
                role TEXT DEFAULT 'user',
                score REAL DEFAULT 0.0
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                filename TEXT,
                is_active INTEGER DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS tournaments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER,
                user1 TEXT,
                user2 TEXT,
                score1 REAL,
                score2 REAL,
                round_by_round TEXT
            )
        """)
        # Seed default teams
        try:
            db.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'admin123', 'admin')")
            db.execute("INSERT INTO users (username, password, role) VALUES ('team_alpha', 'pass', 'user')")
            db.execute("INSERT INTO users (username, password, role) VALUES ('team_beta', 'pass', 'user')")
            db.execute("INSERT INTO users (username, password, role) VALUES ('team_gamma', 'pass', 'user')")
        except:
            pass
        db.commit()

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password)).fetchone()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            return redirect(url_for('dashboard'))
        flash("Invalid Credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session: return redirect(url_for('login'))
    db = get_db()
    user_id = session['user_id']
    username = session['username']

    user_dir = os.path.join(app.config['UPLOAD_FOLDER'], username)
    os.makedirs(user_dir, exist_ok=True)

    if request.method == 'POST' and 'code_file' in request.files:
        file = request.files['code_file']
        if file and file.filename.endswith('.py'):
            filename = secure_filename(file.filename)
            file.save(os.path.join(user_dir, filename))
            db.execute("INSERT INTO submissions (user_id, filename) VALUES (?, ?)", (user_id, filename))
            db.commit()
            flash("Code uploaded successfully!")

    action = request.args.get('action')
    sub_id = request.args.get('sub_id')
    if action and sub_id:
        if action == 'activate':
            db.execute("UPDATE submissions SET is_active = 0 WHERE user_id = ?", (user_id,))
            db.execute("UPDATE submissions SET is_active = 1 WHERE id = ? AND user_id = ?", (sub_id, user_id))
        elif action == 'delete':
            sub = db.execute("SELECT * FROM submissions WHERE id = ? AND user_id = ?", (sub_id, user_id)).fetchone()
            if sub:
                try: os.remove(os.path.join(user_dir, sub['filename']))
                except: pass
                db.execute("DELETE FROM submissions WHERE id = ?", (sub_id,))
        db.commit()

    subs = db.execute("SELECT * FROM submissions WHERE user_id = ?", (user_id,)).fetchall()
    return render_template('dashboard.html', submissions=subs)

@app.route('/sandbox', methods=['POST'])
def sandbox():
    if 'user_id' not in session: return "Unauthorized", 403
    db = get_db()
    sub_id = request.form.get('sub_id')
    sub = db.execute("SELECT * FROM submissions WHERE id = ? AND user_id = ?", (sub_id, session['user_id'])).fetchone()
    if not sub: return "Submission not found"

    bot_path = os.path.join(app.config['UPLOAD_FOLDER'], session['username'], sub['filename'])
    mock_bot_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'system_mock')
    os.makedirs(mock_bot_dir, exist_ok=True)
    mock_bot_path = os.path.join(mock_bot_dir, 'tit_for_tat.py')
    with open(mock_bot_path, 'w') as f:
        f.write("def make_move(my, opp, r, L, H, R, inf):\n    return opp[-1] if r > 0 else H")

    s1, s2, logs = run_match(bot_path, mock_bot_path)
    return {"your_score": round(s1, 2), "baseline_score": round(s2, 2), "logs": logs}

@app.route('/scoreboard')
def scoreboard():
    db = get_db()
    # Pull all user teams alongside their active file deployment string name
    users = db.execute("""
        SELECT u.username, u.score, s.filename 
        FROM users u 
        LEFT JOIN submissions s ON u.id = s.user_id AND s.is_active = 1
        WHERE u.role != 'admin' 
        ORDER BY u.score DESC
    """).fetchall()
    matches = db.execute("SELECT * FROM matches ORDER BY id DESC LIMIT 20").fetchall()
    return render_template('scoreboard.html', users=users, matches=matches)

@app.route('/visualizer/<int:match_id>')
def visualizer(match_id):
    db = get_db()
    match = db.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    return render_template('visualizer.html', match=match)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if session.get('role') != 'admin': return "Access Denied", 403
    db = get_db()
    message = None
    if request.method == 'POST' and 'run_tournament' in request.form:
        message = execute_tournament(DATABASE, app.config['UPLOAD_FOLDER'])
    
    # Gather up-to-date deployment rosters for administrative logging
    teams = db.execute("""
        SELECT u.username, s.filename, s.is_active 
        FROM users u
        LEFT JOIN submissions s ON u.id = s.user_id AND s.is_active = 1
        WHERE u.role != 'admin'
    """).fetchall()
    
    return render_template('admin.html', message=message, teams=teams)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)