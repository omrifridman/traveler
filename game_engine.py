import os
import sys
import importlib.util
import json
import sqlite3

def run_match(bot1_path, bot2_path, L=2, H=100, R=2, inflation_rate=0.05, total_rounds=20):
    """Executes a single repeated match between two bot files."""
    # Dynamic import functions
    def load_bot_func(path):
        try:
            spec = importlib.util.spec_from_file_location("bot_mod", path)
            mod = importlib.util.module_module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod.make_move
        except Exception as e:
            # Fallback if bot code crashes or fails to compile
            return lambda my_h, opp_h, r, l, h, re, inf: l

    func1 = load_bot_func(bot1_path)
    func2 = load_bot_func(bot2_path)

    h1, h2 = [], []
    p1_total_score, p2_total_score = 0.0, 0.0
    round_logs = []

    for r in range(total_rounds):
        # Calculate contemporary discount factor due to cumulative inflation
        # Discount factor delta = 1 / (1 + i)^r
        delta = 1.0 / ((1.0 + inflation_rate) ** r)

        # Execute moves safely wrapped in try/except blocks
        try:
            move1 = int(func1(h1.copy(), h2.copy(), r, L, H, R, inflation_rate))
            if not (L <= move1 <= H): move1 = L
        except:
            move1 = L

        try:
            move2 = int(func2(h2.copy(), h1.copy(), r, L, H, R, inflation_rate))
            if not (L <= move2 <= H): move2 = L
        except:
            move2 = L

        # Calculate nominal payoffs based on game rules
        if move1 == move2:
            base1, base2 = move1, move2
        elif move1 < move2:
            base1 = move1 + R
            base2 = move1 - R
        else:
            base1 = move2 - R
            base2 = move2 + R

        # Apply economic real value discount factor
        real_payoff1 = base1 * delta
        real_payoff2 = base2 * delta

        p1_total_score += real_payoff1
        p2_total_score += real_payoff2

        h1.append(move1)
        h2.append(move2)

        round_logs.append({
            "round": r,
            "move1": move1,
            "move2": move2,
            "payoff1": round(real_payoff1, 2),
            "payoff2": round(real_payoff2, 2)
        })

    return p1_total_score, p2_total_score, round_logs


def execute_tournament(db_path, upload_dir):
    """Finds active scripts, runs round-robin matchups, records metrics."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Fetch active submission per user
    cursor.execute("""
        SELECT u.username, s.filename 
        FROM users u 
        JOIN submissions s ON u.id = s.user_id 
        WHERE s.is_active = 1
    """)
    active_bots = cursor.fetchall()

    if len(active_bots) < 2:
        conn.close()
        return "Not enough active bots to start a tournament."

    # Reset standings / profiles
    scores = {bot[0]: 0.0 for bot in active_bots}
    match_records = []

    # Round Robin Pairings
    for i in range(len(active_bots)):
        for j in range(i + 1, len(active_bots)):
            user1, file1 = active_bots[i]
            user2, file2 = active_bots[j]

            path1 = os.path.join(upload_dir, user1, file1)
            path2 = os.path.join(upload_dir, user2, file2)

            s1, s2, logs = run_match(path1, path2)

            scores[user1] += s1
            scores[user2] += s2

            match_records.append((user1, user2, s1, s2, json.dumps(logs)))

    # Record Tournament metadata entry
    cursor.execute("INSERT INTO tournaments DEFAULT VALUES")
    tournament_id = cursor.lastrowid

    # Record individual match summaries
    for m in match_records:
        cursor.execute("""
            INSERT INTO matches (tournament_id, user1, user2, score1, score2, round_by_round)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (tournament_id, m[0], m[1], m[2], m[3], m[4]))

    # Persist updated global leaderboards
    for username, total_score in scores.items():
        cursor.execute("UPDATE users SET score = score + ? WHERE username = ?", (total_score, username))

    conn.commit()
    conn.close()
    return f"Tournament #{tournament_id} executed successfully!"