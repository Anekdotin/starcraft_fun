import sc2
from sc2 import run_game, maps, Race, Difficulty, position, Result
from sc2.player import Bot, Computer
from sc2.constants import LARVA, SPAWNINGPOOL, LAIR, \
    ZERGLING, EFFECT_INJECTLARVA,\
    OVERLORD, EXTRACTOR, DRONE, QUEEN, HATCHERY, RESEARCH_ZERGLINGMETABOLICBOOST, AbilityId


from sc2.data import race_townhalls


HEADLESS = False
import math



class ZergRushBot(sc2.BotAI):

    def __init__(self):
        self.MAX_WORKERS = 50
        self.moved_workers_to_gas = False
        self.moved_workers_from_gas = False

        # upgrades
        self.mboost_started = False

        # attacks
        self.attack_1_sent = False


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


        larvae = self.units(LARVA)
        hatchery = self.units(HATCHERY).ready.first
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


    async def build_queens(self):
        hatchery = self.units(HATCHERY).ready.first
        if not self.already_pending(QUEEN) and self.units(SPAWNINGPOOL).ready.exists:
            if self.can_afford(QUEEN):
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

        if self.units(HATCHERY).amount < self.time / 2 \
                and self.can_afford(HATCHERY) \
                and (4 > len(self.units(HATCHERY))) \
                and not self.already_pending(HATCHERY):

            await self.expand_now()

    async def build_extractor(self):
        hq = self.townhalls.first
        larvae = self.units(LARVA)

        if self.units(EXTRACTOR).amount < 2 and not self.already_pending(EXTRACTOR):
            if self.can_afford(EXTRACTOR):
                drone = self.workers.random
                target = self.state.vespene_geyser.closest_to(drone.position)
                err = await self.do(drone.build(EXTRACTOR, target))

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

        hatchery = self.units(HATCHERY).ready.first
        if self.can_afford(SPAWNINGPOOL)\
                and (len(self.units(SPAWNINGPOOL)) == 0)\
                and not self.already_pending(SPAWNINGPOOL):
            for d in range(4, 15):
                pos = hatchery.position.to2.towards(self.game_info.map_center, d)
                if await self.can_place(SPAWNINGPOOL, pos):
                    drone = self.workers.closest_to(pos)
                    err = await self.do(drone.build(SPAWNINGPOOL, pos))
                    if not err:
                        self.spawning_pool_started = True
                        break


    async def build_attack_units(self):
        larvae = self.units(LARVA)
        if self.units(SPAWNINGPOOL).ready.exists:
            if larvae.exists and self.can_afford(ZERGLING):
                await self.do(larvae.random.train(ZERGLING))

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



run_game(maps.get("AbyssalReefLE"), [
    Bot(Race.Zerg, ZergRushBot()),
    Computer(Race.Protoss, Difficulty.Easy),
], realtime=False)