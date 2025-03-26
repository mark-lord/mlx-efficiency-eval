import fire
import mlx_lm
import subprocess
import re
import csv
import time
import signal
import sys
from datetime import datetime
import threading
from typing import Optional
import os

FIFO_PATH = '/tmp/power_monitor_fifo'
POWER_MONITOR_CSV = 'gpu_power_continuous.csv'

class ModelGenerator:
    def __init__(self, model_name: str = "./ministral-8b"):
        """Initialize the model and tokenizer."""
        print(f"Loading model {model_name}...")
        self.model, self.tokenizer = mlx_lm.load(model_name)
        self.total_tokens = 0
        self.start_time = None
        self.last_processed_line = 0
        self.monitoring_thread = None
        self.is_monitoring = False
        self.generation_metrics_csv = None
        self.final_energy_joules = 0
        self.final_energy_kwh = 0
        self.total_power_samples = 0
        self.total_power_sum = 0
        
        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """Handle signals to ensure clean shutdown."""
        print("\nReceived signal to stop. Cleaning up...")
        self.stop_power_monitoring()
        sys.exit(0)
        
    def generate(self, prompt: str, max_tokens: int) -> str:
        """Generate text from the model."""
        messages = [{"role": "user", "content": prompt}]
        prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        response = mlx_lm.generate(
            self.model,
            self.tokenizer,
            prompt,
            max_tokens,
        )
        return response

    def start_power_monitoring(self):
        """Start power monitoring by sending command through FIFO."""
        try:
            # Clean up previous power monitoring file if it exists
            if os.path.exists(POWER_MONITOR_CSV):
                os.remove(POWER_MONITOR_CSV)
                print(f"Cleaned up previous power monitoring file: {POWER_MONITOR_CSV}")
            
            with open(FIFO_PATH, 'w') as fifo:
                fifo.write('start\n')
                fifo.flush()
            
            # Start the monitoring thread
            self.is_monitoring = True
            self.monitoring_thread = threading.Thread(target=self._monitor_power_data)
            self.monitoring_thread.daemon = True
            self.monitoring_thread.start()
            
        except Exception as e:
            print(f"Error starting power monitoring: {e}")
            print("Make sure gpu_power_monitor_continuous.py is running first!")

    def stop_power_monitoring(self):
        """Stop power monitoring by sending command through FIFO."""
        try:
            if self.is_monitoring:
                with open(FIFO_PATH, 'w') as fifo:
                    fifo.write('stop\n')
                    fifo.flush()
                
                # Stop the monitoring thread
                self.is_monitoring = False
                if self.monitoring_thread:
                    self.monitoring_thread.join(timeout=1.0)
                
        except Exception as e:
            print(f"Error stopping power monitoring: {e}")

    def _monitor_power_data(self):
        """Monitor the power monitor's CSV and create enriched metrics."""
        # Initialize the metrics CSV if it doesn't exist
        if not os.path.exists(self.generation_metrics_csv):
            with open(self.generation_metrics_csv, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Timestamp', 'GPU Power (mW)', 'Cumulative Tokens', 
                               'Cumulative Energy (J)', 'Cumulative kWh'])
        
        cumulative_energy = 0
        sample_interval = 0.1  # 100ms in seconds
        
        while self.is_monitoring:
            try:
                if not os.path.exists(POWER_MONITOR_CSV):
                    time.sleep(0.1)
                    continue
                
                with open(POWER_MONITOR_CSV, 'r') as csvfile:
                    lines = csvfile.readlines()
                    if len(lines) <= self.last_processed_line:
                        time.sleep(0.1)
                        continue
                    
                    # Process new lines
                    for line in lines[self.last_processed_line:]:
                        if line.strip() and not line.startswith('Timestamp'):  # Skip header
                            timestamp, power = line.strip().split(',')
                            power = float(power)
                            
                            # Track power samples for average calculation
                            self.total_power_samples += 1
                            self.total_power_sum += power
                            
                            # Calculate energy in joules (power * time)
                            energy_increment = (power / 1000) * sample_interval  # Convert to joules
                            cumulative_energy += energy_increment
                            cumulative_kwh = cumulative_energy / 3600000  # Convert joules to kWh
                            
                            # Update final energy values
                            self.final_energy_joules = cumulative_energy
                            self.final_energy_kwh = cumulative_kwh
                            
                            # Write to enriched metrics CSV
                            with open(self.generation_metrics_csv, 'a', newline='') as metrics_file:
                                writer = csv.writer(metrics_file)
                                writer.writerow([
                                    timestamp, power, self.total_tokens,
                                    cumulative_energy, cumulative_kwh
                                ])
                    
                    self.last_processed_line = len(lines)
                
            except Exception as e:
                print(f"Error in power monitoring: {e}")
                time.sleep(0.1)

    def parse_token_count(self, user_input: str) -> int:
        """Parse various formats of token count input."""
        # Remove commas and spaces
        cleaned = user_input.replace(',', '').replace(' ', '')
        
        # Handle scientific notation
        if 'e' in cleaned.lower():
            base, exponent = cleaned.lower().split('e')
            return int(float(base) * (10 ** float(exponent)))
        
        return int(cleaned)

    def print_summary(self, kwh_cost: float):
        """Print a summary of the generation run with energy metrics."""
        # Calculate timing metrics
        elapsed_time = time.time() - self.start_time
        tokens_per_second = self.total_tokens / elapsed_time if elapsed_time > 0 else 0
        
        # Calculate power metrics
        average_wattage = self.total_power_sum / self.total_power_samples if self.total_power_samples > 0 else 0
        
        # Calculate energy metrics
        tokens_per_joule = self.total_tokens / self.final_energy_joules if self.final_energy_joules > 0 else 0
        kwh_for_million = (1_000_000 / tokens_per_joule) / 3600000 if tokens_per_joule > 0 else 0
        cost_for_million = kwh_for_million * kwh_cost if kwh_for_million > 0 else 0
        
        # Calculate time projection for 1M tokens
        time_for_million = 1_000_000 / tokens_per_second if tokens_per_second > 0 else 0
        
        # Print to console
        print("\n=== Generation Summary ===")
        print(f"Total Tokens Generated: {self.total_tokens:,}")
        print(f"Time Taken: {elapsed_time:.2f} seconds")
        print(f"Generation Speed: {tokens_per_second:.2f} tokens/second")
        print(f"Average Power Usage: {average_wattage:.2f} mW")
        print(f"Total Energy Used: {self.final_energy_joules:,.2f} J")
        print(f"Total Energy Used: {self.final_energy_kwh:.4f} kWh")
        print(f"Energy Efficiency: {tokens_per_joule:.2f} tokens/J")
        print(f"\nProjections for 1M tokens:")
        print(f"Time Required: {time_for_million:.2f} seconds ({time_for_million/3600:.2f} hours)")
        print(f"Energy Required: {kwh_for_million:.2f} kWh")
        print(f"Estimated Cost: ${cost_for_million:.2f}")
        
        # Append summary to CSV
        with open(self.generation_metrics_csv, 'a', newline='') as csvfile:
            writer = csv.writer(csvfile)
            # Add empty row for separation
            writer.writerow([])
            # Add summary header
            writer.writerow(['=== Generation Summary ==='])
            # Add summary data
            writer.writerow(['Total Tokens Generated', self.total_tokens])
            writer.writerow(['Time Taken (seconds)', f"{elapsed_time:.2f}"])
            writer.writerow(['Generation Speed (tokens/second)', f"{tokens_per_second:.2f}"])
            writer.writerow(['Average Power Usage (mW)', f"{average_wattage:.2f}"])
            writer.writerow(['Total Energy Used (J)', f"{self.final_energy_joules:.2f}"])
            writer.writerow(['Total Energy Used (kWh)', f"{self.final_energy_kwh:.4f}"])
            writer.writerow(['Energy Efficiency (tokens/J)', f"{tokens_per_joule:.2f}"])
            writer.writerow([''])
            writer.writerow(['Projections for 1M tokens:'])
            writer.writerow(['Time Required (seconds)', f"{time_for_million:.2f}"])
            writer.writerow(['Time Required (hours)', f"{time_for_million/3600:.2f}"])
            writer.writerow(['Energy Required (kWh)', f"{kwh_for_million:.2f}"])
            writer.writerow(['Estimated Cost ($)', f"{cost_for_million:.2f}"])
            writer.writerow(['kWh Cost Used ($/kWh)', f"{kwh_cost:.2f}"])

def main():
    generator = ModelGenerator()
    
    try:
        while True:
            print("\n=== MLX Model Generation System ===")
            print("1. Generate text")
            print("2. Exit")
            
            choice = input("\nEnter your choice (1-2): ").strip()
            
            if choice == "2":
                break
            elif choice == "1":
                prompt = input("Enter your prompt: ").strip()
                token_input = input("How many tokens to generate? ").strip()
                csv_name = input("Enter a name for the metrics CSV file (e.g., 'run1_metrics.csv'): ").strip()
                kwh_cost_input = input("Enter cost per kWh (default: $0.35): ").strip()
                
                # Ensure CSV name ends with .csv
                if not csv_name.endswith('.csv'):
                    csv_name += '.csv'
                
                # Parse kWh cost with default
                try:
                    kwh_cost = float(kwh_cost_input) if kwh_cost_input else 0.35
                except ValueError:
                    print("Invalid kWh cost. Using default of $0.35")
                    kwh_cost = 0.35
                
                generator.generation_metrics_csv = csv_name
                generator.total_tokens = 0  # Reset token count for new run
                generator.final_energy_joules = 0  # Reset energy metrics
                generator.final_energy_kwh = 0
                generator.total_power_samples = 0  # Reset power tracking
                generator.total_power_sum = 0
                
                try:
                    target_tokens = generator.parse_token_count(token_input)
                    print(f"\nStarting generation of {target_tokens:,} tokens...")
                    print("Make sure gpu_power_monitor_continuous.py is running!")
                    print(f"Monitoring data will be saved to {csv_name}")
                    
                    # Start power monitoring
                    generator.start_power_monitoring()
                    
                    # Record start time
                    generator.start_time = time.time()
                    
                    # Generate text in chunks until target is reached
                    chunk_size = 256  # Adjust this based on your needs
                    while generator.total_tokens < target_tokens:
                        response = generator.generate(prompt, chunk_size)
                        # Count tokens based on chunk size instead of word count
                        generator.total_tokens += chunk_size
                        
                        # Small delay to prevent overwhelming the system
                        time.sleep(0.1)
                    
                    # Stop power monitoring
                    generator.stop_power_monitoring()
                    print(f"\nGeneration complete!")
                    
                    # Print summary
                    generator.print_summary(kwh_cost)
                    
                except ValueError as e:
                    print(f"Error: Invalid token count format. {e}")
                except KeyboardInterrupt:
                    print("\nGeneration interrupted by user.")
                    generator.stop_power_monitoring()
                except Exception as e:
                    print(f"An error occurred: {e}")
                    generator.stop_power_monitoring()
            else:
                print("Invalid choice. Please try again.")
    
    finally:
        # Ensure monitoring is stopped when exiting
        generator.stop_power_monitoring()

if __name__ == "__main__":
    main()

# You can still run with custom parameters like so:
# HF_HUB_DISABLE_PROGRESS_BARS=1 python generate.py --model mlx-community/Qwen2.5-Coder-14B-Instruct-4bit --prompt "Write a story about Einstein" --max-tokens 256
