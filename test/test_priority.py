import os
import json
import ast
from pathlib import Path
import pytest
from datetime import datetime
import re
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class TestFunctionMapper(ast.NodeVisitor):
    def __init__(self):
        self.mappings = {}
        self.current_test = None

    def visit_FunctionDef(self, node):
        if node.name.startswith("test_"):
            self.current_test = node.name
            self.mappings[self.current_test] = set()
            self.generic_visit(node)
            self.current_test = None
        else:
            self.generic_visit(node)

    def visit_Call(self, node):
        if self.current_test and isinstance(node.func, ast.Name):
            self.mappings[self.current_test].add(node.func.id)
        self.generic_visit(node)

def map_test_functions(file_path):
    with open(file_path, "r") as f:
        tree = ast.parse(f.read())
    mapper = TestFunctionMapper()
    mapper.visit(tree)
    return mapper.mappings

def get_changed_functions():
    diff_output = os.popen("git diff").read()
    lines = diff_output.splitlines()

    func_pattern = re.compile(r'^\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(')
    changed_funcs = set()

    i = 0
    while i < len(lines):
        if lines[i].startswith('+++ b/src/'):
            for j in range(i + 1, min(i + 6, len(lines))):
                match = func_pattern.match(lines[j])
                if match:
                    changed_funcs.add(match.group(1))
        i += 1

    return changed_funcs

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

# def prioritize_tests():
#     failure_log = load_failure_log()
#     changed_funcs = get_changed_functions()
#     test_function_map = map_test_functions("test_cases.py")

#     print("Changed functions:", changed_funcs)
#     print("Failure log:", failure_log)
#     print("Test function map:", test_function_map)

#     # First priority: test functions themselves changed
#     priority_1 = [test for test in test_function_map if test in changed_funcs]

#     # Second priority: top 2 tests by failure count (excluding already selected)
#     sorted_failures = sorted(
#         ((test, failure_log.get(test, 0)) for test in test_function_map if test not in priority_1),
#         key=lambda x: x[1],
#         reverse=True
#     )
#     priority_2 = [test for test, _ in sorted_failures[:2]]

#     prioritized = priority_1 + priority_2

#     print("Selected test cases:", prioritized)
#     return prioritized

def get_ai_prioritized_tests(changed_funcs, test_function_map, failure_log):
    client = OpenAI()
    prompt = f"""
    You're a test prioritization assistant.
    Here are the recently changed functions: {list(changed_funcs)}

    Here is the mapping of test cases to the functions they call:
    {json.dumps({k: list(v) for k, v in test_function_map.items()}, indent=2)}


    And here are the failure counts for each test:
    {json.dumps(failure_log, indent=2)}

    From this, pick the top most important test cases to run and explain why.
    Return only a list of test case names.
    """

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )

    # Extract just the names from the response
    output = response.choices[0].message.content
    test_names = [line.strip("-• ").strip() for line in output.splitlines() if "test_" in line]
    return test_names

def prioritize_tests():
    failure_log = load_failure_log()
    changed_funcs = get_changed_functions()
    test_function_map = map_test_functions("test_cases.py")

    print("Changed functions:", changed_funcs)
    print("Failure log:", failure_log)
    print("Test function map:", test_function_map)

    prioritized = get_ai_prioritized_tests(changed_funcs, test_function_map, failure_log)
    matches = re.findall(r'test_[a-zA-Z0-9_]+', "\n".join(prioritized))
    unique_tests = list(set(matches))

    print("AI-prioritized tests:", unique_tests)
    return unique_tests


def main():
    env = os.getenv("ENV", "dev")

    if env == "prod":
        print("Running all tests (Production Mode)...")
        pytest.main(["--json-report", "--json-report-file=report.json", "--disable-warnings"])
        update_failure_log()
    else:
        print("Running prioritized tests (Dev Mode)...")
        tests_to_run = prioritize_tests()
        if tests_to_run:
            test_expr = " or ".join(tests_to_run)
            print(f"Executing: pytest -k \"{test_expr}\"")
            pytest.main(["-k", test_expr, "--disable-warnings"])
        else:
            print("No prioritized tests to run.")
if __name__ == "__main__":
    main()
