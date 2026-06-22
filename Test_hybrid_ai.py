import json
import random
import sys
import time

import ai_player as legacy_ai


DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))
WIN = 10**12
INF = 10**18
TIME_LIMIT = 0.55
RNG = random.Random(20260620)


def opponent(player):
    return 3 - player


def inside(x, y, size):
    return 0 <= x < size and 0 <= y < size


def stone_count(board):
    return sum(1 for row in board for cell in row if cell)


def infer_player(board):
    return 1 if stone_count(board) % 2 == 0 else 2


class GomokuV2:
    def __init__(self):
        self.player = None
        self.deadline = 0.0

    def reset_timer(self):
        self.deadline = time.time() + TIME_LIMIT

    def timeout(self):
        return time.time() >= self.deadline

    def count_side(self, board, x, y, dx, dy, player):
        size = len(board)
        count = 0
        nx, ny = x + dx, y + dy
        while inside(nx, ny, size) and board[ny][nx] == player:
            count += 1
            nx += dx
            ny += dy
        return count

    def has_five(self, board, x, y, player):
        if not inside(x, y, len(board)) or board[y][x] != player:
            return False
        for dx, dy in DIRECTIONS:
            total = 1
            total += self.count_side(board, x, y, dx, dy, player)
            total += self.count_side(board, x, y, -dx, -dy, player)
            if total >= 5:
                return True
        return False

    def is_win_move(self, board, x, y, player):
        if board[y][x] != 0:
            return False
        board[y][x] = player
        ok = self.has_five(board, x, y, player)
        board[y][x] = 0
        return ok

    def center(self, size):
        return size // 2, size // 2

    def center_score(self, size, x, y):
        c = (size - 1) / 2
        return int(max(0, 120 - (abs(x - c) + abs(y - c)) * 9))

    def opening_move(self, board, player):
        size = len(board)
        cx, cy = self.center(size)
        stones = stone_count(board)
        if stones == 0:
            return cx, cy
        if stones == 1 and player == 2:
            options = [(cx + 1, cy + 1), (cx - 1, cy - 1), (cx + 1, cy - 1), (cx - 1, cy + 1)]
            legal = [(x, y) for x, y in options if inside(x, y, size) and board[y][x] == 0]
            if legal:
                return legal[0]
        return None

    def candidates(self, board, radius=2):
        size = len(board)
        stones = []
        for y in range(size):
            for x in range(size):
                if board[y][x] != 0:
                    stones.append((x, y))
        if not stones:
            return [self.center(size)]

        cells = set()
        for sx, sy in stones:
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    if dx == 0 and dy == 0:
                        continue
                    nx, ny = sx + dx, sy + dy
                    if inside(nx, ny, size) and board[ny][nx] == 0:
                        cells.add((nx, ny))
        return list(cells)

    def line_string(self, board, x, y, dx, dy, player):
        size = len(board)
        chars = []
        for i in range(-5, 6):
            nx, ny = x + dx * i, y + dy * i
            if not inside(nx, ny, size):
                chars.append("2")
            else:
                cell = board[ny][nx]
                if cell == 0:
                    chars.append("0")
                elif cell == player:
                    chars.append("1")
                else:
                    chars.append("2")
        return "".join(chars)

    def pattern_score(self, line):
        patterns = (
            ("11111", 100_000_000),
            ("011110", 12_000_000),
            ("011112", 1_600_000),
            ("211110", 1_600_000),
            ("11110", 1_250_000),
            ("01111", 1_250_000),
            ("01110", 420_000),
            ("010110", 390_000),
            ("011010", 390_000),
            ("001110", 95_000),
            ("011100", 95_000),
            ("0101110", 90_000),
            ("0111010", 90_000),
            ("001100", 13_000),
            ("001010", 9_000),
            ("010100", 9_000),
            ("0110", 7_500),
            ("01010", 6_500),
            ("00100", 900),
            ("0100", 650),
            ("0010", 650),
        )
        total = 0
        for pat, score in patterns:
            if pat in line:
                total += score
        return total

    def move_features(self, board, x, y, player):
        if board[y][x] != 0:
            return {"score": -INF, "four": 0, "live_four": 0, "three": 0, "win": False}

        board[y][x] = player
        score = self.center_score(len(board), x, y)
        four = 0
        live_four = 0
        three = 0

        for dx, dy in DIRECTIONS:
            line = self.line_string(board, x, y, dx, dy, player)
            score += self.pattern_score(line)

            if "11111" in line:
                board[y][x] = 0
                return {"score": WIN, "four": 99, "live_four": 99, "three": 99, "win": True}
            if "011110" in line:
                live_four += 1
                four += 2
            if "011112" in line or "211110" in line or "11110" in line or "01111" in line:
                four += 1
            if "01110" in line or "010110" in line or "011010" in line:
                three += 1
            if "001110" in line or "011100" in line or "0101110" in line or "0111010" in line:
                three += 1

        board[y][x] = 0
        return {"score": score, "four": four, "live_four": live_four, "three": three, "win": False}

    def wins_after(self, board, x, y, player):
        if board[y][x] != 0:
            return []
        board[y][x] = player
        wins = []
        for cx, cy in self.candidates(board, 2):
            if self.is_win_move(board, cx, cy, player):
                wins.append((cx, cy))
        board[y][x] = 0
        return wins

    def threat_rank(self, board, x, y, player):
        feat = self.move_features(board, x, y, player)
        if feat["win"]:
            return 100, feat["score"]
        follow = self.wins_after(board, x, y, player)
        rank = 0
        if len(follow) >= 2:
            rank = 96
        elif feat["live_four"] > 0:
            rank = 92
        elif feat["four"] >= 2:
            rank = 90
        elif feat["four"] >= 1 and feat["three"] >= 1:
            rank = 88
        elif len(follow) == 1:
            rank = 78
        elif feat["three"] >= 2:
            rank = 76
        elif feat["three"] == 1:
            rank = 54
        bonus = len(follow) * 3_000_000 + feat["four"] * 900_000 + feat["three"] * 120_000
        return rank, feat["score"] + bonus

    def quick_threat_rank(self, board, x, y, player):
        feat = self.move_features(board, x, y, player)
        if feat["win"]:
            return 100
        if feat["live_four"] > 0:
            return 92
        if feat["four"] >= 2:
            return 90
        if feat["four"] >= 1 and feat["three"] >= 1:
            return 88
        if feat["three"] >= 2:
            return 76
        if feat["four"] >= 1:
            return 68
        if feat["three"] == 1:
            return 50
        return 0

    def immediate_wins(self, board, player, cand):
        wins = [(x, y) for x, y in cand if self.is_win_move(board, x, y, player)]
        wins.sort(key=lambda m: self.move_value(board, m[0], m[1], player), reverse=True)
        return wins

    def move_value(self, board, x, y, player):
        opp = opponent(player)
        attack_rank, attack_score = self.threat_rank(board, x, y, player)
        defend_rank, defend_score = self.threat_rank(board, x, y, opp)
        defense_weight = 1.28 if player == 2 else 1.15
        return attack_score * 1.18 + defend_score * defense_weight + attack_rank * 4_000_000 + defend_rank * 3_800_000

    def leaves_forced_loss(self, board, x, y, player):
        opp = opponent(player)
        if board[y][x] != 0:
            return True
        board[y][x] = player
        cand = self.candidates(board, 2)
        opp_wins = self.immediate_wins(board, opp, cand)
        if len(opp_wins) >= 1:
            board[y][x] = 0
            return True
        for ox, oy in cand:
            if self.quick_threat_rank(board, ox, oy, opp) >= 88:
                board[y][x] = 0
                return True
        board[y][x] = 0
        return False

    def order_moves(self, board, cand, player):
        scored = []
        size = len(board)
        for x, y in cand:
            score = self.move_value(board, x, y, player)
            score += self.center_score(size, x, y)
            scored.append((score, x, y))
        scored.sort(reverse=True)
        return [(x, y) for _, x, y in scored]

    def choose_tactical(self, board, player, cand):
        opp = opponent(player)

        wins = self.immediate_wins(board, player, cand)
        if wins:
            return wins[0]

        opp_wins = self.immediate_wins(board, opp, cand)
        if opp_wins:
            if len(opp_wins) == 1:
                return opp_wins[0]
            return max(opp_wins, key=lambda m: self.move_value(board, m[0], m[1], player))

        own_best = None
        own_rank = -1
        own_score = -INF
        opp_best = None
        opp_rank = -1
        opp_score = -INF

        for x, y in cand:
            rank, score = self.threat_rank(board, x, y, player)
            if rank >= 76 and (rank > own_rank or score > own_score):
                own_best, own_rank, own_score = (x, y), rank, score

            rank, score = self.threat_rank(board, x, y, opp)
            if rank >= 76 and (rank > opp_rank or score > opp_score):
                opp_best, opp_rank, opp_score = (x, y), rank, score

        if own_best is not None and own_rank >= 88:
            return own_best
        if opp_best is not None and opp_rank >= 88 and (own_best is None or own_rank < 88):
            return opp_best
        if own_best is not None and (player == 1 or own_rank >= opp_rank):
            return own_best
        if opp_best is not None and opp_rank >= 76:
            return opp_best
        if own_best is not None:
            return own_best
        return None

    def evaluate_board(self, board, root):
        cand = self.candidates(board, 2)
        own = []
        enemy = []
        opp = opponent(root)
        for x, y in cand:
            own.append(self.move_value(board, x, y, root))
            enemy.append(self.move_value(board, x, y, opp))
        own.sort(reverse=True)
        enemy.sort(reverse=True)
        weights = (1.0, 0.45, 0.24, 0.13, 0.08)
        s1 = sum(int(own[i] * weights[i]) for i in range(min(len(own), len(weights))))
        s2 = sum(int(enemy[i] * weights[i]) for i in range(min(len(enemy), len(weights))))
        defense = 1.18 if root == 2 else 1.08
        return s1 - int(s2 * defense)

    def minimax(self, board, depth, alpha, beta, turn, root):
        if self.timeout() or depth <= 0:
            return self.evaluate_board(board, root)

        cand = self.candidates(board, 2)
        if not cand:
            return 0

        wins = self.immediate_wins(board, turn, cand)
        if wins:
            return WIN if turn == root else -WIN

        opp_wins = self.immediate_wins(board, opponent(turn), cand)
        if len(opp_wins) >= 2:
            return -WIN if turn == root else WIN

        ordered = self.order_moves(board, cand, turn)[:9 if depth >= 2 else 14]

        if turn == root:
            value = -INF
            for x, y in ordered:
                if self.timeout():
                    break
                board[y][x] = turn
                score = self.minimax(board, depth - 1, alpha, beta, opponent(turn), root)
                board[y][x] = 0
                value = max(value, score)
                alpha = max(alpha, value)
                if alpha >= beta:
                    break
            return value

        value = INF
        for x, y in ordered:
            if self.timeout():
                break
            board[y][x] = turn
            score = self.minimax(board, depth - 1, alpha, beta, opponent(turn), root)
            board[y][x] = 0
            value = min(value, score)
            beta = min(beta, value)
            if alpha >= beta:
                break
        return value

    def choose_move(self, board, player):
        if player == 1:
            return legacy_ai.choose_move(board, player, 0.60)

        self.reset_timer()
        size = len(board)
        opening = self.opening_move(board, player)
        if opening is not None:
            return opening

        radius = 3 if stone_count(board) >= 18 else 2
        cand = self.candidates(board, radius)
        if not cand:
            return self.center(size)

        ordered_all = self.order_moves(board, cand, player)
        cand = ordered_all[:40]

        tactical = self.choose_tactical(board, player, cand)
        if tactical is not None:
            return tactical

        safe = [m for m in ordered_all[:18] if not self.leaves_forced_loss(board, m[0], m[1], player)]
        search_pool = safe if safe else ordered_all[:12]
        search_pool = search_pool[:8]

        best_move = search_pool[0]
        best_score = -INF
        depth = 2
        if stone_count(board) < 16 and player == 1:
            depth = 3

        for x, y in search_pool:
            if self.timeout():
                break
            board[y][x] = player
            if self.has_five(board, x, y, player):
                score = WIN
            else:
                score = self.minimax(board, depth - 1, -INF, INF, opponent(player), player)
            board[y][x] = 0

            rank, tactical_score = self.threat_rank(board, x, y, player)
            _, defend_score = self.threat_rank(board, x, y, opponent(player))
            score += int(tactical_score * 0.45 + defend_score * (0.75 if player == 2 else 0.55))
            score += rank * 900_000

            if self.leaves_forced_loss(board, x, y, player):
                score -= 60_000_000

            if score > best_score:
                best_score = score
                best_move = (x, y)

        return best_move


def parse_payload(text, remembered_player):
    data = json.loads(text)
    if isinstance(data, dict):
        board = data["board"]
        player = data.get("current_player", data.get("player", data.get("turn", remembered_player)))
    else:
        board = data
        player = remembered_player
    if player not in (1, 2):
        player = infer_player(board)
    return board, player


def fallback(board):
    size = len(board) if board else 15
    cx = size // 2
    if board and board[cx][cx] == 0:
        return cx, cx
    for y in range(size):
        for x in range(size):
            if board[y][x] == 0:
                return x, y
    return 0, 0


def main():
    ai = GomokuV2()
    remembered_player = None
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        parts = line.split(" ", 1)
        cmd = parts[0]
        if cmd == "end":
            break
        if cmd == "init":
            if len(parts) > 1:
                try:
                    remembered_player = int(parts[1].strip())
                    ai.player = remembered_player
                except Exception:
                    remembered_player = None
            print("OK")
            sys.stdout.flush()
        elif cmd == "action":
            board = None
            try:
                board, player = parse_payload(parts[1], remembered_player)
                x, y = ai.choose_move(board, player)
                if not inside(x, y, len(board)) or board[y][x] != 0:
                    x, y = fallback(board)
                print(f"{x},{y}")
                sys.stdout.flush()
            except Exception:
                x, y = fallback(board) if board else (0, 0)
                print(f"{x},{y}")
                sys.stdout.flush()


if __name__ == "__main__":
    main()
