import sc2
from sc2 import run_game, maps, Race, Difficulty, position, Result
from sc2.player import Bot, Computer
from sc2.constants import  *
from sc2.position import Point2, Point3

import random
import cv2
import numpy as np
import keras
import math

HEADLESS = True


class MarineRushBot(sc2.BotAI):
    """
    This will build marines out of 3 barracks and rush in.


    """
    def __init__(self):
        self.MAX_WORKERS = 50
        self.do_something_after = 0



    def random_location_variance(self, location):
        x = location[0]
        y = location[1]

        #  FIXED THIS
        x += random.randrange(-5, 5)
        y += random.randrange(-5, 5)

        if x < 0:
            print("x below")
            x = 0
        if y < 0:
            print("y below")
            y = 0
        if x > self.game_info.map_size[0]:
            print("x above")
            x = self.game_info.map_size[0]
        if y > self.game_info.map_size[1]:
            print("y above")
            y = self.game_info.map_size[1]

        go_to = position.Point2(position.Pointlike((x, y)))

        return go_to


    def buildfaraway(self, distance):
        x = distance[0]
        y = distance[1]

        #  FIXED THIS
        x += random.randrange(-5, 5)
        y += random.randrange(-5, 5)

        if x < 0:
            print("x below")
            x = 0
        if y < 0:
            print("y below")
            y = 0

        go_to = position.Point2(position.Pointlike((x, y)))

        return go_to


    async def on_step(self, iteration):
        """
        Assigns function..keeps harvesters harvesting
        :param iteration:
        :return:
        """
        self.time = (self.state.game_loop / 22.4) / 60

        await self.build_scvs()
        await self.expand()
        await self.build_supply()
        await self.build_barracks()
        await self.build_marines()
        await self.build_refineries()

        # get units for harvester to harvest
        for a in self.units(REFINERY):
            if a.assigned_harvesters < a.ideal_harvesters:
                w = self.workers.closer_than(30, a)
                if w.exists:
                    await self.do(w.random.gather(a))

        # get units for cc to harvest
        for a in self.units(COMMANDCENTER):
            if a.assigned_harvesters < a.ideal_harvesters:
                w = self.workers.closer_than(30, a)
                if w.exists:
                    await self.do(w.random.gather(a))

        # cc = self.units(COMMANDCENTER)
        # for scv in self.units(SCV).idle:
        #     await self.do(scv.gather(self.state.mineral_field.closest_to(cc)))

        for b in self.units(SUPPLYDEPOT).ready:
            if b.add_on_tag == 0 and self.can_afford(BARRACKSTECHLAB):
                try:
                    await self.do(b.build(BARRACKSTECHLAB))
                except:
                    pass
    async def build_scvs(self):
        """
        Builds scv's to max amount
        :return:
        """
        if (len(self.units(COMMANDCENTER)) * 16) > len(self.units(SCV))\
                and len(self.units(SCV)) < self.MAX_WORKERS:
            for cc in self.units(COMMANDCENTER).ready.noqueue:
                if self.can_afford(SCV):
                    await self.do(cc.train(SCV))


    async def build_supply(self):
        cc = self.units(COMMANDCENTER)
        if not cc.exists:
            return
        else:
            cc = cc.first

        if self.can_afford(SCV) and self.workers.amount < 16 and cc.noqueue:
            await self.do(cc.train(SCV))


        # Raise depos when enemies are nearby
        for depo in self.units(SUPPLYDEPOT).ready:
            for unit in self.known_enemy_units.not_structure:
                if unit.position.to2.distance_to(depo.position.to2) < 15:
                    break
            else:
                await self.do(depo(MORPH_SUPPLYDEPOT_LOWER))

        # Lower depos when no enemies are nearby
        for depo in self.units(SUPPLYDEPOTLOWERED).ready:
            for unit in self.known_enemy_units.not_structure:
                if unit.position.to2.distance_to(depo.position.to2) < 10:
                    await self.do(depo(MORPH_SUPPLYDEPOT_RAISE))
                    break

        depos = [
            Point2((max({p.x for p in d}), min({p.y for p in d})))
            for d in self.main_base_ramp.top_wall_depos
        ]

        depo_count = (self.units(SUPPLYDEPOT) | self.units(SUPPLYDEPOTLOWERED)).amount

        if self.can_afford(SUPPLYDEPOT) and not self.already_pending(SUPPLYDEPOT):
            if depo_count >= len(depos):
                return
            depo = list(depos)[depo_count]
            r = await self.build(SUPPLYDEPOT, near=depo, max_distance=2, placement_step=1)



    async def expand(self):
        """
        Expand till 4 bases. Upgrade to Orbital CC's
        :return:
        """
        if self.units(COMMANDCENTER).amount < self.time / 2\
                and self.can_afford(COMMANDCENTER)\
                and (4 > len(self.units(COMMANDCENTER))):

            await self.expand_now()


    async def build_refineries(self):
        """
        Build 2 refineries per cc, after there is a barracks...
        :return:
        """
        if self.units(BARRACKS).ready.exists:
            if self.units(COMMANDCENTER).ready:
                for c in self.units(COMMANDCENTER).ready:

                    vaspenes = self.state.vespene_geyser.closer_than(15.0, c)
                    for vaspene in vaspenes:
                        if not self.can_afford(REFINERY):
                            break
                        worker = self.select_build_worker(vaspene.position)
                        if worker is None:
                            break
                        if not self.units(REFINERY).closer_than(1.0, vaspene).exists:
                            await self.do(worker.build(REFINERY, vaspene))


    async def build_barracks(self):
        """
        Build 3 barracks to start...stop till x command cc's and a factory starport
        :return:
        """
        if self.units(SUPPLYDEPOT).ready.exists:
            sups = self.units(SUPPLYDEPOT).ready.first
            if self.can_afford(BARRACKS) and not self.already_pending(BARRACKS):
                if 4 > len(self.units(BARRACKS)):
                    await self.build(BARRACKS, near=sups.position.towards(self.game_info.map_center, 2))





    async def build_marines(self):
        for mmm in self.units(BARRACKS).ready.noqueue:
            if self.can_afford(MARINE) and self.supply_left > 0:
                await self.do(mmm.train(MARINE))


    async def build_factory(self):
        pass

    async def build_starport(self):
        pass

    async def build_upgrades(self):
        pass

run_game(maps.get("AbyssalReefLE"), [
    Bot(Race.Terran, MarineRushBot()),
    Computer(Race.Protoss, Difficulty.Easy),
], realtime=False)