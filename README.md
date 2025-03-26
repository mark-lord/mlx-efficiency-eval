# MLX Efficiency Evaluation Tool

A tool for evaluating the energy efficiency of MLX-based language models by measuring power consumption during text generation.

## Features

- Real-time power monitoring during text generation
- Detailed energy consumption metrics
- Token generation speed analysis
- Cost projections for large-scale generation
- CSV export of detailed metrics
- Support for custom kWh cost calculations

## Prerequisites

- Python 3.8+
- MLX framework
- GPU power monitoring capabilities
- `gpu_power_monitor_continuous.py` running in the background

## Installation

1. Clone the repository:
```bash
git clone https://github.com/mark-lord/mlx-efficiency-eval.git
cd mlx-efficiency-eval
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Start the power monitoring service:
```bash
python gpu_power_monitor_continuous.py
```

## Usage

1. Run the generation tool:
```bash
python record-generate.py
```

2. Follow the interactive prompts to:
   - Enter your prompt
   - Specify the number of tokens to generate
   - Name your metrics CSV file
   - Set the cost per kWh (default: $0.35)

3. The tool will:
   - Generate the requested text
   - Monitor power consumption
   - Calculate efficiency metrics
   - Save detailed data to CSV
   - Display a comprehensive summary

## Output

The tool generates two types of output:

1. Real-time CSV file with:
   - Timestamp
   - GPU Power (mW)
   - Cumulative Tokens
   - Cumulative Energy (J)
   - Cumulative kWh

2. Summary statistics including:
   - Total tokens generated
   - Time taken
   - Generation speed
   - Average power usage
   - Energy efficiency
   - Projections for 1M tokens

## License

MIT License - see LICENSE file for details 