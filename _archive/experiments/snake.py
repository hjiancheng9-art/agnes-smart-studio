"""Snake game using curses.

Controls:
    Arrow keys / WASD : change direction
    p                 : pause / resume
    q                 : quit
    r                 : restart after game over
"""

import curses
import random
import time


def main(stdscr: curses.window) -> None:
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(120)

    sh, sw = stdscr.getmaxyx()
    if sh < 6 or sw < 20:
        stdscr.addstr(0, 0, "Terminal too small (need >=20x6)")
        stdscr.refresh()
        stdscr.getch()
        return

    while True:
        score = play_round(stdscr)
        if not show_game_over(stdscr, score):
            break


def play_round(stdscr: curses.window) -> int:
    sh, sw = stdscr.getmaxyx()
    cy, cx = sh // 2, sw // 4

    snake = [(cy, cx), (cy, cx - 1), (cy, cx - 2)]
    direction = (0, 1)  # moving right

    food = place_food(snake, sh, sw)
    score = 0
    paused = False

    while True:
        stdscr.erase()
        draw_frame(stdscr, sh, sw)
        draw_header(stdscr, sw, score, paused)

        stdscr.addch(food[0], food[1], "*")

        for i, (y, x) in enumerate(snake):
            ch = "@" if i == 0 else "#"
            try:
                stdscr.addch(y, x, ch)
            except curses.error:
                pass

        stdscr.refresh()

        key = stdscr.getch()
        direction, paused, quit_flag = handle_key(key, direction, paused)
        if quit_flag:
            return score

        if paused:
            time.sleep(0.05)
            continue

        new_head = (snake[0][0] + direction[0], snake[0][1] + direction[1])

        if (
            new_head[0] <= 0
            or new_head[0] >= sh - 1
            or new_head[1] <= 0
            or new_head[1] >= sw - 1
            or new_head in snake
        ):
            return score

        snake.insert(0, new_head)

        if new_head == food:
            score += 1
            food = place_food(snake, sh, sw)
        else:
            snake.pop()


def place_food(snake, sh: int, sw: int) -> tuple[int, int]:
    while True:
        food = (random.randint(1, sh - 2), random.randint(1, sw - 2))
        if food not in snake:
            return food


def handle_key(key: int, direction: tuple[int, int], paused: bool):
    quit_flag = False
    new_dir = direction

    if key == ord("q"):
        quit_flag = True
    elif key == ord("p"):
        paused = not paused
    else:
        candidate = {
            curses.KEY_UP: (-1, 0),
            ord("w"): (-1, 0),
            curses.KEY_DOWN: (1, 0),
            ord("s"): (1, 0),
            curses.KEY_LEFT: (0, -1),
            ord("a"): (0, -1),
            curses.KEY_RIGHT: (0, 1),
            ord("d"): (0, 1),
        }.get(key)

        if candidate and (candidate[0], candidate[1]) != (-direction[0], -direction[1]):
            new_dir = candidate

    return new_dir, paused, quit_flag


def draw_frame(stdscr: curses.window, sh: int, sw: int) -> None:
    stdscr.border()


def draw_header(stdscr: curses.window, sw: int, score: int, paused: bool) -> None:
    status = " [PAUSED]" if paused else ""
    text = f"Score: {score}{status}  (p=pause q=quit)"
    try:
        stdscr.addstr(0, 1, text[: sw - 2])
    except curses.error:
        pass


def show_game_over(stdscr: curses.window, score: int) -> bool:
    sh, sw = stdscr.getmaxyx()
    msg = f"Game Over!  Score: {score}"
    hint = "[r] restart   [q] quit"

    stdscr.erase()
    draw_frame(stdscr, sh, sw)
    my, mx = sh // 2, max(0, (sw - len(msg)) // 2)
    hy = my + 1
    hx = max(0, (sw - len(hint)) // 2)
    try:
        stdscr.addstr(my, mx, msg)
        stdscr.addstr(hy, hx, hint)
    except curses.error:
        pass
    stdscr.refresh()

    stdscr.nodelay(False)
    while True:
        key = stdscr.getch()
        if key == ord("r"):
            stdscr.nodelay(True)
            return True
        if key == ord("q"):
            stdscr.nodelay(True)
            return False


if __name__ == "__main__":
    curses.wrapper(main)
