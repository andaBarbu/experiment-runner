import threading
import time
import requests

from ExperimentOrchestrator.Experiment.Run.RunController import RunController


class WorkerRuntime:

    def __init__(self, master_url, heartbeat_interval=40, idle_timeout=120):
        self.master_url = master_url
        self.heartbeat_interval = heartbeat_interval
        self.idle_timeout = idle_timeout  # Exit after N seconds with no tasks

        self._stop = False
        self.current_run = None
        self.agent_id = None
        self.last_task_time = None

    # =========================
    # MAIN LOOP
    # =========================
    def run_loop(self, agent_id, config):
        self.agent_id = agent_id
        self.last_task_time = time.time()
        print(f"[WORKER] Starting with agent_id: {self.agent_id}")
        print(f"[WORKER] Master URL: {self.master_url}")

        # start heartbeat thread
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        print(f"[WORKER] Heartbeat thread started")
        print(f"[WORKER] Waiting for tasks (will exit after {self.idle_timeout}s of inactivity)...")

        while True:
            task = self._get_task()

            if not task:
                # Check if we've been idle too long
                idle_time = time.time() - self.last_task_time
                if idle_time > self.idle_timeout:
                    print(f"[WORKER] No tasks for {self.idle_timeout}s - exiting")
                    break
                
                self.current_run = None
                time.sleep(3)
                continue

            self.last_task_time = time.time()
            self.current_run = task

            try:
                result = self._execute(task, config)
                self._send_result(task["__run_id"], result)

            except Exception as e:
                self._send_failure(task["__run_id"], str(e))

            finally:
                self.current_run = None
        
        print(f"[WORKER] Worker {self.agent_id} exiting")

    # =========================
    # TASK FETCH
    # =========================
    def _get_task(self):
        try:
            r = requests.get(
                self.master_url + "/task",
                params={"agent_id": self.agent_id},
                timeout=5
            )
            task = r.json().get("run")
            if task:
                print(f"[WORKER] Got task: {task.get('__run_id', 'unknown')}")
            return task
        except requests.exceptions.Timeout:
            print(f"[WORKER] Task request timeout (master not responding)")
            return None
        except Exception as e:
            print(f"[WORKER] Error getting task: {e}")
            return None

    # =========================
    # EXECUTION
    # =========================
    def _execute(self, run, config):
        print(f"[WORKER] Executing task {run.get('__run_id')}")
        current_run = run.get('__current_run', 0)
        total_runs = run.get('__total_runs', 1)
        
        try:
            controller = RunController(run, config, current_run, total_runs)
            controller.do_run()
            print(f"[WORKER] Task {run.get('__run_id')} completed successfully")
            return run  # updated in-place
        except Exception as e:
            print(f"[WORKER] Task {run.get('__run_id')} failed with error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise

    # =========================
    # RESULT
    # =========================
    def _send_result(self, run_id, data):
        try:
            requests.post(self.master_url + "/result", json={
                "run_id": run_id,
                "data": data,
                "status": "COMPLETED"
            }, timeout=5)
            print(f"[WORKER] Result sent for task {run_id}")
        except Exception as e:
            print(f"[WORKER] Error sending result: {e}")

    def _send_failure(self, run_id, error):
        try:
            requests.post(self.master_url + "/result", json={
                "run_id": run_id,
                "status": "FAILED",
                "error": error
            }, timeout=5)
            print(f"[WORKER] Task {run_id} failed: {error}")
        except Exception as e:
            print(f"[WORKER] Error sending failure: {e}")

    # =========================
    # HEARTBEAT
    # =========================
    def _heartbeat_loop(self):
        while not self._stop:
            try:
                requests.post(self.master_url + "/heartbeat", json={
                    "agent_id": self.agent_id,
                    "status": "RUNNING" if self.current_run else "IDLE",
                    "run_id": self.current_run["__run_id"] if self.current_run else None,
                    "timestamp": time.time()
                }, timeout=5)
            except requests.exceptions.Timeout:
                print(f"[WORKER] Heartbeat timeout")
            except Exception as e:
                print(f"[WORKER] Heartbeat error: {e}")

            time.sleep(self.heartbeat_interval)