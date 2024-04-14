import argparse
import os
import pandas as pd
import matplotlib.pyplot as plt
import re
import csv
import numpy as np
from itertools import zip_longest

parser = argparse.ArgumentParser(description='Process traffic demand')
parser.add_argument('-d', type=str, default='datasets/current', help='path to directory with .xlsx data')
parser.add_argument('-o', type=str, default='datasets/processed', help='path to processed sorted .xlsx output')
parser.add_argument('-p', type=str, default='datasets/plot-data', help='path to xlsx plot tables')
parser.add_argument('-od', type=str, default='datasets/od-data', help='path to for od-data')
parser.add_argument('-dfr', type=str, default='datasets/dfrouter-data', help='path to dfrouter data csv')
args = parser.parse_args()

def process_xlsx(file_path):
    df = pd.read_excel(file_path)
    df = df[['Speed','Volume', 'Number', 'Time']]
    df['Time'] = pd.to_datetime(df['Time'])
    df['Volume'] = df['Volume'].fillna(0)
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
    filtered_df = filter(cur_df)
    sorted_filtered_df = filtered_df.sort_values(by='Time')
    return sorted_filtered_df[sorted_filtered_df['Time'] < sorted_filtered_df['Time'].iloc[0] + pd.Timedelta(days=n)]

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

def process_for_dfrouter(df, filename, sorted_by_detector_dict):
    for_dfr_dir = args.dfr
    os.makedirs(for_dfr_dir, exist_ok=True)
    map_detector_id = str(extract_number(filename)) # 6581, 900700 etc..
    df_sorted = df.sort_values(by=['Number', 'Time'])
    unique_date = pd.to_datetime(df['Time']).dt.date.unique()[0].strftime('%Y-%m-%d')
    df_sorted.fillna(0, inplace=True)
    detector_ids = ["d_" + map_detector_id + "_" + str(number) for number in df_sorted['Number']]

    df_sorted['Detector'] = detector_ids
    df_sorted['Time'] = 5
    df_selected = df_sorted[['Detector','Time' ,'Volume', 'Speed']]
    df_selected['Volume'] /= 12
    df_selected_renamed = df_selected.rename(columns={'Volume': 'qPKW', 'Speed': 'vPKW'})[['Detector', 'Time', 'qPKW', 'vPKW']]
    if map_detector_id not in sorted_by_detector_dict:
        sorted_by_detector_dict[map_detector_id] = []
    sorted_by_detector_dict[map_detector_id].append(df_selected_renamed)

def dfrouter_final(sorted_by_detector_dict):
    for_dfr_dir = args.dfr
    os.makedirs(for_dfr_dir, exist_ok=True)

    for detector in sorted_by_detector_dict.keys():
        total_qPKW = []
        total_vPKW = []
        avg_qPKW = []
        avg_vPKW = []
        
        for day in sorted_by_detector_dict[detector]:
            total_qPKW = [x + y for x, y in zip_longest(total_qPKW, day['qPKW'].tolist(), fillvalue=0)]
            total_vPKW = [x + y for x, y in zip_longest(total_vPKW, day['vPKW'].tolist(), fillvalue=0)]

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

def main():
    n = 20
    
    sorted_by_detector_dict = {}
    for filename in os.listdir(args.d):
        if filename.endswith('.xlsx'):
            file_path = os.path.join(args.d, filename)
            cur_df = process_xlsx(file_path)
            
            first_n_days_data = sort_first_n_days(n, cur_df=cur_df)
            
            time_stats = form_mean_stats(first_n_days_data=first_n_days_data)
            save_processed(first_n_days_data, 'proc_'+filename)
            save_processed_mean(time_stats, 'mean_'+filename)

            print(time_stats)
            print(first_n_days_data)
            #plot(time_stats, filename)


            for date, group_data in first_n_days_data.groupby(pd.to_datetime(first_n_days_data['Time']).dt.date):
                process_for_dfrouter(group_data, filename=filename,sorted_by_detector_dict=sorted_by_detector_dict)
                first_n_days_data.drop(group_data.index, inplace=True)
            
    dfrouter_final(sorted_by_detector_dict=sorted_by_detector_dict)      

if __name__ == '__main__':
    main()