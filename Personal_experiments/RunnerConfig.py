import time
import os

from ConfigValidator.Config.Models.FactorModel import FactorModel
from ConfigValidator.Config.Models.RunTableModel import RunTableModel
from ConfigValidator.Config.Models.RunnerContext import RunnerContext
from pathlib import Path
from ConfigValidator.Config.Models.OperationType import OperationType


def run_experiment(algorithm, input_size):
    data = range(input_size)

    start = time.time()

    if algorithm == "sum_loop":
        total = 0
        for x in data:
            total += x
    elif algorithm == "optimized_sum":
        total = sum(data)

    end = time.time()

    return (end - start) * 1000


class RunnerConfig:

    name = "code_performance_example"
    default_output = Path("experiments")
    results_output_path = Path(os.getenv("EXPERIMENT_RUNNER_OUTPUT_PATH", str(default_output)))

    operation_type = OperationType.AUTO

    time_between_runs_in_ms = 1000

    experiment_path = None

    def create_run_table_model(self):
        factor1 = FactorModel("algorithm", ["sum_loop", "optimized_sum"])
        factor2 = FactorModel("input_size", [10000, 100000, 500000])

        return RunTableModel(
            factors=[factor1, factor2],
            data_columns=["execution_time_ms"]
        )

    def populate_run_data(self, context: RunnerContext):

        algorithm = context.run_variation["algorithm"]
        input_size = context.run_variation["input_size"]

        exec_time = run_experiment(algorithm, input_size)

        return {
            "execution_time_ms": exec_time
        }