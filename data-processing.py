import argparse
import os
import pandas as pd
import matplotlib.pyplot as plt
import re
import csv
import numpy as np
from itertools import zip_longest
from datetime import datetime, timedelta

parser = argparse.ArgumentParser(description='Process traffic demand')
parser.add_argument('-d', type=str, default='datasets/current', help='path to directory with .xlsx data')
parser.add_argument('-o', type=str, default='datasets/processed', help='path to processed sorted .xlsx output')
parser.add_argument('-p', type=str, default='datasets/plot-data', help='path to xlsx plot tables')
parser.add_argument('-dfr', type=str, default='datasets/dfrouter-data', help='path to dfrouter data csv')
args = parser.parse_args()

pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None) 

start_time = datetime.strptime('06:00', '%H:%M')
end_time = datetime.strptime('09:00', '%H:%M')
step_minutes = 5

times = []

current_time = start_time
while current_time <= end_time:
    times.append(current_time.strftime('%H:%M'))
    current_time += timedelta(minutes=step_minutes)

times_dfr = [t for t in range(0, 181, 5)]

weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday']
weekends = ['Saturday', 'Sunday']

def process_xlsx(file_path):
    df = pd.read_excel(file_path)
    df = df[['Speed','Volume', 'Number', 'Time']]
    df['Time'] = pd.to_datetime(df['Time'])
    df.fillna({'Volume': 0, 'Speed': 0}, inplace=True)
    return df

def save_processed(df, filename):
    processed_dir = args.o
    os.makedirs(processed_dir, exist_ok=True)
    filepath = os.path.join(processed_dir, filename)
    df.to_excel(filepath, index=False)

def save_processed_mean(ts, filename):
    plot_dir = args.p
    os.makedirs(plot_dir, exist_ok=True)
    filepath = os.path.join(plot_dir, filename)
    with open(filepath, 'w') as file:
        for key, value in ts.items():
            file.write(f"{key}: {value}\n")


def filter(df):
    return df[(df['Time'].dt.hour == 6) | 
              ((df['Time'].dt.hour == 9) & ((df['Time'].dt.minute == 0) |
              (df['Time'].dt.minute < 5)) | ((df['Time'].dt.hour > 6) & (df['Time'].dt.hour < 9)))]

def sort_first_n_days(n, cur_df):
    filtered_df = filter(cur_df).sort_values(by=['Number', 'Time'])
    filtered_df['WD'] = filtered_df['Time'].dt.day_name()
    mask = filtered_df['WD'].isin(weekdays)
    filtered_df = filtered_df[mask]
    #print(filtered_df[mask])
    return filtered_df[filtered_df['Time'] < filtered_df['Time'].iloc[0] + pd.Timedelta(days=n)]

def form_mean_stats(first_n_days_data):
    time_stats = {}
    grouped = first_n_days_data.groupby(first_n_days_data['Time'].dt.strftime('%H:%M'))
    for group_name, group_data in grouped:
        avg_volume = group_data['Volume'].sum() / len(group_data['Time'].dt.date.unique())
        time_stats[group_name] = int(avg_volume)
    return time_stats

def extract_number(filename):
    parts = filename.split('_') 
    if len(parts) >= 3:
        number_part = parts[2].split('.')[0]
        return int(number_part) if number_part.isdigit() else None
    return None

def process_for_dfrouter(day, filename, sorted_by_detector_dict):
    for_dfr_dir = args.dfr
    os.makedirs(for_dfr_dir, exist_ok=True)
    map_detector_id = str(extract_number(filename)) # 6581, 900700 etc..
    
    day = day.reset_index(drop=True)

    unique_date = pd.to_datetime(day['Time']).dt.date.unique()[0].strftime('%Y-%m-%d')
    
    detector_ids = ["d_" + map_detector_id + "_" + str(number) for number in day['Number']]
    unique_det_ids = ["d_" + map_detector_id + "_" + str(number) for number in day['Number'].unique()]

    day['Detector'] = detector_ids
    day['Volume'] /= 12
    day = day.rename(columns={'Volume': 'qPKW', 'Speed': 'vPKW'})[['Detector', 'Time', 'qPKW', 'vPKW']]
    #print(day)
    #day = day.iloc[2:]
    #day = day.drop([55,56])
    #print(day)
    #TODO: here validate the time counts and fix dfrouter table creation times
    #VALIDATION PART
    date_time_range = pd.to_datetime(unique_date)
    time_range = pd.date_range(start=date_time_range.replace(hour=6, minute=0, second=0),
                               end=date_time_range.replace(hour=9, minute=0, second=0), freq='5min')
    for det_line_id in unique_det_ids:
        line_df = day[day['Detector'] == det_line_id]
        #print(line_df)
        validator = pd.DataFrame({'Detector': det_line_id,'Time': time_range})
        #print(validator)
        validated_line_df = pd.merge(validator, line_df, on=['Detector', 'Time'], how='left')
        validated_line_df.fillna(0, inplace=True)
        #print(validated_line_df)
        day = pd.concat([day, validated_line_df], ignore_index=True).drop_duplicates().sort_index().sort_values(by=['Detector', 'Time']).reset_index(drop=True)
        #print(day)
    #--------------
    #TIME SETTING PART (to avoid warnings)
    line_dfs = []
    for det_line_id in unique_det_ids:
        line_df = day[day['Detector'] == det_line_id].copy()
        line_df.drop(columns=['Time'], inplace=True)
        line_df.loc[:, 'Time'] = times_dfr
        #print(line_df)
        line_dfs.append(line_df.reindex(columns=['Detector', 'Time', 'qPKW', 'vPKW']))
    day = pd.concat(line_dfs, ignore_index=True)
    #print(day)
    #------------
    if map_detector_id not in sorted_by_detector_dict:
        sorted_by_detector_dict[map_detector_id] = []
    sorted_by_detector_dict[map_detector_id].append(day)

def dfrouter_final(sorted_by_detector_dict, total_boxplot_list):
    for_dfr_dir = args.dfr
    os.makedirs(for_dfr_dir, exist_ok=True)

    for detector in sorted_by_detector_dict.keys():
        total_qPKW = []
        total_vPKW = []
        avg_qPKW = []
        avg_vPKW = []
        
        unique_detectors = sorted_by_detector_dict[detector][0]['Detector'].unique().tolist() #d_6586_1

        detectors_dict = {key: {'qPKW': None, 'vPKW': None} for key in unique_detectors}

        for day in sorted_by_detector_dict[detector]:
            total_qPKW = [x + y for x, y in zip_longest(total_qPKW, day['qPKW'].tolist(), fillvalue=0)]
            total_vPKW = [x + y for x, y in zip_longest(total_vPKW, day['vPKW'].tolist(), fillvalue=0)]
            for key in unique_detectors:
                filtered_qpkw = day.loc[day['Detector'] == key, 'qPKW'].tolist()
                filtered_vpkw = day.loc[day['Detector'] == key, 'vPKW'].tolist()
                if detectors_dict[key]['qPKW'] is None:
                    detectors_dict[key]['qPKW'] = np.array(filtered_qpkw).reshape(-1, 1)
                else:
                    detectors_dict[key]['qPKW'] = np.concatenate((detectors_dict[key]['qPKW'], np.array(filtered_qpkw).reshape(-1, 1)), axis=1)
##########################################
                if detectors_dict[key]['vPKW'] is None:
                    detectors_dict[key]['vPKW'] = np.array(filtered_vpkw).reshape(-1, 1)
                else:
                    detectors_dict[key]['vPKW'] = np.concatenate((detectors_dict[key]['vPKW'], np.array(filtered_vpkw).reshape(-1, 1)), axis=1)                    

        avg_qPKW += [int(x/(len(sorted_by_detector_dict[detector]))) for x in total_qPKW]
        avg_vPKW += [round(x/(len(sorted_by_detector_dict[detector])), 2) for x in total_vPKW]

        dump_df = {'Detector': sorted_by_detector_dict[detector][0]['Detector'],
                   'Time': sorted_by_detector_dict[detector][0]['Time'],
                   'qPKW': avg_qPKW,
                   'vPKW': avg_vPKW
                  }
        output_df = pd.DataFrame(dump_df)

        output_file = os.path.join(for_dfr_dir, f'dfrouter-mean-measures.csv') # 21-day-mean data for simulation
        write_header = not os.path.exists(output_file)
        output_df.to_csv(output_file, index=False, mode='a', header=write_header, sep=';')
        total_boxplot_list.append(detectors_dict)


def plot(mean_dict, plot_name):
    plt.figure(figsize=(10, 6))
    plt.bar(mean_dict.keys(), mean_dict.values(), color='skyblue')
    plt.title('Average Volume per Time Interval, detector: ' + str(extract_number(plot_name)))
    plt.xlabel('Time Interval')
    plt.ylabel('Average Volume')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()

    plt.figure(figsize=(10, 6))
    plt.boxplot(mean_dict.values())
    plt.title('Boxplot of Volume per Time Interval')
    plt.xlabel('Time Interval')
    plt.ylabel('Volume')
    plt.tight_layout()
    plt.show()

def plot_time_boxplots(total_boxplot_list):
    #posits=[i for i in range(37)]
    posits= [i for i in range(12)]

    for detector in total_boxplot_list:
        for det_line_info in detector.keys():
            _, det_id, line_id = det_line_info.split('_')
            for metric in ['qPKW', 'vPKW']:
                
                #plt.boxplot([detector[det_line_info][metric][i] for i in range(detector[det_line_info][metric].shape[0])], positions=posits)
                plt.boxplot([detector[det_line_info][metric][:, i] for i in range(detector[det_line_info][metric].shape[1])], positions=posits)
                
                #plt.xticks(posits, times)
                plt.xlabel('Боксплоты')
                plt.ylabel(f'Метрика {metric}')
                plt.title(f'detector-id: {det_id}, line-id: {line_id}, metric: {metric}')
                
                plt.show()

def main():
    n = 21
    
    sorted_by_detector_dict = {}
    total_boxplot_list = []
    for filename in os.listdir(args.d):
        if filename.endswith('.xlsx'):
            file_path = os.path.join(args.d, filename)
            cur_df = process_xlsx(file_path)
            
            first_n_days_data = sort_first_n_days(n, cur_df=cur_df)
            #print(first_n_days_data)
            #time_stats = form_mean_stats(first_n_days_data=first_n_days_data)
            #save_processed(first_n_days_data, 'proc_'+filename)
            #save_processed_mean(time_stats, 'mean_'+filename)

            #print(time_stats)
            #print(first_n_days_data)
            #plot(time_stats, filename)


            for date, group_data in first_n_days_data.groupby(pd.to_datetime(first_n_days_data['Time']).dt.date):
                process_for_dfrouter(day=group_data, filename=filename,sorted_by_detector_dict=sorted_by_detector_dict)
                first_n_days_data.drop(group_data.index, inplace=True)
                #print(first_n_days_data)
            
    dfrouter_final(sorted_by_detector_dict=sorted_by_detector_dict, total_boxplot_list=total_boxplot_list)      
    #plot_time_boxplots(total_boxplot_list=total_boxplot_list)
if __name__ == '__main__':
    main()