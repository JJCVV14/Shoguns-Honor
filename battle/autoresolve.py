import random


def resolve(attacker_army, defender_army, terrain_mod=1.0):
    atk = attacker_army.strength() * (1 + attacker_army.general.rank * 0.05)
    dfd = defender_army.strength() * (1 + defender_army.general.rank * 0.05) * terrain_mod
    ratio = atk / max(1.0, dfd)
    winner = "attacker" if ratio + random.uniform(-0.2, 0.2) >= 1 else "defender"

    winner_loss = min(0.7, 0.3 / max(0.5, ratio if winner == "attacker" else 1 / max(0.5, ratio)))
    if winner == "attacker":
        for u in attacker_army.units:
            u.hp *= (1 - winner_loss)
        for u in defender_army.units:
            u.hp = 0
    else:
        for u in defender_army.units:
            u.hp *= (1 - winner_loss)
        for u in attacker_army.units:
            u.hp = 0

    attacker_army.units = [u for u in attacker_army.units if u.hp > 0]
    defender_army.units = [u for u in defender_army.units if u.hp > 0]
    return winner
