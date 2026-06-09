import sys
import random
import json

"""
作为接入测试框架的示例
仅实现随即落子，请新建或修改此代码，调用你的模型文件完成测试
"""

def main():
    while True:
        line = sys.stdin.readline().strip()
        if not line:
            break

        if line == "end":
            break

        parts = line.split(' ', 1)
        command = parts[0]

        if command == "init":

            print("OK")
            sys.stdout.flush()

        elif command == "action":
            try:
                data = json.loads(parts[1])
                board = data["board"]

                empty_cells = []
                for y in range(len(board)):
                    for x in range(len(board[y])):
                        if board[y][x] == 0:
                            empty_cells.append((x, y))

                if empty_cells:
                    x, y = random.choice(empty_cells)
                    print(f"{x},{y}")
                    sys.stdout.flush()
                else:
                    print("0,0")
                    sys.stdout.flush()

            except Exception as e:
                print(f"0,0")
                sys.stdout.flush()


if __name__ == "__main__":
    main()