from flask import Flask, request, jsonify
import threading
import time
from pathlib import Path
import pandas as pd
import os

from ProgressManager.RunTable.Models.RunProgress import RunProgress

import threading
from ProgressManager.RunTable.Models.RunProgress import RunProgress

class TaskManager:

    def __init__(self, run_table, experiment_path: Path):
        self.run_table = run_table
        self.experiment_path = experiment_path
        self.assigned_runs = {}
        self.total_runs = len(run_table)
        self.lock = threading.Lock()

    def get_next_task(self, agent_id):
        with self.lock:
            for idx, run in enumerate(self.run_table):
                if run['__done'] == RunProgress.TODO:

                    run_id = run["__run_id"]

                    run_dir = self.experiment_path / str(run_id)
                    run_dir.mkdir(parents=True, exist_ok=True)

                    run['__done'] = "RUNNING"
                    run['agent_id'] = agent_id

                    run['__current_run'] = idx
                    run['__total_runs'] = self.total_runs

                    run["run_dir"] = str(run_dir)

                    self.assigned_runs[run_id] = agent_id

                    return run

        return None

    def complete_task(self, run_id, data):
        with self.lock:
            for run in self.run_table:
                if run["__run_id"] == run_id:
                    if data:
                        for k, v in data.items():
                            run[k] = v

                    run["__done"] = RunProgress.DONE

                    self.assigned_runs.pop(run_id, None)

                    pd.DataFrame(self.run_table).to_csv(
                        self.experiment_path / "run_table.csv",
                        index=False
                    )
                    return

class APIServer:    
    def __init__(self, task_manager, worker_monitor):
        self.app = Flask(__name__)
        self.task_manager = task_manager
        self.monitor = worker_monitor
        
        # Register endpoints
        @self.app.route('/task', methods=['GET'])
        def get_task():
            agent_id = request.args.get('agent_id')
            self.monitor.heartbeat(agent_id)
            
            task = self.task_manager.get_next_task(agent_id)
            return jsonify({"run": task if task else None})
        
        @self.app.route('/result', methods=['POST'])
        def submit_result():
            payload = request.get_json()

            run_id = payload.get('run_id')
            run_data = payload.get('data', {})   
            status = payload.get('status')

            if status == "FAILED":
                print(f"[MASTER] Run {run_id} failed: {payload.get('error')}")

            self.task_manager.complete_task(run_id, run_data)

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
            todo_count = sum(1 for r in self.task_manager.run_table if r['__done'] == RunProgress.TODO)
            running_count = sum(1 for r in self.task_manager.run_table if r['__done'] == "RUNNING")
            done_count = sum(1 for r in self.task_manager.run_table if r['__done'] == RunProgress.DONE)
            
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

class WorkerMonitor:
    def __init__(self, task_manager):
        self.heartbeats = {}
        self.task_manager = task_manager
        self.timeout = 60

    def heartbeat(self, agent_id):
        self.heartbeats[agent_id] = time.time()

    def monitor(self):
        while True:
            time.sleep(10)
            now = time.time()

            dead = [
                agent for agent, t in self.heartbeats.items()
                if now - t > self.timeout
            ]

            for agent in dead:
                print(f"[MASTER] Worker {agent} dead")

                for run in self.task_manager.run_table:
                    if run.get("agent_id") == agent and run["__done"] != RunProgress.DONE:
                        run["__done"] = RunProgress.TODO
                        run["agent_id"] = None

                del self.heartbeats[agent]

class DistributedMasterOrchestrator:

    def __init__(self, config, metadata, host="0.0.0.0", port=5000):
        self.config = config
        self.metadata = metadata
        self.host = host
        self.port = port

        self.experiment_path = config.results_output_path / config.name
        self.experiment_path.mkdir(parents=True, exist_ok=True)

        run_table = config.create_run_table_model().generate_experiment_run_table()
        
        self.run_table_path = self.experiment_path / "run_table.csv"
        pd.DataFrame(run_table).to_csv(self.run_table_path, index=False)
        
        self.task_manager = TaskManager(run_table, self.experiment_path)
        self.monitor = WorkerMonitor(self.task_manager)
        self.api = APIServer(self.task_manager, self.monitor)

    def start(self): 
        threading.Thread(target=self.monitor.monitor, daemon=True).start() 
        self.api.app.run(host=self.host, port=self.port)