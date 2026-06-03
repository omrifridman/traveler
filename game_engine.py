import os
import sqlite3
import importlib.util
import random
import json
import itertools

def run_nim_match(bot1_path, bot2_path, bot3_path, num_stacks, p1_pts, p2_pts, p3_pts):
    bots = [load_bot(bot1_path, "bot1"), load_bot(bot2_path, "bot2"), load_bot(bot3_path, "bot3")]
    if not all(bots): 
        raise ValueError("Failed to load one or more bots.")

    # Initialize stacks with > 1000 items
    stacks = [random.randint(1001, 2000) for _ in range(num_stacks)]
    turn = 0
    logs = []

    while sum(stacks) > 0:
        current_bot = bots[turn % 3]
        try:
            # Bot function: make_nim_move(stacks_list) -> returns (stack_index, amount_to_take)
            stack_idx, amount = current_bot.make_nim_move(list(stacks))
            stack_idx, amount = int(stack_idx), int(amount)

            if 0 <= stack_idx < num_stacks and 0 < amount <= stacks[stack_idx]:
                stacks[stack_idx] -= amount
                logs.append({
                    "round": turn + 1, 
                    "player": (turn % 3) + 1, 
                    "stack_idx": stack_idx, 
                    "amount": amount, 
                    "remaining": list(stacks)
                })
            else:
                raise ValueError("Invalid move")
        except Exception as e:
            # Auto-play penalty: take 1 from the first available stack so the game doesn't stall
            for i in range(num_stacks):
                if stacks[i] > 0:
                    stacks[i] -= 1
                    logs.append({
                        "round": turn + 1, 
                        "player": (turn % 3) + 1, 
                        "stack_idx": i, 
                        "amount": 1, 
                        "remaining": list(stacks), 
                        "error": str(e)
                    })
                    break

        if sum(stacks) == 0:
            break
        turn += 1

    # Winner is the last one to take. 2nd place is the next player. 3rd is the final player.
    winner_idx = turn % 3
    second_idx = (turn + 1) % 3
    third_idx = (turn + 2) % 3

    scores = [0, 0, 0]
    scores[winner_idx] = p1_pts
    scores[second_idx] = p2_pts
    scores[third_idx] = p3_pts

    return scores, logs


def execute_nim_tournament(database_path, upload_folder, num_stacks=2, p1_pts=4, p2_pts=1, p3_pts=-2, match_count=30):
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    db = conn.cursor()

    active_subs = db.execute("""
        SELECT u.username, s.filename, u.id as user_id
        FROM users u
        JOIN submissions s ON u.id = s.user_id
        WHERE s.is_active = 1 AND u.role != 'admin'
    """).fetchall()

    if len(active_subs) < 3:
        conn.close()
        return "Nim Tournament requires at least 3 active bots to run."

    db.execute("UPDATE users SET score = 0.0")
    db.execute("INSERT INTO tournaments DEFAULT VALUES")
    tournament_id = db.lastrowid

    # Play every combination of 3 bots
    for trio in itertools.combinations(active_subs, 3):
        bot_paths = [os.path.join(upload_folder, b['username'], b['filename']) for b in trio]
        match_scores = [0, 0, 0]
        all_logs = []

        for m in range(match_count):
            # Rotate starting player each match for fairness
            rotated_paths = bot_paths[m % 3:] + bot_paths[:m % 3]
            
            # Map the rotated score outputs back to the absolute 0,1,2 user indices
            rotated_indices = [(i - (m % 3)) % 3 for i in range(3)] 

            scores, logs = run_nim_match(*rotated_paths, num_stacks, p1_pts, p2_pts, p3_pts)

            for i in range(3):
                match_scores[i] += scores[rotated_indices[i]]

            for log in logs:
                log['game'] = m + 1
            all_logs.extend(logs)

        avg_scores = [s / match_count for s in match_scores]

        db.execute(
            "INSERT INTO matches (tournament_id, game_mode, user1, user2, user3, score1, score2, score3, round_by_round) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tournament_id, 'nim', trio[0]['username'], trio[1]['username'], trio[2]['username'], avg_scores[0], avg_scores[1], avg_scores[2], json.dumps(all_logs))
        )

        for i in range(3):
            db.execute("UPDATE users SET score = score + ? WHERE id = ?", (avg_scores[i], trio[i]['user_id']))

    conn.commit()
    conn.close()
    return "Nim Tournament executed successfully!"


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