from flask import Flask, request, jsonify
import threading
import time
from ProgressManager.RunTable.Models.RunProgress import RunProgress

import threading
from ProgressManager.RunTable.Models.RunProgress import RunProgress


class TaskManager:

    def __init__(self, run_table):
        self.run_table = run_table
        self.assigned_runs = {}
        self.total_runs = len(run_table)

        self.lock = threading.Lock()   # ✅ FIXED (you were missing this)

    def get_next_task(self, agent_id):
        with self.lock:
            for idx, run in enumerate(self.run_table):
                if run['__done'] == RunProgress.TODO:

                    run['__done'] = "RUNNING"
                    run['agent_id'] = agent_id

                    run['__current_run'] = idx
                    run['__total_runs'] = self.total_runs

                    self.assigned_runs[run['__run_id']] = agent_id

                    return run

        return None

    def complete_task(self, run_id, data):
        with self.lock:
            for run in self.run_table:
                if run["__run_id"] == run_id:

                    run.update(data)
                    run["__done"] = RunProgress.DONE

                    self.assigned_runs.pop(run_id, None)
                    return
    
    def reset_tasks_for_agent(self, agent_id):
        """🔥 IMPORTANT: recovery function"""
        with self.lock:
            for run in self.run_table:
                if run.get("agent_id") == agent_id and run["__done"] == "RUNNING":
                    run["__done"] = RunProgress.TODO
                    run["agent_id"] = None

            self.assigned_runs = {
                k: v for k, v in self.assigned_runs.items()
                if v != agent_id
            }
                
class APIServer:
    """Flask API server for distributed task management"""
    
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
            run_data = payload.get('data', {})   # ✅ extract correctly
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

        run_table = config.create_run_table_model().generate_experiment_run_table()
        

        self.task_manager = TaskManager(run_table)
        self.monitor = WorkerMonitor(self.task_manager)
        self.api = APIServer(self.task_manager, self.monitor)

    def start(self): 
        threading.Thread(target=self.monitor.monitor, daemon=True).start() 
        self.api.app.run(host=self.host, port=self.port)