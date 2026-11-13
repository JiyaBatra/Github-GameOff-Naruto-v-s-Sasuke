import os
import pygame

from battle import (
    WIDTH, HEIGHT, GROUND_Y, FPS, WHITE, RED, BLUE,
    Fighter, Shuriken, draw_health_bar, remove_white,
)

"""
How online sync works (simple, friend-game style):
- Each player moves their OWN fighter and sends its position every frame.
- When you punch / throw, an event is sent to the opponent.
- The player who gets HIT subtracts their own health.
"""


def start_punch(f):
    """Start a punch. Returns the hitbox, or None if on cooldown."""
    if f.attack_cooldown > 0:
        return None
    f.attack_timer = 12
    f.attack_cooldown = 35
    if f.facing == 1:
        return pygame.Rect(int(f.x + f.width - 5), int(f.y + 55), 65, 90)
    return pygame.Rect(int(f.x - 55), int(f.y + 55), 65, 90)


def load_shuriken(asset_folder):
    path = os.path.join(asset_folder, "shur.jpg")
    if os.path.exists(path):
        img = pygame.image.load(path).convert_alpha()
        img = pygame.transform.scale(img, (36, 36))
        return remove_white(img)
    img = pygame.Surface((36, 36), pygame.SRCALPHA)
    pygame.draw.line(img, WHITE, (3, 18), (33, 18), 5)
    pygame.draw.line(img, WHITE, (18, 3), (18, 33), 5)
    pygame.draw.circle(img, WHITE, (18, 18), 5, 2)
    return img


def run_online_battle(net, my_user, opp_user, side, my_char, opp_char,
                      asset_folder="assets"):
    """
    side 0 = left, side 1 = right.
    Returns "lobby" normally or "disconnected" if the server connection died.
    """
    screen = pygame.display.get_surface()
    pygame.display.set_caption("Naruto vs Sasuke - Online Battle")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("arial", 24, bold=True)
    small_font = pygame.font.SysFont("arial", 18)
    big_font = pygame.font.SysFont("arial", 48, bold=True)

    background_path = os.path.join(asset_folder, "bg.jpg")
    if os.path.exists(background_path):
        background = pygame.image.load(background_path).convert()
        background = pygame.transform.scale(background, (WIDTH, HEIGHT))
    else:
        background = None

    shuriken_image = load_shuriken(asset_folder)

    controls = {
        "left": pygame.K_LEFT,
        "right": pygame.K_RIGHT,
        "jump": pygame.K_UP,
    }

    left_x, right_x = 100, 695
    me = Fighter(
        my_char, left_x if side == 0 else right_x,
        controls, 1 if side == 0 else -1, asset_folder
    )
    opp = Fighter(
        opp_char, right_x if side == 0 else left_x,
        controls, -1 if side == 0 else 1, asset_folder
    )

    projectiles = []
    game_over = False
    result_text = ""
    exit_code = "lobby"
    running = True

    while running:
        clock.tick(FPS)

        # ---------- local input events ----------
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                net.send({"t": "leave"})
                pygame.quit()
                raise SystemExit

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

                if not game_over:
                    if event.key == pygame.K_g:
                        hb = start_punch(me)
                        if hb:
                            net.send({
                                "t": "game", "k": "punch",
                                "hb": [hb.x, hb.y, hb.w, hb.h],
                                "dir": me.facing,
                            })
                    if event.key == pygame.K_f and me.projectile_cooldown == 0:
                        me.throw_shuriken(shuriken_image, projectiles)
                        s = projectiles[-1]
                        net.send({
                            "t": "game", "k": "shur",
                            "x": s.x, "y": s.y, "dir": s.direction,
                        })

        # ---------- network messages ----------
        for msg in net.poll():
            t = msg.get("t")

            if t == "disconnected":
                exit_code = "disconnected"
                running = False

            elif t == "opp_left":
                if not game_over:
                    game_over = True
                    result_text = "Opponent left - YOU WIN!"

            elif t == "game":
                try:
                    k = msg["k"]
                    if k == "state":
                        opp.x = float(msg["x"])
                        opp.y = float(msg["y"])
                        opp.facing = int(msg["f"])
                        opp.walk_count = int(msg["w"])
                        opp.on_ground = bool(msg["g"])
                        opp.health = int(msg["h"])
                        opp.hurt_timer = int(msg["ht"])
                        opp.attack_timer = int(msg["at"])
                    elif k == "punch" and not game_over:
                        hitbox = pygame.Rect(*msg["hb"])
                        if hitbox.colliderect(me.rect):
                            me.health = max(0, me.health - 10)
                            me.hurt_timer = 10
                            me.x += 18 * int(msg["dir"])
                            me.x = max(0, min(WIDTH - me.width, me.x))
                    elif k == "shur":
                        projectiles.append(Shuriken(
                            float(msg["x"]), float(msg["y"]),
                            int(msg["dir"]), shuriken_image, opp
                        ))
                except (KeyError, TypeError, ValueError):
                    pass

        # ---------- local game logic ----------
        if not game_over:
            keys = pygame.key.get_pressed()
            me.update(keys, opp)

            for p in projectiles[:]:
                p.update()
                if p.owner is me:
                    if p.rect.colliderect(opp.rect):
                        projectiles.remove(p)      # damage is applied by victim
                        continue
                elif p.rect.colliderect(me.rect):
                    me.health = max(0, me.health - 12)
                    me.hurt_timer = 10
                    projectiles.remove(p)
                    continue
                if p.x < -50 or p.x > WIDTH + 50:
                    projectiles.remove(p)

        # Always send our state (even after game over) so the opponent
        # sees our final health.
        net.send({
            "t": "game", "k": "state",
            "x": round(me.x, 1), "y": round(me.y, 1),
            "f": me.facing, "w": me.walk_count, "g": me.on_ground,
            "h": me.health, "ht": me.hurt_timer, "at": me.attack_timer,
        })

        if not game_over:
            if me.health <= 0:
                game_over = True
                result_text = "YOU LOSE!"
            elif opp.health <= 0:
                game_over = True
                result_text = "YOU WIN!"

        # ---------- drawing ----------
        if background:
            screen.blit(background, (0, 0))
            shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 65))
            screen.blit(shade, (0, 0))
        else:
            screen.fill((45, 55, 75))

        pygame.draw.rect(screen, (35, 35, 45), (0, GROUND_Y + 205, WIDTH, 15))
        pygame.draw.line(
            screen, (215, 205, 175),
            (0, GROUND_Y + 205), (WIDTH, GROUND_Y + 205), 3
        )

        left_f, right_f = (me, opp) if side == 0 else (opp, me)
        left_name = my_user if side == 0 else opp_user
        right_name = opp_user if side == 0 else my_user
        draw_health_bar(
            screen, 35, 48, left_f.health, RED,
            f"{left_name[:14]} ({left_f.name})", font
        )
        draw_health_bar(
            screen, WIDTH - 355, 48, right_f.health, BLUE,
            f"{right_name[:14]} ({right_f.name})", font
        )

        me.draw(screen)
        opp.draw(screen)
        for p in projectiles:
            p.draw(screen)

        screen.blit(
            small_font.render(
                "Move: LEFT/RIGHT | Jump: UP | Punch: G | "
                "Shuriken: F | ESC: leave",
                True, WHITE
            ),
            (20, HEIGHT - 35)
        )

        if game_over:
            shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 175))
            screen.blit(shade, (0, 0))

            text = big_font.render(result_text, True, (255, 220, 90))
            screen.blit(
                text, text.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 25))
            )
            hint = font.render("Press ESC to return to the lobby", True, WHITE)
            screen.blit(
                hint, hint.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 40))
            )

        pygame.display.flip()

    if exit_code != "disconnected":
        net.send({"t": "leave"})
    return exit_code