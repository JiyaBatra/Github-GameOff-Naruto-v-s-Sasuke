import os
import random
import pygame

WIDTH, HEIGHT = 900, 600
GROUND_Y = HEIGHT - 220
FPS = 60

WHITE = (245, 245, 245)
BLACK = (15, 15, 20)
RED = (210, 55, 65)
BLUE = (65, 125, 220)
GREEN = (65, 190, 110)
DARK = (25, 25, 35)

# If a character looks backwards when standing, flip this to True/False.
FLIP_STANDING_WHEN_LEFT = True


# ---------------------------------------------------------------- assets

def remove_white(image, threshold=225):
    """Make near-white pixels transparent (JPGs have no alpha)."""
    image = image.convert_alpha()
    for x in range(image.get_width()):
        for y in range(image.get_height()):
            r, g, b, _ = image.get_at((x, y))
            if r > threshold and g > threshold and b > threshold:
                image.set_at((x, y), (r, g, b, 0))
    return image


def load_character(path, size=(105, 220)):
    image = pygame.image.load(path).convert_alpha()
    image = pygame.transform.scale(image, size)
    return remove_white(image)


def load_sprite_set(asset_folder, character):
    if character.lower() == "naruto":
        right_files = ["NR2.jpg", "NR3.jpg"]
        left_files = ["NL2.jpg", "NL3.jpg"]
        standing_file = "Nstanding.jpg"
    else:
        right_files = ["SR1.jpg", "SR2.jpg"]
        left_files = ["SL2.jpg", "SL3.jpg"]
        standing_file = "Sstanding.jpg"

    all_files = right_files + left_files + [standing_file]
    missing = [
        f for f in all_files
        if not os.path.exists(os.path.join(asset_folder, f))
    ]
    if missing:
        raise FileNotFoundError(
            "Missing sprite file(s) in assets folder: " + ", ".join(missing)
        )

    right = [load_character(os.path.join(asset_folder, f)) for f in right_files]
    left = [load_character(os.path.join(asset_folder, f)) for f in left_files]
    standing = load_character(os.path.join(asset_folder, standing_file))
    return right, left, standing


# ---------------------------------------------------------------- shuriken

class Shuriken:
    def __init__(self, x, y, direction, image, owner):
        self.x = float(x)
        self.y = float(y)
        self.direction = direction
        self.image = image
        self.owner = owner
        self.speed = 10
        self.angle = 0
        self.rect = pygame.Rect(int(x), int(y), 36, 36)

    def update(self):
        self.x += self.speed * self.direction
        self.angle = (self.angle + 18 * self.direction) % 360
        self.rect.topleft = (int(self.x), int(self.y))

    def draw(self, surface):
        rotated = pygame.transform.rotate(self.image, self.angle)
        surface.blit(rotated, rotated.get_rect(center=self.rect.center))


# ---------------------------------------------------------------- fighter

class Fighter:
    def __init__(self, name, x, controls, facing, asset_folder):
        self.name = name
        self.x = float(x)
        self.y = float(GROUND_Y)
        self.width = 105
        self.height = 220
        self.speed = 5
        self.facing = facing
        self.controls = controls
        self.health = 100
        self.jump_velocity = 0
        self.on_ground = True
        self.walk_count = 0
        self.attack_timer = 0
        self.attack_cooldown = 0
        self.hurt_timer = 0
        self.projectile_cooldown = 0

        self.right_images, self.left_images, self.standing = load_sprite_set(
            asset_folder, name
        )

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.width, self.height)

    def tick_timers(self):
        if self.hurt_timer > 0:
            self.hurt_timer -= 1
        if self.attack_timer > 0:
            self.attack_timer -= 1
        if self.attack_cooldown > 0:
            self.attack_cooldown -= 1
        if self.projectile_cooldown > 0:
            self.projectile_cooldown -= 1

    def jump(self):
        if self.on_ground:
            self.jump_velocity = -15
            self.on_ground = False

    def apply_gravity(self):
        if not self.on_ground:
            self.y += self.jump_velocity
            self.jump_velocity += 0.75
            if self.y >= GROUND_Y:
                self.y = GROUND_Y
                self.jump_velocity = 0
                self.on_ground = True

    def separate_from(self, opponent):
        """Stop fighters walking through each other."""
        if self.rect.colliderect(opponent.rect):
            if self.x < opponent.x:
                self.x = opponent.x - self.width
            else:
                self.x = opponent.x + opponent.width
            self.x = max(0, min(WIDTH - self.width, self.x))

    def update(self, keys, opponent):
        """Human-controlled update (keys = pygame.key.get_pressed())."""
        self.tick_timers()
        moving = False

        if keys[self.controls["left"]] and self.x > 0:
            self.x -= self.speed
            self.facing = -1
            moving = True

        if keys[self.controls["right"]] and self.x < WIDTH - self.width:
            self.x += self.speed
            self.facing = 1
            moving = True

        if keys[self.controls["jump"]]:
            self.jump()

        self.apply_gravity()
        self.separate_from(opponent)

        if moving and self.on_ground:
            self.walk_count += 1
        elif not moving:
            self.walk_count = 0

    def attack(self, opponent):
        if self.attack_cooldown > 0:
            return False

        self.attack_timer = 12
        self.attack_cooldown = 35

        if self.facing == 1:
            hitbox = pygame.Rect(
                int(self.x + self.width - 5), int(self.y + 55), 65, 90
            )
        else:
            hitbox = pygame.Rect(int(self.x - 55), int(self.y + 55), 65, 90)

        if hitbox.colliderect(opponent.rect):
            opponent.health = max(0, opponent.health - 10)
            opponent.hurt_timer = 10
            opponent.x += 18 * self.facing
            opponent.x = max(0, min(WIDTH - opponent.width, opponent.x))

        return True

    def throw_shuriken(self, shuriken_image, projectiles):
        if self.projectile_cooldown > 0:
            return

        self.projectile_cooldown = 55
        start_x = self.x + self.width if self.facing == 1 else self.x - 36
        start_y = self.y + 85
        projectiles.append(
            Shuriken(start_x, start_y, self.facing, shuriken_image, self)
        )

    def draw(self, surface):
        # Blink while hurt.
        if self.hurt_timer > 0 and self.hurt_timer % 4 < 2:
            return

        if self.walk_count == 0 or not self.on_ground:
            image = self.standing
            if self.facing == -1 and FLIP_STANDING_WHEN_LEFT:
                image = pygame.transform.flip(image, True, False)
        else:
            images = self.right_images if self.facing == 1 else self.left_images
            image = images[(self.walk_count // 8) % len(images)]

        surface.blit(image, (int(self.x), int(self.y)))

        # Simple punch flash so you can see the attack.
        if self.attack_timer > 0:
            if self.facing == 1:
                fist = (int(self.x + self.width + 15), int(self.y + 100))
            else:
                fist = (int(self.x - 15), int(self.y + 100))
            pygame.draw.circle(surface, (255, 220, 90), fist, 14)
            pygame.draw.circle(surface, WHITE, fist, 14, 2)


# ---------------------------------------------------------------- HUD

def draw_health_bar(surface, x, y, health, color, label, font):
    pygame.draw.rect(surface, (65, 65, 75), (x, y, 320, 25), border_radius=8)
    fill_width = int(320 * max(0, health) / 100)
    if fill_width:
        pygame.draw.rect(
            surface, color, (x, y, fill_width, 25), border_radius=8
        )
    pygame.draw.rect(surface, WHITE, (x, y, 320, 25), 2, border_radius=8)
    text = font.render(f"{label}  {health}/100", True, WHITE)
    surface.blit(text, (x, y - 27))


# ---------------------------------------------------------------- AI

def run_ai(p2, p1, projectiles, shuriken_image, state):
    """Basic computer opponent controlling p2."""
    p2.tick_timers()
    state["delay"] -= 1
    distance = p1.rect.centerx - p2.rect.centerx

    moving = False
    if abs(distance) > 115:
        step = p2.speed * 0.72
        p2.x += step if distance > 0 else -step
        p2.facing = 1 if distance > 0 else -1
        moving = True
    else:
        p2.facing = 1 if distance > 0 else -1

    p2.x = max(0, min(WIDTH - p2.width, p2.x))

    if p2.on_ground and random.random() < 0.008:
        p2.jump()

    p2.apply_gravity()
    p2.separate_from(p1)

    if moving and p2.on_ground:
        p2.walk_count += 1
    elif not moving:
        p2.walk_count = 0

    if state["delay"] <= 0:
        if abs(distance) < 145:
            p2.attack(p1)
        elif abs(distance) < 420:
            p2.throw_shuriken(shuriken_image, projectiles)
        state["delay"] = random.randint(35, 65)


# ---------------------------------------------------------------- battle

def run_battle(mode, player_one, player_two, asset_folder="assets"):
    """
    Run one complete battle. Returns to the caller when ESC is pressed.
    """
    if not pygame.get_init():
        pygame.init()

    screen = pygame.display.get_surface()
    if screen is None or screen.get_size() != (WIDTH, HEIGHT):
        screen = pygame.display.set_mode((WIDTH, HEIGHT))

    pygame.display.set_caption("Naruto vs Sasuke - Battle")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("arial", 24, bold=True)
    small_font = pygame.font.SysFont("arial", 18)
    big_font = pygame.font.SysFont("arial", 48, bold=True)

    # Background
    background_path = os.path.join(asset_folder, "bg.jpg")
    if os.path.exists(background_path):
        background = pygame.image.load(background_path).convert()
        background = pygame.transform.scale(background, (WIDTH, HEIGHT))
    else:
        background = None

    # Shuriken image
    shuriken_path = os.path.join(asset_folder, "shur.jpg")
    if os.path.exists(shuriken_path):
        shuriken_image = pygame.image.load(shuriken_path).convert_alpha()
        shuriken_image = pygame.transform.scale(shuriken_image, (36, 36))
        shuriken_image = remove_white(shuriken_image)
    else:
        shuriken_image = pygame.Surface((36, 36), pygame.SRCALPHA)
        pygame.draw.line(shuriken_image, WHITE, (3, 18), (33, 18), 5)
        pygame.draw.line(shuriken_image, WHITE, (18, 3), (18, 33), 5)
        pygame.draw.circle(shuriken_image, WHITE, (18, 18), 5, 2)

    p1_controls = {
        "left": pygame.K_LEFT,
        "right": pygame.K_RIGHT,
        "jump": pygame.K_UP,
    }
    p2_controls = {
        "left": pygame.K_a,
        "right": pygame.K_d,
        "jump": pygame.K_w,
    }

    p1 = Fighter(player_one, 100, p1_controls, 1, asset_folder)
    p2 = Fighter(player_two, 695, p2_controls, -1, asset_folder)

    projectiles = []
    game_over = False
    winner = ""
    ai_state = {"delay": 60}

    running = True
    while running:
        clock.tick(FPS)

        # ---------- events (one-shot key presses only) ----------
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

                if not game_over:
                    if event.key == pygame.K_g:
                        p1.attack(p2)
                    if event.key == pygame.K_f:
                        p1.throw_shuriken(shuriken_image, projectiles)

                    if mode == "Human vs Human":
                        if event.key == pygame.K_q:
                            p2.attack(p1)
                        if event.key == pygame.K_e:
                            p2.throw_shuriken(shuriken_image, projectiles)

        # ---------- game logic (runs every frame) ----------
        if not game_over:
            keys = pygame.key.get_pressed()
            p1.update(keys, p2)

            if mode == "Human vs Human":
                p2.update(keys, p1)
            else:
                run_ai(p2, p1, projectiles, shuriken_image, ai_state)

            for projectile in projectiles[:]:
                projectile.update()
                target = p2 if projectile.owner is p1 else p1

                if projectile.rect.colliderect(target.rect):
                    target.health = max(0, target.health - 12)
                    target.hurt_timer = 10
                    projectiles.remove(projectile)
                elif projectile.x < -50 or projectile.x > WIDTH + 50:
                    projectiles.remove(projectile)

            if p1.health <= 0:
                game_over = True
                winner = player_two
            elif p2.health <= 0:
                game_over = True
                winner = player_one

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

        draw_health_bar(screen, 35, 48, p1.health, RED, player_one, font)
        draw_health_bar(
            screen, WIDTH - 355, 48, p2.health, BLUE, player_two, font
        )

        p1.draw(screen)
        p2.draw(screen)

        for projectile in projectiles:
            projectile.draw(screen)

        if mode == "Human vs Computer":
            controls_text = "Move: LEFT/RIGHT | Jump: UP | Punch: G | Shuriken: F"
        else:
            controls_text = (
                "P1: Arrows, G punch, F shuriken | "
                "P2: A/D, W, Q punch, E shuriken"
            )
        screen.blit(
            small_font.render(controls_text, True, WHITE), (20, HEIGHT - 35)
        )

        if game_over:
            shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 175))
            screen.blit(shade, (0, 0))

            winner_text = big_font.render(
                f"{winner} WINS!", True, (255, 220, 90)
            )
            screen.blit(
                winner_text,
                winner_text.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 25)),
            )
            hint = font.render("Press ESC to return to the menu", True, WHITE)
            screen.blit(
                hint, hint.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 40))
            )

        pygame.display.flip()

    return