from __future__ import annotations

import pygame

from battle.autoresolve import resolve as auto_resolve
from battle.battle_scene import BattleScene
from game.ai import run_ai_turn, start_research_if_idle
from game.save_load import load_campaign, save_campaign
from game.state import GameState, Army, UnitCard, new_campaign
from settings import SCREEN_HEIGHT, SCREEN_WIDTH, FPS, SAVE_FILE


class Button:
    def __init__(self, rect, text):
        self.rect = pygame.Rect(rect)
        self.text = text

    def draw(self, screen, font):
        pygame.draw.rect(screen, (70, 75, 90), self.rect)
        pygame.draw.rect(screen, (180, 180, 200), self.rect, 1)
        screen.blit(font.render(self.text, True, (240, 240, 240)), (self.rect.x + 8, self.rect.y + 8))

    def hit(self, pos):
        return self.rect.collidepoint(pos)


class App:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Star Sector: Total Command")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 16)
        self.big = pygame.font.SysFont("arial", 28, bold=True)
        self.mode = "menu"
        self.gs: GameState | None = None
        self.pending_battle = None

    def run(self):
        while True:
            dt = self.clock.tick(FPS)
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    return
                self.handle_event(e)
            self.draw()
            pygame.display.flip()

    def handle_event(self, e):
        if self.mode == "menu":
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                x, y = e.pos
                if 560 < x < 820 and 210 < y < 255:
                    self.mode = "faction_select"
                if 560 < x < 820 and 270 < y < 315:
                    loaded = load_campaign(SAVE_FILE)
                    if loaded:
                        self.gs = loaded
                        self.mode = "campaign"
                if 560 < x < 820 and 330 < y < 375:
                    self.mode = "help"
                if 560 < x < 820 and 390 < y < 435:
                    pygame.event.post(pygame.event.Event(pygame.QUIT))
        elif self.mode == "help":
            if e.type == pygame.KEYDOWN:
                self.mode = "menu"
        elif self.mode == "faction_select":
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                factions = ["empire", "rebels", "republic", "separatists"]
                for i, fid in enumerate(factions):
                    if pygame.Rect(460, 180 + i * 90, 420, 70).collidepoint(e.pos):
                        self.gs = new_campaign(fid)
                        self.mode = "campaign"
        elif self.mode == "campaign" and self.gs:
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
            self.handle_campaign_event(e)

    def handle_campaign_event(self, e):
        gs = self.gs
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if pygame.Rect(1170, 20, 170, 40).collidepoint(e.pos):
                save_campaign(gs, SAVE_FILE); gs.message = "Saved."
            elif pygame.Rect(1170, 70, 170, 40).collidepoint(e.pos):
                self.end_turn()
            elif pygame.Rect(1170, 120, 170, 40).collidepoint(e.pos):
                self.auto_or_manual_battle(auto=True)
            elif pygame.Rect(1170, 170, 170, 40).collidepoint(e.pos):
                self.auto_or_manual_battle(auto=False)
            elif pygame.Rect(1170, 220, 170, 34).collidepoint(e.pos):
                self.recruit_selected()
            elif pygame.Rect(1170, 265, 170, 34).collidepoint(e.pos):
                self.build_selected()
            elif pygame.Rect(1170, 310, 170, 34).collidepoint(e.pos):
                self.start_research_player()
            elif pygame.Rect(1170, 355, 170, 34).collidepoint(e.pos):
                self.tax_adjust(0.1)
            elif pygame.Rect(1170, 400, 170, 34).collidepoint(e.pos):
                self.tax_adjust(-0.1)
            else:
                for p in gs.planets.values():
                    if (p.x - e.pos[0]) ** 2 + (p.y - e.pos[1]) ** 2 < 20 ** 2:
                        gs.selected_planet = p.name
                        gs.selected_army = next((a.id for a in gs.armies.values() if a.planet == p.name and a.faction_id == gs.player_faction), None)
                        break
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 3 and gs.selected_army:
            army = gs.armies.get(gs.selected_army)
            if not army or army.movement <= 0:
                return
            for p in gs.planets.values():
                if (p.x - e.pos[0]) ** 2 + (p.y - e.pos[1]) ** 2 < 20 ** 2 and p.name in gs.planets[army.planet].connections:
                    army.planet = p.name
                    army.movement -= 1
                    if p.owner == "neutral":
                        p.owner = army.faction_id
                        gs.message = f"{gs.factions[army.faction_id].name} peacefully claims {p.name}."
                    gs.selected_planet = p.name
                    break

    def recruit_selected(self):
        gs = self.gs
        if not gs.selected_planet:
            return
        p = gs.planets[gs.selected_planet]
        faction = gs.factions[gs.player_faction]
        if p.owner != gs.player_faction:
            gs.message = "Must own planet to recruit."
            return
        if not gs.selected_army:
            gs.message = "Select own army at planet."
            return
        army = gs.armies[gs.selected_army]
        if len(army.units) >= 12:
            return
        options = [u for u in gs.unit_db[gs.player_faction] if u["req"] <= max(1, p.military + (1 if "Vehicle Depot" in p.buildings else 0))]
        if not options:
            return
        unit = options[-1] if faction.treasury > 250 else options[0]
        if faction.treasury >= unit["cost"]:
            faction.treasury -= unit["cost"]
            army.units.append(UnitCard.from_template(unit))
            gs.message = f"Recruited {unit['name']}"

    def build_selected(self):
        gs = self.gs
        if not gs.selected_planet:
            return
        p = gs.planets[gs.selected_planet]
        faction = gs.factions[gs.player_faction]
        if p.owner != gs.player_faction or len(p.buildings) >= p.slots:
            return
        choices = [b for b in gs.buildings_db if b not in p.buildings]
        for b in choices:
            c = gs.buildings_db[b]["cost"]
            if faction.treasury >= c:
                faction.treasury -= c
                p.buildings.append(b)
                p.military += gs.buildings_db[b].get("military", 0)
                gs.message = f"Built {b}"
                return

    def start_research_player(self):
        gs = self.gs
        fac = gs.factions[gs.player_faction]
        if fac.research_target:
            return
        for t in gs.tech_db:
            if t["id"] not in fac.unlocked_techs and fac.treasury >= t["cost"]:
                fac.treasury -= t["cost"]
                fac.research_target = t["id"]
                fac.research_left = t["turns"]
                gs.message = f"Research started: {t['name']}"
                return

    def tax_adjust(self, delta):
        gs = self.gs
        fac = gs.factions[gs.player_faction]
        fac.tax_rate = max(0.6, min(1.4, fac.tax_rate + delta))

    def resolve_research(self, fid):
        gs = self.gs
        fac = gs.factions[fid]
        if fac.research_target:
            fac.research_left -= 1
            if fac.research_left <= 0:
                fac.unlocked_techs.append(fac.research_target)
                gs.message = f"{fac.name} finished {fac.research_target}"
                fac.research_target = None

    def compute_income(self, fid):
        gs = self.gs
        fac = gs.factions[fid]
        econ_bonus = 0.1 if "econ_1" in fac.unlocked_techs else 0.0
        income = 0
        upkeep = 0
        for p in gs.planets.values():
            if p.owner == fid:
                income += int(p.income(fac.tax_rate, econ_bonus) * fac.economy_mod)
                if fac.tax_rate > 1.1:
                    p.unrest += 4
                else:
                    p.unrest = max(0, p.unrest - 2)
                if p.unrest > 25 and p.stability < 55:
                    p.owner = "neutral"
                    p.unrest = 0
        for a in gs.armies.values():
            if a.faction_id == fid:
                upkeep += sum(u.stats["upkeep"] for u in a.units)
        fac.treasury += income - upkeep

    def end_turn(self):
        gs = self.gs
        order = list(gs.factions.keys())
        start = order.index(gs.current_faction)
        for i in range(1, len(order) + 1):
            fid = order[(start + i) % len(order)]
            gs.current_faction = fid
            for a in gs.armies.values():
                if a.faction_id == fid:
                    a.movement = 2 if "logistics_1" in gs.factions[fid].unlocked_techs else 1
            self.resolve_research(fid)
            self.compute_income(fid)
            if fid != gs.player_faction:
                start_research_if_idle(gs, fid)
                run_ai_turn(gs, fid)
            self.check_for_battles(fid)
        gs.turn += 1
        self.check_victory()

    def check_for_battles(self, active_faction):
        gs = self.gs
        for p in gs.planets.values():
            armies = [a for a in gs.armies.values() if a.planet == p.name and len(a.units) > 0]
            sides = sorted(set(a.faction_id for a in armies))
            if len(sides) >= 2:
                atk = next((a for a in armies if a.faction_id == active_faction), armies[0])
                dfd = next(a for a in armies if a.faction_id != atk.faction_id)
                self.pending_battle = (p.name, atk.id, dfd.id)
                gs.selected_planet = p.name
                return

    def auto_or_manual_battle(self, auto=True):
        gs = self.gs
        if not self.pending_battle:
            gs.message = "No pending battle."
            return
        planet_name, atk_id, dfd_id = self.pending_battle
        atk = gs.armies.get(atk_id)
        dfd = gs.armies.get(dfd_id)
        if not atk or not dfd:
            self.pending_battle = None
            return
        if auto:
            winner = auto_resolve(atk, dfd)
            result = "victory" if winner == "attacker" and atk.faction_id == gs.player_faction else "defeat"
        else:
            result = BattleScene(self.screen, atk, dfd, gs.factions[atk.faction_id].color, gs.factions[dfd.faction_id].color).run()
        if result == "victory":
            gs.planets[planet_name].owner = atk.faction_id
            dfd.units = [u for u in dfd.units if u.hp > 35]
        elif result == "defeat":
            atk.units = [u for u in atk.units if u.hp > 35]
        if not atk.units:
            gs.armies.pop(atk.id, None)
        if not dfd.units:
            gs.armies.pop(dfd.id, None)
        self.pending_battle = None
        self.check_victory()

    def check_victory(self):
        gs = self.gs
        player = gs.player_faction
        owned = [p for p in gs.planets.values() if p.owner == player]
        enemies = [f for f in gs.factions if f != player and any(p.owner == f for p in gs.planets.values())]
        if len(owned) >= 10 or not enemies:
            gs.message = "Victory achieved! Press ESC to quit."
        if not any(a.faction_id == player for a in gs.armies.values()) and not any(p.owner == player for p in gs.planets.values()):
            gs.message = "Defeat. Press ESC to quit."

    def draw(self):
        if self.mode == "menu":
            self.screen.fill((10, 12, 20))
            self.screen.blit(self.big.render("STAR SECTOR: TOTAL COMMAND", True, (220, 220, 240)), (440, 120))
            for i, label in enumerate(["New Campaign", "Load Campaign", "Help / Controls", "Quit"]):
                Button((560, 210 + i * 60, 260, 45), label).draw(self.screen, self.font)
        elif self.mode == "help":
            self.screen.fill((15, 15, 20))
            tips = ["Campaign: LMB select planet, RMB move selected army.", "Buttons: recruit, build, research, tax, end turn.", "If hostile armies share a planet, launch battle or auto-resolve.", "Battle: LMB select squads, RMB order, 1/2/3 formations, R/O abilities.", "Save from campaign panel. Press any key to return."]
            for i, t in enumerate(tips):
                self.screen.blit(self.font.render(t, True, (230, 230, 230)), (150, 180 + i * 34))
        elif self.mode == "faction_select":
            self.screen.fill((18, 15, 24))
            self.screen.blit(self.big.render("Choose Faction", True, (240, 240, 240)), (560, 110))
            for i, fid in enumerate(["empire", "rebels", "republic", "separatists"]):
                row = pygame.Rect(460, 180 + i * 90, 420, 70)
                pygame.draw.rect(self.screen, (50, 50, 65), row)
                pygame.draw.rect(self.screen, (190, 190, 220), row, 1)
                self.screen.blit(self.font.render(fid.upper(), True, (240, 240, 240)), (480, 208 + i * 90))
        elif self.mode == "campaign" and self.gs:
            self.draw_campaign()

    def draw_campaign(self):
        gs = self.gs
        self.screen.fill((22, 26, 35))
        pygame.draw.rect(self.screen, (25, 32, 44), (0, 0, 1150, SCREEN_HEIGHT))
        for p in gs.planets.values():
            color = (130, 130, 130) if p.owner == "neutral" else tuple(gs.factions[p.owner].color)
            for n in p.connections:
                p2 = gs.planets[n]
                pygame.draw.line(self.screen, (60, 70, 80), (p.x, p.y), (p2.x, p2.y), 1)
            pygame.draw.circle(self.screen, color, (p.x, p.y), 14)
            pygame.draw.circle(self.screen, (230, 230, 230), (p.x, p.y), 14, 1)
            self.screen.blit(self.font.render(p.name, True, (230, 230, 230)), (p.x + 16, p.y - 8))
        for a in gs.armies.values():
            p = gs.planets[a.planet]
            pygame.draw.rect(self.screen, (250, 250, 250), (p.x - 5, p.y - 26, 10, 10))
            self.screen.blit(self.font.render(str(len(a.units)), True, (250, 250, 250)), (p.x - 6, p.y - 40))
        panel = pygame.Rect(1150, 0, 216, SCREEN_HEIGHT)
        pygame.draw.rect(self.screen, (35, 36, 48), panel)
        top = gs.factions[gs.player_faction]
        lines = [f"Turn {gs.turn}", f"Treasury: {top.treasury}", f"Tax: {top.tax_rate:.1f}", f"Research: {top.research_target or 'None'}", f"Pending battle: {'Yes' if self.pending_battle else 'No'}"]
        for i, ln in enumerate(lines):
            self.screen.blit(self.font.render(ln, True, (235, 235, 235)), (1160, 460 + i * 24))
        for i, label in enumerate(["Save", "End Turn", "Auto Resolve", "Manual Battle", "Recruit Unit", "Build", "Research", "Tax +", "Tax -"]):
            y = 20 + i * 50 if i < 4 else 220 + (i - 4) * 45
            Button((1170, y, 170, 40 if i < 4 else 34), label).draw(self.screen, self.font)
        if gs.selected_planet:
            p = gs.planets[gs.selected_planet]
            details = [f"Planet: {p.name}", f"Owner: {p.owner}", f"Stability: {p.stability - p.unrest}", f"Income est: {p.income(top.tax_rate)}", f"Military: {p.military}", f"Buildings: {', '.join(p.buildings) or 'None'}"]
            for i, d in enumerate(details):
                self.screen.blit(self.font.render(d, True, (240, 240, 210)), (20, 620 + i * 22))
        self.screen.blit(self.font.render(gs.message, True, (255, 210, 90)), (20, 22))


def run_game():
    App().run()
