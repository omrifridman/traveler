def make_move(my, opp, r, L, H, R, inf):
    return opp[-1] if r > 0 else H
def make_nim_move(s):
    return s.index(max(s)), 1