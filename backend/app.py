import requests
import re
import subprocess

def generate_task(prompt: str, model: str = "codellama:7b-instruct", temperature: float = 0.7) -> str:
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()['response']
    except Exception as e:
        return f"Error: Unable to connect to the model server or generate a response.\nDetails: {e}"

def save_code_and_tests(response: str) -> bool:
    # Extract all code blocks from the response
    code_blocks = []
    
    # Try to extract fenced code blocks first (```python...```)
    fenced_matches = re.findall(r"```(?:python)?\n(.*?)```", response, re.DOTALL)
    if fenced_matches:
        code_blocks.extend([block.strip() for block in fenced_matches])
    
    # Try CodeLlama format [PYTHON]...[/PYTHON]
    python_matches = re.findall(r"\[PYTHON\](.*?)\[/PYTHON\]", response, re.DOTALL)
    if python_matches:
        code_blocks.extend([block.strip() for block in python_matches])
    
    if not code_blocks:
        print("❌ Could not find any code blocks in the response.")
        return False
    
    # Combine all code blocks
    combined_code = "\n\n".join(code_blocks)
    
    # Extract function definitions and test functions separately
    func_pattern = r"(def\s+(?!test_)\w+\([^)]*\):.*?)(?=def\s+test_|\Z)"
    test_pattern = r"(def\s+test_\w+\([^)]*\):.*?)(?=def\s+|\Z)"
    
    func_matches = re.findall(func_pattern, combined_code, re.DOTALL)
    test_matches = re.findall(test_pattern, combined_code, re.DOTALL)
    
    if not func_matches:
        print("❌ Could not find any function definitions in the code blocks.")
        return False
    
    if not test_matches:
        print("❌ Could not find any test functions in the code blocks.")
        return False
    
    # Combine all functions (non-test functions)
    func_code = "\n\n".join([func.strip() for func in func_matches])
    
    # Combine all test functions
    test_code = "\n\n".join([test.strip() for test in test_matches])
    
    # Save function code
    with open("generated_code.py", "w") as f:
        f.write(func_code + "\n")
    
    # Save test code with import statement
    with open("test_generated_code.py", "w") as f:
        f.write(f"import pytest\nfrom generated_code import *\n\n{test_code}\n")
    
    print("✅ Saved generated_code.py and test_generated_code.py")
    return True

def run_tests():
    print("⏳ Running pytest...\n")
    result = subprocess.run(
        ["pytest", "test_generated_code.py", "-v", "--maxfail=1", "--disable-warnings"],
        capture_output=True,
        text=True
    )
    print(result.stdout)
    if result.returncode == 0:
        print("🎉 All tests passed!")
        return True, None
    else:
        print("❌ Tests failed.")
        print(result.stderr)
        return False, result.stderr

def fix_failing_code(original_prompt: str, error_output: str, previous_code: str) -> str:
    """Generate fixed code based on test failures"""
    fix_prompt = (
        f"The following code was generated for the task: '{original_prompt}'\n\n"
        f"Previous code:\n{previous_code}\n\n"
        f"But the tests failed with this error:\n{error_output}\n\n"
        f"Please fix the code and provide BOTH the corrected function and its tests in a SINGLE code block:\n\n"
        f"```python\n"
        f"def function_name(args):\n"
        f"    # your corrected implementation\n"
        f"    return result\n\n"
        f"def test_function_name():\n"
        f"    # pytest test cases\n"
        f"    assert function_name(test_input) == expected_output\n"
        f"```\n\n"
        f"Important: Fix the issue and put EVERYTHING in ONE code block."
    )
    return generate_task(fix_prompt)

def run_with_retry(original_prompt: str, max_retries: int = 3):
    """Run the generation and testing with retry logic"""
    for attempt in range(max_retries):
        print(f"\n🔄 Attempt {attempt + 1}/{max_retries}")
        
        if attempt == 0:
            # First attempt - use original generation
            result = generate_task(full_prompt)
        else:
            # Retry - try to fix the previous failure
            with open("generated_code.py", "r") as f:
                previous_code = f.read()
            result = fix_failing_code(original_prompt, last_error, previous_code)
        
        print("✅ Model Response:\n")
        print(result)
        
        if save_code_and_tests(result):
            success, error_output = run_tests()
            if success:
                print(f"\n🎉 Success after {attempt + 1} attempt(s)!")
                return True
            else:
                last_error = error_output
                if attempt < max_retries - 1:
                    print(f"\n🔧 Test failed. Attempting to fix... (Attempt {attempt + 2}/{max_retries})")
        else:
            print("❌ Failed to parse code. Retrying...")
    
    print(f"\n💥 Failed after {max_retries} attempts.")
    return False

if __name__ == "__main__":
    prompt = input("🧠 Describe the function you want to generate with tests:\n> ")
    full_prompt = (
        f"Write a clean Python function for this task: {prompt}\n\n"
        f"Include comprehensive tests that cover:\n"
        f"- Normal cases\n"
        f"- Edge cases (empty inputs, zero, negative numbers, None, etc.)\n"
        f"- Boundary conditions\n"
        f"- Error handling if needed\n\n"
        f"Please provide BOTH the function and its tests in a SINGLE code block like this:\n\n"
        f"```python\n"
        f"def function_name(args):\n"
        f"    # your function implementation with error handling\n"
        f"    return result\n\n"
        f"def test_function_name():\n"
        f"    # pytest test cases covering all scenarios\n"
        f"    assert function_name(test_input) == expected_output\n"
        f"    assert function_name(edge_case) == expected_output\n"
        f"```\n\n"
        f"Important: Put EVERYTHING in ONE code block. Include comprehensive test cases using pytest assertions."
    )
    print("\n⏳ Generating...\n")
    
    # Use retry logic for robust generation
    last_error = None
    run_with_retry(prompt)
