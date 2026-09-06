"""
Script to help migrate from monolithic admin.py to modular structure
"""
import os
import re
import ast
from collections import defaultdict

def extract_functions(file_path):
    """Extract functions from a Python file and categorize them by module"""
    with open(file_path, 'r') as f:
        code = f.read()
    
    # Parse the file into an AST
    tree = ast.parse(code)
    
    # Function categories
    categories = {
        'dashboard': ['index', 'dashboard', 'system_status'],
        'users': ['users', 'user', 'new_user', 'edit_user', 'delete_user', 'reset_password', 'user_access'],
        'companies': ['companies', 'company', 'create_company', 'edit_company', 'delete_company'],
        'sites': ['sites', 'site', 'create_site', 'edit_site', 'delete_site'],
        'tanks': ['tanks', 'tank', 'create_tank', 'edit_tank', 'delete_tank', 'monitor'],
        'alarms': ['alarm', 'acknowledge', 'clear'],
        'reports': ['report', 'export', 'usage', 'inventory', 'consumption', 'statistics'],
        'utils': ['log_activity', 'handle_db_errors', 'ensure_deleted_at', 'add_soft_delete', 'validate'],
        'auth': ['admin_required', 'permission_required']
    }
    
    # Initialize result dict
    function_modules = defaultdict(list)
    uncategorized = []
    
    # Extract all function definitions
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            func_name = node.name
            
            # Categorize the function
            assigned = False
            for category, keywords in categories.items():
                if any(keyword in func_name for keyword in keywords):
                    function_modules[category].append((func_name, node.lineno))
                    assigned = True
                    break
            
            if not assigned:
                uncategorized.append((func_name, node.lineno))
    
    # Add uncategorized functions to 'utils' for now
    function_modules['utils'].extend(uncategorized)
    
    return function_modules

def create_migration_plan(functions_by_module):
    """Create a migration plan with file destinations for each function"""
    plan = []
    
    for module, functions in functions_by_module.items():
        dest_file = f"blueprints/admin/{module}.py"
        
        # Create section for this module
        plan.append(f"\n## Functions to move to {dest_file}:")
        
        for func_name, line_no in sorted(functions, key=lambda x: x[1]):
            plan.append(f"  - {func_name} (line {line_no})")
    
    return "\n".join(plan)

if __name__ == "__main__":
    # Path to the current admin.py file
    admin_file = "admin.py"
    
    if not os.path.exists(admin_file):
        print(f"File {admin_file} not found!")
        exit(1)
    
    # Extract functions and categorize them
    functions_by_module = extract_functions(admin_file)
    
    # Create migration plan
    plan = create_migration_plan(functions_by_module)
    
    print("Migration Plan for admin.py:")
    print("--------------------------")
    print(plan)
    
    # Save the plan to a file
    with open("admin_migration_plan.txt", "w") as f:
        f.write("# Migration Plan for admin.py\n\n")
        f.write("This file contains a plan for migrating functions from the monolithic admin.py\n")
        f.write("to a modular structure in the blueprints/admin/ directory.\n\n")
        f.write(plan)
    
    print("\nMigration plan saved to admin_migration_plan.txt")