import random


def resolve(attacker_army, defender_army, terrain_mod=1.0):
    atk = attacker_army.strength() * (1 + attacker_army.general.rank * 0.05)
    dfd = defender_army.strength() * (1 + defender_army.general.rank * 0.05) * terrain_mod
    ratio = atk / max(1.0, dfd)
    winner = "attacker" if ratio + random.uniform(-0.2, 0.2) >= 1 else "defender"
    atk_loss = min(0.8, 0.35 / max(0.5, ratio))
    def_loss = min(0.85, 0.45 * max(0.7, ratio))
    for u in attacker_army.units:
        u.hp *= (1 - atk_loss)
    for u in defender_army.units:
        u.hp *= (1 - def_loss)
    attacker_army.units = [u for u in attacker_army.units if u.hp > 20]
    defender_army.units = [u for u in defender_army.units if u.hp > 20]
    return winner
