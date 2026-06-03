import os
import sqlite3
import json
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from game_engine import execute_tournament, run_match, execute_nim_tournament

app = Flask(__name__)
app.secret_key = "super_secret_cyber_key_change_me"
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'submissions')
DATABASE = os.path.join(os.path.dirname(__file__), 'database.db')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.template_filter('clean_name')
def clean_name_filter(s):
    if not s: 
        return ""
    return s.replace('_', ' ').title()

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT DEFAULT 'user', score REAL DEFAULT 0.0)")
        db.execute("CREATE TABLE IF NOT EXISTS submissions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, filename TEXT, is_active INTEGER DEFAULT 0, FOREIGN KEY(user_id) REFERENCES users(id))")
        db.execute("CREATE TABLE IF NOT EXISTS tournaments (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        db.execute("CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY AUTOINCREMENT, tournament_id INTEGER, user1 TEXT, user2 TEXT, score1 REAL, score2 REAL, round_by_round TEXT)")

        try:
            db.execute("ALTER TABLE matches ADD COLUMN game_mode TEXT DEFAULT 'traveler'")
            db.execute("ALTER TABLE matches ADD COLUMN user3 TEXT")
            db.execute("ALTER TABLE matches ADD COLUMN score3 REAL")
        except sqlite3.OperationalError:
            pass # Columns already exist, safely ignore
        
        try:
            db.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'admin123', 'admin')")
            db.execute("INSERT INTO users (username, password, role) VALUES ('ben', '330940552', 'user')")
            db.execute("INSERT INTO users (username, password, role) VALUES ('yonatan', '329371967', 'user')")
            db.execute("INSERT INTO users (username, password, role) VALUES ('eitan', '123456789', 'user')")
            db.execute("INSERT INTO users (username, password, role) VALUES ('shajar', '215826991', 'user')")
            db.execute("INSERT INTO users (username, password, role) VALUES ('lihie', '215790403', 'user')")
            db.execute("INSERT INTO users (username, password, role) VALUES ('itamar', '215713421', 'user')")
            db.execute("INSERT INTO users (username, password, role) VALUES ('gash', '215869819', 'user')")
            db.execute("INSERT INTO users (username, password, role) VALUES ('hayim', '215918293', 'user')")
            db.execute("INSERT INTO users (username, password, role) VALUES ('sasha', '337914147', 'user')")
            db.execute("INSERT INTO users (username, password, role) VALUES ('m00li', '215973181', 'user')")
            db.execute("INSERT INTO users (username, password, role) VALUES ('itai', '328292586', 'user')")
        except sqlite3.IntegrityError: 
            pass
        db.commit()

@app.route('/')
def index():
    if 'user_id' not in session: 
        return redirect(url_for('login'))
    if session.get('role') == 'admin': 
        return redirect(url_for('admin'))
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
            if user['role'] == 'admin':
                return redirect(url_for('admin'))
            return redirect(url_for('dashboard'))
            
        flash("Invalid Credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session: 
        return redirect(url_for('login'))
    if session.get('role') == 'admin': 
        return redirect(url_for('admin'))
    
    db = get_db()
    user_id = session['user_id']
    username = session['username']

    if request.method == 'POST' and 'code_file' in request.files:
        file = request.files['code_file']
        if file and file.filename.endswith('.py'):
            filename = secure_filename(file.filename)
            user_folder = os.path.join(app.config['UPLOAD_FOLDER'], username)
            os.makedirs(user_folder, exist_ok=True)
            
            file.save(os.path.join(user_folder, filename))
            db.execute("INSERT INTO submissions (user_id, filename) VALUES (?, ?)", (user_id, filename))
            db.commit()
            flash("Code script uploaded successfully!")

    action = request.args.get('action')
    sub_id = request.args.get('sub_id')
    if action and sub_id:
        if action == 'activate':
            db.execute("UPDATE submissions SET is_active = 0 WHERE user_id = ?", (user_id,))
            db.execute("UPDATE submissions SET is_active = 1 WHERE id = ? AND user_id = ?", (sub_id, user_id))
        elif action == 'delete':
            sub = db.execute("SELECT * FROM submissions WHERE id = ? AND user_id = ?", (sub_id, user_id)).fetchone()
            if sub:
                try: 
                    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], username, sub['filename']))
                except OSError: 
                    pass
                db.execute("DELETE FROM submissions WHERE id = ?", (sub_id,))
        db.commit()

    subs = db.execute("SELECT * FROM submissions WHERE user_id = ?", (user_id,)).fetchall()
    return render_template('dashboard.html', submissions=subs)

@app.route('/sandbox', methods=['POST'])
def sandbox():
    if 'user_id' not in session:
        return {"error": "Unauthorized"}, 403

    db = get_db()
    game_mode = request.form.get('game_mode', 'traveler')
    bot1_id = request.form.get('bot1_id')
    bot2_id = request.form.get('bot2_id')

    user_id = session['user_id']
    username = session['username']

    def get_bot_path_and_name(bot_id):
        if bot_id == 'system_tft':
            mock_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'system_mock')
            os.makedirs(mock_dir, exist_ok=True)
            mock_path = os.path.join(mock_dir, 'tit_for_tat.py')
            with open(mock_path, 'w') as f:
                f.write("def make_move(my, opp, r, L, H, R, inf):\n    return opp[-1] if r > 0 else H\ndef make_nim_move(s):\n    return s.index(max(s)), 1")
            return mock_path, "🤖 System"
        else:
            sub = db.execute("SELECT * FROM submissions WHERE id = ? AND user_id = ?", (bot_id, user_id)).fetchone()
            if not sub: return None, None
            return os.path.join(app.config['UPLOAD_FOLDER'], username, sub['filename']), sub['filename']

    bot1_path, bot1_name = get_bot_path_and_name(bot1_id)
    bot2_path, bot2_name = get_bot_path_and_name(bot2_id)

    if not bot1_path or not bot2_path:
        return {"error": "Submissions could not be found."}, 404

    if game_mode == 'traveler':
        L = int(request.form.get('L') or 2)
        H = int(request.form.get('H') or 100)
        R = int(request.form.get('R') or 2)
        inflation = float(request.form.get('inflation') or 0.05)
        rounds = int(request.form.get('rounds') or 20)
        
        s1, s2, logs = run_match(bot1_path, bot2_path, L=L, H=H, R=R, inflation=inflation, rounds=rounds)
        return {"mode": "traveler", "bot1": bot1_name, "bot2": bot2_name, "s1": round(s1, 2), "s2": round(s2, 2), "logs": logs}
        
    elif game_mode == 'nim':
        bot3_id = request.form.get('bot3_id')
        bot3_path, bot3_name = get_bot_path_and_name(bot3_id)
        if not bot3_path: return {"error": "Bot 3 is required for Nim."}, 400
        
        stacks = int(request.form.get('num_stacks') or 2)
        p1 = int(request.form.get('p1_score') or 4)
        p2 = int(request.form.get('p2_score') or 1)
        p3 = int(request.form.get('p3_score') or -2)
        
        from game_engine import run_nim_match
        scores, logs = run_nim_match(bot1_path, bot2_path, bot3_path, stacks, p1, p2, p3)
        return {"mode": "nim", "bot1": bot1_name, "bot2": bot2_name, "bot3": bot3_name, "s1": scores[0], "s2": scores[1], "s3": scores[2], "logs": logs}


@app.route('/visualizer/<int:match_id>')
def visualizer(match_id):
    db = get_db()
    match = db.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()

    logs, pairings, unique_games = [], [], []
    if match:
        if match['round_by_round']:
            try:
                logs = json.loads(match['round_by_round'])
                unique_games = sorted(list(set(log.get('game', 1) for log in logs)))
            except Exception:
                logs = []

        # We must select user3, score3, and game_mode so the template knows how to format the list
        pairings = db.execute(
            "SELECT id, user1, user2, user3, score1, score2, score3, game_mode FROM matches WHERE tournament_id = ?",
            (match['tournament_id'],)
        ).fetchall()

    return render_template('visualizer.html', match=match, logs=logs, pairings=pairings, unique_games=unique_games)

@app.route('/scoreboard')
def scoreboard():
    db = get_db()
    users = db.execute("""
        SELECT u.username, u.score, s.filename 
        FROM users u 
        LEFT JOIN submissions s ON u.id = s.user_id AND s.is_active = 1 
        WHERE u.role != 'admin' 
        ORDER BY u.score DESC
    """).fetchall()
    
    matches = db.execute("SELECT * FROM matches ORDER BY id DESC LIMIT 200").fetchall()
    
    return render_template('scoreboard.html', users=users, matches=matches)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if session.get('role') != 'admin': 
        return "Access Denied", 403
        
    db = get_db()
    message = None
    
    if request.method == 'POST' and 'run_tournament' in request.form:
        game_mode = request.form.get('game_mode', 'traveler')
        try:
            if game_mode == 'traveler':
                L = int(request.form.get('L') or 2)
                H = int(request.form.get('H') or 100)
                R = int(request.form.get('R') or 2)
                inflation = float(request.form.get('inflation') or 0.05)
                rounds = int(request.form.get('rounds') or 20)
                match_count = int(request.form.get('match_count') or 50)
                randomize = 'randomize' in request.form
                message = execute_tournament(DATABASE, app.config['UPLOAD_FOLDER'], L, H, R, inflation, rounds, match_count, randomize)
            elif game_mode == 'nim':
                stacks = int(request.form.get('num_stacks') or 2)
                p1 = int(request.form.get('p1_score') or 4)
                p2 = int(request.form.get('p2_score') or 1)
                p3 = int(request.form.get('p3_score') or -2)
                match_count = int(request.form.get('match_count') or 30)
                message = execute_nim_tournament(DATABASE, app.config['UPLOAD_FOLDER'], stacks, p1, p2, p3, match_count)
        except ValueError:
            message = "SYSTEM ERROR: Invalid inputs detected."

    teams = db.execute("""
        SELECT u.username, s.filename 
        FROM users u 
        LEFT JOIN submissions s ON u.id = s.user_id AND s.is_active = 1 
        WHERE u.role != 'admin'
    """).fetchall()
    
    return render_template('admin.html', message=message, teams=teams)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)