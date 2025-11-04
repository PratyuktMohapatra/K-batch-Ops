from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import yaml
import uuid
import pymysql
import os
import subprocess
import paramiko
import time
import socket
import logging
from jinja2 import Template
from threading import Thread

# ----------------------------- [0] Load .env -----------------------------
load_dotenv()

app = Flask(__name__)
CORS(app)

TMP_FOLDER = "/tmp"
TEMPLATE_YAML = os.path.join(os.getcwd(), "job_template.yaml")
SERVICE_TEMPLATE_YAML = os.path.join(os.getcwd(), "service_template.yaml")

VNC_NODEPORT_REGISTRY_FILE = os.path.join(os.getcwd(), "vnc_nodeport_registry.txt")
WEB_NODEPORT_REGISTRY_FILE = os.path.join(os.getcwd(), "web_nodeport_registry.txt")

VNC_NODEPORT_RANGE = range(31000, 32000)
WEB_NODEPORT_RANGE = range(32001, 33001)

REMOTE_SSH_HOST = os.getenv("REMOTE_SSH_HOST")
REMOTE_SSH_USER = os.getenv("REMOTE_SSH_USER")
REMOTE_SSH_PASS = os.getenv("REMOTE_SSH_PASS")

HOST_IP = os.getenv("HOST_IP")
MICROK8S_CMD = os.getenv("MICROK8S_CMD", "microk8s kubectl").split()

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")

logging.basicConfig(level=logging.INFO)

# [1] NodePort Helpers
def update_nodeport_registry_from_k8s(registry_file, port_range):
    result = subprocess.run(
        MICROK8S_CMD + ["get", "svc", "--all-namespaces", "-o", "jsonpath={..nodePort}"],
        capture_output=True, text=True
    )
    active_ports = set()
    for p in result.stdout.strip().split():
        try:
            port = int(p)
            if port in port_range:
                active_ports.add(port)
        except ValueError:
            pass
    with open(registry_file, "w") as f:
        for port in sorted(active_ports):
            f.write(f"{port}\n")

def get_used_nodeports_from_file(registry_file):
    if not os.path.exists(registry_file):
        return set()
    with open(registry_file, "r") as f:
        return set(int(line.strip()) for line in f if line.strip().isdigit())

def get_all_used_nodeports(registry_file, port_range):
    update_nodeport_registry_from_k8s(registry_file, port_range)
    return get_used_nodeports_from_file(registry_file)

def get_next_available_nodeport(registry_file, port_range):
    used_ports = get_all_used_nodeports(registry_file, port_range)
    for port in port_range:
        if port not in used_ports:
            with open(registry_file, "a") as f:
                f.write(f"{port}\n")
            return port
    raise RuntimeError(f"No available NodePort in range {port_range}")

# [2] Port Waiter
def wait_for_ports(host, port, timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except Exception:
            time.sleep(2)
    return False

# [3] Remote Remmina Execution
def execute_remmina_remotely(node_port):
    command = f'DISPLAY=:0 remmina -c vnc://{HOST_IP}:{node_port}'
    logging.info(f"Attempting to SSH into remote host and run Remmina on port {node_port}")
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=REMOTE_SSH_HOST, username=REMOTE_SSH_USER, password=REMOTE_SSH_PASS)

        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode()
        error = stderr.read().decode()

        logging.info("Remmina Output:\n" + output)
        if error:
            logging.error("Remmina Error:\n" + error)
        ssh.close()
    except Exception as e:
        logging.error(f"Error executing Remmina remotely: {e}")

# [4] Pod Info Fetchers
def get_pod_name_from_label(label_selector, namespace="default"):
    result = subprocess.run(
        MICROK8S_CMD + [
            "get", "pods", "-l", label_selector, "-n", namespace,
            "-o", "jsonpath={.items[0].metadata.name}"
        ],
        capture_output=True, text=True
    )
    return result.stdout.strip()

def get_pod_ip(pod_name, namespace="default"):
    result = subprocess.run(
        MICROK8S_CMD + [
            "get", "pod", pod_name, "-n", namespace,
            "-o", "jsonpath={.status.podIP}"
        ],
        capture_output=True, text=True
    )
    return result.stdout.strip()

# [5] Log Completion Watcher
def wait_for_completion_in_logs(pod_name, namespace="default", timeout=300):
    try:
        result = subprocess.run(
            MICROK8S_CMD + ["logs", pod_name, "-n", namespace],
            capture_output=True, text=True
        )
        if "Har Generated successfully" in result.stdout:
            logging.info(f"Detected completion signal in initial logs of {pod_name}")
            return True
    except Exception as e:
        logging.error(f"Error fetching initial logs: {e}")

    start_time = time.time()
    process = subprocess.Popen(
        MICROK8S_CMD + ["logs", "-f", pod_name, "-n", namespace],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    try:
        for line in iter(process.stdout.readline, ''):
            logging.info(f"[{pod_name}] {line.strip()}")
            if "Har Generated successfully" in line:
                logging.info(f"Detected completion signal in live logs of {pod_name}")
                process.terminate()
                return True
            if time.time() - start_time > timeout:
                logging.warning(f"Timeout while watching logs of {pod_name}")
                process.terminate()
                break
    except Exception as e:
        logging.error(f"Error watching logs: {e}")
    return False

# [6] Cleanup Logic
def delete_pod_and_service(name, namespace="default"):
    try:
        subprocess.run(MICROK8S_CMD + ["delete", "pods", "-l", f"app={name}", "-n", namespace], check=True)
        subprocess.run(MICROK8S_CMD + ["delete", "svc", f"{name}-svc", "-n", namespace], check=True)
        logging.info(f"Deleted pods with label app={name} and service {name}-svc")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error deleting pod/service {name}: {e}")

def watch_and_cleanup(deployment_name):
    logging.info(f"Started cleanup watcher thread for {deployment_name}")
    pod_name = get_pod_name_from_label(f"app={deployment_name}")
    if pod_name and wait_for_completion_in_logs(pod_name):
        delete_pod_and_service(deployment_name)

def update_ips_in_database(client_id, frequency, vnc_node_port, web_node_port):
    container_ip = f"{HOST_IP}:{vnc_node_port}"
    browser_container_ip = f"http://{HOST_IP}:{web_node_port}"
    
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME
        )
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE execution_order
            SET container_ip = %s, browser_container_ip = %s
            WHERE client_id = %s AND frequency = %s
        """, (container_ip, browser_container_ip, client_id, frequency))

        conn.commit()
        logging.info(f"Database updated with container_ip={container_ip}, browser_container_ip={browser_container_ip}")
    except Exception as e:
        logging.error(f"Database update failed: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

# [7] Flask Endpoint
@app.route('/run-automation', methods=['POST'])
def run_automation():
    data = request.get_json()
    client_id = data.get("client_id")
    frequency = data.get("frequency")
    batch_id = data.get("batch_id")
    if not client_id or not frequency:
        return jsonify({"error": "Missing client_id or frequency"}), 400

    timestamp = int(time.time())
    deployment_name = f"batch-{client_id}-{frequency}-{timestamp}"

    tmp_deploy_yaml = os.path.join(TMP_FOLDER, f"{deployment_name}.yaml")
    tmp_service_yaml = os.path.join(TMP_FOLDER, f"{deployment_name}-svc.yaml")

    vnc_node_port = get_next_available_nodeport(VNC_NODEPORT_REGISTRY_FILE, VNC_NODEPORT_RANGE)
    web_node_port = get_next_available_nodeport(WEB_NODEPORT_REGISTRY_FILE, WEB_NODEPORT_RANGE)

    with open(TEMPLATE_YAML) as f:
        deploy_template = Template(f.read())
    rendered_deployment = deploy_template.render(
        deployment_name=deployment_name,
        client_id=client_id,
        frequency=frequency,
        batch_id=batch_id
    )
    with open(tmp_deploy_yaml, "w") as f:
        f.write(rendered_deployment)

    with open(SERVICE_TEMPLATE_YAML) as f:
        svc_template = Template(f.read())
    rendered_service = svc_template.render(
        deployment_name=deployment_name,
        vnc_node_port=vnc_node_port,
        web_node_port=web_node_port
    )
    with open(tmp_service_yaml, "w") as f:
        f.write(rendered_service)

    try:
        subprocess.run(MICROK8S_CMD + ["apply", "-f", tmp_deploy_yaml], check=True)
        subprocess.run(MICROK8S_CMD + ["apply", "-f", tmp_service_yaml], check=True)
        update_ips_in_database(client_id, frequency, vnc_node_port, web_node_port)

    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Failed to apply deployment/service", "details": str(e)}), 500

    time.sleep(5)
    pod_name = get_pod_name_from_label(f"app={deployment_name}")
    pod_ip = get_pod_ip(pod_name)
    vnc_port = 5901

    if wait_for_ports(HOST_IP, vnc_node_port, timeout=60):
        logging.info(f"VNC NodePort {vnc_node_port} is reachable.")
        execute_remmina_remotely(vnc_node_port)
    else:
        logging.error(f"Timed out waiting for VNC NodePort {vnc_node_port} on {HOST_IP}")

    Thread(target=watch_and_cleanup, args=(deployment_name,), daemon=True).start()

    return jsonify({
        "status": "Deployment and service created; Remmina launched (if port ready)",
        "deployment_name": deployment_name,
        "pod_name": pod_name,
        "pod_ip": pod_ip,
        "vnc_port": vnc_port,
        "vnc_node_port": vnc_node_port,
        "web_node_port": web_node_port
    })

# [8] App Runner
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
