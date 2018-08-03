import sc2
from sc2 import run_game, maps, Race, Difficulty, position, Result
from sc2.player import Bot, Computer
from sc2.constants import LARVA, SPAWNINGPOOL, LAIR, \
    ZERGLING, EFFECT_INJECTLARVA, \
    OVERLORD, EXTRACTOR, DRONE, QUEEN, HATCHERY, RESEARCH_ZERGLINGMETABOLICBOOST, \
    AbilityId, ROACHWARREN, ROACH

import numpy as np
import time
import math
import random


HEADLESS = False


class ZergRushBot(sc2.BotAI):

    def __init__(self, title=1):


        self.use_model = True
        self.MAX_WORKERS = 50
        self.title = title
        self.moved_workers_to_gas = False
        self.moved_workers_from_gas = False
        self.roach_warren_started = False
        # upgrades
        self.mboost_started = False
        self.lair_built = False
        # attacks
        self.attack_1_sent = False
        self.attack_2_sent = False

    async def on_step(self, iteration):
        """
        Assigns function..keeps harvesters harvesting
        :param iteration:
        :return:
        """

        self.time = (self.state.game_loop / 22.4) / 60

        await self.expand()
        await self.build_queens()
        await self.build_drones()
        await self.build_extractor()
        await self.build_spawnning_pool()
        await self.build_attack_units()
        await self.unit_upgrades()
        await self.attack()
        await self.build_roach_warren()
        await self.building_upgrades()
        await self.intel()
        await self.move_units_general_spot()
        await self.defend()

        larvae = self.units(LARVA)
        try:
            hatchery = self.units(HATCHERY).ready.first
        except:
            hatchery = self.units(LAIR).ready.first
        # build supply
        if self.supply_left < 5:
            if self.can_afford(OVERLORD) and larvae.exists:
                await self.do(larvae.random.train(OVERLORD))
                return

        # no lazy units
        for idle_worker in self.workers.idle:
            mf = self.state.mineral_field.closest_to(idle_worker)
            await self.do(idle_worker.gather(mf))

        # fill exctractors
        if self.units(EXTRACTOR).ready.exists and not self.moved_workers_to_gas:
            self.moved_workers_to_gas = True
            extractor = self.units(EXTRACTOR).first
            for drone in self.workers.random_group_of(3):
                await self.do(drone.gather(extractor))


        # constant queen injections
        for queen in self.units(QUEEN).idle:
            abilities = await self.get_available_abilities(queen)
            if AbilityId.EFFECT_INJECTLARVA in abilities:
                await self.do(queen(EFFECT_INJECTLARVA, hatchery))

    async def defend(self):
        if len(self.known_enemy_units) > 0:
            target = self.known_enemy_units.closest_to(random.choice(self.units(HATCHERY)))
            for u in self.units(ZERGLING).idle:
                await self.do(u.attack(target))
            for u in self.units(ROACH).idle:
                await self.do(u.attack(target))


    async def move_units_general_spot(self):
        wait = random.randrange(7, 100)/100
        self.do_something_after = self.time + wait



    async def intel(self):
        if HEADLESS:
            import cv2
            game_data = np.zeros((self.game_info.map_size[1], self.game_info.map_size[0], 3), np.uint8)
            for unit in self.units().ready:
                pos = unit.position
                cv2.circle(game_data,
                           (int(pos[0]),
                            int(pos[1])),
                           int(unit.radius*8),
                           (255, 255, 255),
                           math.ceil(int(unit.radius*0.5)))


            for unit in self.known_enemy_units:
                pos = unit.position
                cv2.circle(game_data,
                           (int(pos[0]),
                            int(pos[1])),
                           int(unit.radius*8), (125, 125, 125),
                           math.ceil(int(unit.radius*0.5)))

            try:
                line_max = 50
                mineral_ratio = self.minerals / 1500
                if mineral_ratio > 1.0:
                    mineral_ratio = 1.0

                vespene_ratio = self.vespene / 1500
                if vespene_ratio > 1.0:
                    vespene_ratio = 1.0

                population_ratio = self.supply_left / self.supply_cap
                if population_ratio > 1.0:
                    population_ratio = 1.0

                plausible_supply = self.supply_cap / 200.0

                worker_weight = len(self.units(DRONE)) / (self.supply_cap-self.supply_left)
                if worker_weight > 1.0:
                    worker_weight = 1.0

                cv2.line(game_data, (0, 19), (int(line_max*worker_weight), 19), (250, 250, 200), 3)  # worker/supply ratio
                cv2.line(game_data, (0, 15), (int(line_max*plausible_supply), 15), (220, 200, 200), 3)  # plausible supply (supply/200.0)
                cv2.line(game_data, (0, 11), (int(line_max*population_ratio), 11), (150, 150, 150), 3)  # population ratio (supply_left/supply)
                cv2.line(game_data, (0, 7), (int(line_max*vespene_ratio), 7), (210, 200, 0), 3)  # gas / 1500
                cv2.line(game_data, (0, 3), (int(line_max*mineral_ratio), 3), (0, 255, 25), 3)  # minerals minerals/1500
            except Exception as e:
                print(str(e))


            # flip horizontally to make our final fix in visual representation:
            grayed = cv2.cvtColor(game_data, cv2.COLOR_BGR2GRAY)
            self.flipped = cv2.flip(grayed, 0)

            resized = cv2.resize(self.flipped, dsize=None, fx=2, fy=2)

            if not HEADLESS:
                if self.use_model:
                    cv2.imshow(str(self.title), resized)
                    cv2.waitKey(1)
                else:
                    cv2.imshow(str(self.title), resized)
                    cv2.waitKey(1)


    async def build_queens(self):
        if len(self.units(QUEEN)) < 1:
            try:
                hatchery = self.units(HATCHERY).ready.first
            except:
                try:
                    hatchery = self.units(LAIR).ready.first
                except:
                    hatchery = 0
            if hatchery != 0:
                if not self.already_pending(QUEEN) and self.units(SPAWNINGPOOL).ready.exists:
                    if self.can_afford(QUEEN) and len(self.units(QUEEN)) < 3:
                        await self.do(hatchery.train(QUEEN))

    async def build_drones(self):
        """
        Builds scv's to max amount
        :return:
        """
        hq = self.townhalls.first
        larvae = self.units(LARVA)
        if self.can_afford(DRONE) and self.workers.amount < 16 and hq.noqueue and larvae.exists:
            await self.do(larvae.random.train(DRONE))


    async def expand(self):
        """
        Expand till 4 bases.
        :return:
        """
        try:
            if self.units(HATCHERY).amount < self.time / 2 \
                    and self.can_afford(HATCHERY) \
                    and (3 > len(self.units(HATCHERY))) \
                    and not self.already_pending(HATCHERY):

                await self.expand_now()
        except Exception as e:
            print("EXPAND: ", str(e))

    async def build_extractor(self):
        hq = self.townhalls.first
        larvae = self.units(LARVA)

        if self.units(EXTRACTOR).amount < 2 and not self.already_pending(EXTRACTOR):
            if self.can_afford(EXTRACTOR):
                drone = self.workers.random
                target = self.state.vespene_geyser.closest_to(drone.position)
                await self.do(drone.build(EXTRACTOR, target))

        if hq.assigned_harvesters > hq.ideal_harvesters:
            if self.can_afford(DRONE) and larvae.exists and len(self.units(DRONE)) < self.MAX_WORKERS:
                larva = larvae.random
                await self.do(larva.train(DRONE))

        for a in self.units(EXTRACTOR):
            if a.assigned_harvesters < a.ideal_harvesters:
                w = self.workers.closer_than(20, a)
                if w.exists:
                    await self.do(w.random.gather(a))

    async def build_spawnning_pool(self):
        try:
            hatchery = self.units(HATCHERY).ready.first
        except:
            hatchery = self.units(LAIR).ready.first
        if self.can_afford(SPAWNINGPOOL) \
                and (len(self.units(SPAWNINGPOOL)) == 0) \
                and not self.already_pending(SPAWNINGPOOL):
            for d in range(4, 15):
                pos = hatchery.position.to2.towards(self.game_info.map_center, d)
                if await self.can_place(SPAWNINGPOOL, pos):
                    drone = self.workers.closest_to(pos)
                    err = await self.do(drone.build(SPAWNINGPOOL, pos))
                    if not err:
                        self.spawning_pool_started = True
                        break


    async def build_roach_warren(self):
        if self.units(LAIR).ready.exists:
            hatchery = self.units(LAIR).ready.first

            if self.can_afford(ROACHWARREN) and (len(self.units(ROACHWARREN)) == 0) and not self.already_pending(ROACHWARREN) and self.roach_warren_started is False:
                for d in range(6, 17):
                    pos = hatchery.position.to2.towards(self.game_info.map_center, d)
                    if await self.can_place(ROACHWARREN, pos):
                        drone = self.workers.closest_to(pos)
                        err = await self.do(drone.build(ROACHWARREN, pos))
                        if not err:
                            self.roach_warren_started = True
                            break


    async def build_attack_units(self):
        larvae = self.units(LARVA)
        if self.units(SPAWNINGPOOL).ready.exists:
            if larvae.exists and self.can_afford(ZERGLING) and len(self.units(ZERGLING)) < 30:
                await self.do(larvae.random.train(ZERGLING))

        if self.units(ROACHWARREN).ready.exists:
            if larvae.exists and self.can_afford(ROACHWARREN):
                await self.do(larvae.random.train(ROACHWARREN))


    async def building_upgrades(self):
        hq = self.townhalls.first

        # upgrade to lair
        if self.units(SPAWNINGPOOL).ready.exists and not self.lair_built is False:
            if not self.units(LAIR).exists and hq.noqueue:
                if self.can_afford(LAIR):
                    await self.do(hq.build(LAIR))
                    self.lair_built = True


    async def unit_upgrades(self):
        # zeg speed
        if self.vespene >= 100:
            sp = self.units(SPAWNINGPOOL).ready
            if sp.exists and self.minerals >= 100 and not self.mboost_started:
                await self.do(sp.first(RESEARCH_ZERGLINGMETABOLICBOOST))
                self.mboost_started = True


    async def attack(self):

        # attack 1
        if len(self.units(ZERGLING)) > 20 and self.attack_1_sent is False:
            for unit in self.units(ZERGLING):
                await self.do(unit.attack(self.enemy_start_locations[0]))
                self.attack_1_sent = True

        # attack 2

        if len(self.units(ZERGLING)) > 10 and len(self.units(ROACH)) > 10 and self.attack_2_sent is False:
            for unit in self.units(ZERGLING) | self.units(ROACH):
                await self.do(unit.attack(self.enemy_start_locations[0]))
                self.attack_2_sent = True


start_time = time.time()
run_game(maps.get("AbyssalReefLE"), [
    Bot(Race.Zerg, ZergRushBot()),
    Computer(Race.Protoss, Difficulty.Easy),
], realtime=False)
print("--- %s seconds ---" % (time.time() - start_time))