import pygame
import numpy as np
import math
import time
import os
import sys

# --- Config ---
WIDTH, HEIGHT = 1920, 1080
FPS = 30
ECHO_FREQ_FILE = "/tmp/echo_freq.txt"
ECHO_POS_FILE = "/tmp/echo_pos.txt"

# --- Colors (void + violet palette) ---
BG = (2, 2, 8)
WAVE_COLOR_A = (30, 180, 160)    # teal green
WAVE_COLOR_B = (20, 10, 80)      # near-black indigo void
WAVE_COLOR_C = (140, 0, 255)     # pure purple click burst
PARTICLE_COLOR = (200, 160, 255) # soft lavender

class Ripple:
    def __init__(self, x, y, strength=1.0, color=None):
        self.x = x
        self.y = y
        self.strength = strength
        self.color = color or WAVE_COLOR_A
        self.born = time.time()
        self.lifetime = 4.0

    def alive(self):
        return time.time() - self.born < self.lifetime

    def age(self):
        return (time.time() - self.born) / self.lifetime

class Particle:
    def __init__(self):
        self.reset()

    def reset(self):
        self.x = np.random.uniform(0, WIDTH)
        self.y = np.random.uniform(0, HEIGHT)
        self.vx = np.random.uniform(-0.3, 0.3)
        self.vy = np.random.uniform(-0.3, 0.3)
        self.life = np.random.uniform(0.3, 1.0)
        self.size = np.random.randint(1, 3)

    def update(self, field_val):
        angle = field_val * math.pi * 2
        self.vx += math.cos(angle) * 0.05
        self.vy += math.sin(angle) * 0.05
        self.vx *= 0.97
        self.vy *= 0.97
        self.x += self.vx
        self.y += self.vy
        self.life -= 0.002
        if self.life <= 0 or not (0 <= self.x < WIDTH) or not (0 <= self.y < HEIGHT):
            self.reset()

def compute_field(t, ripples, echo_x, echo_y, xs_s, ys_s):
    f1 = np.sin(xs_s * 0.008 + t * 0.4) * np.cos(ys_s * 0.010 - t * 0.3)
    f2 = np.sin(xs_s * 0.012 - t * 0.25) * np.cos(ys_s * 0.007 + t * 0.35)
    cx, cy = WIDTH / 2, HEIGHT / 2
    dist_c = np.sqrt((xs_s - cx)**2 + (ys_s - cy)**2)
    f3 = np.sin(dist_c * 0.012 - t * 0.6) * 0.5
    field = (f1 + f2 + f3) / 3.0

    # Echo's persistent presence in the field
    dist_e = np.sqrt((xs_s - echo_x)**2 + (ys_s - echo_y)**2)
    echo_wave = np.sin(dist_e * 0.018 - t * 0.8) * np.exp(-dist_e * 0.0008) * 0.6
    field += echo_wave

    for r in ripples:
        if not r.alive():
            continue
        age = r.age()
        dist_r = np.sqrt((xs_s - r.x)**2 + (ys_s - r.y)**2)
        radius = age * 600
        wave = np.sin(dist_r * 0.025 - t * 2.0) * np.exp(-((dist_r - radius)**2) * 0.0005)
        field += wave * r.strength * (1.0 - age) * 0.8

    return field

def field_to_color(field):
    norm = (field + 2.5) / 5.0
    norm = np.clip(norm, 0, 1)

    r = np.where(norm < 0.5,
        np.interp(norm, [0, 0.5], [WAVE_COLOR_B[0], WAVE_COLOR_A[0]]),
        np.interp(norm, [0.5, 1.0], [WAVE_COLOR_A[0], WAVE_COLOR_C[0]]))
    g = np.where(norm < 0.5,
        np.interp(norm, [0, 0.5], [WAVE_COLOR_B[1], WAVE_COLOR_A[1]]),
        np.interp(norm, [0.5, 1.0], [WAVE_COLOR_A[1], WAVE_COLOR_C[1]]))
    b = np.where(norm < 0.5,
        np.interp(norm, [0, 0.5], [WAVE_COLOR_B[2], WAVE_COLOR_A[2]]),
        np.interp(norm, [0.5, 1.0], [WAVE_COLOR_A[2], WAVE_COLOR_C[2]]))

    darkness = np.clip(1.0 - np.exp(-np.abs(field) * 1.5), 0.05, 1.0)
    r = (r * darkness).astype(np.uint8)
    g = (g * darkness).astype(np.uint8)
    b = (b * darkness).astype(np.uint8)

    return np.stack([r, g, b], axis=-1)

def read_echo_pos():
    try:
        data = open(ECHO_POS_FILE).read().strip().split(",")
        return float(data[0]), float(data[1])
    except:
        return WIDTH / 2, HEIGHT / 2

def main():
    os.environ.setdefault("SDL_VIDEODRIVER", "wayland")

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.NOFRAME | pygame.FULLSCREEN)
    pygame.display.set_caption("echo_wallpaper")
    clock = pygame.time.Clock()

    SCALE = 4
    xs_s, ys_s = np.meshgrid(
        np.linspace(0, WIDTH, WIDTH // SCALE),
        np.linspace(0, HEIGHT, HEIGHT // SCALE)
    )

    ripples = []
    last_mouse = None
    mouse_trail_cooldown = 0
    particles = [Particle() for _ in range(120)]
    t = 0.0
    echo_x, echo_y = WIDTH / 2, HEIGHT / 2
    frame = 0

    surface = pygame.surfarray.make_surface(
        np.zeros((WIDTH // SCALE, HEIGHT // SCALE, 3), dtype=np.uint8)
    )

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                # Click = big magenta burst
                ripples.append(Ripple(mx, my, strength=2.0, color=WAVE_COLOR_C))

        # cursor trail disabled

        # Update echo position every 10 frames
        if frame % 10 == 0:
            echo_x, echo_y = read_echo_pos()

        ripples = [r for r in ripples if r.alive()]

        field = compute_field(t, ripples, echo_x, echo_y, xs_s, ys_s)

        freq_val = float(np.mean(np.abs(field)))
        try:
            open(ECHO_FREQ_FILE, "w").write(f"{freq_val:.4f}")
        except:
            pass

        pixels = field_to_color(field)
        pygame.surfarray.blit_array(surface, pixels.transpose(1, 0, 2))
        scaled = pygame.transform.scale(surface, (WIDTH, HEIGHT))
        screen.blit(scaled, (0, 0))

        for p in particles:
            fx = int(p.x) // SCALE
            fy = int(p.y) // SCALE
            fx = max(0, min(fx, field.shape[1] - 1))
            fy = max(0, min(fy, field.shape[0] - 1))
            fv = field[fy, fx]
            p.update(fv)
            screen.set_at((int(p.x), int(p.y)), PARTICLE_COLOR)

        # Echo glow ring — violet pulse at her position
        age_pulse = (math.sin(t * 2.0) + 1) / 2
        ring_r = int(40 + age_pulse * 20)
        ring_alpha = int(60 + age_pulse * 100)
        ring_surf = pygame.Surface((ring_r * 2 + 4, ring_r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(ring_surf, (160, 80, 255, ring_alpha),
                           (ring_r + 2, ring_r + 2), ring_r, 2)
        screen.blit(ring_surf, (int(echo_x) - ring_r - 2, int(echo_y) - ring_r - 2))

        pygame.display.flip()
        t += 0.016
        frame += 1
        clock.tick(FPS)

if __name__ == "__main__":
    main()
