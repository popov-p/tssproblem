import numpy as np
import pyswarms as ps
import utils
import subprocess
from concurrent.futures import ProcessPoolExecutor
import xml.etree.ElementTree as ET
import sys
from functools import partial
import time
import pdb
import os
import csv
import multiprocessing as mp
#pso utils
fitness_counter = mp.Value('i', 0)
lock = mp.Lock()


def create_bounds(xml_file):
    lower_bounds = []
    upper_bounds = []

    tree = ET.parse(xml_file)
    root = tree.getroot()

    for tl_logic in root.findall(".//tlLogic"):
        for phase in tl_logic.findall("phase"):
            if "y" not in phase.attrib["state"]:
                lower_bounds.extend([30])
                upper_bounds.extend([60])

    return np.array(lower_bounds), np.array(upper_bounds)

#end utils

def evaluate_particle(particle, **kwargs):
    iter_id = utils.generate_id()
    output_file = f"/mnt/tss-inter-logs/{kwargs.get('folder_name')}/statistic_output_{iter_id}.xml"
    additional_file = f"/mnt/tss-inter-logs/{kwargs.get('folder_name')}/tl_logic_{iter_id}.xml"
    utils.create_new_logic(net_input=kwargs.get('net_file'), additional_output=additional_file, solution=np.round(particle))
    
    new_additional_files = f"{os.path.abspath('commercial/dfrouter/routes.rou.xml')}, {os.path.abspath('commercial/dfrouter/vehicles.rou.xml')}, " + additional_file 
    updated_sumocfg = f"/mnt/tss-inter-logs/{kwargs.get('folder_name')}/osm_{iter_id}.sumocfg"
    utils.update_additional_files(kwargs.get('sumocfg_file'),utils.net_dict.get('commercial'),new_additional_files, updated_sumocfg)
    command = [utils.sumo_executable,
        '-c', updated_sumocfg,
        '--statistic-output', output_file,
        '--time-to-teleport', utils.time_to_teleport,
        '--no-warnings', 't',
        '--no-step-log', 't',
        '--quit-on-end', 't',
        #'-e', utils.last_simulation_step,
        '--default.carfollowmodel', utils.default_carfollowmodel,
        '--collision.mingap-factor', utils.collision_mingap_factor
    ]


    process = subprocess.Popen(command)
    with lock:
        fitness_counter.value += 1
    process.wait()
    fitness_value = utils.get_total_waiting_time(output_file)
    subprocess.run(['rm', additional_file, output_file])
    return fitness_value

def fitness_func(swarm, **kwargs):
    times = kwargs.get('times')
    partial_evaluate_particle = partial(evaluate_particle, **kwargs)
    with ProcessPoolExecutor(14) as executor:
        fitness_values = list(executor.map(partial_evaluate_particle, swarm))
    cur_swarm_time = time.time()
    times.append(cur_swarm_time) #current swarm time logging 
    return np.array(fitness_values)

def main(argv):
    if len(argv) != 1:
        print('Usage: python gen.py <simulation-folder-name (for example: "medium")>') #rework this 
        sys.exit(1)
    else:
        simulation_name = 'commercial' #argv[1]
        swarm_times = [time.time(), ]
        lower_bounds, upper_bounds = create_bounds(utils.net_dict.get(simulation_name))
        num_variables = len(lower_bounds)
        options = {'c1': 2.05, 'c2': 2.05, 'w': 0.72984} #global-best-pso 
        iters = 300
        optimizer = ps.single.GlobalBestPSO(n_particles=30, dimensions=num_variables, options=options, oh_strategy={ "w":'exp_decay', "c1":'nonlin_mod',"c2":'lin_variation'}, bounds=(lower_bounds, upper_bounds))
        ff_wrapper = lambda swarm: fitness_func(swarm=swarm, 
                                                net_file=utils.net_dict.get(simulation_name), 
                                                folder_name=simulation_name,
                                                sumocfg_file=utils.sumocfg_dict.get(simulation_name),
                                                times=swarm_times)
        best_cost, best_position = optimizer.optimize(ff_wrapper, iters=iters, verbose=False)
    rounded_times = [round(cur - prev, 2) for prev, cur in zip(swarm_times, swarm_times[1:])]
    data = zip(optimizer.cost_history, range(1, len(optimizer.cost_history) + 1), rounded_times)
    #results-dump
    current_dir = os.getcwd()
    table = f"{current_dir}/{simulation_name}/results/results.csv"

    with open(table, 'a', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(('pso', np.round(best_position),
                                  best_cost, iters, fitness_counter.value,
                                  np.round(sum(rounded_times), decimals=2),
                                  np.round(np.mean(rounded_times), decimals=2)))

    subprocess.run(['rm', 'report.log']) #delete default log file
    current_dir = os.getcwd()
    res_path = f"{current_dir}/{simulation_name}/results/ch_iter_time_pso.csv"
    if os.path.exists(res_path):
        subprocess.run(['rm', res_path])
    for row in data:
        utils.dump_data(res_path, row)
    #------------
if __name__ == "__main__":
    main(sys.argv)