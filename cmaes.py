import cma
import numpy as np
import utils
import subprocess
from concurrent.futures import ProcessPoolExecutor
import xml.etree.ElementTree as ET
import sys
from functools import partial
import time
import os
import csv
#cmaes utils

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

    bounds_dict = {'bounds': [lower_bounds, upper_bounds]}
    return bounds_dict

#end utils

def fitness_func(solution, **kwargs):
    iter_id = utils.generate_id()
    output_file = f"/mnt/tss-inter-logs/{kwargs.get('folder_name')}/statistic_output_{iter_id}.xml"
    additional_file = f"/mnt/tss-inter-logs/{kwargs.get('folder_name')}/tl_logic_{iter_id}.xml"
    utils.create_new_logic(net_input=kwargs.get('net_file'), additional_output=additional_file, solution=np.round(solution))
    
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
        '-e', utils.last_simulation_step,
        '--default.carfollowmodel', utils.default_carfollowmodel,
        '--collision.mingap-factor', utils.collision_mingap_factor,
    ]

    process = subprocess.Popen(command)
    process.wait()
    fitness_value = utils.get_total_waiting_time(output_file)
    subprocess.run(['rm', additional_file, output_file])
    return fitness_value

def main(argv):
    if len(argv) != 1:
        print('Usage: python gen.py <simulation-folder-name (for example: "medium")>')
        sys.exit(1)
    else:
        simulation_name = 'commercial' #argv[1]
        #parameters preparation
        opts = create_bounds(xml_file=utils.net_dict.get(simulation_name))
        dimension = len(opts.get('bounds')[1])

        opts['AdaptSigma'] = cma.sigma_adaptation.CMAAdaptSigmaTPA
        x0 = np.random.uniform(low=opts.get('bounds')[0], high=opts.get('bounds')[1], size=dimension)
        sigma = 5
        #----------------------
        es = cma.CMAEvolutionStrategy(x0, sigma, opts)
        iter_count = 80
        ff_partial = partial(fitness_func,
                             net_file=utils.net_dict.get(simulation_name),
                             folder_name=simulation_name,
                             sumocfg_file=utils.sumocfg_dict.get(simulation_name))
        #plotting parameters preparation
        iter_times = [time.time(),]
        cost_history = []
        #-------------------------------
        with ProcessPoolExecutor(6) as executor:
            for _ in range(iter_count):
                solutions = es.ask()
                fitness_values = list(executor.map(ff_partial, solutions))
                es.tell(solutions, fitness_values)
                iter_times.append(time.time()) #iteration time logging
                cost_history.append(es.result.fbest) #current best fitness value
        rounded_times = [round(cur - prev, 2) for prev, cur in zip(iter_times, iter_times[1:])]
        data = zip(cost_history, range(1, len(cost_history) + 1), rounded_times)
        #results-dump
        current_dir = os.getcwd()
        table = f"{current_dir}/{simulation_name}/results/results.csv"
        
        #header = ['name', 'xbest', 'fbest', 'iter-count', 'evals-all', 'sum-time', 'avg-iter-time']
        with open(table, 'a', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(('cmaes', simulation_name, np.round(es.result.xbest),
                                  es.result.fbest, iter_count, es.best.evalsall,
                                  np.round(sum(rounded_times), decimals=2),
                                  np.round(np.mean(rounded_times), decimals=2)))
        
        res_path = f"{current_dir}/{simulation_name}/results/ch_iter_time_cmaes.csv"
        if os.path.exists(res_path):
            subprocess.run(['rm', res_path])
        for row in data:
            utils.dump_data(res_path, row)
        #------------                  
if __name__ == "__main__":
    main(sys.argv)