import random
import json
import os
from os import listdir
from os.path import isfile, join

from datetime import datetime
import time
import BL_JPS
import hashlib # For hashing unknown map configurations

from UTS_Imass_Miner_Pathing import get_worker_paths, get_worker_movement, allocate_miners, get_path, requires_rerouting

# Directions 0:Up, 1:Right, 2:Down, 3:Left
UP = 0
RIGHT = 1
DOWN = 2
LEFT = 3

# Requires fix on action duration
def Noop(unit, current_cycle):
    return {'unitID' : unit['ID'], 'unitAction': {'parameter': 0, 'type': 0}, 'time' : current_cycle}

def Move(unit, dst, dir_param, current_cycle): 
    return {'unitID' : unit['ID'], 'unitAction': {'parameter': dir_param, 'type': 1}, 'time' : current_cycle}

def Harvest(unit, dst, dir_param, current_cycle):
    return {'unitID' : unit['ID'], 'unitAction': {'parameter': dir_param, 'type': 2}, 'time' : current_cycle}

def Return(unit, dst, dir_param, current_cycle):
    return {'unitID' : unit['ID'], 'unitAction': {'parameter': dir_param, 'type': 3}, 'time' : current_cycle}  

def Produce(unit, output_type, dir_param, current_cycle):
    return {'unitID' : unit['ID'], 'unitAction': {'parameter': dir_param, 'type': 4, 'unitType': output_type}, 'time' : current_cycle}

def Attack(unit, dst, current_cycle):
    return {'unitID' : unit['ID'], 'unitAction': {'x': dst[0], 'y': dst[1], 'type': 5}, 'time' : current_cycle}



class Self_Learner_Tuning:
    def __init__(self):
        self.parameter_ranges = {}
        self.parameter_ranges['miners'] = [0,1,2,3,4,200]
        self.parameter_ranges['barracks'] = [0,1,2,3,4]
        self.parameter_ranges['workers'] = [0,1,2,3,4,200]
        self.parameter_ranges['fighters'] = 4
        self.build_order_success = {}

        # In the format miner, barracks, additional construction and attacking workers
        # Some manually set parameters that tend to cover a range of strategies.
        # Just incase we don't have much time to learn focus at least on some of these
        self.first_trial_configs = [ (1,0,200,()),(1,1,3,()),(1,3,2,()),(2,3,1,()),(3,0,200,()),(3,1,200,()),(3,3,3,()),(3,3,5,()),(4,1,4,()),(4,3,200,())]
        self.configs_trialed = 0
        self.sampled_configs = {}
        self.config_file_path = None
        self.pgs_str = None # Used for re-iding the map

    def set_config_file_path(self, path, pgs_str, filename = ''):
        map_id = 0
        exists = True
        self.pgs_str = pgs_str
        if not filename:
            while exists:
                map_id += 1
                self.config_file_path = path+'/'+str(map_id)+'_config.json'
                exists = os.path.isfile(self.config_file_path)
        else:
            self.config_file_path = join(path,filename)

    def get_largest_config(self, rank_index=0):
        config = None
        if len(self.sampled_configs)>rank_index:
            build_win_rates = [(self.sampled_configs[x][2],x) for x in self.sampled_configs]
            build_win_rates.sort(reverse=True)
            print ('largest best config is:',build_win_rates[0][1], self.sampled_configs[build_win_rates[0][1]])
            config = build_win_rates[rank_index][1]
        else:
            config = self.get_explore_config()
        return config


    def get_best_config(self, rank_index=0):
        config = None
        if len(self.sampled_configs)>rank_index:
            build_win_rates = [(self.sampled_configs[x][0],x) for x in self.sampled_configs]
            build_win_rates.sort(reverse=True)
            print ('Current best config is:',build_win_rates[0][1], self.sampled_configs[build_win_rates[0][1]])
            config = build_win_rates[rank_index][1]
        else:
            config = self.get_explore_config()
        return config

    def get_explore_config(self):
        if self.configs_trialed < len(self.first_trial_configs):
            config = self.first_trial_configs[self.configs_trialed]
            self.configs_trialed += 1
            return config 
        
        miners = random.choice(self.parameter_ranges['miners'])
        barracks = random.choice(self.parameter_ranges['barracks'])
        workers = random.choice(self.parameter_ranges['workers'])
        while miners == 200 and miners==workers: # We won't ever be able to sample so many.
            miners = random.choice(self.parameter_ranges['miners'])
            workers = random.choice(self.parameter_ranges['workers'])
        if miners == 200: # We won't ever be able to sample so many.
            workers = 0
        roster = [random.randint(0,2) for x in range(random.randint(1,4))]
        return miners, barracks, miners, tuple(roster)
    
    def submit_config_score(self, config, win, draw, loss):
        score = 0
        if win:
            score += 1
        if draw:
            score += 0.5
        if config not in self.sampled_configs:
            self.sampled_configs[config] = [0,0,0] # average_score, total_score, games_played

        self.sampled_configs[config][1] += score
        self.sampled_configs[config][2] += 1
        win_rate = self.sampled_configs[config][1]/float(self.sampled_configs[config][2])
        self.sampled_configs[config][0] = win_rate
        if self.config_file_path is not None:
            with open(self.config_file_path,'w') as f:
                samples= [[str(x),self.sampled_configs[x]] for x in self.sampled_configs]
                

                # samples = str(self.sampled_configs)#.replace('(','"(').replace(')',')"')
                json.dump({'pgs':self.pgs_str,'samples':samples},f)



class UTS_Imass_AI:

    def __init__(self, utt, server_id, pre_game_analysis_shared_memory):
        self.actions = []
        self.game_meta_data = utt

        self.IMASS_BOT_VERSION = 0.9

        self.episode_num = 0
    
        self.unit_meta_data = {}
        self.current_time_log = {}
        self.all_time_log = {}

        self.bljps = BL_JPS.BL_JPS()
        self.pre_game_analysis_shared_memory = pre_game_analysis_shared_memory

        # If we are the odd numbered server then flag us as the dominant agent
        self.dominant_agent = (server_id % 2) == 1
        # if self.pre_game_analysis_shared_memory['sharing_enabled']:
            # print ('Hello im a self learner! Dominance:', self.dominant_agent)

        self.roster_map = {0:'Light',1:'Ranged',2:'Heavy'}

        self.current_pgs = None
        self.process_game_meta_data()
        self.init_actions()
        self.reset()


    def begin_self_learning(self, temp_map_path, timelimit_seconds, pgs):
        if timelimit_seconds > 1:
            # return 
            import subprocess

            start_time = datetime.now()
            self.pre_game_analysis_shared_memory['sharing_enabled'] = True
            # self.pre_game_analysis_shared_memory[('configs',str(pgs))].set_config_file_path(os.path.dirname(temp_map_path), str(pgs) )

            try:
                # On the competition website it says we have 60 minutes per map to learn on
                # So lets stop 2 minutes before the cut off just to make sure we're under time
                while (datetime.now()-start_time).total_seconds() < timelimit_seconds-2*60:
                    print ('Training ... ',(datetime.now()-start_time).total_seconds())
                    # Remotely start our archived version of microrts to play games against our selves and store the results
                    subprocess.call(['java', '-jar', 'remote_microrts_not_uts_imass.jar','-m',temp_map_path])
            except Exception as e:
                print ("UTS_Imass python agent error during self learning")
                print ("Error:",e)

            self.pre_game_analysis_shared_memory['sharing_enabled'] = False
        

    def create_temp_map_file(self, pgs):
        if self.agent_log_directory is None:
            return False, ''

        try:
            temp_file_path = self.agent_log_directory.replace('"','')+'/temp.xml'
            with open(temp_file_path, 'w') as f:
                start = ''
                end = ''
                start += '<rts.PhysicalGameState width="{}" height="{}">\n'.format(int(self.map_width),int(self.map_height))
                end += '</rts.PhysicalGameState>\n'
                start += ' <terrain>'+self.terrain+' </terrain>\n'
                start += ' <players>\n'
                for player in pgs['players']:
                    start += '<rts.Player ID="{}" resources="{}"></rts.Player>\n'.format(player['ID'],player['resources']) 
                start += ' </players>\n'
                start += '  <units>\n'
                end = ' </units>' + end 
                for unit in pgs['units']:
                    start += ' <rts.units.Unit type="{}" ID="{}" player="{}" x="{}" y="{}" resources="{}" hitpoints="{}" ></rts.units.Unit>\n'.format(unit['type'],unit['ID'],unit['player'],unit['x'],unit['y'],unit['resources'],unit['hitpoints'] )
                start += end
                f.write(start) 
            print ('Temporary self learning map created:',temp_file_path)
            print ('Now running self learning on precompiled micro rts')
            return True, temp_file_path

        except Exception as e:
            print ("UTS_Imass python AI failed to create temp map file. This will inhibit its ability to learn from new maps. Please contact bot author to resolve in tournament settings.")
            print ("Error:",e)

        return False, ''

    def set_terrain(self, map_width, map_height, terrain, pgs):
        if self.terrain is None:
            self.pgs_str = str(pgs)

            self.terrain = terrain
            self.terrain_walls = [i for i, x in enumerate(self.terrain) if x != "0"]
            self.map_width = map_width
            self.map_height = map_height

            # if 'configs' not in self.pre_game_analysis_shared_memory:

            if ('configs',self.pgs_str) not in self.pre_game_analysis_shared_memory:
                print ('Error: Requires pre training through pre-game-analysis to generate data to play from.')
                print ('Error: Set to random mode.')
                self.assist_miners, self.assist_barracks, self.assist_workers, self.roster = random.randint(0,5) , random.randint(0,3) , random.randint(0,5) ,()
            else:
                if self.pre_game_analysis_shared_memory['sharing_enabled'] == False:
                    self.assist_miners, self.assist_barracks, self.assist_workers, self.roster = self.pre_game_analysis_shared_memory[('configs',self.pgs_str)].get_largest_config()

                if self.dominant_agent:
                    self.assist_miners, self.assist_barracks, self.assist_workers, self.roster = self.pre_game_analysis_shared_memory[('configs',str(pgs))].get_best_config()
                else:
                    if random.random()>0.6: # 40% of the time choose between rank 2-4
                        self.assist_miners, self.assist_barracks, self.assist_workers, self.roster = self.pre_game_analysis_shared_memory[('configs',str(pgs))].get_best_config(random.randint(1,4))
                    else:
                        self.assist_miners, self.assist_barracks, self.assist_workers, self.roster = self.pre_game_analysis_shared_memory[('configs',str(pgs))].get_explore_config()
            if not self.roster: # If no roster was given generate one
                self.roster = tuple([random.randint(0,2) for i in range(random.randint(1,4))])
            if self.roster.count(self.roster[0]) == len(self.roster): # If all the elements are the same compress it to one element
                self.roster = (self.roster[0],)
            self.assist_workers += self.assist_miners
            # self.assist_miners, self.assist_barracks, self.assist_workers, self.roster = 4,1,4,(,)
    

    def load_config(self, config_file_path):
        sampled_configs = {}
        if config_file_path is not None:
            if os.path.isfile(config_file_path):
                with open(config_file_path,'r') as f:
                    data = json.load(f)
                    if data['pgs'] is None:
                        return '', sampled_configs
                    samples = data['samples']
                    for key, value in samples:
                        # key = key.remove('() ')
                        key="".join([char for char in key if char not in "() "])
                        if key[-1] == ',':
                            key = key[:-1]
                        key = '['+key+']'

                        key = json.loads(key)
                        if key == 3:
                            key = (key[0],key[1],key[2],())
                        else:
                            key = (key[0],key[1],key[2],tuple(key[3:]))
                        sampled_configs[key] = value
                    return data['pgs'], sampled_configs
        return '', sampled_configs


    def check_map_caches(self, pgs):
        pgs_str = str(pgs)

        # First attempt to load data from previous runs
        if self.agent_log_directory is not None:
            onlyfiles = [f for f in listdir(self.agent_log_directory) if isfile(join(self.agent_log_directory, f))]
            for filename in onlyfiles:
                if '_config.json' in filename:
                    loaded_pgs, sample_data = self.load_config(join(self.agent_log_directory, filename))
                    if loaded_pgs :
                        new_learner = Self_Learner_Tuning()
                        new_learner.set_config_file_path(self.agent_log_directory,loaded_pgs,filename)
                        new_learner.sampled_configs = sample_data
                        self.pre_game_analysis_shared_memory[('configs',loaded_pgs)] = new_learner
                        print ('loaded config for map',join(self.agent_log_directory, filename)) 
                        if pgs_str == loaded_pgs:
                            print ('This save was for the current map. Using saved settings')

        # if no data exists for this run then build new data
        if ('configs',pgs_str) not in self.pre_game_analysis_shared_memory:
            new_learner = Self_Learner_Tuning()
            new_learner.set_config_file_path(self.agent_log_directory,pgs_str)
            self.pre_game_analysis_shared_memory[('configs',pgs_str)] = new_learner
            print ('created config for this map',new_learner.config_file_path)  


    def pre_game_analysis(self, time_limit, read_write_directory, current_state_json):
        # self.agent_log_directory = 'E:/microrts-master/UTS_Imass_2019_Server/test'
        if read_write_directory not None:
            self.agent_log_directory = read_write_directory.replace('\\','/').strip('"') 
        self.pgs_str = str(current_state_json['pgs'])

        self.check_map_caches(current_state_json['pgs'])
        self.set_terrain(current_state_json['pgs']['width'],current_state_json['pgs']['height'],current_state_json['pgs']['terrain'], current_state_json['pgs'])
        succ, map_log_dir = self.create_temp_map_file(current_state_json['pgs'])
        if succ:
            self.begin_self_learning(map_log_dir, time_limit,current_state_json['pgs'])

    def process_game_meta_data(self):
        unit_data = self.game_meta_data['unitTypes']
        for unit_data in unit_data:
            self.unit_meta_data[unit_data['name']] = unit_data

    def init_actions(self):
        self.possible_actions = [('NoOp')]
        self.worker_actions = [0]
        self.base_actions = [0]
        self.barracks_actions = [0]
        self.attacker_actions = [0]
        self.ranged_attacker_actions = [0]
        for action_t in ('Move','Attack','Harvest','Return'):
            for dir in ('Up','Right','Down','Left'):
                self.worker_actions.append(len(self.possible_actions))
                if action_t == 'Move' or action_t == 'Attack':
                    self.attacker_actions.append(len(self.possible_actions))
                if action_t == 'Move':
                    self.ranged_attacker_actions.append(len(self.possible_actions))
                self.possible_actions.append((action_t,dir))

        for action_t in ('Worker','Barracks','Light','Ranged','Heavy'):
            for dir in ('Up','Right','Down','Left'):
                if action_t == 'Worker':
                    self.base_actions.append(len(self.possible_actions))
                if action_t == 'Barracks':
                    self.worker_actions.append(len(self.possible_actions))
                if action_t == 'Light' or action_t == 'Heavy' or action_t == 'Ranged':
                    self.barracks_actions.append(len(self.possible_actions))
                self.possible_actions.append(('Produce',dir, action_t))
        
        self.ranged_attacker_actions.append(len(self.possible_actions))
        self.ranged_attack_action_id = len(self.possible_actions)
        self.possible_actions.append(('Attack','Ranged'))


    def build_mining_routes(self, resource_locs, base_locs, struct_locs):
        if self.worker_lines is not None:
            return True
        
        succ, worker_lines = get_worker_paths(resource_locs, base_locs, struct_locs, self.map_width, self.map_height, self.miner_line_count, self.bljps)
        if not succ:
            # print ('Failed to initialise worker lines for {} workers'.format(self.miner_line_count))
            return False
        self.worker_lines = worker_lines
        return True

    def get_dir(self, dir_str):
        dir_param = None
        dx = 0
        dy = 0
        if dir_str == 'Up':
            dir_param = UP
            dy -= 1
        elif dir_str == 'Right':
            dx += 1
            dir_param = RIGHT
        elif dir_str == 'Left':
            dx -= 1
            dir_param = LEFT
        elif dir_str == 'Down':
            dir_param = DOWN
            dy += 1
        return dx, dy, dir_param

    def get_dir2(self, dir_id):
        dir_param = None
        dx = 0
        dy = 0
        if dir_id == UP:
            dy -= 1
        elif dir_id == RIGHT:
            dx += 1
        elif dir_id == LEFT:
            dx -= 1
        elif dir_id == DOWN:
            dy += 1
        return dx, dy

    def get_local_action_length(self, unit, action_id):
        unit_data = self.unit_meta_data[unit['type']]
        if action_id == 0: # NoOp
            return 1
        if self.possible_actions[action_id][0] == 'Move':
            return unit_data['moveTime'] 
        if self.possible_actions[action_id][0] == 'Harvest':
            return unit_data['harvestTime'] 
        if self.possible_actions[action_id][0] == 'Return':
            return unit_data['returnTime'] 
        if self.possible_actions[action_id][0] == 'Attack':
            return unit_data['attackTime'] 
        if self.possible_actions[action_id][0] == 'Produce':
            unit_data = self.unit_meta_data[self.possible_actions[action_id][2]]
            return unit_data['produceTime']

    # Translates between my action description tuple (Action_Type, Direction, Production_Output)
    # To actions that can be sent to microrts
    def fill_action(self, my_unit, enemies, action, start_turn_actions):
        if action == 'NoOp':
            return Noop(my_unit, self.cycle)

        dx, dy, dir_param = self.get_dir(action[1])

        if action[0] == 'Move':
            return Move(my_unit, (5,5), dir_param, self.cycle)      

        if action[0] == 'Attack':
            if action[1] == 'Ranged':
                
                for enemy in enemies.values():
                    if self.can_hit_unit(my_unit, enemy, start_turn_actions):
                        return Attack(my_unit, (enemy['x'], enemy['y']), self.cycle)   
                print ('Error no attack target for ranged unit')
                return Noop(my_unit, self.cycle)
            else:
                return Attack(my_unit, (my_unit['x']+dx, my_unit['y']+dy), self.cycle)   

        if action[0] == 'Harvest':
            return Harvest(my_unit, (5,5), dir_param, self.cycle)      

        if action[0] == 'Return':
            return Return(my_unit, (5,5), dir_param, self.cycle)  

        if action[0] == 'Produce':
            return Produce(my_unit, action[2], dir_param, self.cycle)  

        print ("Error this line should not execute")
        return Noop(my_unit, self.cycle)

    def can_hit_unit(self, my_unit, enemy, start_turn_actions):
        d = abs(my_unit['x']- enemy['x']) + abs(my_unit['y']- enemy['y'])
        # min_d = max(abs(my_unit['x']- enemy['x']), abs(my_unit['y']- enemy['y']))
        my_unit_attack_range = self.unit_meta_data[my_unit['type']]['attackRange']
        my_unit_attack_time = self.unit_meta_data[my_unit['type']]['attackTime']
        enemy_move_time = self.unit_meta_data[enemy['type']]['moveTime']

        # if (d > 1 and my_unit_attack_range == 1) or (my_unit_attack_range > 1 and min_d > my_unit_attack_range-1):

        if my_unit_attack_range < d:
            return False

        for s_action in start_turn_actions:
            if s_action['ID'] == enemy['ID']:
                if s_action['action']['type'] == 1: # move action
                    # The enemy would move before or on the same cycle we could attack
                    # So don't bother trying to attack them
                    if s_action['time']+enemy_move_time <= self.cycle+my_unit_attack_time: 
                        return False
                break

        return True

    def can_hit_unit_with_move(self, my_unit, enemy, start_turn_actions):
        cx,cy = enemy['x'],enemy['y']
        nx,ny = enemy['x'],enemy['y']

        my_unit_attack_range = self.unit_meta_data[my_unit['type']]['attackRange']

        for s_action in start_turn_actions:
            if s_action['ID'] == enemy['ID']:
                if s_action['action']['type'] == 1: # move action
                    dx,dy = self.get_dir2(s_action['action']['parameter'])
                    nx += dx
                    ny += dy
                    # The enemy would move before or on the same cycle we could attack
                    # So don't bother trying to attack them
                    d = abs(my_unit['x']- nx) + abs(my_unit['y']- ny)
                    # min_d = max(abs(my_unit['x']- nx), abs(my_unit['y']- ny))
                    if my_unit_attack_range >= d:
                        return True
                        
        d = abs(my_unit['x']- cx) + abs(my_unit['y']- cy)
        # min_d = max(abs(my_unit['x']- cx), abs(my_unit['y']- cy))
        # if ((d > 1 and my_unit_attack_range == 1) or (my_unit_attack_range > 1 and min_d > (my_unit_attack_range-1))):
        if my_unit_attack_range >= d:
            return True

        return False




    def filter_valid_actions(self, my_unit, my_units, enemies, resource_locs, action, start_turn_actions):

        dx, dy, dir_param = self.get_dir(action[1])
        if my_unit['x']+dx <0 or my_unit['y']+dy <0 or my_unit['x']+dx>=self.map_width or my_unit['y']+dy >=self.map_height: #exceeds map limits
            return False

        if action[0] == 'Attack':
            if my_unit['type'] == 'Ranged': #if its a ranged unit then just check if we can hit
                for enemy in enemies.values():
                    if self.can_hit_unit(my_unit, enemy, start_turn_actions):
                        return True      
            else:
                for enemy in enemies.values():
                    if (my_unit['x']+dx, my_unit['y']+dy ) == (enemy['x'], enemy['y']):
                        return self.can_hit_unit(my_unit, enemy, start_turn_actions)
    
            return False
        elif my_unit['type'] != 'Base' and my_unit['type'] != 'Barracks':
            # We are in attack range of another unit. Only allow attack actions
            # Or based on their move action they will be in attack range
            for enemy in enemies.values():
                if self.can_hit_unit_with_move(my_unit, enemy, start_turn_actions):
                    return False
        
        if action == 'NoOp':
            return True

        if action[0] == 'Harvest':
            if my_unit['resources'] == 1:
                return False
            if (my_unit['x']+dx, my_unit['y']+dy ) in resource_locs:
                return True
            return False

        if action[0] == 'Return':
            if my_unit['resources'] == 0:
                return False            
            for allie in my_units.values():
                if allie['type'] == 'Base':
                    if (my_unit['x']+dx, my_unit['y']+dy ) == (allie['x'], allie['y']):
                        return True
            return False

        if action[0] == 'Move':
            if (my_unit['x']+dx, my_unit['y']+dy ) in self.blocked_cells:
                return False

            return True

        if action[0] == 'Produce':
            if self.get_unit_cost(action[2]) > self.player_funds: # not enough funds
                return False
            if action[2] == 'Barracks': # Limit barracks produced
                if self.num_barracks >= self.assist_barracks:
                    return False 
            if action[2] == 'Worker': # Limit Workers produced
                if self.created_worker_count >= self.assist_workers:
                    return False

            if (my_unit['x']+dx, my_unit['y']+dy ) in self.blocked_cells:
                return False
            return True
        

    def get_action(self, my_unit, my_units, enemies, resource_locs, start_turn_actions, players_money, replay_action_id, this_cycle_actions):

        if my_unit['type'] == 'Worker':
            my_possible_actions = self.worker_actions
        elif my_unit['type'] == 'Base':
            my_possible_actions = self.base_actions
        elif my_unit['type'] == 'Barracks':
            my_possible_actions = self.barracks_actions
        elif my_unit['type'] == 'Ranged':
            my_possible_actions = self.ranged_attacker_actions
        else:
            my_possible_actions = self.attacker_actions
        valid_actions = []
        for action_index in my_possible_actions:
           if self.filter_valid_actions(my_unit, my_units, enemies, resource_locs, self.possible_actions[action_index], start_turn_actions):
                valid_actions.append(action_index)
        if len(valid_actions) ==0:
            valid_actions = [0] # This can happen when the unit is waiting for an enemy to move into range

        move_order = ['Down','Right','Up','Left']
        alt_order = ['Up','Left','Down','Right']
        barracks_option = 22
        if self.player_id == 1:
            move_order,alt_order = alt_order,move_order
            barracks_option = 24

        # For automated miner
        automated_worker_flag = False
        if my_unit['ID'] in self.miner_mapping or my_unit['resources']:
            automated_worker_flag = True
            if my_unit['ID'] in self.miner_mapping:
                miner_line = self.miner_mapping[my_unit['ID']]
            else:
                miner_line = None

            all_attack_options = True
            for i in valid_actions:
                if self.possible_actions[i][0] != 'Attack':
                    all_attack_options = False
            # If all the options are attack then the miner is defending itself. Leave this beahviour in place
            if not all_attack_options:
                # Otherwise the worker is free for us to move
                succ, offset, behaviour = get_worker_movement(self.worker_lines, miner_line, my_unit['resources'], (my_unit['x'],my_unit['y']), self.map_width, self.map_height, list(self.blocked_cells), self.bljps, self.base_locs)
                
                if not succ: #miner_line is None and 
                    automated_worker_flag = False # If our worker with resources and no path to a base then put them on non miner behaviour
                
                if behaviour == 'Harvest':
                    valid_actions2 = valid_actions
                    valid_actions = []
                    for i in valid_actions2:
                        if self.possible_actions[i][0] == 'Harvest':
                            valid_actions.append(i)

                if behaviour == 'Return':
                    valid_actions2 = valid_actions
                    valid_actions = []
                    for i in valid_actions2:
                        if self.possible_actions[i][0] == 'Return':
                            valid_actions.append(i) 
                
                if behaviour == 'Move':
                    valid_actions2 = valid_actions
                    valid_actions = []
                    for i in valid_actions2:
                        if self.possible_actions[i][0] == 'Move' and self.get_dir(self.possible_actions[i][1])[:2] == offset:
                            valid_actions.append(i) 

                # If we can do the allocated action just wait
                if len(valid_actions) == 0:              
                    valid_actions.append(0)  
        if my_unit['type'] == 'Base':
            if self.created_worker_count >= self.assist_workers:
                valid_actions = [0]
            else:
                del valid_actions[0]
                if self.current_worker_count<self.assist_miners: # Make the miners closer to the minerals. Others should spawn away from them
                    move_order = alt_order

                for direction in move_order:
                    valid_actions2 = [x for x in valid_actions if self.possible_actions[x][1] == direction]
                    if len(valid_actions2):
                        break
                valid_actions = valid_actions2
                
        elif my_unit['type'] == 'Barracks':
            del valid_actions[0]
            for direction in move_order:
                dx,dy, _ = self.get_dir(direction)
                if (dx+my_unit['x'],dy+my_unit['y']) not in self.worker_line_locs: # Avoid over crowding mining routes
                    valid_actions2 = [x for x in valid_actions if self.possible_actions[x][1] == direction]
                    if len(valid_actions2):
                        break
                else:
                    valid_actions2 = []
            valid_actions = valid_actions2

            if len(valid_actions) == 0:
                valid_actions = [0]
            else:
                if self.roster:
                    roster_unit = self.roster_map[self.roster[self.roster_id]]
                    # print (self.roster_id, roster_unit,self.roster)
                    valid_actions = [x for x in valid_actions if self.possible_actions[x][2] == roster_unit]
                    

        elif not automated_worker_flag:
            if my_unit['type'] == 'Worker' and self.num_barracks < self.assist_barracks and barracks_option in valid_actions:
                valid_actions = [barracks_option]
                # Make barracks
            else:
                new_val = []
                # If in attack range of anything go with that
                for i in valid_actions:
                    if self.possible_actions[i][0] == 'Attack':
                        new_val = [i]
                # If not in attack range move closer
                if not new_val:
                    best_p = []
                    for e in enemies.values():
                        if e['type'] != 'Base' and e['type'] != 'Barracks':
                            s = time.time()
                            p = get_path((my_unit['x'],my_unit['y']), (e['x'],e['y']), self.map_width, self.map_height, self.blocked_cells, self.bljps)

                            if p and (len(p)<len(best_p) or not best_p):
                                best_p = p
                            if my_unit['type'] == 'Ranged' and not p:
                                for dx,dy in ((-3,0),(3,0),(0,-3),(0,3),(1,-2),(2,-1)):
                                    if (e['x']+dx,e['y']+dy) not in self.blocked_cells:
                                        p = get_path((my_unit['x'],my_unit['y']), (e['x']+dx,e['y']+dy), self.map_width, self.map_height, self.blocked_cells, self.bljps)
                                        if p:
                                            if (len(p)<len(best_p) or not best_p):
                                                best_p = p
                                            break

                                ranged_locs = [x for dx in ()]

                            self.current_time_log['attack_closest'] += time.time() - s

                    if best_p:
                        # if (len(best_p)<=3 and random.random()>0.5) or len(best_p)>3:
                            offset = best_p[1][0]-my_unit['x'], best_p[1][1]-my_unit['y']
                            for i in valid_actions:
                                if self.possible_actions[i][0] == 'Move' and self.get_dir(self.possible_actions[i][1])[:2] == offset:
                                    new_val.append(i) 
                # If not in attack range move closer
                if not new_val:
                    best_p = []
                    for e in enemies.values():
                        if e['type'] == 'Base' or e['type'] == 'Barracks':
                            s = time.time()
                            p = get_path((my_unit['x'],my_unit['y']), (e['x'],e['y']), self.map_width, self.map_height, self.blocked_cells, self.bljps)
                            self.current_time_log['attack_closest'] += time.time() - s
                            
                            if p and (len(p)<len(best_p) or not best_p):
                                best_p = p
                            if my_unit['type'] == 'Ranged' and not p:
                                for dx,dy in ((-3,0),(3,0),(0,-3),(0,3),(1,-2),(2,-1)):
                                    if (e['x']+dx,e['y']+dy) not in self.blocked_cells:
                                        p = get_path((my_unit['x'],my_unit['y']), (e['x']+dx,e['y']+dy), self.map_width, self.map_height, self.blocked_cells, self.bljps)
                                        if p:
                                            if (len(p)<len(best_p) or not best_p):
                                                best_p = p
                                            break


                    if best_p:
                        offset = best_p[1][0]-my_unit['x'], best_p[1][1]-my_unit['y']
                        for i in valid_actions:
                            if self.possible_actions[i][0] == 'Move' and self.get_dir(self.possible_actions[i][1])[:2] == offset:
                                new_val.append(i) 


                # move out of the way of miners
                if not new_val and (my_unit['x'], my_unit['y']) in self.worker_line_locs:
                    for i in valid_actions:
                        if self.possible_actions[i][0] == 'Move':
                            new_val.append(i)
                    
                valid_actions = new_val
                if len(valid_actions) == 0:              
                    valid_actions.append(0) 

        if len(valid_actions) == 0:              
            valid_actions.append(0) 

        if len(valid_actions) == 1:
            action_index = valid_actions[0]
        else:
            action_index = random.choice(valid_actions)

        action = self.possible_actions[action_index]
        return self.fill_action(my_unit, enemies, action, start_turn_actions), action, action_index
        
    def extract_resources(self, game_state):
        resources = {}
        for unit in game_state['pgs']['units']:
            if unit['player'] == -1: # resource
                resources[(unit['x'],unit['y'])]=unit['resources']
        return resources

    def get_unit_cost(self, unit_str):
        return self.unit_meta_data[unit_str]['cost']

    def calc_available_funds(self, my_units, start_turn_actions, player_money):
        self.player_funds = player_money[self.player_id]

        for unit_action in start_turn_actions:
            # if unit_id in start_turn_actions:
            if unit_action['ID'] in my_units:
                a_type = unit_action['action']['type']
                if a_type != 4:
                    continue # ignore all actions other than production
                self.player_funds -= self.get_unit_cost(unit_action['action']['unitType'])

    def block_cell(self, x, y):
        if x >= self.map_width:
            a = 1
        self.blocked_cells[x, y] = 1

    def block_in_progress_actions(self, my_units, en_units, start_turn_actions, resource_locs):
        for allie in my_units.values():
            self.block_cell(allie['x'], allie['y'])
        for enemy in en_units.values():
            self.block_cell(enemy['x'], enemy['y'])
        for x,y in resource_locs:
            self.block_cell(x, y)
        
        for unit_action in start_turn_actions:
            a_type = unit_action['action']['type']
            if a_type == 4 or a_type == 1: # production or move commands
                dx, dy = self.get_dir2(unit_action['action']['parameter'])
                unit_id = unit_action['ID']
                if unit_action['ID'] in my_units:
                    self.block_cell(my_units[unit_id]['x']+dx, my_units[unit_id]['y']+dy)
                else:
                    self.block_cell(en_units[unit_id]['x']+dx, en_units[unit_id]['y']+dy)

    def forward(self, current_state_json, my_player_id):
        start_frame = time.time()
        self.current_time_log = {}
        self.current_time_log['attack_closest'] = 0
        self.current_time_log['miner_movement'] = 0

        self.player_id = my_player_id
        self.enemy_id = 1 - my_player_id 
        self.cycle = current_state_json['time']
        self.set_terrain(current_state_json['pgs']['width'],current_state_json['pgs']['height'],current_state_json['pgs']['terrain'], current_state_json['pgs'])
        
        self.turn_actions = []

        self.blocked_cells = {}
        start_turn_actions = current_state_json['actions']
        self.in_progress = {x['ID']:x for x in start_turn_actions}

        players_money = current_state_json['pgs']['players'][0]['resources'], current_state_json['pgs']['players'][1]['resources']
        my_units = {x['ID']:x for x in current_state_json['pgs']['units'] if x['player'] ==  self.player_id}
        en_units = {x['ID']:x for x in current_state_json['pgs']['units'] if x['player'] ==  self.enemy_id}

        resource_locs = self.extract_resources(current_state_json)
        # my_units: Dict[_t, ExtendedUnit] = self.filter_units(self.my_id, observation)
        # en_units: Dict[int, ExtendedUnit] = self.filter_units(self.enemy_id, observation)


        # keep track of all the unit ids for both players
        # so we can use in the reward section of number of units killed
        self.base_locs = []
        struct_locs = []
        my_workers = []

        for map_index in self.terrain_walls:
            y = int(map_index / self.map_width)
            x = map_index % self.map_width
            self.block_cell(x,y)
            struct_locs.append((x,y))

        for x,y in resource_locs:
            self.block_cell(x,y)

        self.num_barracks= 0
        for unit in my_units:

            if my_units[unit]['type'] == 'Base':
                self.base_locs.append((my_units[unit]['x'],my_units[unit]['y']))
                struct_locs.append((my_units[unit]['x'],my_units[unit]['y']))
                self.block_cell(my_units[unit]['x'],my_units[unit]['y'])

            if my_units[unit]['type'] == 'Barracks':
                struct_locs.append((my_units[unit]['x'],my_units[unit]['y']))
                self.block_cell(my_units[unit]['x'],my_units[unit]['y'])

                self.num_barracks += 1
            if my_units[unit]['type'] == 'Worker':
                self.all_game_worker_ids.add(unit)
                my_workers.append(unit)

        if self.cycle == 0:
            self.created_worker_count = len(self.all_game_worker_ids)

        self.end_game_assist = players_money[1] == 0
        for unit in en_units:
            if en_units[unit]['type'] == 'Base' or en_units[unit]['type'] == 'Barracks':
                struct_locs.append((en_units[unit]['x'],en_units[unit]['y']))
                self.block_cell(en_units[unit]['x'],en_units[unit]['y'])
            else:
                self.end_game_assist = False

        for action in start_turn_actions:
            if action['ID'] in my_units and 'unitType' in action['action'] and action['action']['unitType'] == 'Barracks':
                self.num_barracks += 1
 

        # If we fail to build mining routes just have the AI idle
        # If the number of resources or bases has changed
        if len(resource_locs) != self.prev_cycle_resource_locs or self.prev_cycle_base_locs != len(self.base_locs):
            # Check that the base or mineral that changes was one we were using
            # Otherwise ignore the change
            if requires_rerouting(list(resource_locs), self.base_locs, struct_locs, self.map_width, self.map_height,  self.worker_lines): 

                self.miner_line_count = self.assist_miners

                self.miner_mapping = {}
                self.worker_lines = None
                if len(self.base_locs)>0 and len(resource_locs) >0:
                    start_routing = time.time()
                    self.build_mining_routes(list(resource_locs), self.base_locs, struct_locs)
                    self.current_time_log['routing_time'] = time.time() - start_routing
                    self.worker_line_locs = set()
                    if self.worker_lines is not None:
                        for line in self.worker_lines:
                            for p in line[3]:
                                self.worker_line_locs.add(p)
                 
        # When an allocated miner dies remove it from the mapping so we can reallocate
        previous_miner_allocation = list(self.miner_mapping)
        for prev_miner in previous_miner_allocation:
            if prev_miner not in my_workers:
                del self.miner_mapping[prev_miner]
        
        # If we still need to add workers to become auto miners then assign them
        if self.worker_lines is not None and len(self.worker_lines) != len(self.miner_mapping):
            s = time.time()
            my_workers = [x for x in my_units.values() if x['type']=='Worker']
            allocate_miners(self.worker_lines, my_workers, self.map_width, self.map_height, self.blocked_cells, self.miner_mapping, self.bljps)
            self.current_time_log['miner_movement'] = time.time() - s

        self.prev_cycle_resource_locs = len(resource_locs)
        self.prev_cycle_base_locs = len(self.base_locs)

        self.calc_available_funds(my_units, start_turn_actions, players_money)
        self.block_in_progress_actions(my_units, en_units, start_turn_actions, resource_locs)
           
        self.current_worker_count = len(my_workers)

        self.max_miners = max(self.max_miners, len(self.miner_mapping))
        self.max_workers = max(self.current_worker_count, self.max_workers)
        self.max_barracks = max(self.num_barracks, self.max_barracks)

        all_actions = []
        this_cycle_actions = []
        for unit in my_units.values():
            if unit['ID'] in self.in_progress:
                continue
            else:
                replay_action = None
                new_action, action_desc, action_id = self.get_action(unit, my_units, en_units, resource_locs, start_turn_actions, players_money, replay_action, this_cycle_actions)
                if action_desc[0] == 'Move' or action_desc[0] == 'Produce':
                    dx, dy, dir_param = self.get_dir(action_desc[1])
                    if (unit['x']+dx,unit['y']+dy) in self.blocked_cells:
                        print ('Error cannot make units use the same grid location')
                    self.block_cell(unit['x']+dx,unit['y']+dy)

                    if action_desc[0] == 'Produce':
                        self.player_funds -= self.get_unit_cost(action_desc[2])


                        if action_desc[2] == 'Barracks':
                            self.num_barracks += 1
                        if action_desc[2] == 'Worker':
                            self.current_worker_count += 1
                            self.created_worker_count += 1 # Temporary increase. Set permanently when the unit spawns
                        if self.roster and (action_desc[2] == 'Light' or action_desc[2] == 'Ranged' or action_desc[2] == 'Heavy'):
                            self.roster_id = (self.roster_id+1) % len(self.roster)

                this_cycle_actions.append((unit['ID'],action_id))
                all_actions.append(new_action)
                self.in_progress[unit['ID']] = new_action
                self.turn_actions.append(action_id)
        
        frame_time = time.time() - start_frame
        self.current_time_log['forward_total'] = frame_time
        if self.current_time_log['forward_total'] > 0.07:
            print (self.current_time_log)
        return all_actions

    def backward(self, winner_id):    
        self.episode_num += 1
        if winner_id==self.player_id:
            result = 'win'
        elif winner_id==self.enemy_id:
            result = 'loss'
        else:
            result = 'draw'

        # print (result,'map_name:',self.map_filename,'My_ID',self.player_id,'winner_id',winner_id,'cycle',self.cycle)
        # print ('miners',self.assist_miners,'barracks',self.assist_barracks,'workers:',self.assist_workers,'roster', self.roster)    


        # Only if we are in self learning of the pre analysis of the game can we learn (I think this is the way the competition wants to run?)
        if self.pre_game_analysis_shared_memory['sharing_enabled']:
            # config = self.assist_miners, self.assist_barracks, self.assist_workers, ()
            # self.pre_game_analysis_shared_memory['configs'].submit_config_score(config, winner_id==self.player_id, winner_id==-1, winner_id==self.enemy_id)
            # if self.roster:
                # if the config had originally specced more than needed than remove extra elements
                # This should condense the data by transforming unreachable configs into commonly hit configs
                self.assist_workers-=self.assist_miners
                config = self.assist_miners, self.assist_barracks, self.assist_workers, self.roster
                # if self.dominant_agent:
                #     print (config)
                self.pre_game_analysis_shared_memory[('configs',self.pgs_str)].submit_config_score(config, winner_id==self.player_id, winner_id==-1, winner_id==self.enemy_id)
                
                if self.max_miners<5:
                    self.assist_miners = self.max_miners
                self.assist_barracks = self.max_barracks
                if self.max_workers<5:
                    self.assist_workers = self.max_workers

                if self.assist_workers>200 :# hack for some bug where it goes to 400 for some reason
                    self.assist_workers = 200
                if self.assist_barracks == 0:
                    self.roster = ()  # If we never had any barracks they remove the roster it had no impact

                config = self.assist_miners, self.assist_barracks, self.assist_workers, self.roster
                
                # if self.dominant_agent:
                    # print (config)
                self.pre_game_analysis_shared_memory[('configs',self.pgs_str)].submit_config_score(config, winner_id==self.player_id, winner_id==-1, winner_id==self.enemy_id)
        # self.max_miners = max(self.max_miners, self.miner_mapping)
        # self.max_workers = max(self.current_worker_count, self.max_workers)
        # self.max_barracks = max(self.num_barracks, self.max_barracks)


    def reset(self):
        # random.seed(self.episode_num)


        self.config_name = None
        self.player_id = None
        self.enemy_id = None
        self.agent_log_directory = None
        self.map_filename = None
        self.terrain = None
        self.terrain_walls = None
        self.map_width = None
        self.map_height = None
      
        self.created_worker_count = 0
        self.all_game_worker_ids = set()

        self.prev_cycle_resource_locs = 0
        self.prev_cycle_base_locs = 0

        self.worker_lines = None
        self.miner_mapping = {} #  Used to map which worker is going to which line

        self.cycle = 0
        self.blocked_cells = {}
        self.in_progress = {} # Keeps track of units who are in the middle of an action
        self.roster_id = 0
        self.max_miners = 0
        self.max_workers = 0
        self.max_barracks = 0
        self.worker_line_locs = set() # Keeps track of locations the miners are using. Try to avoid them
