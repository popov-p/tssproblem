import argparse
import os
import pandas as pd
import matplotlib.pyplot as plt
import re
import csv
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

def save_for_od_data(ts, filename):
    od_dir = args.od
    os.makedirs(od_dir, exist_ok=True)
    
    stats = {'min': min(ts.values()),
                  'max': max(ts.values()),
                  'avg': int(sum(ts.values()) / len(ts))}
    
    filepath = os.path.join(od_dir, filename)
    with open(filepath, 'w') as file:
        for key, value in stats.items():
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

def process_for_dfrouter(df, filename):
    map_detector_id = str(extract_number(filename)) # 6581, 900700 etc..
    df_sorted = df.sort_values(by='Number')
    detector_ids = ["d_" + map_detector_id + "_" + str(number) for number in df_sorted['Number']]

    df_sorted['Detector'] = detector_ids
    df_sorted['Time'] = 5
    df_selected = df_sorted[['Detector','Time' ,'Volume', 'Speed']]
    df_selected_renamed = df_selected.rename(columns={'Volume': 'qPKW', 'Speed': 'vPKW'})[['Detector', 'Time', 'qPKW', 'vPKW']]
    df_selected_renamed.to_csv(os.path.join(args.d, 'dfrouter-measures.csv'), index=False, mode='a', header=False)
def plot(mean_dict, plot_name):
    plt.figure(figsize=(10, 6))
    plt.bar(mean_dict.keys(), mean_dict.values(), color='skyblue')
    plt.title('Average Volume per Time Interval, detector: ' + str(extract_number(plot_name)))
    plt.xlabel('Time Interval')
    plt.ylabel('Average Volume')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()

def main():
    for filename in os.listdir(args.d):
        if filename.endswith('.xlsx'):
            file_path = os.path.join(args.d, filename)
            cur_df = process_xlsx(file_path)
            n = 20
            first_n_days_data = sort_first_n_days(n, cur_df=cur_df)
            process_for_dfrouter(cur_df, filename=filename)
            time_stats = form_mean_stats(first_n_days_data=first_n_days_data)
            save_processed(first_n_days_data, 'proc_'+filename)
            save_processed_mean(time_stats, 'mean_'+filename)
            save_for_od_data(time_stats, 'range_'+filename)
            print(time_stats)
            print(first_n_days_data)
            #plot(time_stats, filename)

if __name__ == '__main__':
    main()