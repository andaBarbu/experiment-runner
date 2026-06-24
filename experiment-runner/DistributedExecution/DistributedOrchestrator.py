from ProgressManager.RunTable.Models.RunProgress import RunProgress
from ProgressManager.Output.CSVOutputManager import CSVOutputManager
from EventManager.Models.RunnerEvents import RunnerEvents
from EventManager.EventSubscriptionController import EventSubscriptionController
from ProgressManager.Validation.AnomaliesChecker import ResultsValidator, AnomalyReport

from flask import Flask, request, jsonify
import threading
import time
from pathlib import Path
import pandas as pd
import os
from waitress import serve

###     =========================================================
###     |                                                       |
###     |                  TaskManager                          |
###     |       - Assign available runs to connected workers    |
###     |       - Update and persist run_table.csv state        |
###     |       - Trigger AFTER_EXPERIMENT lifecycle event      |
###     |       - Detect experiment completion                  |
###     |                                                       |
###     |       *Any state modification to runs should happen   |
###     |        through this class to avoid race conditions    |
###     |                                                       |
###     =========================================================
class TaskManager:

    def __init__(self, run_table, experiment_path: Path):
        self.run_table = run_table
        self.experiment_path = experiment_path
        self.assigned_runs = {}
        self.total_runs = len(run_table)
        self.lock = threading.Lock()
        self.csv_manager = CSVOutputManager(experiment_path)
        self.completed = False
        self.shutdown = False
        self.validation_results = {}

    def get_next_task(self, agent_id):
        with self.lock:

            # If experiment already completed
            if self.completed:
                return None

            for idx, run in enumerate(self.run_table):
                if run['__done'] == RunProgress.TODO:
                    run_id = run["__run_id"]

                    run_dir = self.experiment_path / str(run_id)
                    run_dir.mkdir(parents=True, exist_ok=True)

                    run['__done'] = RunProgress.RUNNING
                    run['agent_id'] = agent_id

                    run['__current_run'] = idx + 1
                    run['__total_runs'] = self.total_runs
                    run["run_dir"] = str(run_dir)

                    self.assigned_runs[run_id] = agent_id
                    self.csv_manager.write_run_table(self.run_table)

                    task = run.copy()
                    task['__done'] = task['__done'].name

                    print(f"[MASTER] Assigned {run_id} -> {agent_id}")
                    return task
            return None

    def complete_task(self, run_id, data):
        with self.lock:
            for run in self.run_table:
                if run["__run_id"] == run_id:
                    # Merge returned data 
                    if data:
                        for k, v in data.items():
                            run[k] = v
                    run["__done"] = RunProgress.DONE

                    self.assigned_runs.pop(run_id, None)
                    self.csv_manager.write_run_table(self.run_table)
                    print(f"[MASTER] Completed run {run_id}")
                    break

            # Check if all runs are done
            all_done = all(
                run['__done'] == RunProgress.DONE
                for run in self.run_table
            )
            if all_done and not self.completed:
                self.completed = True
                self.shutdown = True
                print("\n[MASTER] ALL RUNS COMPLETED\n")

                # AFTER_EXPERIMENT hook
                print("[MASTER] Calling AFTER_EXPERIMENT hook")
                EventSubscriptionController.raise_event(
                    RunnerEvents.AFTER_EXPERIMENT
                )
                #time.sleep(5)
                #shutdown_server()

    def restore_crashed_runs(self):
        """
        If server restarts and finds RUNNING runs,
        restore them to TODO.
        """
        changed = False

        for run in self.run_table:
            if run['__done'] == RunProgress.RUNNING:
                run['__done'] = RunProgress.TODO
                run['agent_id'] = None
                changed = True
        if changed:
            print("[MASTER] Restored RUNNING -> TODO after restart")
            self.csv_manager.write_run_table(self.run_table)

    def experiment_already_completed(self):
        return all(
            run['__done'] == RunProgress.DONE
            for run in self.run_table
        )

###     =========================================================
###     |                                                       |
###     |                  APIServer                            |
###     |       - Handles the communication between workers     |
###     |           and the orchestrator                        |
###     |               - Handle task distribution requests     |
###     |               - Receive completed experiment results  |
###     |               - Handle worker heartbeat updates       |
###     |               - Receive worker heartbeat updates      |
###     |               - Provide experiment                    |
###     |                   monitoring/status endpoint          |
###     |               - Trigger orchestrator shutdown         |
###     |                                                       |
###     |                                                       |
###     =========================================================
class APIServer:

    def __init__(self, task_manager, worker_monitor, validation_results):
        self.app = Flask(__name__)
        self.task_manager = task_manager
        self.monitor = worker_monitor
        self.validation_results = validation_results
        
        @self.app.route('/task', methods=['GET'])
        def get_task():
            agent_id = request.args.get('agent_id')
            self.monitor.heartbeat(agent_id)
            #task = self.task_manager.get_next_task(agent_id)

            if self.task_manager.shutdown:
                return jsonify({
                    "shutdown": True,
                    "run": None
                })
            
            task = self.task_manager.get_next_task(agent_id)

            return jsonify({
                "shutdown": False,
                "run": task if task else None
            })

        @self.app.route('/result', methods=['POST'])
        def submit_result():
            payload = request.get_json()
            run_id = payload.get('run_id')
            run_data = payload.get('data', {})
            status = payload.get('status')
            anomalies = request.json.get("anomalies", [])

            if status == "FAILED":
                print(f"[MASTER] Run failed: {run_id}")
                print(payload.get('error'))

                # Return run to TODO
                for run in self.task_manager.run_table:
                    if run['__run_id'] == run_id:
                        run['__done'] = RunProgress.TODO
                        run['agent_id'] = None
                self.task_manager.csv_manager.write_run_table(
                    self.task_manager.run_table
                )
            else:
                self.task_manager.complete_task(run_id, run_data)
                if anomalies:
                    report = AnomalyReport()
                    report.anomalies.extend(anomalies)
                    self.validation_results[run_id] = report
            return jsonify({"status": "ok"})

        @self.app.route('/heartbeat', methods=['POST'])
        def heartbeat():
            data = request.get_json()
            agent_id = data.get('agent_id')
            self.monitor.heartbeat(agent_id)

            return jsonify({"status": "ok"})

        @self.app.route('/status', methods=['GET'])
        def status():
            total_runs = len(self.task_manager.run_table)
            todo_count = sum(
                1 for r in self.task_manager.run_table
                if r['__done'] == RunProgress.TODO
            )
            running_count = sum(
                1 for r in self.task_manager.run_table
                if r['__done'] == RunProgress.RUNNING
            )
            done_count = sum(
                1 for r in self.task_manager.run_table
                if r['__done'] == RunProgress.DONE
            )
            return jsonify({
                "status": "ok",
                "total_runs": total_runs,
                "runs": {
                    "todo": todo_count,
                    "running": running_count,
                    "done": done_count
                },
                "active_agents": len(self.monitor.heartbeats)
            })
        
        @self.app.route('/shutdown', methods=['POST'])
        def shutdown():
            shutdown_server()
            return jsonify({"status": "shutting down"})

###     =========================================================
###     |                                                       |
###     |                  WorkerMonitor                        |
###     |       - Keeps track of connected workers              |
###     |       - If a worker fails to send a heartbeat         |
###     |         within the timeout period, it is considered   |
###     |         dead                                          |
###     |           - Return the assigment back to TODO         |
###     |                                                       |
###     |                                                       |
###     =========================================================
class WorkerMonitor:

    def __init__(self, task_manager):
        self.heartbeats = {}
        self.task_manager = task_manager
        self.timeout = 60

    def heartbeat(self, agent_id):
        self.heartbeats[agent_id] = time.time()

    def monitor(self):
        while not self.task_manager.completed:
            time.sleep(10)
            now = time.time()
            dead = [
                agent for agent, t in self.heartbeats.items()
                if now - t > self.timeout
            ]
            for agent in dead:
                print(f"[MASTER] Worker {agent} dead")

                for run in self.task_manager.run_table:
                    if (
                        run.get("agent_id") == agent
                        and run["__done"] != RunProgress.DONE
                    ):
                        print(f"[MASTER] Returning run "
                              f"{run['__run_id']} -> TODO")

                        run["__done"] = RunProgress.TODO
                        run["agent_id"] = None
                self.task_manager.csv_manager.write_run_table(
                    self.task_manager.run_table
                )
                del self.heartbeats[agent]

###     =========================================================
###     |                                                       |
###     |                  DistributedOrchestrator              |
###     |       - Initialize experiment infrastructure          |
###     |       - Load or create run_table.csv                  |
###     |       - Restore interrupted experiments               |
###     |       - Start monitoring threads                      |
###     |       - Start the API server                          |
###     |       - If anomalies are present combined them        |
###     |         into a report                                 |
###     |                                                       |
###     |                                                       |
###     =========================================================

class DistributedOrchestrator:

    def __init__(self, config, metadata, host="0.0.0.0", port=5000):
        self.config = config
        self.metadata = metadata
        self.host = host
        self.port = port
        self.validation_results = {}

        self.experiment_path = (config.results_output_path / config.name)
        self.experiment_path.mkdir(parents=True, exist_ok=True)
        self.run_table_path = (self.experiment_path / "run_table.csv")

        EventSubscriptionController.raise_event(
            RunnerEvents.VALIDATE_EXPERIMENT
        )
        if self.run_table_path.exists():
            print("[MASTER] Existing experiment detected")

            csv_manager = CSVOutputManager(self.experiment_path)
            run_table = csv_manager.read_run_table()
        else:
            print("[MASTER] Creating new experiment")

            run_table = (config.create_run_table_model().generate_experiment_run_table())
            pd.DataFrame(run_table).to_csv(self.run_table_path, index=False)

        self.task_manager = TaskManager(run_table, self.experiment_path)
        self.task_manager.restore_crashed_runs()

        if self.task_manager.experiment_already_completed():
            print("[MASTER] Experiment already completed")

            self.finished_before_start = True
        else:
            self.finished_before_start = False
        self.monitor = WorkerMonitor(self.task_manager)

        self.api = APIServer(self.task_manager, self.monitor, self.validation_results)

    def start(self):
        if self.finished_before_start:
            return

        EventSubscriptionController.raise_event(
            RunnerEvents.BEFORE_EXPERIMENT
        )

        threading.Thread(
            target=self.monitor.monitor,
            daemon=True
        ).start()

        print(f"[MASTER] Starting server "
            f"on {self.host}:{self.port}")

        server_thread = threading.Thread(
            target=lambda: serve(
                self.api.app,
                host=self.host,
                port=self.port
            ),
            daemon=True
        )

        server_thread.start()

        while not self.task_manager.shutdown:
            time.sleep(1)

        print("[MASTER] Waiting for workers to shutdown...")
        time.sleep(10)
        combined_report = AnomalyReport()

        for report in self.validation_results.values():
            combined_report.anomalies.extend(report.anomalies)

        if combined_report.has_anomalies():
            log_file_path = (
                self.experiment_path
                / self.config.energy_validation_log_file
            )

            ResultsValidator.save_report_to_file(
                combined_report,
                log_file_path
            )

        print("[MASTER] Shutting down")
        os._exit(0)
        
def shutdown_server():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        os._exit(0)
    func()