import os
import sqlite3
import importlib.util
import random
import json

def load_bot(bot_path, module_name):
    """Dynamically loads a bot script from a given file path."""
    spec = importlib.util.spec_from_file_location(module_name, bot_path)
    bot_module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(bot_module)
        return bot_module
    except Exception as e:
        print(f"Error loading {bot_path}: {e}")
        return None

def run_match(bot1_path, bot2_path, L=2, H=100, R=2, inflation=0.05, rounds=20):
    """Simulates a match between two bots over a set number of rounds."""
    bot1 = load_bot(bot1_path, "bot1")
    bot2 = load_bot(bot2_path, "bot2")

    if not bot1 or not bot2:
        raise ValueError("Failed to load one or both bot modules.")

    history1 = []
    history2 = []
    total_score1 = 0.0
    total_score2 = 0.0
    logs = []

    for r in range(rounds):
        # 1. Execute Bot 1
        try:
            move1 = bot1.make_move(history1, history2, r, L, H, R, inflation)
            move1 = max(L, min(H, int(move1)))
            history1.append(move1)
        except Exception:
            move1 = "ERROR"
            history1.append(H) # Fallback so the opponent doesn't crash reading history

        # 2. Execute Bot 2
        try:
            move2 = bot2.make_move(history2, history1, r, L, H, R, inflation)
            move2 = max(L, min(H, int(move2)))
            history2.append(move2)
        except Exception:
            move2 = "ERROR"
            history2.append(H)

        # 3. Payoff Logic with Error Penalty
        if move1 == "ERROR" and move2 == "ERROR":
            payoff1, payoff2 = 0, 0
        elif move1 == "ERROR":
            payoff1 = 0
            payoff2 = H + R  # Give max points to the other player
        elif move2 == "ERROR":
            payoff1 = H + R  # Give max points to the other player
            payoff2 = 0
        else:
            # Normal Traveler's Dilemma Logic
            if move1 == move2:
                payoff1 = move1
                payoff2 = move2
            elif move1 < move2:
                payoff1 = move1 + R
                payoff2 = move1 - R
            else:
                payoff1 = move2 - R
                payoff2 = move2 + R

        # Apply Inflation/Decay if applicable
        current_multiplier = (1.0 - inflation) ** r
        final_payoff1 = payoff1 * current_multiplier
        final_payoff2 = payoff2 * current_multiplier

        total_score1 += final_payoff1
        total_score2 += final_payoff2

        logs.append({
            "round": r + 1,
            "move1": move1,
            "move2": move2,
            "payoff1": round(final_payoff1, 2),
            "payoff2": round(final_payoff2, 2)
        })

    # --- NORMALIZATION LOGIC ---
    # Calculate the sum of all inflation multipliers over the match
    sum_multipliers = sum((1.0 - inflation) ** r for r in range(rounds))
    
    # Absolute max payoff in a round: Bid H-1, opponent bids H -> (H - 1) + R
    max_round_payoff = (H - 1 + R) if H > L else H
    # Absolute min payoff in a round: Bid H, opponent bids L -> L - R
    min_round_payoff = L - R
    
    total_max = max_round_payoff * sum_multipliers
    total_min = min_round_payoff * sum_multipliers
    
    # Map raw scores to a 0-100 Performance Index
    if total_max > total_min:
        norm_score1 = 100.0 * (total_score1 - total_min) / (total_max - total_min)
        norm_score2 = 100.0 * (total_score2 - total_min) / (total_max - total_min)
    else:
        norm_score1 = 50.0
        norm_score2 = 50.0

    return norm_score1, norm_score2, logs

def execute_tournament(database_path, upload_folder, L=2, H=100, R=2, inflation=0.05, rounds=20, match_count=50, randomize=False):
    """Executes a full round-robin tournament between all active bot submissions."""
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    db = conn.cursor()

    active_subs = db.execute("""
        SELECT u.username, s.filename, u.id as user_id 
        FROM users u 
        JOIN submissions s ON u.id = s.user_id 
        WHERE s.is_active = 1 AND u.role != 'admin'
    """).fetchall()

    if len(active_subs) < 2:
        conn.close()
        return "Tournament requires at least 2 active bots to run."

    # Reset scores
    db.execute("UPDATE users SET score = 0.0")
    
    # Create new tournament record
    db.execute("INSERT INTO tournaments DEFAULT VALUES")
    tournament_id = db.lastrowid

    # Round Robin
    for i in range(len(active_subs)):
        for j in range(i + 1, len(active_subs)):
            bot1_data = active_subs[i]
            bot2_data = active_subs[j]

            bot1_path = os.path.join(upload_folder, bot1_data['username'], bot1_data['filename'])
            bot2_path = os.path.join(upload_folder, bot2_data['username'], bot2_data['filename'])

            match_score1 = 0
            match_score2 = 0
            all_logs = []

            # Run series of matches
            for m in range(match_count):
                cur_L = L
                cur_H = H
                cur_R = R
                cur_inf = inflation
                cur_rounds = rounds

                if randomize:
                    cur_L = max(2, L + random.randint(-2, 2))
                    cur_H = max(10, H + random.randint(-20, 20))
                    cur_R = max(1, R + random.randint(-1, 2))
                    cur_inf = max(0.0, inflation + random.uniform(-0.02, 0.02))
                    cur_rounds = max(5, rounds + random.randint(-5, 10))

                s1, s2, logs = run_match(bot1_path, bot2_path, cur_L, cur_H, cur_R, cur_inf, cur_rounds)
                match_score1 += s1
                match_score2 += s2
                
                # Append game number to logs for tracking in visualizer
                for log_entry in logs:
                    log_entry['game'] = m + 1
                all_logs.extend(logs)

            # Average scores over match count
            avg_score1 = match_score1 / match_count
            avg_score2 = match_score2 / match_count

            # Log Match with JSON dumped logs
            db.execute(
                "INSERT INTO matches (tournament_id, user1, user2, score1, score2, round_by_round) VALUES (?, ?, ?, ?, ?, ?)",
                (tournament_id, bot1_data['username'], bot2_data['username'], avg_score1, avg_score2, json.dumps(all_logs))
            )

            # Update User Scores
            db.execute("UPDATE users SET score = score + ? WHERE id = ?", (avg_score1, bot1_data['user_id']))
            db.execute("UPDATE users SET score = score + ? WHERE id = ?", (avg_score2, bot2_data['user_id']))

    conn.commit()
    conn.close()
    return "Tournament executed successfully!"