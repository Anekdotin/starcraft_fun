import sc2
from sc2 import run_game, maps, Race, Difficulty, position, Result
from sc2.player import Bot, Computer
from sc2.constants import COMMANDCENTER, BARRACKS, SCV,\
    MARINE, REAPER, SUPPLYDEPOT,\
    REFINERY, BARRACKSTECHLAB,SUPPLYDEPOTLOWERED,\
    MORPH_SUPPLYDEPOT_RAISE, MORPH_SUPPLYDEPOT_LOWER,BARRACKSREACTOR, FACTORY, FACTORYTECHLAB
from sc2.position import Point2, Pointlike
from sc2.helpers import ControlGroup
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
        self.scouts_and_spots = {}

        self.attack_groups = set()


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
        await self.scout()
        await self.idle_workers()
        await self.build_factory()
        await self.attack()

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


    async def scout(self):
        if len(self.units(BARRACKS).ready) == 3:
            # {DISTANCE_TO_ENEMY_START:EXPANSIONLOC}
            self.expand_dis_dir = {}

            for el in self.expansion_locations:
                distance_to_enemy_start = el.distance_to(self.enemy_start_locations[0])
                # print(distance_to_enemy_start)
                self.expand_dis_dir[distance_to_enemy_start] = el

            self.ordered_exp_distances = sorted(k for k in self.expand_dis_dir)

            existing_ids = [unit.tag for unit in self.units]
            # removing of scouts that are actually dead now.
            to_be_removed = []
            for noted_scout in self.scouts_and_spots:
                if noted_scout not in existing_ids:
                    to_be_removed.append(noted_scout)

            for scout in to_be_removed:
                del self.scouts_and_spots[scout]
            # end removing of scouts that are dead now.

            if len(self.units(BARRACKS).ready) == 0:
                unit_type = SCV
                unit_limit = 1
            else:
                unit_type = REAPER
                unit_limit = 15

            assign_scout = True


            if assign_scout:
                if len(self.units(unit_type).idle) > 0:
                    for obs in self.units(unit_type).idle[:unit_limit]:
                        if obs.tag not in self.scouts_and_spots:
                            for dist in self.ordered_exp_distances:
                                try:
                                    location = next(value for key, value in self.expand_dis_dir.items() if key == dist)
                                    # DICT {UNIT_ID:LOCATION}
                                    active_locations = [self.scouts_and_spots[k] for k in self.scouts_and_spots]

                                    if location not in active_locations:
                                        if unit_type == SCV:
                                            for unit in self.units(SCV):
                                                if unit.tag in self.scouts_and_spots:
                                                    continue

                                        await self.do(obs.move(location))
                                        self.scouts_and_spots[obs.tag] = location
                                        break
                                except Exception as e:
                                    pass

            for obs in self.units(unit_type):
                if obs.tag in self.scouts_and_spots:
                    if obs in [probe for probe in self.units(SCV)]:
                        await self.do(obs.move(self.random_location_variance(self.scouts_and_spots[obs.tag])))

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
        if self.units(COMMANDCENTER).amount < self.time / 2 and self.can_afford(COMMANDCENTER) and (4 > len(self.units(COMMANDCENTER))) and not self.already_pending(COMMANDCENTER):
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
        cc = self.units(COMMANDCENTER).first

        # build 2 to start
        if self.units(SUPPLYDEPOT).ready.exists:
            sups = self.units(SUPPLYDEPOT).ready.first
            if self.can_afford(BARRACKS) and not self.already_pending(BARRACKS):
                if 0 == len(self.units(BARRACKS)):

                    await self.build(BARRACKS, near=sups.position.towards(self.game_info.map_center, 1))

        # build 2 to start
        if 1 <= len(self.units(BARRACKS)):
            po = cc.position.towards_with_random_angle(self.game_info.map_center, 16)
            if self.can_afford(BARRACKS) and not self.already_pending(BARRACKS):
                if 0 == len(self.units(BARRACKS)):
                    try:
                        await self.build(BARRACKS, near=po)
                    except:
                        await self.build(BARRACKS, near=sups.position.towards(self.game_info.map_center, 1))

        # build 2 tech labs
        for sp in self.units(BARRACKS).ready:
            if 0 <= len((self.units(BARRACKSTECHLAB))) <= 1:
                if sp.add_on_tag == 0 and self.can_afford(BARRACKSTECHLAB):
                    await self.do(sp.build(BARRACKSTECHLAB))

        # build rest reactors
        for sp in self.units(BARRACKS).ready:
            if len((self.units(BARRACKSTECHLAB))) == 2:
                if sp.add_on_tag == 0 and self.can_afford(BARRACKSREACTOR):
                    await self.do(sp.build(BARRACKSREACTOR))


    async def idle_workers(self):
        for idle_worker in self.workers.idle:
            mf = self.state.mineral_field.closest_to(idle_worker)
            await self.do(idle_worker.gather(mf))

    async def build_marines(self):
        for mmm in self.units(BARRACKS).ready.noqueue:
            if self.can_afford(MARINE) and self.supply_left > 0:
                await self.do(mmm.train(MARINE))


    async def build_factory(self):
        cc = self.units(COMMANDCENTER).first

        p = cc.position.towards_with_random_angle(self.game_info.map_center, 16)
        # build 2 to start
        if self.units(BARRACKS).ready.exists:

            if self.can_afford(FACTORY) and not self.already_pending(FACTORY):
                if 2 <= len(self.units(BARRACKS)):
                    try:
                        await self.build(FACTORY, near=p)
                    except:
                        await self.build(FACTORY, near=cc.position.towards(self.game_info.map_center, 1))


        # build 1 tech lab
        for fp in self.units(FACTORY).ready:
            if 0 <= len((self.units(FACTORYTECHLAB))) <= 1:
                if fp.add_on_tag == 0 and self.can_afford(FACTORYTECHLAB):
                    await self.do(fp.build(FACTORYTECHLAB))


    async def build_starport(self):
        pass


    async def build_upgrades(self):
        pass

    async def attack(self):
        if self.units(MARINE).idle.amount > 15:
            cg = ControlGroup(self.units(MARINE).idle)
            self.attack_groups.add(cg)

        for ac in list(self.attack_groups):
            alive_units = ac.select_units(self.units)
            if alive_units.exists and alive_units.idle.exists:
                target = self.known_enemy_structures.random_or(self.enemy_start_locations[0]).position
                for marine in ac.select_units(self.units):
                    await self.do(marine.attack(target))
            else:
                self.attack_groups.remove(ac)

run_game(maps.get("AbyssalReefLE"), [
    Bot(Race.Terran, MarineRushBot()),
    Computer(Race.Protoss, Difficulty.Easy),
], realtime=False)