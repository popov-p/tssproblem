import numpy as np
import pygad
import utils
import subprocess
import xml.etree.ElementTree as ET
import sys
import time
import os 
import csv
import multiprocessing as mp
#genetic utils 
data = [] #ch-iter-time storage
rounded_times = [] #rounded-times-storage for .md table log

fitness_counter = mp.Value('i', 0)
lock = mp.Lock()

def set_gene_space(xml_file): #function to define boundaries for genes in chromosome
    gene_space = []

    tree = ET.parse(xml_file)
    root = tree.getroot()

    for tl_logic in root.findall(".//tlLogic"):
        for phase in tl_logic.findall("phase"):
            if "y" not in phase.attrib["state"]: #if current light phase is not yellow - optimize it 
                gene_space.append({'low': 20, 'high': 70})
    return gene_space
#-------------
def on_generation(ga_instance, **kwargs):
    times = kwargs.get('times')
    prev_generation_time = times[-1]
    cur_generation_time = time.time()
    times.append(cur_generation_time) #current generation time logging
    best_solution, best_fitness_value, best_solution_idx = ga_instance.best_solution(ga_instance.last_generation_fitness)
    data.append((abs(best_fitness_value), ga_instance.generations_completed, round(cur_generation_time-prev_generation_time, 2)))
    rounded_times.append(round(cur_generation_time-prev_generation_time, 2))
#end utils

def fitness_func(ga_instance, solution, solution_idx, **kwargs): #specific argument order for genetic algorithm
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
        #'-e', utils.last_simulation_step,
        '--default.carfollowmodel', utils.default_carfollowmodel,
        '--collision.mingap-factor', utils.collision_mingap_factor
    ]

    #----------------------
    start_time = time.time()
    fitness_value = None
    process = subprocess.Popen(command)
    with lock:
        fitness_counter.value += 1
    while True:
        return_code = process.poll()
        if return_code is not None:
            fitness_value = utils.get_total_waiting_time(output_file)
            subprocess.run(['rm', additional_file, output_file, updated_sumocfg])
            break
        if time.time() - start_time > 5:
            process.terminate()
            fitness_value = 1e6
            subprocess.run(['rm', additional_file, output_file, updated_sumocfg])
            print("COMPUTATIONAL TIME EXCEEDED. EXITING...")
            break
        time.sleep(1)
    process.wait()
    return -fitness_value


def main(argv):
    if len(argv) != 1:
        print('Usage: python gen.py <simulation-folder-name (for example: "medium")>')
        sys.exit(1)
    else:
        simulation_name = 'commercial' #argv[1] 
        gene_type = int
        gene_space = set_gene_space(utils.net_dict.get(simulation_name))
        generation_times = [time.time(), ]
        num_generations = 400
        ff_wrapper = lambda ga_instance, solution, solution_idx: fitness_func(ga_instance, 
                                                                              solution, 
                                                                              solution_idx, 
                                                                              net_file=utils.net_dict.get(simulation_name), 
                                                                              folder_name = simulation_name,
                                                                              sumocfg_file = utils.sumocfg_dict.get(simulation_name))
        
        og_wrapper = lambda ga_instance: on_generation(ga_instance,
                                                       folder_name=simulation_name,
                                                       times=generation_times)
        ga_instance = pygad.GA(num_generations=num_generations,
                                num_parents_mating=24, 
                                fitness_func=ff_wrapper,
                                sol_per_pop=48,
                                num_genes=len(gene_space),
                                gene_space=gene_space,
                                gene_type=gene_type,
                                parallel_processing=15,
                                save_best_solutions=True,
                                on_generation=og_wrapper
                                )
        ga_instance.run()
    
    #results-dump
    current_dir = os.getcwd()
    table = f"{current_dir}/{simulation_name}/results/results.csv"

    best_sol, best_sol_fit, best_match_idx = ga_instance.best_solution()
    header = ['alg-name','map-name', 'xbest', 'fbest', 'iter-count', 'evals-all', 'sum-time', 'avg-iter-time']
    with open(table, 'a', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(header)
            csv_writer.writerow(('gen', simulation_name, best_sol,
                                  abs(best_sol_fit), num_generations, fitness_counter.value -1,
                                  np.round(sum(rounded_times), decimals=2),
                                  np.round(np.mean(rounded_times), decimals=2)))



    res_path = f"{current_dir}/{simulation_name}/results/ch_iter_time_gen.csv"
    if os.path.exists(res_path):
        subprocess.run(['rm', res_path])
    for row in data:
        utils.dump_data(res_path, row)
    #------------
if __name__ == "__main__":
    main(sys.argv)