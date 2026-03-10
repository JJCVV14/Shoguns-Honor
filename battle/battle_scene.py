from __future__ import annotations

import random
import pygame


class BattleSquad:
    def __init__(self, card, team, pos, color):
        self.card = card
        self.team = team
        self.pos = pygame.Vector2(pos)
        self.target = pygame.Vector2(pos)
        self.hp = card.hp
        self.card = card
        self.morale = card.stats["morale"]
        self.fatigue = 0.0
        self.routing = False
        self.selected = False
        self.color = color
        self.formation = "line"

    def speed(self):
        form_mod = 0.8 if self.formation == "line" else (1.1 if self.formation == "column" else 0.9)
        return self.card.stats["speed"] * form_mod * max(0.55, 1 - self.fatigue / 100)


class BattleScene:
    def __init__(self, screen, attacker_army, defender_army, atk_color, def_color):
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 16)
        self.small = pygame.font.SysFont("arial", 12)
        self.big = pygame.font.SysFont("arial", 24, bold=True)
        self.highgrounds = self._generate_highgrounds()
        self.atk_general_cd = {"rally": 0, "orbital": 0}
        self.def_general_cd = {"rally": 0, "orbital": 0}
        self.squads = []
        y = 130
        for c in attacker_army.units:
            self.squads.append(BattleSquad(c, "attacker", (120, y), atk_color)); y += 58
        y = 130
        for c in defender_army.units:
            self.squads.append(BattleSquad(c, "defender", (1120, y), def_color)); y += 58
        self.selected = []
        self.time = 0
        self.result = None
        self.projectiles = []

    def _generate_highgrounds(self):
        zones = []
        # Original zone was 220x120; make each new zone ~3x smaller by dimension.
        zone_w, zone_h = 73, 40
        margin_x = 140
        margin_top = 70
        margin_bottom = 130
        max_x = self.screen.get_width() - margin_x - zone_w
        max_y = self.screen.get_height() - margin_bottom - zone_h

        attempts = 0
        while len(zones) < 4 and attempts < 200:
            attempts += 1
            candidate = pygame.Rect(
                random.randint(margin_x, max_x),
                random.randint(margin_top, max_y),
                zone_w,
                zone_h,
            )
            # Keep a little spacing so labels don't overlap each other.
            if any(candidate.inflate(14, 14).colliderect(zone) for zone in zones):
                continue
            zones.append(candidate)

        # Fallback in the unlikely case random placement couldn't fill all slots.
        while len(zones) < 4:
            idx = len(zones)
            x = margin_x + (idx % 2) * (zone_w + 40)
            y = margin_top + (idx // 2) * (zone_h + 40)
            zones.append(pygame.Rect(x, y, zone_w, zone_h))

        return zones

    def run(self):
        while not self.result:
            dt = self.clock.tick(60) / 1000
            self.time += dt
            self.handle_events()
            self.update(dt)
            self.draw()
        return self.result

    def handle_events(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.result = "retreat"
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_1:
                    for s in self.selected: s.formation = "line"
                if e.key == pygame.K_2:
                    for s in self.selected: s.formation = "column"
                if e.key == pygame.K_3:
                    for s in self.selected: s.formation = "brace"
                if e.key == pygame.K_r and self.atk_general_cd["rally"] <= 0:
                    for s in self.squads:
                        if s.team == "attacker" and s.pos.x < 700:
                            s.morale = min(100, s.morale + 18)
                    self.atk_general_cd["rally"] = 25
                if e.key == pygame.K_o and self.atk_general_cd["orbital"] <= 0:
                    mx, my = pygame.mouse.get_pos()
                    for s in self.squads:
                        if s.team == "defender" and s.pos.distance_to((mx, my)) < 80:
                            s.hp -= 45
                            s.morale -= 20
                    self.atk_general_cd["orbital"] = 35
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                self.selected = [s for s in self.squads if s.team == "attacker" and pygame.Rect(s.pos.x - 16, s.pos.y - 16, 32, 32).collidepoint(e.pos)]
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 3:
                for s in self.selected:
                    s.target = pygame.Vector2(e.pos)

    def update(self, dt):
        self.atk_general_cd = {k: max(0, v - dt) for k, v in self.atk_general_cd.items()}
        spawned_projectiles = []
        for s in self.squads:
            if s.hp <= 0:
                continue
            enemies = [e for e in self.squads if e.team != s.team and e.hp > 0]
            if not enemies:
                continue
            nearest = min(enemies, key=lambda e: s.pos.distance_to(e.pos))
            dist = s.pos.distance_to(nearest.pos)
            if s.team == "defender":
                s.target = nearest.pos if dist > s.card.stats["range"] * 0.85 else s.pos
            if s.routing:
                direction = (s.pos - nearest.pos).normalize() if dist > 0 else pygame.Vector2(-1, 0)
                s.pos += direction * s.speed() * dt
                s.morale += 7 * dt
                if s.morale > 38:
                    s.routing = False
                continue
            if dist > 6:
                delta = s.target - s.pos
                if delta.length() > 3:
                    s.pos += delta.normalize() * s.speed() * dt
                    s.fatigue = min(100, s.fatigue + 6 * dt)
                else:
                    s.fatigue = max(0, s.fatigue - 3 * dt)
            if dist <= s.card.stats["range"]:
                accuracy = s.card.stats["accuracy"] + (0.08 if any(hg.collidepoint(s.pos) for hg in self.highgrounds) else 0)
                fire_chance = dt * 4.5
                if random.random() < fire_chance:
                    direction = (nearest.pos - s.pos)
                    if direction.length_squared() > 0:
                        direction = direction.normalize()
                        start = s.pos + direction * 18
                        speed = 620
                        travel_time = min(0.8, max(0.08, dist / speed))
                        spawned_projectiles.append({
                            "pos": pygame.Vector2(start),
                            "vel": direction * speed,
                            "ttl": travel_time,
                            "color": (255, 70, 70) if s.team == "attacker" else (80, 220, 255),
                        })
                    if random.random() < accuracy:
                        flank = 1.2 if abs(nearest.pos.y - s.pos.y) > 80 else 1.0
                        nearest.hp -= s.card.stats["damage"] * flank
                        nearest.morale -= 5 * flank
            if dist < 32:
                nearest.hp -= s.card.stats["melee"] * dt * 3
                nearest.morale -= 6 * dt
            casualty_factor = 100 - (s.hp / max(1, s.card.stats["health"]) * 100)
            s.morale -= (0.03 * casualty_factor + 0.02 * s.fatigue) * dt
            if s.morale < 20:
                s.routing = True
        # Persist squad HP back to campaign units *before* removing dead squads.
        # Otherwise a squad that dies in battle can keep stale HP on its card.
        for sq in self.squads:
            sq.card.hp = max(0, sq.hp)

        self.squads = [s for s in self.squads if s.hp > 0]
        atk = [s for s in self.squads if s.team == "attacker"]
        dfd = [s for s in self.squads if s.team == "defender"]
        if not atk:
            self.result = "defeat"
        elif not dfd:
            self.result = "victory"

        # Battles now end only when one side has no units left.
        # Routing squads remain on the battlefield and do not trigger early victory.
        self.projectiles.extend(spawned_projectiles)
        for pr in self.projectiles:
            pr["pos"] += pr["vel"] * dt
            pr["ttl"] -= dt
        self.projectiles = [pr for pr in self.projectiles if pr["ttl"] > 0]

    def draw(self):
        self.screen.fill((28, 35, 40))
        for hg in self.highgrounds:
            pygame.draw.rect(self.screen, (65, 95, 70), hg)
            label = self.small.render("High Ground", True, (220, 240, 220))
            label_pos = (hg.centerx - label.get_width() // 2, hg.centery - label.get_height() // 2)
            self.screen.blit(label, label_pos)
        for s in self.squads:
            rect = pygame.Rect(s.pos.x - 14, s.pos.y - 14, 28, 28)
            pygame.draw.rect(self.screen, s.color, rect)
            if s in self.selected:
                pygame.draw.rect(self.screen, (255, 255, 255), rect, 2)
            hpw = max(0, int(28 * (s.hp / max(1, s.card.stats["health"]))))
            mw = max(0, int(28 * (s.morale / 100)))
            name_text = self.small.render(s.card.name, True, (235, 235, 235))
            self.screen.blit(name_text, (rect.centerx - name_text.get_width() // 2, rect.y - 22))
            pygame.draw.rect(self.screen, (180, 20, 20), (rect.x, rect.y - 8, hpw, 4))
            pygame.draw.rect(self.screen, (50, 160, 230), (rect.x, rect.y - 3, mw, 3))
        for pr in self.projectiles:
            tail = pr["pos"] - pr["vel"] * 0.03
            pygame.draw.line(self.screen, pr["color"], pr["pos"], tail, 2)
        info = "LMB select | RMB move/attack | 1 line 2 column 3 brace | R rally | O orbital"
        self.screen.blit(self.font.render(info, True, (235, 235, 235)), (18, 730))
        self.screen.blit(self.big.render("BATTLE", True, (245, 245, 210)), (620, 12))
        pygame.display.flip()
