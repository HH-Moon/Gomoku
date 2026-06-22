import json
import math
import random
import sys
import time


DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))
WIN_SCORE = 1_000_000_000
INF = 10_000_000_000
DEFAULT_SIZE = 15
DEFAULT_TIME_LIMIT = 0.60

RNG = random.Random(20260620)
ZOBRIST = {}
TT = {}
KILLERS = {}


class SearchTimeout(Exception):
    pass


def other(player):
    return 3 - player


def on_board(x, y, size):
    return 0 <= x < size and 0 <= y < size


def count_stones(board):
    return sum(1 for row in board for cell in row if cell)


def infer_player(board):
    stones = count_stones(board)
    return 1 if stones % 2 == 0 else 2


def center_of(board):
    size = len(board) if board else DEFAULT_SIZE
    return size // 2, size // 2


def is_empty(board, x, y):
    return on_board(x, y, len(board)) and board[y][x] == 0


def nearest_empty_to_center(board):
    size = len(board)
    cx, cy = center_of(board)
    if is_empty(board, cx, cy):
        return cx, cy
    empties = []
    for y in range(size):
        for x in range(size):
            if board[y][x] == 0:
                dist = abs(x - cx) + abs(y - cy)
                empties.append((dist, x, y))
    if empties:
        _, x, y = min(empties)
        return x, y
    return 0, 0


def count_dir(board, x, y, dx, dy, player):
    size = len(board)
    total = 0
    nx, ny = x + dx, y + dy
    while on_board(nx, ny, size) and board[ny][nx] == player:
        total += 1
        nx += dx
        ny += dy
    return total


def has_five_from(board, x, y, player):
    if not on_board(x, y, len(board)) or board[y][x] != player:
        return False
    for dx, dy in DIRECTIONS:
        total = 1
        total += count_dir(board, x, y, dx, dy, player)
        total += count_dir(board, x, y, -dx, -dy, player)
        if total >= 5:
            return True
    return False


def would_win(board, x, y, player):
    if not is_empty(board, x, y):
        return False
    board[y][x] = player
    ok = has_five_from(board, x, y, player)
    board[y][x] = 0
    return ok


def candidate_moves(board, radius=2):
    size = len(board)
    stones = []
    for y in range(size):
        for x in range(size):
            if board[y][x] != 0:
                stones.append((x, y))

    if not stones:
        return [center_of(board)]

    candidates = set()
    for sx, sy in stones:
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = sx + dx, sy + dy
                if on_board(nx, ny, size) and board[ny][nx] == 0:
                    candidates.add((nx, ny))

    if not candidates:
        return [nearest_empty_to_center(board)]
    return list(candidates)


def center_bonus(board, x, y):
    size = len(board)
    c = (size - 1) / 2.0
    dist = abs(x - c) + abs(y - c)
    return int(max(0, 24 - dist * 3))


def ensure_zobrist(size):
    if size in ZOBRIST:
        return
    table = []
    for y in range(size):
        row = []
        for x in range(size):
            row.append([0, RNG.getrandbits(64), RNG.getrandbits(64)])
        table.append(row)
    ZOBRIST[size] = table


def board_hash(board):
    size = len(board)
    ensure_zobrist(size)
    table = ZOBRIST[size]
    key = 0
    for y in range(size):
        for x in range(size):
            cell = board[y][x]
            if cell:
                key ^= table[y][x][cell]
    return key


def line_chars(board, x, y, dx, dy, player, span=5):
    size = len(board)
    chars = []
    coords = []
    enemy = other(player)
    for step in range(-span, span + 1):
        nx, ny = x + step * dx, y + step * dy
        coords.append((nx, ny))
        if not on_board(nx, ny, size):
            chars.append("O")
        else:
            cell = board[ny][nx]
            if cell == player:
                chars.append("X")
            elif cell == 0:
                chars.append(".")
            elif cell == enemy:
                chars.append("O")
            else:
                chars.append("O")
    return "".join(chars), coords, span


def analyze_move(board, x, y, player):
    if not is_empty(board, x, y):
        return -INF, 0, 0

    board[y][x] = player
    score = center_bonus(board, x, y)
    win_points = set()
    open_threes = 0
    broken_threes = 0

    for dx, dy in DIRECTIONS:
        c1 = count_dir(board, x, y, dx, dy, player)
        c2 = count_dir(board, x, y, -dx, -dy, player)
        run = 1 + c1 + c2

        e1x, e1y = x + dx * (c1 + 1), y + dy * (c1 + 1)
        e2x, e2y = x - dx * (c2 + 1), y - dy * (c2 + 1)
        open_ends = 0
        if on_board(e1x, e1y, len(board)) and board[e1y][e1x] == 0:
            open_ends += 1
        if on_board(e2x, e2y, len(board)) and board[e2y][e2x] == 0:
            open_ends += 1

        if run >= 5:
            board[y][x] = 0
            return WIN_SCORE, 99, 99
        if run == 4:
            score += 520_000 if open_ends == 2 else 170_000 if open_ends == 1 else 0
        elif run == 3:
            score += 58_000 if open_ends == 2 else 7_500 if open_ends == 1 else 0
        elif run == 2:
            score += 2_200 if open_ends == 2 else 240 if open_ends == 1 else 0

        chars, coords, center_idx = line_chars(board, x, y, dx, dy, player, 5)

        for start in range(center_idx - 4, center_idx + 1):
            segment = chars[start:start + 5]
            if len(segment) < 5 or "O" in segment:
                continue
            xs = segment.count("X")
            dots = segment.count(".")
            if xs == 5:
                board[y][x] = 0
                return WIN_SCORE, 99, 99
            if xs == 4 and dots == 1:
                empty_idx = segment.index(".")
                px, py = coords[start + empty_idx]
                if on_board(px, py, len(board)):
                    win_points.add((px, py))
                score += 120_000
            elif xs == 3 and dots == 2:
                score += 5_000
            elif xs == 2 and dots == 3:
                score += 180

        found_open_three = False
        found_broken_three = False
        for length in (5, 6, 7):
            for start in range(0, len(chars) - length + 1):
                if not (start <= center_idx < start + length):
                    continue
                segment = chars[start:start + length]
                if "O" in segment:
                    continue
                if segment in (".XXX.", ".XX.X.", ".X.XX."):
                    found_open_three = True
                elif segment in (".XX.X.", ".X.XX.", ".X.X.X."):
                    found_broken_three = True
                elif length == 6 and segment in (".XXX..", "..XXX.", ".XX.X.", ".X.XX."):
                    found_open_three = True

        if found_open_three:
            open_threes += 1
        elif found_broken_three:
            broken_threes += 1

    wp = len(win_points)
    if wp >= 2:
        score += 7_500_000
    elif wp == 1:
        score += 620_000

    if open_threes >= 2:
        score += 720_000
    elif open_threes == 1:
        score += 85_000

    if broken_threes >= 2:
        score += 130_000
    elif broken_threes == 1:
        score += 22_000

    board[y][x] = 0
    return score, wp, open_threes


def move_score(board, x, y, player):
    score, _, _ = analyze_move(board, x, y, player)
    return score


def winning_moves(board, player, candidates=None):
    if candidates is None:
        candidates = candidate_moves(board, 2)
    wins = []
    for x, y in candidates:
        if would_win(board, x, y, player):
            wins.append((x, y))
    if len(wins) > 1:
        wins.sort(key=lambda p: move_score(board, p[0], p[1], player), reverse=True)
    return wins


def next_winning_count(board, x, y, player, radius=2):
    if not is_empty(board, x, y):
        return 0, []
    board[y][x] = player
    wins = winning_moves(board, player, candidate_moves(board, radius))
    board[y][x] = 0
    return len(wins), wins


def forcing_profile(board, x, y, player):
    score, win_count, open_threes = analyze_move(board, x, y, player)
    follow_wins, win_moves = next_winning_count(board, x, y, player, 2)
    force_rank = threat_rank(score, max(win_count, follow_wins), open_threes)
    if follow_wins >= 2:
        force_rank = max(force_rank, 96)
        score += 12_000_000
    elif follow_wins == 1:
        force_rank = max(force_rank, 70)
        score += 1_100_000
    return force_rank, score, follow_wins, win_moves


def threat_rank(score, win_count, open_threes):
    if score >= WIN_SCORE:
        return 100
    if win_count >= 2:
        return 92
    if win_count >= 1 and open_threes >= 1:
        return 88
    if open_threes >= 2:
        return 84
    if win_count >= 1:
        return 64
    if score >= 1_000_000:
        return 58
    if open_threes >= 1:
        return 76
    return 0


def order_moves(board, moves, player, tt_move=None, ply=0):
    opp = other(player)
    killers = KILLERS.get(ply, ())
    scored = []
    for x, y in moves:
        attack = move_score(board, x, y, player)
        defense = move_score(board, x, y, opp)
        score = attack + int(defense * 1.14) + center_bonus(board, x, y)
        if tt_move == (x, y):
            score += 1_800_000
        if (x, y) in killers:
            score += 260_000
        scored.append((score, x, y))
    scored.sort(reverse=True)
    return [(x, y) for _, x, y in scored]


def weighted_top(scores):
    if not scores:
        return 0
    scores.sort(reverse=True)
    weights = (1.0, 0.42, 0.22, 0.12, 0.07, 0.04)
    total = 0.0
    for i, score in enumerate(scores[:len(weights)]):
        total += score * weights[i]
    return int(total)


def position_shape_score(board, player):
    size = len(board)
    c = (size - 1) / 2.0
    total = 0
    for y in range(size):
        for x in range(size):
            cell = board[y][x]
            if cell == 0:
                continue
            value = int(max(0, 18 - (abs(x - c) + abs(y - c)) * 2))
            if cell == player:
                total += value
            elif cell == other(player):
                total -= value
    return total


def static_eval(board, player):
    candidates = candidate_moves(board, 2)
    own_scores = []
    opp_scores = []
    opp = other(player)
    for x, y in candidates:
        own_scores.append(move_score(board, x, y, player))
        opp_scores.append(move_score(board, x, y, opp))

    own = weighted_top(own_scores)
    enemy = weighted_top(opp_scores)
    return own - int(enemy * 1.08) + position_shape_score(board, player)


def branch_width(depth, stone_count):
    if depth >= 5:
        width = 8
    elif depth == 4:
        width = 10
    elif depth == 3:
        width = 12
    elif depth == 2:
        width = 16
    else:
        width = 24

    if stone_count < 8:
        width += 8
    elif stone_count < 18:
        width += 4
    return width


def tactical_move(board, player, candidates):
    opp = other(player)

    own_wins = winning_moves(board, player, candidates)
    if own_wins:
        return own_wins[0]

    opp_wins = winning_moves(board, opp, candidates)
    if opp_wins:
        return max(opp_wins, key=lambda p: move_score(board, p[0], p[1], player))

    best_force = None
    best_force_rank = -1
    best_force_score = -INF
    best_opp_force = None
    best_opp_force_rank = -1
    best_opp_force_score = -INF

    for x, y in candidates:
        rank, score, _, _ = forcing_profile(board, x, y, player)
        if rank >= 70 and (rank > best_force_rank or score > best_force_score):
            best_force_rank = rank
            best_force_score = score
            best_force = (x, y)

        orank, oscore, _, _ = forcing_profile(board, x, y, opp)
        if orank >= 70 and (orank > best_opp_force_rank or oscore > best_opp_force_score):
            best_opp_force_rank = orank
            best_opp_force_score = oscore
            best_opp_force = (x, y)

    if best_force is not None and best_force_rank >= 88:
        return best_force
    if best_opp_force is not None and best_opp_force_rank >= 76:
        return best_opp_force
    if best_force is not None and best_force_rank >= best_opp_force_rank:
        return best_force
    if best_opp_force is not None:
        return best_opp_force

    return None


def negamax(board, depth, alpha, beta, player, deadline, zkey, ply):
    if time.monotonic() >= deadline:
        raise SearchTimeout

    candidates = candidate_moves(board, 2)
    if not candidates:
        return 0, nearest_empty_to_center(board)

    own_wins = winning_moves(board, player, candidates)
    if own_wins:
        return WIN_SCORE + depth, own_wins[0]

    opp = other(player)
    opp_wins = winning_moves(board, opp, candidates)
    if len(opp_wins) == 1:
        candidates = opp_wins
    elif len(opp_wins) > 1:
        return -WIN_SCORE - depth, opp_wins[0]

    if depth <= 0:
        return static_eval(board, player), None

    key = (zkey, player)
    entry = TT.get(key)
    tt_move = None
    alpha_orig, beta_orig = alpha, beta
    if entry and entry[0] >= depth:
        _, flag, value, move = entry
        tt_move = move
        if flag == "EXACT":
            return value, move
        if flag == "LOWER":
            alpha = max(alpha, value)
        elif flag == "UPPER":
            beta = min(beta, value)
        if alpha >= beta:
            return value, move
    elif entry:
        tt_move = entry[3]

    ordered = order_moves(board, candidates, player, tt_move, ply)
    width = branch_width(depth, count_stones(board))
    ordered = ordered[:min(width, len(ordered))]

    best_score = -INF
    best_move = ordered[0]
    table = ZOBRIST[len(board)]

    for x, y in ordered:
        if time.monotonic() >= deadline:
            raise SearchTimeout

        board[y][x] = player
        child_key = zkey ^ table[y][x][player]
        score, _ = negamax(board, depth - 1, -beta, -alpha, opp, deadline, child_key, ply + 1)
        score = -score
        board[y][x] = 0

        if score > best_score:
            best_score = score
            best_move = (x, y)
        if score > alpha:
            alpha = score
        if alpha >= beta:
            killer_list = KILLERS.setdefault(ply, [])
            if (x, y) not in killer_list:
                killer_list.insert(0, (x, y))
                del killer_list[2:]
            break

    if len(TT) > 160_000:
        TT.clear()

    if best_score <= alpha_orig:
        flag = "UPPER"
    elif best_score >= beta_orig:
        flag = "LOWER"
    else:
        flag = "EXACT"
    TT[key] = (depth, flag, best_score, best_move)
    return best_score, best_move


def choose_move(board, player, time_limit=DEFAULT_TIME_LIMIT):
    if not board or not board[0]:
        return 0, 0

    size = len(board)
    ensure_zobrist(size)
    stones = count_stones(board)
    if stones == 0:
        return center_of(board)

    radius = 3 if stones > 14 else 2
    candidates = candidate_moves(board, radius)
    candidates = order_moves(board, candidates, player)[:42]

    urgent = tactical_move(board, player, candidates)
    if urgent and is_empty(board, urgent[0], urgent[1]):
        return urgent

    best = candidates[0] if candidates else nearest_empty_to_center(board)
    deadline = time.monotonic() + max(0.2, time_limit)
    zkey = board_hash(board)

    max_depth = 5
    if stones < 8:
        max_depth = 4
    elif stones > 54:
        max_depth = 4

    for depth in range(1, max_depth + 1):
        if time.monotonic() >= deadline - 0.18:
            break
        try:
            score, move = negamax(board, depth, -INF, INF, player, deadline, zkey, 0)
        except SearchTimeout:
            break
        if move is not None and is_empty(board, move[0], move[1]):
            best = move
        if abs(score) >= WIN_SCORE // 2:
            break

    if not is_empty(board, best[0], best[1]):
        return nearest_empty_to_center(board)
    return best


def parse_action_payload(text, remembered_player=None):
    data = json.loads(text)
    if isinstance(data, dict):
        board = data.get("board")
        player = data.get("current_player")
        if player is None:
            player = data.get("player")
        if player is None:
            player = data.get("turn")
    else:
        board = data
        player = None

    if player is None:
        player = remembered_player
    if player not in (1, 2):
        player = infer_player(board)
    return board, player


def legal_reply(board, move):
    x, y = move
    if is_empty(board, x, y):
        return x, y
    return nearest_empty_to_center(board)


def main():
    remembered_player = None

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue

        parts = line.split(" ", 1)
        command = parts[0]

        if command == "end":
            break

        if command == "init":
            if len(parts) > 1:
                try:
                    remembered_player = int(parts[1].strip())
                except Exception:
                    remembered_player = None
            print("OK")
            sys.stdout.flush()
            continue

        if command == "action":
            board = None
            try:
                if len(parts) < 2:
                    raise ValueError("missing action payload")
                board, player = parse_action_payload(parts[1], remembered_player)
                move = choose_move(board, player, DEFAULT_TIME_LIMIT)
                x, y = legal_reply(board, move)
                print(f"{x},{y}")
                sys.stdout.flush()
            except Exception:
                try:
                    if board:
                        x, y = nearest_empty_to_center(board)
                    else:
                        x, y = 0, 0
                    print(f"{x},{y}")
                    sys.stdout.flush()
                except Exception:
                    print("0,0")
                    sys.stdout.flush()


if __name__ == "__main__":
    main()
