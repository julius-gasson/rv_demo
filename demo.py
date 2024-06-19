import argparse
import psutil
import os
from pycontract.pycontract_core import Monitor, error
from pycontract.pycontract_plantuml import visualize
from pycontract.extra_csv import CSVSource

class Pressure(Monitor):
    low_counts: dict = {}
    high_counts: dict = {}
    up_counts: dict = {}
    down_counts: dict = {}
    prev_value: dict = {}
    HIGH: float
    LOW: float
    MAX_UNSAFE: int
    FREQ: int = 15
    def __init__(self, low, high, max_delta, max_unsafe):
        super().__init__()
        self.MAX_UNSAFE = max_unsafe
        self.MAX_DELTA = max_delta
        self.LOW = low
        self.HIGH = high
    def transition(self, event):
        if event['Tipo Grandezza'] != "Pressione a valle":
             return
        prev = self.prev_value.get(event['ID'], None)
        self.prev_value[event['ID']] = float(event['Valore'])
        match event:
            case {'ID': pdm_id, "Valore": value, 'Tipo Grandezza': "Pressione a valle"} \
                if float(value) > self.HIGH:
                    count: int = self.high_counts.get(pdm_id, 0)
                    count += 1
                    self.high_counts[pdm_id] = count
                    if count > self.MAX_UNSAFE:
                        return error(f"{pdm_id} was too high for {count * self.FREQ} minutes")
                    else:
                        self.low_counts[pdm_id] = 0
        match event:
            case {'ID': pdm_id, "Valore": value, 'Tipo Grandezza': "Pressione a valle"} \
                if float(value) < self.LOW:
                    count: int = self.low_counts.get(pdm_id, 0)
                    count += 1
                    self.low_counts[pdm_id] = count
                    if count > self.MAX_UNSAFE:
                        return error(f"{pdm_id} was too low for {count * self.FREQ} minutes")
                    else:
                        self.low_counts[pdm_id] = count
                        self.high_counts[pdm_id] = 0
        match event:
            case {'ID': pdm_id, "Valore": value, 'Tipo Grandezza': "Pressione a valle"} \
                if prev and float(value) - prev > self.MAX_DELTA:
                    count: int = self.up_counts.get(pdm_id, 0)
                    count += 1
                    self.up_counts[pdm_id] = count
                    if count > self.MAX_UNSAFE:
                        return error(f"{pdm_id} increased by over {self.MAX_DELTA} bars for {count * self.FREQ} minutes")
                    self.down_counts[pdm_id] = 0
        match event:
            case {'ID': pdm_id, "Valore": value, 'Tipo Grandezza': "Pressione a valle"} \
                if prev and prev - float(value) > self.MAX_DELTA:
                    count: int = self.down_counts.get(pdm_id, 0)
                    count += 1
                    self.down_counts[pdm_id] = count
                    if count > self.MAX_UNSAFE:
                        return error(f"{pdm_id} decreased by over {self.MAX_DELTA} bars for {count * self.FREQ} minutes")
                    self.up_counts[pdm_id] = 0
        match event:
            case {'ID': pdm_id, "Valore": value, 'Tipo Grandezza': "Pressione a valle"} \
                if prev and abs(float(value) - prev) <= self.MAX_DELTA:
                    self.up_counts[pdm_id] = 0
                    self.down_counts[pdm_id] = 0
        match event:
             case {'ID': pdm_id, "Valore": value, 'Tipo Grandezza': "Pressione a valle"} \
                if float(value) > self.LOW and float(value) < self.HIGH:
                    self.high_counts[pdm_id] = 0
                    self.low_counts[pdm_id] = 0

def print_intro(args):
    print("=" * 80)
    print("Pressure Monitor with PyContract".center(80))
    print("=" * 80)
    print("This program monitors the following behaviours of pressure values:")
    print(f"\t1. Pressure values may not fall below {args.low} bars for more than {args.max_unsafe * 15} minutes.")
    print(f"\t2. Values may not exceed {args.high} bars for more than {args.max_unsafe * 15} minutes.")
    print(f"\t3. Pressure values may not increase or decrease by more than {args.max_delta} bars for more than {args.max_unsafe * 15} minutes.")
    print("=" * 80)

def get_next_input(monitor: Monitor):
    resp: str = input("Press Enter to continue or 'q' to quit: ")
    if resp == 'q':
        print("Exiting monitor...")
        monitor.end()
        exit(0)
    elif resp != '':
        print("Invalid input. Please press Enter to continue or 'q' to quit.")
        return get_next_input(monitor)

def main():
    parser = argparse.ArgumentParser(description="Monitor pressure values from a CSV file.")
    parser.add_argument("infile", type=str, help="The CSV file containing pressure data.")
    parser.add_argument("-l", "--max_lines", type=int, default=None, help="Maximum number of lines to read")
    parser.add_argument("-n", "--max_unsafe", type=int, default=3, help="Maximum number of unsafe readings before an error is triggered.")
    parser.add_argument("-d", "--max_delta", type=float, default=0.001, help="Safe difference between two pressure readings.")
    parser.add_argument("-L", "--low", type=float, default=0.019, help="Lower threshold for pressure.")
    parser.add_argument("-H", "--high", type=float, default=0.032, help="Upper threshold for pressure.")
    parser.add_argument("-v", "--visualize", action="store_true", help="Visualise the pressure monitoring setup.")
    parser.add_argument("-m", "--memory", action="store_true", help="Measure the memory usage of the file")
    parser.add_argument("--online", action="store_true", help="Monitor pressure readings online from a CSV file")
    
    args = parser.parse_args()
    
    # Check for file extension
    if not args.infile.endswith(".csv"):
        print("Error: The input file must be a CSV.")
        exit(1)
    if args.visualize:
        visualize(__file__)
    print_intro(args)
    monitor = Pressure(
        low=args.low,
        high=args.high,
        max_delta=args.max_delta,
        max_unsafe=args.max_unsafe
    )
    with CSVSource(args.infile) as csv_reader:
        line_count = 0
        for event in csv_reader:
            line_count += 1
            if args.max_lines is not None and line_count > args.max_lines:
                 break
            elif event is not None:
                if args.online:
                    get_next_input(monitor)
                print(event)
                monitor.eval(event)
        monitor.end()
    if args.memory:
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        print(f"RSS (Physical Memory): {memory_info.rss / (1024 * 1024):.2f} MB")
        print(f"VMS (Virtual Memory): {memory_info.vms / (1024 * 1024):.2f} MB")

if __name__ == '__main__':
    main()
