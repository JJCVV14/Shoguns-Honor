from __future__ import annotations

import pygame

from battle.autoresolve import resolve as auto_resolve
from battle.battle_scene import BattleScene
from game.ai import run_ai_turn, start_research_if_idle
from game.save_load import load_campaign, save_campaign
from game.state import Army, GameState, General, UnitCard, new_campaign
from settings import SCREEN_HEIGHT, SCREEN_WIDTH, FPS, SAVE_FILE


MIN_UNIT_HP = 1.0


class Button:
    def __init__(self, rect, text):
        self.rect = pygame.Rect(rect)
        self.text = text

    def draw(self, screen, font):
        pygame.draw.rect(screen, (70, 75, 90), self.rect)
        pygame.draw.rect(screen, (180, 180, 200), self.rect, 1)
        screen.blit(font.render(self.text, True, (240, 240, 240)), (self.rect.x + 8, self.rect.y + 8))


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
        self.last_battle = {"title": "", "detail": ""}
        self.recruit_items = []
        self.build_items = []
        self.research_items = []

    def run(self):
        while True:
            self.clock.tick(FPS)
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
                        self._sanitize_armies()
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
                        self._sanitize_armies()
                        self.mode = "campaign"
        elif self.mode == "recruit" and self.gs:
            self.handle_recruit_event(e)
        elif self.mode == "build" and self.gs:
            self.handle_build_event(e)
        elif self.mode == "army_view" and self.gs:
            self.handle_army_view_event(e)
        elif self.mode == "research" and self.gs:
            self.handle_research_event(e)
        elif self.mode == "recruit_queue" and self.gs:
            self.handle_recruit_queue_event(e)
        elif self.mode == "battle_result":
            if e.type == pygame.KEYDOWN or (e.type == pygame.MOUSEBUTTONDOWN and e.button == 1):
                self.mode = "campaign"
        elif self.mode == "campaign" and self.gs:
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
            self.handle_campaign_event(e)

    def _sanitize_armies(self):
        gs = self.gs
        for army in gs.armies.values():
            if army.faction_id not in gs.unit_db:
                continue
            allowed_names = {u["name"] for u in gs.unit_db[army.faction_id]}
            army.units = [u for u in army.units if u.name in allowed_names]
        self._cleanup_destroyed_armies()

    def _cleanup_destroyed_armies(self):
        gs = self.gs
        for army in gs.armies.values():
            army.units = [u for u in army.units if u.hp > MIN_UNIT_HP]
        for aid in [aid for aid, army in gs.armies.items() if not army.units]:
            gs.armies.pop(aid, None)

    def _capture_planet_if_uncontested(self, planet_name, faction_id):
        gs = self.gs
        planet = gs.planets[planet_name]
        if planet.owner == faction_id:
            return
        hostile_armies = [
            a for a in gs.armies.values()
            if a.planet == planet_name and a.faction_id != faction_id and len(a.units) > 0
        ]
        if hostile_armies:
            return
        previous_owner = planet.owner
        planet.owner = faction_id
        if previous_owner == "neutral":
            gs.message = f"{gs.factions[faction_id].name} peacefully claims {planet_name}."
        else:
            gs.message = f"{gs.factions[faction_id].name} captures undefended {planet_name}."

    def handle_campaign_event(self, e):
        gs = self.gs
        self._cleanup_destroyed_armies()
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if pygame.Rect(1170, 20, 170, 40).collidepoint(e.pos):
                save_campaign(gs, SAVE_FILE)
                gs.message = "Saved."
            elif pygame.Rect(1170, 70, 170, 40).collidepoint(e.pos):
                self.end_turn()
            elif pygame.Rect(1170, 120, 170, 40).collidepoint(e.pos):
                self.auto_or_manual_battle(auto=True)
            elif pygame.Rect(1170, 170, 170, 40).collidepoint(e.pos):
                self.auto_or_manual_battle(auto=False)
            elif pygame.Rect(1170, 220, 170, 34).collidepoint(e.pos):
                self.open_recruit_screen()
            elif pygame.Rect(1170, 265, 170, 34).collidepoint(e.pos):
                self.open_build_screen()
            elif pygame.Rect(1170, 445, 170, 34).collidepoint(e.pos):
                self.open_army_view()
            elif pygame.Rect(1170, 490, 170, 34).collidepoint(e.pos):
                self.open_recruit_queue_screen()
            elif pygame.Rect(1170, 310, 170, 34).collidepoint(e.pos):
                self.open_research_screen()
            elif pygame.Rect(1170, 355, 170, 34).collidepoint(e.pos):
                self.tax_adjust(0.1)
            elif pygame.Rect(1170, 400, 170, 34).collidepoint(e.pos):
                self.tax_adjust(-0.1)
            else:
                for p in gs.planets.values():
                    if (p.x - e.pos[0]) ** 2 + (p.y - e.pos[1]) ** 2 < 20 ** 2:
                        gs.selected_planet = p.name
                        gs.selected_army = next(
                            (a.id for a in gs.armies.values() if a.planet == p.name and a.faction_id == gs.player_faction and not a.is_planet_garrison),
                            next((a.id for a in gs.armies.values() if a.planet == p.name and a.faction_id == gs.player_faction), None),
                        )
                        break

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 3 and gs.selected_army:
            army = gs.armies.get(gs.selected_army)
            if not army or army.movement <= 0 or not army.can_move:
                return
            for p in gs.planets.values():
                if (p.x - e.pos[0]) ** 2 + (p.y - e.pos[1]) ** 2 < 20 ** 2 and p.name in gs.planets[army.planet].connections:
                    army.planet = p.name
                    army.movement -= 1
                    self._capture_planet_if_uncontested(p.name, army.faction_id)
                    merged_into = self.merge_friendly_armies(p.name, army.faction_id, keep_army_id=army.id)
                    if merged_into:
                        gs.selected_army = merged_into
                    gs.selected_planet = p.name
                    self.check_for_battles(army.faction_id)
                    break

    def open_recruit_screen(self):
        gs = self.gs
        if not gs.selected_planet:
            gs.message = "Select a planet first."
            return

        planet = gs.planets[gs.selected_planet]
        if planet.owner != gs.player_faction:
            gs.message = "Must own planet to recruit."
            return

        military_req = max(1, planet.military + (1 if "Vehicle Depot" in planet.buildings else 0))
        self.recruit_items = [u for u in gs.unit_db[gs.player_faction] if u["req"] <= military_req]
        self.mode = "recruit"

    def handle_recruit_event(self, e):
        gs = self.gs
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.mode = "campaign"
            return

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if pygame.Rect(30, 680, 210, 38).collidepoint(e.pos):
                self.mode = "campaign"
                return
            for i, unit in enumerate(self.recruit_items):
                if pygame.Rect(45, 120 + i * 80, 980, 70).collidepoint(e.pos):
                    self.queue_recruitment(unit)
                    self.mode = "campaign"
                    return

    def open_recruit_queue_screen(self):
        self.mode = "recruit_queue"

    def handle_recruit_queue_event(self, e):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.mode = "campaign"
            return
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if pygame.Rect(30, 680, 210, 38).collidepoint(e.pos):
                self.mode = "campaign"

    def queue_recruitment(self, unit):
        gs = self.gs
        planet = gs.planets[gs.selected_planet]
        faction = gs.factions[gs.player_faction]

        turns = max(1, 4 - planet.military)
        if faction.treasury < unit["cost"]:
            gs.message = "Insufficient funds."
            return

        faction.treasury -= unit["cost"]
        gs.recruit_queue.append(
            {
                "faction": gs.player_faction,
                "planet": planet.name,
                "unit": unit["name"],
                "turns": turns,
            }
        )
        gs.message = f"Recruiting {unit['name']} at {planet.name} ({turns} turn(s))."

    def resolve_recruitment(self, fid):
        gs = self.gs
        finished_indexes = []
        for i, item in enumerate(gs.recruit_queue):
            if item["faction"] != fid:
                continue
            item["turns"] -= 1
            if item["turns"] <= 0:
                finished_indexes.append(i)

        for i in reversed(finished_indexes):
            item = gs.recruit_queue.pop(i)
            template = next((u for u in gs.unit_db[item["faction"]] if u["name"] == item["unit"]), None)
            if template:
                new_army = Army(
                    id=gs.next_army_id,
                    faction_id=item["faction"],
                    planet=item["planet"],
                    general=General(name="New Detachment"),
                    units=[UnitCard.from_template(template)],
                    movement=0,
                    is_planet_garrison=False,
                    can_move=True,
                )
                gs.armies[gs.next_army_id] = new_army
                gs.next_army_id += 1
                if item["faction"] == gs.player_faction:
                    gs.message = f"{item['unit']} is ready at {item['planet']} as a new army."

    def merge_friendly_armies(self, planet_name, faction_id, keep_army_id=None):
        gs = self.gs
        friendly = [
            a for a in gs.armies.values()
            if a.planet == planet_name and a.faction_id == faction_id and len(a.units) > 0
        ]
        if len(friendly) < 2:
            return keep_army_id

        if keep_army_id and keep_army_id in gs.armies:
            base = gs.armies[keep_army_id]
        else:
            base = max(friendly, key=lambda a: len(a.units))

        for army in list(friendly):
            if army.id == base.id:
                continue
            base.units.extend(army.units)
            base.movement = min(base.movement, army.movement)
            gs.armies.pop(army.id, None)

        return base.id

    def open_research_screen(self):
        gs = self.gs
        fac = gs.factions[gs.player_faction]
        self.research_items = [t for t in gs.tech_db if t["id"] not in fac.unlocked_techs]
        self.mode = "research"

    def handle_research_event(self, e):
        gs = self.gs
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.mode = "campaign"
            return

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if pygame.Rect(30, 680, 210, 38).collidepoint(e.pos):
                self.mode = "campaign"
                return
            if pygame.Rect(260, 680, 210, 38).collidepoint(e.pos):
                self.start_research_player()
                self.mode = "campaign"
                return
            for i, tech in enumerate(self.research_items):
                if pygame.Rect(45, 120 + i * 90, 1100, 80).collidepoint(e.pos):
                    self.start_research_player(tech["id"])
                    self.mode = "campaign"
                    return

    def open_build_screen(self):
        gs = self.gs
        if not gs.selected_planet:
            gs.message = "Select a planet first."
            return

        planet = gs.planets[gs.selected_planet]
        if planet.owner != gs.player_faction:
            gs.message = "Must own planet to build."
            return

        self.build_items = [b for b in gs.buildings_db if b not in planet.buildings]
        self.mode = "build"

    def handle_build_event(self, e):
        gs = self.gs
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.mode = "campaign"
            return

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if pygame.Rect(30, 680, 210, 38).collidepoint(e.pos):
                self.mode = "campaign"
                return
            for i, building in enumerate(self.build_items):
                if pygame.Rect(45, 170 + i * 72, 980, 62).collidepoint(e.pos):
                    self.build_selected(building)
                    self.mode = "campaign"
                    return

    def build_selected(self, building):
        gs = self.gs
        planet = gs.planets[gs.selected_planet]
        faction = gs.factions[gs.player_faction]

        if building in planet.buildings:
            gs.message = f"{building} is already built on {planet.name}."
            return
        if len(planet.buildings) >= planet.slots:
            gs.message = f"{planet.name} has no free building slots."
            return

        cost = gs.buildings_db[building]["cost"]
        if faction.treasury < cost:
            gs.message = "Insufficient funds."
            return

        faction.treasury -= cost
        planet.buildings.append(building)
        planet.military += gs.buildings_db[building].get("military", 0)
        gs.message = f"Built {building} on {planet.name}."

    def open_army_view(self):
        gs = self.gs
        if not gs.selected_army or gs.selected_army not in gs.armies:
            gs.message = "Select an army to inspect."
            return
        self.mode = "army_view"

    def handle_army_view_event(self, e):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.mode = "campaign"
            return
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if pygame.Rect(30, 680, 210, 38).collidepoint(e.pos):
                self.mode = "campaign"
                return
            if pygame.Rect(260, 680, 210, 38).collidepoint(e.pos) and self.gs and self.gs.selected_army:
                army = self.gs.armies.get(self.gs.selected_army)
                if army:
                    merged_id = self.merge_friendly_armies(army.planet, army.faction_id, keep_army_id=army.id)
                    self.gs.selected_army = merged_id
                    self.gs.message = "Friendly armies merged on planet."

    def ensure_planet_garrisons(self):
        gs = self.gs
        for planet in gs.planets.values():
            if planet.owner in ("neutral", "revolutionaries"):
                continue
            exists = any(a.planet == planet.name and a.faction_id == planet.owner and a.is_planet_garrison for a in gs.armies.values())
            if exists:
                continue
            unit_template = gs.unit_db[planet.owner][0]
            garrison = Army(
                id=gs.next_army_id,
                faction_id=planet.owner,
                planet=planet.name,
                general=General(name="Planetary Commander"),
                units=[UnitCard.from_template(unit_template)],
                movement=0,
                is_planet_garrison=True,
                can_move=False,
            )
            gs.armies[gs.next_army_id] = garrison
            gs.next_army_id += 1

    def trigger_revolutionaries(self):
        gs = self.gs
        for planet in gs.planets.values():
            if planet.owner in ("neutral", "revolutionaries"):
                continue
            if planet.stability - planet.unrest > 0:
                continue
            planet.owner = "revolutionaries"
            planet.unrest = 0
            for aid in [aid for aid,a in gs.armies.items() if a.planet == planet.name and a.faction_id != "revolutionaries"]:
                gs.armies.pop(aid, None)
            template = gs.unit_db["revolutionaries"][0]
            rev_units = [UnitCard.from_template(template) for _ in range(4)]
            gs.armies[gs.next_army_id] = Army(
                id=gs.next_army_id,
                faction_id="revolutionaries",
                planet=planet.name,
                general=General(name="Revolutionary Cell"),
                units=rev_units,
                movement=0,
                is_planet_garrison=True,
                can_move=False,
            )
            gs.next_army_id += 1
            gs.message = f"Revolutionaries have seized {planet.name}!"

    def start_research_player(self, tech_id=None):
        gs = self.gs
        fac = gs.factions[gs.player_faction]
        if fac.research_target:
            gs.message = "Research already in progress."
            return

        options = [t for t in gs.tech_db if t["id"] not in fac.unlocked_techs]
        if tech_id:
            options = [t for t in options if t["id"] == tech_id]

        for t in options:
            if fac.treasury >= t["cost"]:
                fac.treasury -= t["cost"]
                fac.research_target = t["id"]
                fac.research_left = max(1, int(t["turns"] / max(0.1, fac.research_mod)))
                gs.message = f"Research started: {t['name']} ({fac.research_left} turns)"
                return
        gs.message = "Cannot start research (insufficient funds or no valid option)."

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
        if fid == "revolutionaries":
            return
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
                if fac.tax_rate > 1.2:
                    p.stability -= 2
                else:
                    p.stability = min(100, p.stability + 1)

        for a in gs.armies.values():
            if a.faction_id == fid:
                upkeep += sum(u.stats["upkeep"] for u in a.units)

        fac.treasury += income - upkeep

    def end_turn(self):
        gs = self.gs
        if self.pending_battle:
            gs.message = "Resolve the pending battle before ending the turn."
            return

        self._cleanup_destroyed_armies()
        order = list(gs.factions.keys())
        start = order.index(gs.current_faction)

        for i in range(1, len(order) + 1):
            fid = order[(start + i) % len(order)]
            gs.current_faction = fid
            for army in gs.armies.values():
                if army.faction_id == fid:
                    if army.can_move:
                        army.movement = 2 if "logistics_1" in gs.factions[fid].unlocked_techs else 1
                    else:
                        army.movement = 0
            self.resolve_research(fid)
            self.resolve_recruitment(fid)
            self.compute_income(fid)
            if fid not in (gs.player_faction, "revolutionaries"):
                start_research_if_idle(gs, fid)
                run_ai_turn(gs, fid)
            self._cleanup_destroyed_armies()
            self.check_for_battles(fid)
            if self.pending_battle:
                break

        self.trigger_revolutionaries()
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

    def _resolve_battle_outcome(self, attacker_won: bool, planet_name: str, atk, dfd):
        gs = self.gs
        winner_faction = atk.faction_id if attacker_won else dfd.faction_id
        gs.planets[planet_name].owner = winner_faction

        atk.units = [u for u in atk.units if u.hp > MIN_UNIT_HP]
        dfd.units = [u for u in dfd.units if u.hp > MIN_UNIT_HP]

        if not atk.units:
            gs.armies.pop(atk.id, None)
        if not dfd.units:
            gs.armies.pop(dfd.id, None)

        self._capture_planet_if_uncontested(planet_name, winner_faction)
        player_won = winner_faction == gs.player_faction

        self.last_battle = {
            "title": "VICTORY" if player_won else "DEFEAT",
            "detail": (
                f"Battle of {planet_name}: "
                f"{gs.factions[atk.faction_id].name} vs {gs.factions[dfd.faction_id].name}. "
                f"Winner: {gs.factions[winner_faction].name}"
            ),
        }

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
            attacker_won = auto_resolve(atk, dfd) == "attacker"
        else:
            result = BattleScene(
                self.screen,
                atk,
                dfd,
                gs.factions[atk.faction_id].color,
                gs.factions[dfd.faction_id].color,
            ).run()
            attacker_won = result == "victory"

        self._resolve_battle_outcome(attacker_won, planet_name, atk, dfd)
        self._cleanup_destroyed_armies()
        self.pending_battle = None
        self.mode = "battle_result"
        self.check_victory()

    def check_victory(self):
        gs = self.gs
        player = gs.player_faction
        owned = [p for p in gs.planets.values() if p.owner == player]
        enemies = [f for f in gs.factions if f not in (player, "revolutionaries") and any(p.owner == f for p in gs.planets.values())]

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
            tips = [
                "Goal: own 10 planets (or eliminate all rival factions) to win.",
                "Map controls: LMB selects a planet/army. RMB moves selected army to a connected planet.",
                "You can only recruit/build on planets you own. Select a planet first, then click Recruit or Build.",
                "Recruiting uses the Training Queue and takes turns to complete (faster on military worlds).",
                "Buildings consume planet slots and shape strategy: economy, military access, or stability control.",
                "Research unlocks faction bonuses. Pick a tech in Research, or use Auto Pick if unsure.",
                "Taxes raise income but can increase unrest and lower stability if pushed too high.",
                "If opposing armies share a planet, resolve with Auto Resolve or Manual Battle.",
                "Army View lets you inspect unit stats and merge friendly armies on the same planet.",
                "Use Save from the campaign panel often. Press any key to return to menu.",
            ]
            for i, t in enumerate(tips):
                self.screen.blit(self.font.render(t, True, (230, 230, 230)), (150, 180 + i * 34))
        elif self.mode == "faction_select":
            self.screen.fill((18, 15, 24))
            self.screen.blit(self.big.render("Choose Faction", True, (240, 240, 240)), (560, 110))
            for i, (_, label) in enumerate([
                ("empire", "EMPIRE"),
                ("rebels", "REBELS"),
                ("republic", "REPUBLIC"),
                ("separatists", "CONFEDERACY"),
            ]):
                row = pygame.Rect(460, 180 + i * 90, 420, 70)
                pygame.draw.rect(self.screen, (50, 50, 65), row)
                pygame.draw.rect(self.screen, (190, 190, 220), row, 1)
                self.screen.blit(self.font.render(label, True, (240, 240, 240)), (480, 208 + i * 90))
        elif self.mode == "campaign" and self.gs:
            self.draw_campaign()
        elif self.mode == "recruit" and self.gs:
            self.draw_recruit()
        elif self.mode == "build" and self.gs:
            self.draw_build()
        elif self.mode == "army_view" and self.gs:
            self.draw_army_view()
        elif self.mode == "research" and self.gs:
            self.draw_research()
        elif self.mode == "recruit_queue" and self.gs:
            self.draw_recruit_queue()
        elif self.mode == "battle_result":
            self.draw_battle_result()

    def draw_recruit_queue(self):
        gs = self.gs
        self.screen.fill((18, 20, 28))
        self.screen.blit(self.big.render("Training Queue", True, (240, 240, 240)), (40, 35))
        self.screen.blit(self.font.render("View all units currently in recruitment training.", True, (220, 220, 220)), (40, 75))

        entries = [q for q in gs.recruit_queue if q["faction"] == gs.player_faction]
        if not entries:
            self.screen.blit(self.font.render("No units in the queue.", True, (230, 230, 210)), (45, 125))
        else:
            for i, item in enumerate(entries):
                row = pygame.Rect(45, 120 + i * 70, 980, 60)
                pygame.draw.rect(self.screen, (50, 56, 70), row)
                pygame.draw.rect(self.screen, (180, 180, 200), row, 1)
                text = f"{item['unit']} | Planet: {item['planet']} | Turns remaining: {item['turns']}"
                self.screen.blit(self.font.render(text, True, (235, 235, 235)), (58, 143 + i * 70))

        Button((30, 680, 210, 38), "Back to Campaign").draw(self.screen, self.font)

    def draw_battle_result(self):
        self.screen.fill((18, 18, 24))
        title_color = (80, 220, 120) if self.last_battle["title"] == "VICTORY" else (240, 90, 90)
        self.screen.blit(self.big.render(self.last_battle["title"], True, title_color), (620, 250))
        self.screen.blit(self.font.render(self.last_battle["detail"], True, (230, 230, 230)), (330, 320))
        self.screen.blit(self.font.render("Press any key/click to continue.", True, (230, 230, 230)), (550, 390))

    def draw_recruit(self):
        gs = self.gs
        planet = gs.planets[gs.selected_planet]
        self.screen.fill((20, 22, 30))
        self.screen.blit(self.big.render(f"Recruitment - {planet.name}", True, (240, 240, 240)), (40, 35))
        self.screen.blit(self.font.render("Click a unit to queue recruitment. ESC or Back to close.", True, (220, 220, 220)), (40, 75))

        for i, unit in enumerate(self.recruit_items):
            row = pygame.Rect(45, 120 + i * 80, 980, 70)
            pygame.draw.rect(self.screen, (50, 56, 70), row)
            pygame.draw.rect(self.screen, (180, 180, 200), row, 1)
            turns = max(1, 4 - planet.military)
            text = (
                f"{unit['name']} | Cost: {unit['cost']} | Recruit at: {planet.name} | Time: {turns} turn(s) | "
                f"HP:{unit['health']} DMG:{unit['damage']} ARM:{unit['armor']} RNG:{unit['range']} SPD:{unit['speed']}"
            )
            self.screen.blit(self.font.render(text, True, (235, 235, 235)), (58, 145 + i * 80))

        Button((30, 680, 210, 38), "Back to Campaign").draw(self.screen, self.font)

    def draw_build(self):
        gs = self.gs
        planet = gs.planets[gs.selected_planet]
        self.screen.fill((20, 22, 30))
        self.screen.blit(self.big.render(f"Build - {planet.name}", True, (240, 240, 240)), (40, 35))
        self.screen.blit(self.font.render("Built structures:", True, (220, 220, 220)), (40, 85))
        built = ", ".join(planet.buildings) if planet.buildings else "None"
        self.screen.blit(self.font.render(built, True, (230, 230, 210)), (180, 85))
        self.screen.blit(self.font.render(f"Slots used: {len(planet.buildings)}/{planet.slots}", True, (220, 220, 220)), (40, 115))

        for i, building in enumerate(self.build_items):
            data = gs.buildings_db[building]
            row = pygame.Rect(45, 170 + i * 72, 980, 62)
            pygame.draw.rect(self.screen, (50, 56, 70), row)
            pygame.draw.rect(self.screen, (180, 180, 200), row, 1)
            text = f"{building} | Cost: {data['cost']} | {data.get('description', 'No description.')}"
            self.screen.blit(self.font.render(text, True, (235, 235, 235)), (58, 195 + i * 72))

        Button((30, 680, 210, 38), "Back to Campaign").draw(self.screen, self.font)

    def draw_army_view(self):
        gs = self.gs
        army = gs.armies.get(gs.selected_army)
        self.screen.fill((18, 20, 28))
        if not army:
            self.screen.blit(self.big.render("Army no longer exists", True, (240, 120, 120)), (40, 50))
            Button((30, 680, 210, 38), "Back to Campaign").draw(self.screen, self.font)
            return
        title = f"Army View - {gs.factions[army.faction_id].name} @ {army.planet}"
        self.screen.blit(self.big.render(title, True, (240, 240, 240)), (40, 35))
        for i, unit in enumerate(army.units):
            row = pygame.Rect(45, 100 + i * 60, 1180, 52)
            pygame.draw.rect(self.screen, (48, 54, 68), row)
            pygame.draw.rect(self.screen, (160, 170, 190), row, 1)
            txt = f"{unit.name} | HP:{unit.hp:.0f}/{unit.stats['health']} | DMG:{unit.stats['damage']} ARM:{unit.stats['armor']} RNG:{unit.stats['range']} SPD:{unit.stats['speed']}"
            self.screen.blit(self.font.render(txt, True, (235, 235, 235)), (58, 118 + i * 60))
        Button((30, 680, 210, 38), "Back to Campaign").draw(self.screen, self.font)
        Button((260, 680, 210, 38), "Merge Armies Here").draw(self.screen, self.font)

    @staticmethod
    def _tech_effects_text(effects):
        if not effects:
            return "No direct effects."
        return ", ".join(f"{k}: {v}" for k, v in effects.items())

    def draw_research(self):
        gs = self.gs
        fac = gs.factions[gs.player_faction]
        self.screen.fill((18, 20, 28))
        self.screen.blit(self.big.render("Research", True, (240, 240, 240)), (40, 35))
        current = fac.research_target or "None"
        self.screen.blit(self.font.render(f"Current project: {current}", True, (225, 225, 225)), (40, 75))
        if fac.research_target:
            self.screen.blit(self.font.render(f"Turns left: {fac.research_left}", True, (225, 225, 225)), (280, 75))

        for i, tech in enumerate(self.research_items):
            row = pygame.Rect(45, 120 + i * 90, 1100, 80)
            pygame.draw.rect(self.screen, (50, 56, 70), row)
            pygame.draw.rect(self.screen, (180, 180, 200), row, 1)
            turns = max(1, int(tech["turns"] / max(0.1, fac.research_mod)))
            header = f"{tech['name']} ({tech['id']}) | Cost: {tech['cost']} | Time: {turns} turns"
            desc = self._tech_effects_text(tech.get("effects", {}))
            self.screen.blit(self.font.render(header, True, (235, 235, 235)), (58, 142 + i * 90))
            self.screen.blit(self.font.render(desc, True, (210, 220, 240)), (58, 168 + i * 90))

        Button((30, 680, 210, 38), "Back to Campaign").draw(self.screen, self.font)
        Button((260, 680, 210, 38), "Auto Pick").draw(self.screen, self.font)

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
            pygame.draw.rect(self.screen, tuple(gs.factions[a.faction_id].color), (p.x - 5, p.y - 26, 10, 10))
            self.screen.blit(self.font.render(str(len(a.units)), True, (250, 250, 250)), (p.x - 6, p.y - 40))

        panel = pygame.Rect(1150, 0, 216, SCREEN_HEIGHT)
        pygame.draw.rect(self.screen, (35, 36, 48), panel)
        top = gs.factions[gs.player_faction]
        lines = [
            f"Turn {gs.turn}",
            f"Treasury: {top.treasury}",
            f"Tax: {top.tax_rate:.1f}",
            f"Research: {top.research_target or 'None'}",
            f"Pending battle: {'Yes' if self.pending_battle else 'No'}",
            f"Queued recruits: {len([q for q in gs.recruit_queue if q['faction'] == gs.player_faction])}",
        ]
        for i, line in enumerate(lines):
            self.screen.blit(self.font.render(line, True, (235, 235, 235)), (1160, 460 + i * 24))

        labels = ["Save", "End Turn", "Auto Resolve", "Manual Battle", "Recruit Unit", "Build", "Research", "Tax +", "Tax -", "View Army", "Training Queue"]
        for i, label in enumerate(labels):
            y = 20 + i * 50 if i < 4 else 220 + (i - 4) * 45
            Button((1170, y, 170, 40 if i < 4 else 34), label).draw(self.screen, self.font)

        if gs.selected_planet:
            p = gs.planets[gs.selected_planet]
            details = [
                f"Planet: {p.name}",
                f"Owner: {p.owner}",
                f"Stability: {p.stability - p.unrest}",
                f"Income est: {p.income(top.tax_rate)}",
                f"Military: {p.military}",
                f"Buildings: {', '.join(p.buildings) or 'None'}",
            ]
            for i, d in enumerate(details):
                self.screen.blit(self.font.render(d, True, (240, 240, 210)), (20, 620 + i * 22))

        self.screen.blit(self.font.render(gs.message, True, (255, 210, 90)), (20, 22))


def run_game():
    App().run()
