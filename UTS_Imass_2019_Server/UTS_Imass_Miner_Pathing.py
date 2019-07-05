import heapq
import time

def get_resource_mining_locs(matrix, locs, map_width, map_height):
    resource_mining_locs = set()
    for x,y in locs:
        for ox,oy in [(-1,0), (1,0),(0,1),(0,-1)]:
            nx,ny = x+ox, y+oy
            if nx >= 0 and ny >= 0 and nx < map_width and ny < map_height and matrix[ny*map_width + nx] == 0:
                resource_mining_locs.add((nx,ny))
    return resource_mining_locs

# Worker line return is
# True/False if possible to find all lines
# List of workerId Lines
# each line is : (distance to travel, mining loc, return loc, path from mining to return)

def uncompress_bljps_path(path):
    if not path:
        return []

    uncompressed_path = []
    uncompressed_path.append((path[0][0],path[0][1]))

    for p_id in range(len(path)-1):
        current_p = [path[p_id][0],path[p_id][1]]

        while current_p[0] != path[p_id+1][0] or current_p[1] != path[p_id+1][1]:
            if path[p_id+1][0] != current_p[0]:
                if path[p_id+1][0] > current_p[0]:
                    current_p[0] += 1
                else:
                    current_p[0] -= 1
                uncompressed_path.append(tuple(current_p))
            if path[p_id+1][1] != current_p[1]:
                if path[p_id+1][1] > current_p[1]:
                    current_p[1] += 1
                else:
                    current_p[1] -= 1
                uncompressed_path.append(tuple(current_p))
    return uncompressed_path

def requires_rerouting(resource_locs, base_locs, struct_locs, map_width, map_height, previous_lines):
    if previous_lines is None:
        return True
    matrix = [0]*(map_height*map_width)
    for x,y in resource_locs:
        matrix[y*map_width+x] = 1
    for x,y in base_locs:
        matrix[y*map_width+x] = 1
    for x,y in struct_locs:
        matrix[y*map_width+x] = 1

    resource_mining_locs = get_resource_mining_locs(matrix, resource_locs, map_width, map_height)
    return_locs          = get_resource_mining_locs(matrix, base_locs, map_width, map_height)

    for line_data in previous_lines:
        # Check if we can't mine from this location any more
        if line_data[1] not in resource_mining_locs:
            return True
        # Check if we can't return to this location any more
        if line_data[2] not in return_locs:
            return True

    return False





def get_worker_lines(matrix, resource_locs, base_locs, worker_count, bljps, map_width, map_height, strategy, structure_locs):
    s = time.time()

    resource_mining_locs = get_resource_mining_locs(matrix, resource_locs, map_width, map_height)
    return_locs          = get_resource_mining_locs(matrix, base_locs, map_width, map_height)

    succ, new_routes = strategy.get_mining_config(worker_count, return_locs, resource_mining_locs, structure_locs)
    if succ:
        return True, new_routes

    bljps.preProcessGrid(matrix, map_width, map_height)

    possible_routes = []
    for res_mining_loc in resource_mining_locs:
        for return_loc in return_locs:
            if return_loc == res_mining_loc:
                path = [return_loc]
            else:
                path = bljps.findSolution(res_mining_loc[0], res_mining_loc[1], return_loc[0], return_loc[1])
                path = uncompress_bljps_path(path)
            estimated_dist = len(path) - 1
            if estimated_dist >= 0: # a dist of -1 means no path exists
                possible_routes.append((estimated_dist, res_mining_loc, return_loc, path))

    possible_routes.sort()
    if len(possible_routes)< worker_count:
        return False, []

    if worker_count == 1:
        cache_return_locs = (possible_routes[0][2],)
        cache_mining_locs = (possible_routes[0][1],)
        strategy.add_mining_config([possible_routes[0]], cache_return_locs, cache_mining_locs)

        return True, [possible_routes[0]]

    # Now we have to identify the optimal subset of routes
    pqueue = []
    closed_pos = set()
    for x in range(len(possible_routes)):
        heapq.heappush(pqueue, (possible_routes[x][0],[x], set(possible_routes[x][3])))

    result=[]

    while pqueue:
        d, indexes, used_set = heapq.heappop(pqueue)
        if len(indexes) == worker_count:
            # print ('worker lines',worker_count,len(indexes),time.time()-s)
            mining_routes = [possible_routes[x] for x in indexes]

            cache_return_locs = tuple([x[2] for x in mining_routes])
            cache_mining_locs = tuple([x[1] for x in mining_routes])

            strategy.add_mining_config(mining_routes, cache_return_locs, cache_mining_locs)



            return True, mining_routes

        elif len(indexes) > len(result):
            result = [possible_routes[x] for x in indexes]
            
        for i in range(len(possible_routes)): 
            passed = True
            if i in indexes:
                passed = False
            else:
                if used_set.intersection(set(possible_routes[i][3])):
                    passed = False
                    break
            if passed:
                new_indexes = indexes[:]
                new_indexes.append(i)
                if tuple(new_indexes) not in closed_pos:
                    new_union = set(used_set).union(possible_routes[i][3])
                    heapq.heappush(pqueue, (d+possible_routes[i][0], new_indexes, new_union))
                    closed_pos.add(tuple(new_indexes))
    if len(result):


        cache_return_locs = tuple([x[2] for x in result])
        cache_mining_locs = tuple([x[1] for x in result])

        strategy.add_mining_config(result, base_locs, resource_locs)

        return True, result


    return False, []

def get_worker_paths(resource_locs, base_locs, structure_locs, map_width, map_height, worker_count, bljps, strategy):
    # Matrix dictionary
    # 0 is free space
    # 1 is resources
    # 2 is a base structure

    if worker_count == 0 or strategy is None:
        return True, []

    matrix = [0]*(map_height*map_width)
    for x,y in resource_locs:
        matrix[y*map_width+x] = 1

    for x,y in structure_locs:
        matrix[y*map_width+x] = 3

    for x,y in base_locs:
        matrix[y*map_width+x] = 2 

    worker_lines = get_worker_lines(matrix,resource_locs,base_locs, worker_count, bljps, map_width, map_height, strategy, structure_locs)

    return worker_lines


def get_worker_movement(worker_lines, worker_id, worker_has_mineral, worker_loc, map_width, map_height, blocked_cells, bljps, base_locs):
     # rogue miner with a mineral and no mining route
    if worker_id is None:
        matrix = [0]*(map_height*map_width)
        for x,y in blocked_cells:
            matrix[y*map_width+x] = 1
        matrix[worker_loc[1]*map_width+worker_loc[0]] = 0

        return_locs = get_resource_mining_locs(matrix, base_locs, map_width, map_height)
        if worker_loc in return_locs:
            return True, (0,0), 'Return'      
        if len(return_locs) == 0: # no where to return resources to
            return False, (0,0), 'Fail'

        bljps.preProcessGrid(matrix, map_width, map_height)
        possible_routes = []
        for return_loc in return_locs:
            path = bljps.findSolution(worker_loc[0], worker_loc[1], return_loc[0], return_loc[1])
            path = uncompress_bljps_path(path)
            estimated_dist = len(path) - 1
            if estimated_dist >= 0: # a dist of -1 means no path exists
                possible_routes.append((estimated_dist, worker_loc, return_loc, path))

        possible_routes.sort()
        if len(possible_routes) == 0: # no where to return resources to
            return False, (0,0), 'Fail'
        dx = possible_routes[0][3][1][0] - worker_loc[0] 
        dy = possible_routes[0][3][1][1] - worker_loc[1]
        return True, (dx,dy), 'Move'      


    if worker_id >= len(worker_lines):
        return False, (0,0), 'Fail'

    if worker_has_mineral and worker_lines[worker_id][3][-1] == worker_loc: # Return the mineral
        return True, (0,0), 'Return'

    if not worker_has_mineral and worker_lines[worker_id][3][0] == worker_loc: # Gather the mineral
        return True, (0,0), 'Harvest'       

    # Worker is on the line
    if worker_loc in worker_lines[worker_id][3]:
        path_index = worker_lines[worker_id][3].index(worker_loc)
        if worker_has_mineral:
            dx = worker_lines[worker_id][3][path_index+1][0] - worker_lines[worker_id][3][path_index][0] 
            dy = worker_lines[worker_id][3][path_index+1][1] - worker_lines[worker_id][3][path_index][1] 
        else:
            dx = worker_lines[worker_id][3][path_index-1][0] - worker_lines[worker_id][3][path_index][0] 
            dy = worker_lines[worker_id][3][path_index-1][1] - worker_lines[worker_id][3][path_index][1]
        return True, (dx,dy), 'Move'      
    else:

        matrix = [0]*(map_height*map_width)
        for x,y in blocked_cells:
            matrix[y*map_width+x] = 1

        origin = worker_loc
        if worker_has_mineral:
            dest = worker_lines[worker_id][3][-1]
        else:
            dest = worker_lines[worker_id][3][0]

        matrix[origin[1]*map_width+origin[0]] = 0
        bljps.preProcessGrid(matrix, map_width, map_height)
        path = bljps.findSolution(origin[0], origin[1], dest[0], dest[1])
        path = uncompress_bljps_path(path)

        if len(path)==0:
            return False, (0,0), 'Fail'
        return True, (path[1][0] - worker_loc[0], path[1][1] - worker_loc[1]), 'Move'


def get_path(origin, dest, map_width, map_height, blocked_cells, bljps):
    if not (dest[0]>=0 and dest[0] < map_width and dest[1]>=0 and dest[1] < map_height):
        return [] # Dest out of bounds
    matrix = [0]*(map_height*map_width)
    for x,y in blocked_cells:
        matrix[y*map_width+x] = 1

    # Make sure the origin and destination cells are clear to path
    matrix[dest[1]*map_width+dest[0]] = 0
    matrix[origin[1]*map_width+origin[0]] = 0
    bljps.preProcessGrid(matrix, map_width, map_height)
    path = bljps.findSolution(origin[0], origin[1], dest[0], dest[1])
    path = uncompress_bljps_path(path)

    return path


def allocate_miners(worker_lines, worker_units, map_width, map_height, blocked_cells, miner_mapping, bljps):
    available_lines = list(range(len(worker_lines)))
    mapping_vals = list(miner_mapping.values())
    mapping_vals.sort(reverse=True)
    # Find the lines available for allocation
    for i in mapping_vals:
        del available_lines[i]
        
    available_workers = [x for x in worker_units if x['ID'] not in miner_mapping]

    matrix = [0]*(map_height*map_width)
    for x,y in blocked_cells:
        matrix[y*map_width+x] = 1
    bljps.preProcessGrid(matrix, map_width, map_height)

    # Get the distance of each worker to each line
    dist_maxtrix = []
    for current_worker in available_workers:
        if current_worker['ID'] not in miner_mapping:
            worker_loc = current_worker['x'], current_worker['y']
            for line_id in available_lines:
                dst = worker_lines[line_id][1] # Gather point
                if current_worker['resources']:
                    dst = worker_lines[line_id][2] # Return point
                if worker_loc == dst:
                    path = [worker_loc]
                else:
                    path = bljps.findSolution(worker_loc[0], worker_loc[1], dst[0], dst[1])
                    path = uncompress_bljps_path(path)
                
                if len(path):
                    dist_maxtrix.append((len(path), current_worker['ID'], line_id))
    
    dist_maxtrix.sort()
    used_workers = set()
    used_lines = set()

    # Assign the workers by minimal distance pairings
    for dist, worker_id, line_id in dist_maxtrix:
        if line_id not in used_lines and worker_id not in used_workers:
            miner_mapping[worker_id] = line_id
            used_lines.add(line_id)
            used_workers.add(worker_id)
    