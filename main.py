import pygame
import random
import sys
import networkx as nx
from itertools import product

# ————— CONFIG —————
SCREEN_W, SCREEN_H = 800, 600
TILE   = 20
MAP_W  = SCREEN_W // TILE
MAP_H  = SCREEN_H // TILE
FPS     = 60

ROOM_MIN, ROOM_MAX = 4, 10
MAX_ROOMS         = 12
NUM_ENEMIES       = 8

# COLORS
COL_BG    = (10, 10, 10)
COL_FLOOR = (90, 90, 90)
COL_WALL  = (40, 40, 40)
COL_PLYR  = (50, 200, 50)
COL_ENMY  = (200, 50, 50)
COL_BULLET= (250,250,50)

# ————— INITIALIZE —————
pygame.init()
screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
clock  = pygame.time.Clock()
font   = pygame.font.SysFont(None, 24)

# Map: 0=wall,1=floor
game_map = [[0]*MAP_H for _ in range(MAP_W)]

# Graph for A* pathfinding
graph = nx.grid_2d_graph(MAP_W, MAP_H)

# ————— UTILITIES —————
def rect_to_tiles(r):  # convert rect in tile coords to list of cells
    return [(x,y) for x in range(r.left, r.right)
                 for y in range(r.top,  r.bottom)]

def carve_room(r):
    for (x,y) in rect_to_tiles(r):
        game_map[x][y] = 1
        if graph.has_node((x,y)):
            pass  # keep in graph
    return

def carve_h_corridor(x1,x2,y):
    for x in range(min(x1,x2), max(x1,x2)+1):
        game_map[x][y] = 1

def carve_v_corridor(y1,y2,x):
    for y in range(min(y1,y2), max(y1,y2)+1):
        game_map[x][y] = 1

def build_graph():
    """Rebuild graph removing wall nodes."""
    g = nx.grid_2d_graph(MAP_W, MAP_H)
    for x,y in product(range(MAP_W), range(MAP_H)):
        if game_map[x][y] == 0 and g.has_node((x,y)):
            g.remove_node((x,y))
    return g

# ————— DUNGEON GENERATION (BSP-ish) —————
rooms = []
for _ in range(MAX_ROOMS):
    w = random.randint(ROOM_MIN, ROOM_MAX)
    h = random.randint(ROOM_MIN, ROOM_MAX)
    x = random.randint(1, MAP_W - w - 1)
    y = random.randint(1, MAP_H - h - 1)
    new_room = pygame.Rect(x, y, w, h)

    # Check overlap
    if any(new_room.colliderect(r) for r in rooms):
        continue
    carve_room(new_room)
    if rooms:
        # connect to previous via corridors
        prev = rooms[-1].center
        curr = new_room.center
        if random.choice([True, False]):
            carve_h_corridor(prev[0], curr[0], prev[1])
            carve_v_corridor(prev[1], curr[1], curr[0])
        else:
            carve_v_corridor(prev[1], curr[1], prev[0])
            carve_h_corridor(prev[0], curr[0], curr[1])
    rooms.append(new_room)

graph = build_graph()

# ————— ENTITIES —————
class Entity(pygame.sprite.Sprite):
    def __init__(self, x,y,color,size=TILE, speed=2, hp=10):
        super().__init__()
        self.image = pygame.Surface((size,size))
        self.image.fill(color)
        self.rect  = self.image.get_rect()
        self.rect.topleft = (x*TILE, y*TILE)
        self.speed = speed
        self.hp    = hp

    @property
    def cell(self):
        return (self.rect.x//TILE, self.rect.y//TILE)

class Player(Entity):
    def __init__(self,*a,**k):
        super().__init__(*a,**k)
        self.fire_delay = 250  # ms
        self.last_fire  = 0

    def update(self, walls):
        keys = pygame.key.get_pressed()
        dx = (keys[pygame.K_d] - keys[pygame.K_a]) * self.speed
        dy = (keys[pygame.K_s] - keys[pygame.K_w]) * self.speed
        old = self.rect.copy()
        self.rect.move_ip(dx,dy)
        for w in walls:
            if self.rect.colliderect(w):
                self.rect = old
                break

    def shoot(self, target):
        now = pygame.time.get_ticks()
        if now - self.last_fire < self.fire_delay:
            return None
        self.last_fire = now
        bullet = Bullet(self.rect.centerx, self.rect.centery,
                        target[0], target[1])
        return bullet

class Enemy(Entity):
    def __init__(self,*a,**k):
        super().__init__(*a,**k)
        self.path = []
        self.recalc = 0

    def update(self, player, walls):
        now = pygame.time.get_ticks()
        start = self.cell                # ← always define these
        goal  = player.cell

        # Recalculate path every 500ms or if we have no path
        if now - self.recalc > 500 or not self.path:
            try:
                self.path = nx.astar_path(graph, start, goal)
            except nx.NetworkXNoPath:
                self.path = []
            self.recalc = now

        # If there's at least one step beyond 'start', move toward it
        if len(self.path) > 1:
            next_cell = self.path[1]
            dx = (next_cell[0] - start[0]) * self.speed
            dy = (next_cell[1] - start[1]) * self.speed

            old_rect = self.rect.copy()
            self.rect.move_ip(dx, dy)

            # simple wall collision rollback
            for w in walls:
                if self.rect.colliderect(w):
                    self.rect = old_rect
                    break


class Bullet(pygame.sprite.Sprite):
    def __init__(self, x,y,tx,ty, speed=8):
        super().__init__()
        self.image = pygame.Surface((6,6))
        self.image.fill(COL_BULLET)
        self.rect  = self.image.get_rect(center=(x,y))
        vx, vy = tx-x, ty-y
        dist = (vx*vx + vy*vy)**0.5 or 1
        self.vel  = (vx/dist*speed, vy/dist*speed)

    def update(self):
        self.rect.x += self.vel[0]
        self.rect.y += self.vel[1]
        # kill when off-screen
        if not screen.get_rect().colliderect(self.rect):
            self.kill()

# ————— BUILD WALL RECTS FOR COLLISION/DRAW —————
def build_walls():
    walls = []
    for x,y in product(range(MAP_W), range(MAP_H)):
        if game_map[x][y] == 0:
            walls.append(pygame.Rect(x*TILE,y*TILE,TILE,TILE))
    return walls

walls = build_walls()

# ————— SPAWN —————
# pick player start in first room center
start_room = rooms[0]
px,py = start_room.center
player = Player(px//1, py//1, COL_PLYR, speed=4, hp=30)

enemies = pygame.sprite.Group()
for _ in range(NUM_ENEMIES):
    room = random.choice(rooms[1:])
    ex = random.randint(room.left, room.right-1)
    ey = random.randint(room.top,  room.bottom-1)
    enemies.add(Enemy(ex, ey, COL_ENMY, speed=2, hp=5))

bullets = pygame.sprite.Group()
all_sprites = pygame.sprite.Group(player, *enemies)

# ————— MAIN LOOP —————
running = True
while running:
    dt = clock.tick(FPS)
    for evt in pygame.event.get():
        if evt.type == pygame.QUIT:
            running = False

        elif evt.type == pygame.MOUSEBUTTONDOWN and evt.button==1:
            b = player.shoot(pygame.mouse.get_pos())
            if b:
                bullets.add(b)
                all_sprites.add(b)

    # Updates
    player.update(walls)
    for e in enemies:
        e.update(player, walls)
    bullets.update()

    # Bullet hit detection
    for b in bullets:
        hit = pygame.sprite.spritecollideany(b, enemies)
        if hit:
            hit.hp -= 1
            b.kill()
            if hit.hp <= 0:
                hit.kill()

    # Enemy touches player
    if pygame.sprite.spritecollideany(player, enemies):
        player.hp -= 1
        pygame.time.wait(200)  # brief invulnerability
        if player.hp <= 0:
            running = False

    # Draw
    screen.fill(COL_BG)
    # map
    for x,y in product(range(MAP_W), range(MAP_H)):
        col = COL_FLOOR if game_map[x][y]==1 else COL_WALL
        pygame.draw.rect(screen, col, (x*TILE,y*TILE,TILE,TILE))
    # sprites
    all_sprites.draw(screen)

    # HUD
    hp_text = font.render(f"HP: {player.hp}", True, (255,255,255))
    screen.blit(hp_text, (10,10))

    pygame.display.flip()

# Game Over
screen.fill((0,0,0))
go = font.render("GAME OVER", True, (200,50,50))
screen.blit(go, go.get_rect(center=screen.get_rect().center))
pygame.display.flip()
pygame.time.wait(2000)
pygame.quit()
sys.exit()
