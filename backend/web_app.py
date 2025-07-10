from flask import Flask, render_template, request, jsonify, send_file
import requests
import re
import subprocess
import os
import tempfile
import ast
import json
from datetime import datetime
import zipfile
import io

app = Flask(__name__)

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

def analyze_python_file(file_content: str) -> dict:
    """Analyze Python file and extract function/class information"""
    try:
        tree = ast.parse(file_content)
        functions = []
        classes = []
        imports = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Extract function info
                func_info = {
                    'name': node.name,
                    'args': [arg.arg for arg in node.args.args],
                    'lineno': node.lineno,
                    'docstring': ast.get_docstring(node),
                    'has_tests': False,  # Will be updated later
                    'is_private': node.name.startswith('_'),
                    'is_test': node.name.startswith('test_')
                }
                functions.append(func_info)
            
            elif isinstance(node, ast.ClassDef):
                # Extract class info
                class_methods = []
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        class_methods.append({
                            'name': item.name,
                            'args': [arg.arg for arg in item.args.args],
                            'lineno': item.lineno,
                            'is_private': item.name.startswith('_')
                        })
                
                class_info = {
                    'name': node.name,
                    'methods': class_methods,
                    'lineno': node.lineno,
                    'docstring': ast.get_docstring(node),
                    'has_tests': False
                }
                classes.append(class_info)
            
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                # Extract import info
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                else:  # ImportFrom
                    module = node.module or ''
                    for alias in node.names:
                        imports.append(f"{module}.{alias.name}")
        
        return {
            'functions': functions,
            'classes': classes,
            'imports': imports,
            'total_functions': len([f for f in functions if not f['is_test']]),
            'total_test_functions': len([f for f in functions if f['is_test']]),
            'total_classes': len(classes)
        }
    except Exception as e:
        return {'error': f'Failed to analyze file: {str(e)}'}

def generate_tests_for_function(func_info: dict, file_content: str) -> str:
    """Generate tests for a specific function"""
    # Extract the function code
    lines = file_content.split('\n')
    func_start = func_info['lineno'] - 1
    
    # Find function end (simple approach)
    func_end = len(lines)
    for i in range(func_start + 1, len(lines)):
        if lines[i].strip() and not lines[i].startswith(' ') and not lines[i].startswith('\t'):
            func_end = i
            break
    
    func_code = '\n'.join(lines[func_start:func_end])
    
    prompt = f"""
Analyze this Python function and generate comprehensive pytest tests:

```python
{func_code}
```

Generate pytest tests that cover:
1. Normal use cases with valid inputs
2. Edge cases (empty inputs, None, zero, negative numbers)
3. Error conditions and exception handling
4. Boundary conditions
5. Type validation

Return ONLY the test functions in a code block (no imports, no explanations):

```python
def test_{func_info['name']}_normal_cases():
    # Test normal functionality
    assert {func_info['name']}([1, 2, 3, 4, 5]) == expected_result
    
def test_{func_info['name']}_edge_cases():
    # Test edge cases
    assert {func_info['name']}([]) == expected_result
    
def test_{func_info['name']}_error_cases():
    # Test error conditions
    with pytest.raises(ValueError):
        {func_info['name']}(invalid_input)
```

Generate comprehensive tests for the function '{func_info['name']}' with proper assertions.
"""
    
    return generate_task(prompt)

def run_code_quality_checks(file_path: str) -> dict:
    """Run code quality checks on the file"""
    results = {}
    
    # Run flake8 for linting
    try:
        flake8_result = subprocess.run(
            ['flake8', file_path, '--max-line-length=88', '--ignore=E203,W503'],
            capture_output=True, text=True
        )
        results['flake8'] = {
            'success': flake8_result.returncode == 0,
            'output': flake8_result.stdout if flake8_result.stdout else 'No issues found'
        }
    except FileNotFoundError:
        results['flake8'] = {'success': False, 'output': 'flake8 not installed'}
    
    # Run bandit for security
    try:
        bandit_result = subprocess.run(
            ['bandit', '-f', 'json', file_path],
            capture_output=True, text=True
        )
        if bandit_result.stdout:
            bandit_data = json.loads(bandit_result.stdout)
            results['bandit'] = {
                'success': len(bandit_data.get('results', [])) == 0,
                'issues': bandit_data.get('results', []),
                'summary': bandit_data.get('metrics', {})
            }
        else:
            results['bandit'] = {'success': True, 'issues': [], 'summary': {}}
    except (FileNotFoundError, json.JSONDecodeError):
        results['bandit'] = {'success': False, 'output': 'bandit not installed or failed'}
    
    return results

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze_file', methods=['POST'])
def analyze_file():
    """Analyze uploaded Python file"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.endswith('.py'):
        return jsonify({'error': 'Only Python files are supported'}), 400
    
    # Read file content
    file_content = file.read().decode('utf-8')
    
    # Save temporary file for analysis
    temp_file = f"temp_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
    with open(temp_file, 'w') as f:
        f.write(file_content)
    
    try:
        # Analyze file structure
        analysis = analyze_python_file(file_content)
        
        # Run code quality checks
        quality_checks = run_code_quality_checks(temp_file)
        
        # Clean up
        os.remove(temp_file)
        
        return jsonify({
            'success': True,
            'filename': file.filename,
            'analysis': analysis,
            'quality_checks': quality_checks,
            'file_content': file_content
        })
    
    except Exception as e:
        # Clean up on error
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500

@app.route('/generate_tests_for_file', methods=['POST'])
def generate_tests_for_file():
    """Generate tests for functions in uploaded file"""
    data = request.json
    file_content = data.get('file_content', '')
    selected_functions = data.get('selected_functions', [])
    filename = data.get('filename', 'uploaded_file.py')
    
    if not file_content:
        return jsonify({'error': 'No file content provided'}), 400
    
    # Analyze file to get function info
    analysis = analyze_python_file(file_content)
    
    if 'error' in analysis:
        return jsonify({'error': analysis['error']}), 400
    
    # Generate tests for selected functions
    generated_tests = {}
    all_test_code = []
    
    # Add imports
    module_name = filename.replace('.py', '')
    test_imports = f"import pytest\nfrom {module_name} import *\n\n"
    all_test_code.append(test_imports)
    
    # Generate tests for each selected function
    for func_info in analysis['functions']:
        if func_info['name'] in selected_functions and not func_info['is_test']:
            print(f"Generating tests for {func_info['name']}")
            
            try:
                test_code = generate_tests_for_function(func_info, file_content)
                
                # Extract test code from response
                test_matches = re.findall(r"```python\n(.*?)```", test_code, re.DOTALL)
                if not test_matches:
                    # Try without python keyword
                    test_matches = re.findall(r"```\n(.*?)```", test_code, re.DOTALL)
                
                if test_matches:
                    clean_test = test_matches[0].strip()
                    # Remove import statements from individual tests
                    clean_test = re.sub(r'import.*?\n', '', clean_test)
                    clean_test = re.sub(r'from.*?\n', '', clean_test)
                    clean_test = clean_test.strip()
                    
                    if clean_test:  # Only add if we have actual test code
                        generated_tests[func_info['name']] = clean_test
                        all_test_code.append(clean_test)
                        print(f"✅ Generated tests for {func_info['name']}")
                    else:
                        print(f"❌ No test code extracted for {func_info['name']}")
                else:
                    print(f"❌ No code blocks found for {func_info['name']}")
                    
            except Exception as e:
                print(f"❌ Error generating tests for {func_info['name']}: {str(e)}")
                continue
    
    # Combine all tests
    combined_tests = '\n\n'.join(all_test_code)
    
    return jsonify({
        'success': True,
        'individual_tests': generated_tests,
        'combined_tests': combined_tests,
        'test_filename': f"test_{filename}"
    })

@app.route('/download_tests', methods=['POST'])
def download_tests():
    """Download generated tests as a file"""
    data = request.json
    test_code = data.get('test_code', '')
    filename = data.get('filename', 'test_code.py')
    
    if not test_code:
        return jsonify({'error': 'No test code provided'}), 400
    
    # Create a temporary file
    temp_file = f"temp_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
    with open(temp_file, 'w') as f:
        f.write(test_code)
    
    try:
        return send_file(temp_file, as_attachment=True, download_name=filename)
    finally:
        # Clean up after sending
        if os.path.exists(temp_file):
            os.remove(temp_file)

# Keep existing routes
@app.route('/generate', methods=['POST'])
def generate():
    """Original function generation endpoint"""
    data = request.json
    prompt = data.get('prompt', '')
    session_id = data.get('session_id', 'default')
    
    if not prompt:
        return jsonify({'error': 'No prompt provided'}), 400
    
    # Create enhanced prompt
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
    
    # Try up to 3 attempts
    max_retries = 3
    attempts = []
    
    for attempt in range(max_retries):
        if attempt == 0:
            # First attempt
            result = generate_task(full_prompt)
        else:
            # Retry - try to fix the previous failure
            func_file = f"generated_code_{session_id}.py"
            if os.path.exists(func_file):
                with open(func_file, "r") as f:
                    previous_code = f.read()
                result = fix_failing_code(prompt, last_error, previous_code)
            else:
                result = generate_task(full_prompt)
        
        # Try to save and test
        success, func_code, test_code = save_code_and_tests(result, session_id)
        
        attempt_data = {
            'attempt': attempt + 1,
            'ai_response': result,
            'success': False,
            'func_code': func_code,
            'test_code': test_code,
            'test_output': '',
            'error': ''
        }
        
        if success:
            # Run tests
            test_success, test_output = run_tests(session_id)
            attempt_data['test_output'] = test_output
            
            if test_success:
                attempt_data['success'] = True
                attempts.append(attempt_data)
                
                # Clean up session files
                cleanup_session_files(session_id)
                
                return jsonify({
                    'success': True,
                    'attempts': attempts,
                    'final_func_code': func_code,
                    'final_test_code': test_code,
                    'test_output': test_output
                })
            else:
                last_error = test_output
                attempt_data['error'] = test_output
        else:
            attempt_data['error'] = 'Failed to parse code blocks from AI response'
            last_error = 'Failed to parse code blocks'
        
        attempts.append(attempt_data)
    
    # Clean up session files
    cleanup_session_files(session_id)
    
    return jsonify({
        'success': False,
        'attempts': attempts,
        'error': f'Failed after {max_retries} attempts'
    })

def save_code_and_tests(response: str, session_id: str) -> tuple[bool, str, str]:
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
        return False, "", ""
    
    # Combine all code blocks
    combined_code = "\n\n".join(code_blocks)
    
    # Extract function definitions and test functions separately
    func_pattern = r"(def\s+(?!test_)\w+\([^)]*\):.*?)(?=def\s+test_|\Z)"
    test_pattern = r"(def\s+test_\w+\([^)]*\):.*?)(?=def\s+|\Z)"
    
    func_matches = re.findall(func_pattern, combined_code, re.DOTALL)
    test_matches = re.findall(test_pattern, combined_code, re.DOTALL)
    
    if not func_matches:
        return False, "", ""
    
    if not test_matches:
        return False, "", ""
    
    # Combine all functions (non-test functions)
    func_code = "\n\n".join([func.strip() for func in func_matches])
    
    # Combine all test functions
    test_code = "\n\n".join([test.strip() for test in test_matches])
    
    # Save function code with session ID
    func_file = f"generated_code_{session_id}.py"
    test_file = f"test_generated_code_{session_id}.py"
    
    with open(func_file, "w") as f:
        f.write(func_code + "\n")
    
    # Save test code with import statement
    with open(test_file, "w") as f:
        f.write(f"import pytest\nfrom generated_code_{session_id} import *\n\n{test_code}\n")
    
    return True, func_code, test_code

def run_tests(session_id: str) -> tuple[bool, str]:
    test_file = f"test_generated_code_{session_id}.py"
    result = subprocess.run(
        ["pytest", test_file, "-v", "--maxfail=1", "--disable-warnings"],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        return True, result.stdout
    else:
        return False, result.stdout + "\n" + result.stderr

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

def cleanup_session_files(session_id: str):
    """Clean up temporary session files"""
    files_to_clean = [
        f"generated_code_{session_id}.py",
        f"test_generated_code_{session_id}.py"
    ]
    
    for file_path in files_to_clean:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass

if __name__ == '__main__':
    # Create templates directory
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)
