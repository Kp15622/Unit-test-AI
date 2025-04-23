import os
import json
import ast
from pathlib import Path
import pytest
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def map_test_functions(file_path):
    with open(file_path) as f:
        tree = ast.parse(f.read())

    mappings = {}
    current_test = None

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            current_test = node.name
            mappings[current_test] = set()
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if current_test:
                mappings[current_test].add(node.func.id)
    return mappings

def get_changed_files():
    result = os.popen("git diff --name-only origin/main...HEAD").read()
    return [f.strip() for f in result.splitlines() if f.endswith(".py")]

def get_last_modified(file):
    try:
        return datetime.now().timestamp() - Path(file).stat().st_mtime
    except FileNotFoundError:
        return float("inf")

def load_failure_log():
    if Path("failure_log.json").exists():
        with open("failure_log.json") as f:
            return json.load(f)
    return {}

def update_failure_log(report_path="report.json"):
    log_file = "failure_log.json"
    failure_log = load_failure_log()
    if not Path(report_path).exists():
        return
    with open(report_path) as f:
        report = json.load(f)
    for test in report.get("tests", []):
        name = test["nodeid"].split("::")[-1]
        if test["outcome"] == "failed":
            failure_log[name] = failure_log.get(name, 0) + 1
    with open(log_file, "w") as f:
        json.dump(failure_log, f, indent=2)

def prioritize_tests():
    failure_log = load_failure_log()
    changed_files = get_changed_files()
    test_function_map = map_test_functions("test_cases.py")
    print("Changed files:", changed_files)
    print("Failure log:", failure_log)
    print("Test function map:", test_function_map)
    priority_scores = {}
    for test, funcs in test_function_map.items():
        score = 0
        related_files = ["source_code.py"]
        for file in related_files:
            if file in changed_files:
                score += 5
            score += failure_log.get(test, 0) * 2
        priority_scores[test] = score
        print(f"Test: {test}, Score: {score}")
    print("Priority Scores:", sorted(priority_scores, key=priority_scores.get, reverse=True))
    if not priority_scores:
        print("No tests to prioritize.")
        return []
    return sorted(priority_scores, key=priority_scores.get, reverse=True)

def main():
    env = os.getenv("ENV", "dev")

    if env == "prod":
        print("Running all tests (Production Mode)...")
        pytest.main(["--json-report", "--json-report-file=report.json"])
        update_failure_log()
    else:
        print("Running prioritized tests (Dev Mode)...")
        tests_to_run = prioritize_tests()
        if tests_to_run:
            test_expr = " or ".join(tests_to_run)
            print(f"Executing: pytest -k \"{test_expr}\"")
            pytest.main(["-k", test_expr])
        else:
            print("No prioritized tests to run.")

if __name__ == "__main__":
    main()
