def make_move(my_history, opponent_history, round_num, L, H, R, inflation_rate):
    """
    Parameters:
    - my_history: List of integers representing your past moves in this match.
    - opponent_history: List of integers representing your opponent's past moves.
    - round_num: Current round index (starts at 0).
    - L: Minimum possible bid (integer).
    - H: Maximum possible bid (integer).
    - R: Reward/Penalty bonus (integer).
    - inflation_rate: Float representing inflation per round (e.g., 0.05 for 5%).
    
    Returns:
    - An integer between L and H inclusive.
    """
    # Simple strategy: Play Tit-for-Tat if opponent undercut last round, otherwise play H
    if round_num == 0:
        return H
        
    last_opponent_move = opponent_history[-1]
    last_my_move = my_history[-1]
    
    if last_opponent_move < last_my_move:
        return max(L, last_opponent_move)
    
    return H

def make_nim_move(stacks):
    # E.g. [1200, 1500] 
    # Returns (stack_index, amount_to_take)
    
    # Simple logic: take 1 item from the largest stack
    max_stack_idx = stacks.index(max(stacks))
    return max_stack_idx, 1
