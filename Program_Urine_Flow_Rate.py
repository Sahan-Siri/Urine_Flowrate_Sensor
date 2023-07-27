import serial
import csv
import time
import math
import threading
import tkinter as tk
import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

threshold_value = None
ser = None
reading_thread = None
readings_buffer = []
user_ready = False
start_time = None
output_file = None
K=1.0313#Calibrate

ser_lock = threading.Lock()
user_ready_lock = threading.Lock()

def calculate_threshold_value(readings):
    total_value = sum(readings)
    num_readings = len(readings)

    if num_readings == 0:
        return 0.0

    threshold_value = total_value / num_readings
    return round(K*threshold_value,3)

def calculate_capacitance_rate(capacitance_values, time_values):
    capacitance_rate = []
    for i in range(1, len(capacitance_values)):
        delta_capacitance = capacitance_values[i] - capacitance_values[i - 1]
        delta_time = time_values[i] - time_values[i - 1]
        if delta_time != 0:
            rate = delta_capacitance / delta_time
            capacitance_rate.append(rate)
    return capacitance_rate

def start_reading():
    global user_ready, start_time, threshold_value, ser, readings_buffer, output_file

    ser = serial.Serial("COM3", baudrate=9600)

    user_name = input("Please enter your name: ")
    output_file = f"{user_name}_data.csv"

    with user_ready_lock:
        user_ready = False

    while True:
        message = ser.readline().decode().strip()
        if "Capacitance Value" in message:
            with user_ready_lock:
                if threshold_value is not None and not user_ready:  # Only ask once
                    ready = input("Are you ready to start storing data? (Y/N): ")
                    if ready.upper() == 'Y':
                        user_ready = True
                        start_time = time.time()
                        print("Started storing data.")
                    else:
                        print("Thank You")
                        break

            start_index = message.index("=") + 1
            end_index = message.index("pF", start_index)
            value_str = message[start_index:end_index].strip()

            try:
                value = round(K*float(value_str),3)
            except ValueError:
                continue

            if (value/K) > 1000.0:
                continue

            start_index = message.index("(", end_index) + 1
            end_index = message.index(")", start_index)
            val_str = message[start_index:end_index].strip()
            val = float(val_str)

            timestamp = time.time() - start_time if user_ready else 0.0

            if user_ready:
                with ser_lock:
                    if value < threshold_value:
                        value = round(threshold_value,3)

                    with open(output_file, mode="a", newline='') as file:
                        writer = csv.writer(file)

                        if file.tell() == 0:
                            writer.writerow(["Time", "Capacitance", "ADC"])

                        writer.writerow([timestamp,(value - threshold_value), val])
                        file.flush()
                        new_value=round((value-threshold_value),3)
                        print(f"Time: {timestamp:.2f}s, Value: {new_value} mL, Val: {val}")

            readings_buffer.append(value)

            if len(readings_buffer) >= 20 and threshold_value is None:
                threshold_value = calculate_threshold_value(readings_buffer)
                print(f"Initial Value: {threshold_value} mL")
                readings_buffer = []

    ser.close()
    with user_ready_lock:
        user_ready = False


def start_reading_in_thread():
    global reading_thread
    reading_thread = threading.Thread(target=start_reading)
    reading_thread.start()

def stop_reading():
    global ser
    with ser_lock:
        if ser is not None:
            ser.close()
        print("Stopped data reading.")

def calculate_and_save_flow_rate():
    global output_file

    if output_file:
        with open(output_file, mode="r") as file:
            reader = csv.reader(file)
            next(reader)  
            data = list(reader)

        timestamps = [float(row[0]) for row in data]
        capacitance_values = [float(row[1]) for row in data]

        capacitance_rate = calculate_capacitance_rate(capacitance_values, timestamps)

        flow_rate_file = "Flow_rate.csv"
        with open(flow_rate_file, mode="w", newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Time", "Capacitance_Rate"])
            for timestamp, rate in zip(timestamps[1:], capacitance_rate):
                writer.writerow([timestamp, rate])
            print(f"Flow rate data saved in {flow_rate_file}")

def on_close():
    stop_reading()
    calculate_and_save_flow_rate()  
    root.destroy()

def moving_average_filter(data, window_size):
    if len(data) < window_size:
        raise ValueError("Window size cannot be larger than the data size.")
    
    moving_averages = []
    for i in range(window_size, len(data)+1):
        window = data[i-window_size:i]
        avg = sum(window) / window_size
        avg = max(avg, 0)
        moving_averages.append(avg)
    
    return moving_averages


def plot_data(data, xlabel, ylabel):
    plt.plot(data)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title("Urine Flow Rate")
    plt.grid(True)

    # Increase the number of divisions on the x-axis and y-axis
    x_ticks = np.linspace(0, round(len(data),1), num=5)  # Divide x-axis into 5 equally spaced ticks
    y_ticks = np.linspace(round(min(data),1), round(max(data),1), num=5)  # Divide y-axis into 5 equally spaced ticks
    plt.xticks(x_ticks)
    plt.yticks(y_ticks)

    plt.show()

def exponential_moving_average(data, alpha):
    ema = [data[0]]
    for i in range(1, len(data)):
        ema_value = alpha * data[i] + (1 - alpha) * ema[-1]
        ema.append(ema_value)
    return ema

def on_graph():
    output_file = "Flow_rate.csv"

    if output_file:
        with open(output_file, mode="r") as file:
            reader = csv.reader(file)
            next(reader)  # Skip the header row
            data = list(reader)

        capacitance_rates = [float(row[1]) for row in data]

       
        alpha = 0.3  
        smoothed_data = exponential_moving_average(capacitance_rates, alpha)

        window_size = 10  # This can be changed
        filtered_data = moving_average_filter(smoothed_data, window_size)

        new_flow_rate_file = "New_Flowrate.csv"
        with open(new_flow_rate_file, mode="w", newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Time", "Urine_Flow_Rate"])
            for timestamp, rate in zip(data[1:], filtered_data):
                writer.writerow([timestamp[0], rate])
            print(f"Filtered flow rate data saved in {new_flow_rate_file}")

        plot_data(filtered_data, "Time (s)", "Urine Flow Rate (mL/s)")


if __name__ == "__main__":
    root = tk.Tk()
    root.title("Data Reader GUI")
    root.protocol("WM_DELETE_WINDOW", on_close)

    start_button = tk.Button(root, text="Start Reading", command=start_reading_in_thread)
    start_button.pack(pady=10)

    stop_button = tk.Button(root, text="Stop Reading", command=stop_reading)
    stop_button.pack(pady=5)

    flow_rate_button = tk.Button(root, text="Flow rate", command=calculate_and_save_flow_rate)
    flow_rate_button.pack(pady=5)

    graph_button = tk.Button(root, text="Graph", command=on_graph)
    graph_button.pack(pady=5)

    root.mainloop()

    # Automatically save the CSV file with user input name in the same directory as the Python file
    if output_file:
        script_directory = os.path.dirname(os.path.abspath(__file__))
        new_file_path = os.path.join(script_directory, output_file)
        os.rename(output_file, new_file_path)
        print(f"CSV file saved as: {new_file_path}")
