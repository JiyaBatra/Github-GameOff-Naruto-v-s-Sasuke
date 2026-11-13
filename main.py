import os
import sys

import pygame

from battle import run_battle
from Database import create_account, login_account
from Network import NetClient, PORT
from Online_battle import run_online_battle

pygame.init()

WIDTH, HEIGHT = 900, 600
WIN = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Naruto vs Sasuke")

CLOCK = pygame.time.Clock()

FONT = pygame.font.SysFont("arial", 25)
BIG_FONT = pygame.font.SysFont("arial", 48, bold=True)
SMALL_FONT = pygame.font.SysFont("arial", 18)

WHITE = (255, 255, 255)
BLACK = (15, 15, 25)
RED = (190, 45, 55)
BLUE = (45, 90, 170)
GREEN = (50, 160, 90)
GREY = (100, 100, 115)
DARK = (20, 20, 35)

ASSET_FOLDER = "assets"

try:
    background = pygame.image.load(
        os.path.join(ASSET_FOLDER, "bg.jpg")
    ).convert()
    background = pygame.transform.scale(background, (WIDTH, HEIGHT))
except (pygame.error, FileNotFoundError):
    background = None


# ---------------------------------------------------------------- drawing

def draw_background():
    if background:
        WIN.blit(background, (0, 0))
    else:
        WIN.fill(BLACK)

    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 155))
    WIN.blit(overlay, (0, 0))


def draw_text(text, font, color, x, y, center=True):
    image = font.render(str(text), True, color)
    if center:
        rect = image.get_rect(center=(x, y))
    else:
        rect = image.get_rect(topleft=(x, y))
    WIN.blit(image, rect)


def draw_button(text, rect, color=RED, font=FONT):
    current_color = color
    if rect.collidepoint(pygame.mouse.get_pos()):
        current_color = BLUE

    pygame.draw.rect(WIN, current_color, rect, border_radius=12)
    pygame.draw.rect(WIN, WHITE, rect, 2, border_radius=12)
    draw_text(text, font, WHITE, rect.centerx, rect.centery)


def draw_input(label, value, rect, active, password=False):
    draw_text(label, FONT, WHITE, rect.x, rect.y - 25, center=False)

    pygame.draw.rect(WIN, BLUE if active else GREY, rect, 2, border_radius=8)
    shown = "*" * len(value) if password else value
    draw_text(shown, SMALL_FONT, WHITE, rect.x + 10, rect.centery, center=False)


def draw_title():
    draw_text("NARUTO VS SASUKE", BIG_FONT, WHITE, WIDTH // 2, 90)


# ---------------------------------------------------------------- state

screen = "home"

# Offline login
username = ""
password = ""
current_user = "Guest"
auth_type = "login"
active_input = "username"
message = ""

# Game setup
game_mode = ""
player_one = "Naruto"
player_two = "Sasuke"

# Online
net = NetClient()
online_fields = {"ip": "127.0.0.1", "username": "", "password": ""}
FIELD_ORDER = ["ip", "username", "password"]
FIELD_LIMITS = {"ip": 40, "username": 20, "password": 40}
online_active = "ip"
online_msg = ""
waiting_auth = False
online_user = ""
lobby = {"friends": [], "requests": [], "suggestions": []}
pending_invite = ""
info_msg = ""
add_text = ""
add_active = False
last_refresh = 0

# Buttons - home / offline
play_button = pygame.Rect(325, 190, 250, 55)
online_button = pygame.Rect(325, 255, 250, 55)
login_button = pygame.Rect(325, 320, 250, 55)
guest_button = pygame.Rect(325, 385, 250, 55)
exit_button = pygame.Rect(325, 450, 250, 55)

human_computer_button = pygame.Rect(220, 250, 460, 65)
human_human_button = pygame.Rect(220, 340, 460, 65)

naruto_button = pygame.Rect(170, 270, 250, 70)
sasuke_button = pygame.Rect(480, 270, 250, 70)
start_button = pygame.Rect(325, 430, 250, 60)

username_rect = pygame.Rect(300, 235, 300, 45)
password_rect = pygame.Rect(300, 330, 300, 45)

back_button = pygame.Rect(30, 30, 120, 45)

# Buttons - online connect screen
online_rects = {
    "ip": pygame.Rect(300, 215, 300, 45),
    "username": pygame.Rect(300, 295, 300, 45),
    "password": pygame.Rect(300, 375, 300, 45),
}
online_login_btn = pygame.Rect(300, 445, 145, 45)
online_register_btn = pygame.Rect(455, 445, 145, 45)

# Buttons - lobby
ROW_START = 195
ROW_H = 42
MAX_ROWS = 6
COL_X = [30, 330, 630]
COL_W = 240

accept_invite_btn = pygame.Rect(300, 102, 140, 28)
decline_invite_btn = pygame.Rect(460, 102, 140, 28)
add_rect = pygame.Rect(30, 510, 260, 40)
add_btn = pygame.Rect(300, 510, 90, 40)
refresh_btn = pygame.Rect(700, 510, 170, 40)


def row_btn(col, row, slot=0, width=70):
    x = COL_X[col] + COL_W - width - slot * (width + 5)
    return pygame.Rect(x, ROW_START + row * ROW_H, width, 32)


def row_text(col, row, text, dot_color=None):
    y = ROW_START + row * ROW_H + 16
    x = COL_X[col]
    if dot_color:
        pygame.draw.circle(WIN, dot_color, (x + 8, y), 6)
        x += 22
    draw_text(text, SMALL_FONT, WHITE, x, y - 9, center=False)


# ---------------------------------------------------------------- helpers

def reset_auth():
    global username, password, message, active_input
    username = ""
    password = ""
    message = ""
    active_input = "username"


def online_login(kind):
    """kind is 'login' or 'register'. Connects, then sends credentials."""
    global waiting_auth, online_msg
    if waiting_auth:
        return

    ip = online_fields["ip"].strip() or "127.0.0.1"
    try:
        net.connect(ip, PORT)
    except OSError:
        online_msg = "Cannot reach server. Check the IP and that server.py is running."
        return

    net.send({
        "t": kind,
        "username": online_fields["username"],
        "password": online_fields["password"],
    })
    waiting_auth = True
    online_msg = "Connecting..."


def request_lobby():
    global last_refresh
    net.send({"t": "get_lobby"})
    last_refresh = pygame.time.get_ticks()


def go_offline_menu(text):
    """Return to the online login screen after a problem."""
    global screen, online_msg, waiting_auth, online_user, pending_invite
    net.close()
    waiting_auth = False
    online_user = ""
    pending_invite = ""
    online_msg = text
    screen = "online_connect"


def start_online_match(msg):
    global screen, pending_invite, info_msg
    pending_invite = ""
    result = run_online_battle(
        net,
        online_user,
        msg.get("opp_user", "Opponent"),
        msg.get("side", 0),
        msg.get("me", "Naruto"),
        msg.get("opp", "Sasuke"),
        ASSET_FOLDER,
    )
    pygame.display.set_caption("Naruto vs Sasuke")

    if result == "disconnected":
        go_offline_menu("Disconnected from server.")
    else:
        screen = "online_menu"
        info_msg = "Back in the lobby."
        request_lobby()


def handle_net_messages():
    global screen, online_user, online_msg, waiting_auth
    global lobby, pending_invite, info_msg

    msgs = net.poll()
    for i, msg in enumerate(msgs):
        t = msg.get("t")

        if t == "auth_ok":
            online_user = msg.get("user", "")
            waiting_auth = False
            online_msg = ""
            info_msg = ""
            screen = "online_menu"
            request_lobby()

        elif t == "auth_fail":
            waiting_auth = False
            online_msg = msg.get("msg", "Login failed.")
            net.close()

        elif t == "lobby":
            lobby = {
                "friends": msg.get("friends", []),
                "requests": msg.get("requests", []),
                "suggestions": msg.get("suggestions", []),
            }

        elif t == "info":
            info_msg = msg.get("msg", "")

        elif t == "notify":
            info_msg = msg.get("msg", "")
            if msg.get("refresh"):
                request_lobby()

        elif t == "invited":
            pending_invite = msg.get("from", "")

        elif t == "match_start":
            net.unget(msgs[i + 1:])   # keep anything that arrived after it
            start_online_match(msg)
            return

        elif t == "disconnected":
            if screen == "online_menu" or waiting_auth:
                go_offline_menu("Disconnected from server.")


def draw_lobby():
    draw_text(f"ONLINE LOBBY - {online_user}", FONT, WHITE, WIDTH // 2, 35)
    draw_button("LOGOUT", back_button, GREY)

    if pending_invite:
        pygame.draw.rect(WIN, DARK, (130, 70, 640, 65), border_radius=10)
        pygame.draw.rect(WIN, GREEN, (130, 70, 640, 65), 2, border_radius=10)
        draw_text(
            f"{pending_invite} invited you to a battle!",
            SMALL_FONT, WHITE, WIDTH // 2, 84
        )
        draw_button("ACCEPT", accept_invite_btn, GREEN, SMALL_FONT)
        draw_button("DECLINE", decline_invite_btn, GREY, SMALL_FONT)

    for col, title in enumerate(["FRIENDS", "REQUESTS", "SUGGESTIONS"]):
        draw_text(title, FONT, WHITE, COL_X[col] + COL_W // 2, 160)

    # Friends
    if not lobby["friends"]:
        row_text(0, 0, "No friends yet")
    for i, f in enumerate(lobby["friends"][:MAX_ROWS]):
        row_text(0, i, f["name"][:12], GREEN if f["online"] else GREY)
        if f["online"]:
            draw_button("INVITE", row_btn(0, i), BLUE, SMALL_FONT)

    # Friend requests
    if not lobby["requests"]:
        row_text(1, 0, "No requests")
    for i, name in enumerate(lobby["requests"][:MAX_ROWS]):
        row_text(1, i, name[:12])
        draw_button("NO", row_btn(1, i, 0, 50), GREY, SMALL_FONT)
        draw_button("OK", row_btn(1, i, 1, 50), GREEN, SMALL_FONT)

    # Suggestions
    if not lobby["suggestions"]:
        row_text(2, 0, "No suggestions")
    for i, s in enumerate(lobby["suggestions"][:MAX_ROWS]):
        row_text(2, i, s["name"][:12], GREEN if s["online"] else GREY)
        draw_button("ADD", row_btn(2, i), BLUE, SMALL_FONT)

    draw_text(info_msg, SMALL_FONT, WHITE, WIDTH // 2, 458)

    draw_input("Add friend by username", add_text, add_rect, add_active)
    draw_button("ADD", add_btn, BLUE, SMALL_FONT)
    draw_button("REFRESH", refresh_btn, GREY, SMALL_FONT)


def lobby_click(pos):
    global screen, online_user, pending_invite, add_active, add_text, info_msg

    if back_button.collidepoint(pos):
        net.close()
        online_user = ""
        pending_invite = ""
        screen = "home"
        return

    if pending_invite:
        if accept_invite_btn.collidepoint(pos):
            net.send({"t": "invite_accept", "from": pending_invite})
            pending_invite = ""
            return
        if decline_invite_btn.collidepoint(pos):
            net.send({"t": "invite_decline", "from": pending_invite})
            pending_invite = ""
            return

    for i, f in enumerate(lobby["friends"][:MAX_ROWS]):
        if f["online"] and row_btn(0, i).collidepoint(pos):
            net.send({"t": "invite", "to": f["name"]})
            return

    for i, name in enumerate(lobby["requests"][:MAX_ROWS]):
        if row_btn(1, i, 1, 50).collidepoint(pos):
            net.send({"t": "friend_accept", "from": name})
            return
        if row_btn(1, i, 0, 50).collidepoint(pos):
            net.send({"t": "friend_reject", "from": name})
            return

    for i, s in enumerate(lobby["suggestions"][:MAX_ROWS]):
        if row_btn(2, i).collidepoint(pos):
            net.send({"t": "friend_request", "to": s["name"]})
            return

    if add_btn.collidepoint(pos):
        if add_text.strip():
            net.send({"t": "friend_request", "to": add_text.strip()})
            add_text = ""
        return

    if refresh_btn.collidepoint(pos):
        request_lobby()
        return

    add_active = add_rect.collidepoint(pos)


# ---------------------------------------------------------------- main loop

running = True

while running:
    CLOCK.tick(60)

    for event in pygame.event.get():

        if event.type == pygame.QUIT:
            running = False

        # ---------------- HOME ----------------
        if screen == "home":
            if event.type == pygame.MOUSEBUTTONDOWN:
                if play_button.collidepoint(event.pos):
                    screen = "mode"

                elif online_button.collidepoint(event.pos):
                    if net.connected and online_user:
                        screen = "online_menu"
                        request_lobby()
                    else:
                        online_msg = ""
                        screen = "online_connect"

                elif login_button.collidepoint(event.pos):
                    reset_auth()
                    auth_type = "login"
                    screen = "auth"

                elif guest_button.collidepoint(event.pos):
                    current_user = "Guest"
                    screen = "mode"

                elif exit_button.collidepoint(event.pos):
                    running = False

        # ---------------- OFFLINE AUTH ----------------
        elif screen == "auth":
            if event.type == pygame.MOUSEBUTTONDOWN:
                if back_button.collidepoint(event.pos):
                    screen = "home"

                elif username_rect.collidepoint(event.pos):
                    active_input = "username"

                elif password_rect.collidepoint(event.pos):
                    active_input = "password"

                elif pygame.Rect(300, 400, 145, 45).collidepoint(event.pos):
                    auth_type = "login"
                    message = ""

                elif pygame.Rect(455, 400, 145, 45).collidepoint(event.pos):
                    auth_type = "register"
                    message = ""

                elif pygame.Rect(325, 475, 250, 55).collidepoint(event.pos):
                    if auth_type == "register":
                        success, result_message = create_account(
                            username, password
                        )
                        message = result_message
                        if success:
                            current_user = username
                            screen = "mode"
                    else:
                        if login_account(username, password):
                            current_user = username
                            screen = "mode"
                            message = ""
                        else:
                            message = "Invalid username or password."

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    screen = "home"

                elif event.key == pygame.K_TAB:
                    active_input = (
                        "password" if active_input == "username" else "username"
                    )

                elif event.key == pygame.K_BACKSPACE:
                    if active_input == "username":
                        username = username[:-1]
                    else:
                        password = password[:-1]

                elif event.key == pygame.K_RETURN:
                    if active_input == "username":
                        active_input = "password"

                elif event.unicode.isprintable():
                    if active_input == "username" and len(username) < 20:
                        username += event.unicode
                    elif active_input == "password" and len(password) < 40:
                        password += event.unicode

        # ---------------- ONLINE CONNECT / LOGIN ----------------
        elif screen == "online_connect":
            if event.type == pygame.MOUSEBUTTONDOWN:
                if back_button.collidepoint(event.pos):
                    net.close()
                    waiting_auth = False
                    screen = "home"

                elif online_login_btn.collidepoint(event.pos):
                    online_login("login")

                elif online_register_btn.collidepoint(event.pos):
                    online_login("register")

                else:
                    for key, rect in online_rects.items():
                        if rect.collidepoint(event.pos):
                            online_active = key

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    net.close()
                    waiting_auth = False
                    screen = "home"

                elif event.key == pygame.K_TAB:
                    idx = FIELD_ORDER.index(online_active)
                    online_active = FIELD_ORDER[(idx + 1) % len(FIELD_ORDER)]

                elif event.key == pygame.K_BACKSPACE:
                    online_fields[online_active] = (
                        online_fields[online_active][:-1]
                    )

                elif event.key == pygame.K_RETURN:
                    if online_active == "password":
                        online_login("login")
                    else:
                        idx = FIELD_ORDER.index(online_active)
                        online_active = FIELD_ORDER[idx + 1]

                elif event.unicode.isprintable():
                    if len(online_fields[online_active]) < FIELD_LIMITS[online_active]:
                        online_fields[online_active] += event.unicode

        # ---------------- ONLINE LOBBY ----------------
        elif screen == "online_menu":
            if event.type == pygame.MOUSEBUTTONDOWN:
                lobby_click(event.pos)

            if event.type == pygame.KEYDOWN and add_active:
                if event.key == pygame.K_BACKSPACE:
                    add_text = add_text[:-1]

                elif event.key == pygame.K_RETURN:
                    if add_text.strip():
                        net.send({"t": "friend_request", "to": add_text.strip()})
                        add_text = ""

                elif event.key == pygame.K_ESCAPE:
                    add_active = False

                elif event.unicode.isprintable() and len(add_text) < 20:
                    add_text += event.unicode

        # ---------------- MODE SELECTION ----------------
        elif screen == "mode":
            if event.type == pygame.MOUSEBUTTONDOWN:
                if back_button.collidepoint(event.pos):
                    screen = "home"

                elif human_computer_button.collidepoint(event.pos):
                    game_mode = "Human vs Computer"
                    screen = "characters"

                elif human_human_button.collidepoint(event.pos):
                    game_mode = "Human vs Human"
                    screen = "characters"

        # ---------------- CHARACTER SELECTION ----------------
        elif screen == "characters":
            if event.type == pygame.MOUSEBUTTONDOWN:
                if back_button.collidepoint(event.pos):
                    screen = "mode"

                elif naruto_button.collidepoint(event.pos):
                    player_one = "Naruto"
                    player_two = "Sasuke"

                elif sasuke_button.collidepoint(event.pos):
                    player_one = "Sasuke"
                    player_two = "Naruto"

                elif start_button.collidepoint(event.pos):
                    run_battle(game_mode, player_one, player_two, ASSET_FOLDER)
                    pygame.display.set_caption("Naruto vs Sasuke")
                    screen = "mode"

    # ---------------- NETWORK ----------------
    handle_net_messages()

    if (screen == "online_menu"
            and pygame.time.get_ticks() - last_refresh > 4000):
        request_lobby()

    # ---------------- DRAW ----------------
    draw_background()

    if screen == "home":
        draw_title()
        draw_button("PLAY", play_button)
        draw_button("ONLINE", online_button, GREEN)
        draw_button("LOGIN", login_button, BLUE)
        draw_button("GUEST MODE", guest_button, GREY)
        draw_button("EXIT", exit_button, GREY)

    elif screen == "auth":
        draw_title()
        draw_button("BACK", back_button, GREY)
        draw_text(
            "CREATE ACCOUNT" if auth_type == "register" else "LOGIN",
            BIG_FONT, WHITE, WIDTH // 2, 165
        )
        draw_input("Username", username, username_rect, active_input == "username")
        draw_input(
            "Password", password, password_rect,
            active_input == "password", password=True
        )
        draw_button("LOGIN", pygame.Rect(300, 400, 145, 45), BLUE)
        draw_button("REGISTER", pygame.Rect(455, 400, 145, 45), RED)
        draw_button("CONTINUE", pygame.Rect(325, 475, 250, 55))
        draw_text(message, SMALL_FONT, WHITE, WIDTH // 2, 555)

    elif screen == "online_connect":
        draw_title()
        draw_button("BACK", back_button, GREY)
        draw_text("PLAY ONLINE", BIG_FONT, WHITE, WIDTH // 2, 150)
        draw_input(
            "Server IP", online_fields["ip"],
            online_rects["ip"], online_active == "ip"
        )
        draw_input(
            "Username", online_fields["username"],
            online_rects["username"], online_active == "username"
        )
        draw_input(
            "Password", online_fields["password"],
            online_rects["password"], online_active == "password",
            password=True
        )
        draw_button("LOGIN", online_login_btn, BLUE)
        draw_button("REGISTER", online_register_btn, RED)
        draw_text(online_msg, SMALL_FONT, WHITE, WIDTH // 2, 525)

    elif screen == "online_menu":
        draw_lobby()

    elif screen == "mode":
        draw_title()
        draw_button("BACK", back_button, GREY)
        draw_text("SELECT GAME MODE", BIG_FONT, WHITE, WIDTH // 2, 180)
        draw_button("HUMAN vs COMPUTER", human_computer_button)
        draw_button("HUMAN vs HUMAN", human_human_button, BLUE)
        draw_text("Player: " + current_user, SMALL_FONT, WHITE, WIDTH // 2, 470)

    elif screen == "characters":
        draw_title()
        draw_button("BACK", back_button, GREY)
        draw_text("SELECT YOUR CHARACTER", BIG_FONT, WHITE, WIDTH // 2, 180)
        draw_button("NARUTO", naruto_button, RED)
        draw_button("SASUKE", sasuke_button, BLUE)
        draw_text("Player 1: " + player_one, FONT, WHITE, WIDTH // 2, 390)

        if game_mode == "Human vs Human":
            draw_text("Player 2: " + player_two, FONT, WHITE, WIDTH // 2, 420)
        else:
            draw_text("Computer: " + player_two, FONT, WHITE, WIDTH // 2, 420)

        draw_button("START BATTLE", start_button)

    pygame.display.update()


net.close()
pygame.quit()
sys.exit()